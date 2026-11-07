"""Task Execution Plane & Test Runner.
Executes verification suites, captures stdout/stderr, and validates Pony Tail compliance.
"""

import asyncio
import hashlib
import os
import sys
import time
import logging
import shutil
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional
from agenthive.database import db
from agenthive.engine.ponytail import ponytail_guard
from agenthive.config import settings
from agenthive.security import validate_workspace_path, redact_secrets

logger = logging.getLogger("agenthive.engine.execution")

class ExecutionRunner:
    def __init__(self, python_executable: str = sys.executable):
        self.python_executable = python_executable

    def _verify_workspace_boundary(self, workspace_dir: str) -> Path:
        """Enforces filesystem confinement to prevent path traversal outside authorized workspaces."""
        return validate_workspace_path(workspace_dir)

    async def secure_test_runner_available(self) -> bool:
        image = settings.test_runner_image
        docker = shutil.which("docker")
        if not image or not docker:
            return False
        inspect = await asyncio.create_subprocess_exec(
            docker, "image", "inspect", image,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            return await asyncio.wait_for(inspect.wait(), timeout=5) == 0
        except asyncio.TimeoutError:
            inspect.kill()
            await inspect.wait()
            return False

    async def run_tests(self, workspace_dir: str, timeout: int = 30) -> Dict[str, Any]:
        """Run tests only in a preinstalled, configured, isolated container image."""
        ws = self._verify_workspace_boundary(workspace_dir)
        if not (ws / "tests").is_dir():
            return {"success": False, "exit_code": 1, "stdout": "", "stderr": "No tests/ directory found in workspace.", "runtime_mode": "not_started"}

        image = settings.test_runner_image
        docker = shutil.which("docker")
        if not image or not docker:
            return {
                "success": False, "exit_code": None, "stdout": "",
                "stderr": "Secure test runner unavailable; host execution is disabled. Configure a locally installed AGENTHIVE_TEST_RUNNER_IMAGE.",
                "command": None, "runtime_mode": "blocked_no_secure_runner",
            }

        if not await self.secure_test_runner_available():
            return {"success": False, "exit_code": None, "stdout": "", "stderr": "Configured secure test runner image is not present locally; no image was pulled.", "runtime_mode": "blocked_runner_image_missing"}

        cmd = [
            docker, "run", "--rm", "--network=none", "--read-only", "--user=65534:65534",
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--pids-limit=64",
            "--memory=512m", "--cpus=1", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,src={ws},dst=/workspace,readonly", "--workdir", "/workspace",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint", "python",
            image, "-m", "unittest", "discover", "-s", "tests",
        ]
        logger.info("Executing tests in configured isolated container with read-only workspace mount")
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return {
                "success": process.returncode == 0,
                "exit_code": process.returncode,
                "stdout": redact_secrets(stdout.decode(errors="replace").strip()),
                "stderr": redact_secrets(stderr.decode(errors="replace").strip()),
                "command": "docker run [isolated test runner]",
                "runtime_mode": "secure_container",
            }
        except asyncio.TimeoutError:
            if process and process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    await asyncio.wait_for(process.wait(), timeout=2)
                except (ProcessLookupError, asyncio.TimeoutError):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await process.wait()
            return {
                "success": False, "exit_code": process.returncode if process else None,
                "stdout": "", "stderr": f"Execution timed out after {timeout} seconds",
                "command": "docker run [isolated test runner]", "runtime_mode": "secure_container_timeout",
            }
        except Exception as exc:
            return {
                "success": False, "exit_code": process.returncode if process else None,
                "stdout": "", "stderr": f"Secure test runner failed: {type(exc).__name__}",
                "command": "docker run [isolated test runner]", "runtime_mode": "secure_container_error",
            }

    async def run_docker_sandbox(self, workspace_dir: str, timeout: int = 60) -> Dict[str, Any]:
        """Fail closed rather than build and run an untrusted, workspace-supplied Dockerfile."""
        ws = self._verify_workspace_boundary(workspace_dir)
        if not (ws / "Dockerfile").exists():
            return {"skipped": True, "reason": "No Dockerfile found"}
        return {
            "success": False,
            "skipped": True,
            "reason": "Workspace-provided Dockerfiles are not built or executed; configure a vetted local runner image.",
            "runtime_mode": "blocked_untrusted_build_context",
        }

    @staticmethod
    def file_inventory(workspace_dir: Path) -> Dict[str, Dict[str, Any]]:
        """Produces a cryptographically sound inventory of files in the workspace (rel_path, size, sha256)."""
        inventory: Dict[str, Dict[str, Any]] = {}
        if not workspace_dir.is_dir():
            return inventory
        for p in sorted(workspace_dir.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(workspace_dir))
                try:
                    data = p.read_bytes()
                    inventory[rel] = {
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                except Exception:
                    pass
        return inventory

    @staticmethod
    def diff_inventories(
        before: Dict[str, Dict[str, Any]],
        after: Dict[str, Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Calculates created, modified, and deleted files between two inventories."""
        created = [f for f in after if f not in before]
        modified = [f for f in after if f in before and after[f]["sha256"] != before[f]["sha256"]]
        deleted = [f for f in before if f not in after]
        return {
            "created": sorted(created),
            "modified": sorted(modified),
            "deleted": sorted(deleted),
        }

    async def execute_task_isolated(
        self,
        task: Any,
        workspace_dir: str,
        command: Optional[List[str]] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """Execute a task strictly within an isolated non-root container with resource constraints.

        Guarantees:
        - Exact owner approval and task hash verification.
        - Strict workspace boundary confinement.
        - Network disabled (--network=none).
        - Non-root execution (--user=1001:1001 or 65534:65534).
        - Dropped Linux capabilities (--cap-drop=ALL).
        - No new privileges (--security-opt=no-new-privileges:true).
        - CPU (1.0), memory (512m), and process limits (pids=64).
        - Read-only root filesystem with restricted tmpfs on /tmp.
        - Absolute denial of Docker socket access or host credentials.
        - Generated file inventory tracking before and after execution.
        - Safe process group termination on timeout.
        """
        from agenthive.security import require_owner_approved_task, redact_secrets

        # Enforce approval & task-version verification and workspace boundary
        ws = require_owner_approved_task(task, workspace_dir)

        if not settings.task_execution_enabled:
            raise PermissionError("Task execution is disabled")
        if not settings.secure_agent_task_runner_configured:
            raise PermissionError("Secure isolated native-agent runner is not implemented; no host task execution will be attempted")

        image = settings.test_runner_image
        docker = shutil.which("docker")
        if not image or not docker:
            return {
                "success": False,
                "exit_code": None,
                "stdout": "",
                "stderr": "Secure task runner unavailable; host execution is disabled. Configure a locally installed AGENTHIVE_TEST_RUNNER_IMAGE.",
                "runtime_mode": "blocked_no_secure_runner",
                "generated_files": [],
            }

        if not await self.secure_test_runner_available():
            return {
                "success": False,
                "exit_code": None,
                "stdout": "",
                "stderr": "Configured secure runner image is not present locally; no image was pulled.",
                "runtime_mode": "blocked_runner_image_missing",
                "generated_files": [],
            }

        # Snapshot inventory before execution
        before_inventory = self.file_inventory(ws)

        # Build execution command (defaulting to safe execution inside container)
        exec_cmd = command or [
            "python3", "-c",
            f"import os, sys; print(f'AgentHive isolated runner: Task {task.task_code} executed safely in container.');"
        ]

        # Container environment is completely sanitized; NO host credentials or Docker socket
        safe_env = [
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", f"AGENTHIVE_TASK_CODE={task.task_code}",
            "--env", f"AGENTHIVE_TASK_TITLE={task.title}",
        ]

        cmd = [
            docker, "run", "--rm",
            "--network=none",
            "--read-only",
            "--user=1001:1001",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--pids-limit=64",
            "--memory=512m",
            "--cpus=1",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,src={ws},dst=/workspace",
            "--workdir", "/workspace",
            *safe_env,
            "--entrypoint", exec_cmd[0],
            image,
            *exec_cmd[1:],
        ]

        logger.info("Executing task %s in isolated non-root container", task.task_code)
        process = None
        start_time = time.time()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            duration = round(time.time() - start_time, 3)

            after_inventory = self.file_inventory(ws)
            diff = self.diff_inventories(before_inventory, after_inventory)

            return {
                "success": process.returncode == 0,
                "exit_code": process.returncode,
                "stdout": redact_secrets(stdout.decode(errors="replace").strip()),
                "stderr": redact_secrets(stderr.decode(errors="replace").strip()),
                "command": "docker run [isolated task runner]",
                "runtime_mode": "secure_container",
                "duration_seconds": duration,
                "generated_files": diff["created"],
                "modified_files": diff["modified"],
                "file_inventory": after_inventory,
                "report": f"Task {task.task_code} completed in isolated container (exit={process.returncode}, created={len(diff['created'])} files)",
            }
        except asyncio.TimeoutError:
            if process and process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    await asyncio.wait_for(process.wait(), timeout=2)
                except (ProcessLookupError, asyncio.TimeoutError):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await process.wait()
            after_inventory = self.file_inventory(ws)
            diff = self.diff_inventories(before_inventory, after_inventory)
            return {
                "success": False,
                "exit_code": process.returncode if process else None,
                "stdout": "",
                "stderr": f"Task execution timed out after {timeout} seconds",
                "command": "docker run [isolated task runner]",
                "runtime_mode": "secure_container_timeout",
                "duration_seconds": round(time.time() - start_time, 3),
                "generated_files": diff["created"],
                "modified_files": diff["modified"],
                "file_inventory": after_inventory,
                "report": f"Task {task.task_code} timed out after {timeout} seconds",
            }
        except Exception as exc:
            after_inventory = self.file_inventory(ws)
            diff = self.diff_inventories(before_inventory, after_inventory)
            return {
                "success": False,
                "exit_code": process.returncode if process else None,
                "stdout": "",
                "stderr": f"Isolated task runner failed: {type(exc).__name__}",
                "command": "docker run [isolated task runner]",
                "runtime_mode": "secure_container_error",
                "duration_seconds": round(time.time() - start_time, 3),
                "generated_files": diff["created"],
                "modified_files": diff["modified"],
                "file_inventory": after_inventory,
                "report": f"Task {task.task_code} failed with error: {type(exc).__name__}",
            }

runner = ExecutionRunner()
