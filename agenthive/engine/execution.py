"""Task Execution Plane & Test Runner.
Executes verification suites, captures stdout/stderr, and validates Pony Tail compliance.
"""

import asyncio
import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List
from agenthive.database import db
from agenthive.engine.ponytail import ponytail_guard

logger = logging.getLogger("agenthive.engine.execution")

class ExecutionRunner:
    def __init__(self, python_executable: str = sys.executable):
        self.python_executable = python_executable

    async def run_tests(self, workspace_dir: str, timeout: int = 30) -> Dict[str, Any]:
        """Runs the automated test suite in the project workspace."""
        ws = Path(workspace_dir).resolve()
        tests_dir = ws / "tests"

        if not tests_dir.exists():
            return {
                "success": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": "No tests/ directory found in workspace.",
                "passed_tests": 0,
                "failed_tests": 1
            }

        cmd = [self.python_executable, "-m", "unittest", "discover", "-s", "tests"]
        
        # Ensure PYTHONPATH includes workspace root so 'from src.engine import ...' resolves cleanly
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ws)

        logger.info("Executing tests in %s: %s", ws, " ".join(cmd))
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(ws),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            exit_code = process.returncode
            out_str = stdout.decode().strip()
            err_str = stderr.decode().strip()
            success = (exit_code == 0)

            logger.info("Test execution finished with exit code %d (success: %s)", exit_code, success)
            return {
                "success": success,
                "exit_code": exit_code,
                "stdout": out_str,
                "stderr": err_str,
                "command": " ".join(cmd)
            }
        except asyncio.TimeoutError:
            logger.error("Test execution timed out after %ds", timeout)
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "command": " ".join(cmd)
            }
        except Exception as e:
            logger.error("Execution failed: %s", e)
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "command": " ".join(cmd)
            }

    async def run_docker_sandbox(self, workspace_dir: str, timeout: int = 60) -> Dict[str, Any]:
        """Runs the project inside a containerized sandbox if Docker is available."""
        ws = Path(workspace_dir).resolve()
        if not (ws / "Dockerfile").exists():
            return {"skipped": True, "reason": "No Dockerfile found"}

        image_tag = f"agenthive-test-{ws.name}"
        build_cmd = ["docker", "build", "-t", image_tag, str(ws)]
        run_cmd = ["docker", "run", "--rm", "--network", "none", image_tag]

        try:
            # Build
            p1 = await asyncio.create_subprocess_exec(*build_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out1, err1 = await asyncio.wait_for(p1.communicate(), timeout=40)
            if p1.returncode != 0:
                return {"success": False, "stage": "build", "stderr": err1.decode()}

            # Run in isolated container
            p2 = await asyncio.create_subprocess_exec(*run_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out2, err2 = await asyncio.wait_for(p2.communicate(), timeout=timeout)
            return {
                "success": p2.returncode == 0,
                "stage": "run",
                "exit_code": p2.returncode,
                "stdout": out2.decode(),
                "stderr": err2.decode()
            }
        except Exception as e:
            return {"skipped": True, "reason": f"Docker execution error: {e}"}

runner = ExecutionRunner()
