"""ChatGPT Codex Agent Adapter.
Specializes in Software Architecture, Typed Data Structures, Algorithm Design, and Backend Execution.
Integrates directly with the native OpenAI Codex CLI binary (`codex exec`) with scoped workspace
isolation (`-s workspace-write`) and independent sessions.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional
from agenthive.agents.base import BaseAgent
from agenthive.models.project import IndependentAnalysis, TaskItem
from agenthive.config import settings
from agenthive.database import db
from agenthive.security import validate_workspace_path, validate_project_workspace, require_owner_approved_task, prohibit_dangerous_cli_flags, redact_secrets, agent_subprocess_env

logger = logging.getLogger("agenthive.agents.codex")

class CodexAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent-codex",
            name="ChatGPT Codex",
            role="Chief Software Architect & Backend Implementer",
            description="OpenAI Codex Engine (native CLI session with scoped workspace file modification).",
            capabilities=["software_architecture", "data_structures", "backend_apis", "algorithms", "refactoring"]
        )
        self.session_id: Optional[str] = None
        self.binary_path = settings.codex_binary_path
        self.is_cli_available = os.path.exists(self.binary_path) and os.access(self.binary_path, os.X_OK)
        self.last_execution: Dict[str, Any] = {}
        self.last_runtime_evidence: Dict[str, Any] = {
            "runtime_mode": "codex_fallback", "session_id": None,
            "request_id": None, "exit_status": None, "error_reason": "Codex CLI not invoked",
        }
        if self.is_cli_available:
            logger.info("Codex Agent detected native Codex CLI at %s", self.binary_path)
        else:
            logger.info("Codex Agent running in Local Architecture Engine mode (native Codex CLI not found at %s)", self.binary_path)

    async def _run_codex_cli(
        self,
        prompt: str,
        workspace_dir: str,
        timeout: int = 45,
        *,
        read_only: bool = False,
        retry_safe: bool = False,
    ) -> Dict[str, Any]:
        """Run native Codex with bounded lifetime and retain partial output/session evidence."""
        if not self.is_cli_available:
            result = {"success": False, "reason": "Codex CLI not available", "output": "", "session_id": None, "exit_code": None}
            self.last_execution = dict(result)
            return result

        ws = validate_workspace_path(workspace_dir)
        ws.mkdir(parents=True, exist_ok=True)

        max_attempts = 2 if retry_safe and read_only else 1
        retry_history: List[str] = []
        for attempt in range(1, max_attempts + 1):
            cmd = [
                self.binary_path,
                "exec",
                "-C", str(ws),
                "-s", "read-only" if read_only else "workspace-write",
                "--skip-git-repo-check",
                prompt,
            ]
            prohibit_dangerous_cli_flags(cmd)
            stdout_buffer = bytearray()
            stderr_buffer = bytearray()
            process = None
            readers: List[asyncio.Task] = []

            async def drain(stream, buffer: bytearray):
                while True:
                    chunk = await stream.read(65536)
                    if not chunk:
                        break
                    if len(buffer) < 1_048_576:
                        buffer.extend(chunk[: 1_048_576 - len(buffer)])

            async def stop_process(grace_seconds: float = 2.0):
                if process is None or process.returncode is not None:
                    return
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=grace_seconds)
                except asyncio.TimeoutError:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await process.wait()

            try:
                logger.info("Invoking native Codex CLI in %s (attempt %d/%d)...", ws, attempt, max_attempts)
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(ws),
                    env=agent_subprocess_env(),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
                readers = [
                    asyncio.create_task(drain(process.stdout, stdout_buffer)),
                    asyncio.create_task(drain(process.stderr, stderr_buffer)),
                ]
                await asyncio.wait_for(process.wait(), timeout=max(0, timeout))
                await asyncio.gather(*readers)
                out_str = redact_secrets(stdout_buffer.decode(errors="replace").strip())
                err_str = redact_secrets(stderr_buffer.decode(errors="replace").strip())
                combined = f"{out_str}\n{err_str}"
                session_match = re.search(r"session id:\s*([a-f0-9-]+)", combined, re.IGNORECASE)
                captured_session = session_match.group(1) if session_match else None
                if session_match:
                    self.session_id = captured_session
                result = {
                    "success": process.returncode == 0,
                    "exit_code": process.returncode,
                    "output": out_str,
                    "error": err_str,
                    "session_id": captured_session,
                    "runtime_mode": "native_codex_cli" if process.returncode == 0 else "codex_fallback",
                    "process_id": process.pid,
                    "attempts": attempt,
                    "retry_history": list(retry_history),
                }
                self.last_execution = dict(result)
                logger.info("Codex CLI exited %s (session=%s, attempt=%d)", process.returncode, captured_session, attempt)
                return result
            except asyncio.TimeoutError:
                await stop_process()
                if readers:
                    await asyncio.gather(*readers, return_exceptions=True)
                out_str = redact_secrets(stdout_buffer.decode(errors="replace").strip())
                err_str = redact_secrets(stderr_buffer.decode(errors="replace").strip())
                combined = f"{out_str}\n{err_str}"
                session_match = re.search(r"session id:\s*([a-f0-9-]+)", combined, re.IGNORECASE)
                captured_session = session_match.group(1) if session_match else None
                if session_match:
                    self.session_id = captured_session
                reason = f"Timed out after {timeout}s"
                result = {
                    "success": False,
                    "reason": reason,
                    "exit_code": process.returncode if process else None,
                    "output": out_str,
                    "error": err_str,
                    "session_id": captured_session,
                    "runtime_mode": "codex_fallback",
                    "process_id": process.pid if process else None,
                    "attempts": attempt,
                    "retry_history": list(retry_history),
                }
                self.last_execution = dict(result)
                logger.warning(
                    "Codex CLI %s (session=%s); captured %d stdout and %d stderr chars",
                    reason,
                    captured_session,
                    len(out_str),
                    len(err_str),
                )
                if retry_safe and read_only and attempt < max_attempts:
                    retry_history.append(reason)
                    await asyncio.sleep(0.5)
                    continue
                return result
            except asyncio.CancelledError:
                await stop_process()
                if readers:
                    await asyncio.gather(*readers, return_exceptions=True)
                out_str = redact_secrets(stdout_buffer.decode(errors="replace").strip())
                err_str = redact_secrets(stderr_buffer.decode(errors="replace").strip())
                combined = f"{out_str}\n{err_str}"
                session_match = re.search(r"session id:\s*([a-f0-9-]+)", combined, re.IGNORECASE)
                captured_session = session_match.group(1) if session_match else None
                self.last_execution = {
                    "success": False,
                    "reason": "Cancelled",
                    "output": out_str,
                    "error": err_str,
                    "session_id": captured_session,
                    "runtime_mode": "codex_fallback",
                    "process_id": process.pid if process else None,
                    "attempts": attempt,
                    "retry_history": list(retry_history),
                }
                logger.info("Cancelled Codex session %s after capturing partial output", captured_session)
                raise
            except Exception as exc:
                await stop_process()
                if readers:
                    await asyncio.gather(*readers, return_exceptions=True)
                reason = redact_secrets(str(exc))
                result = {
                    "success": False,
                    "reason": reason,
                    "exit_code": process.returncode if process else None,
                    "output": redact_secrets(stdout_buffer.decode(errors="replace").strip()),
                    "error": redact_secrets(stderr_buffer.decode(errors="replace").strip()),
                    "session_id": None,
                    "runtime_mode": "codex_fallback",
                    "process_id": process.pid if process else None,
                    "attempts": attempt,
                    "retry_history": list(retry_history),
                }
                self.last_execution = dict(result)
                logger.error("Failed to execute Codex CLI: %s", reason)
                return result

    async def perform_independent_analysis(self, project_id: str, project_name: str, brief: str) -> IndependentAnalysis:
        logger.info("Codex performing independent analysis for %s (Native CLI Available: %s)", project_name, self.is_cli_available)
        
        prompt = (
            f"Analyze this software project brief from a systems architecture perspective:\n"
            f"Project: {project_name}\nBrief: {brief}\n\n"
            f"Requirements:\n"
            f"- Strictly adhere to Pony Tail minimalism (pure standard library, 0 external pip packages).\n"
            f"- Propose core typed data models and data structures.\n"
            f"- Output a concise architectural plan."
        )

        with db.get_connection() as conn:
            project_row = conn.execute("SELECT project_md_path FROM projects WHERE id = ?", (project_id,)).fetchone()
        analysis_workspace = str(Path(project_row["project_md_path"]).parent) if project_row else None
        if analysis_workspace:
            cli_res = await self._run_codex_cli(
                prompt, analysis_workspace, timeout=30, read_only=True, retry_safe=True
            )
        else:
            cli_res = {"success": False, "reason": "Project workspace not found; native analysis not started", "output": "", "exit_code": None, "session_id": None}
        
        understanding = "Codex native analysis was not completed. No Codex recommendation is available."
        architecture = "No architecture proposal: native Codex CLI did not complete a successful analysis request."
        if cli_res["success"] and cli_res["output"]:
            understanding = f"[Native Codex CLI Analysis] {cli_res['output'][:250]}..."
            architecture = f"[Native Codex CLI Analysis] {cli_res['output'][:280]}..."
        else:
            understanding = f"[CODEX LOCAL FALLBACK — NOT EXECUTED] {understanding}"

        self.last_runtime_evidence = {
            "runtime_mode": cli_res.get("runtime_mode", "codex_fallback"),
            "session_id": cli_res.get("session_id"),
            "request_id": None,
            "process_id": cli_res.get("process_id"),
            "exit_status": cli_res.get("exit_code"),
            "error_reason": cli_res.get("reason") or (cli_res.get("error") if not cli_res.get("success") else None),
        }

        return IndependentAnalysis(
            project_id=project_id,
            agent_id=self.agent_id,
            agent_name=self.name,
            understanding=understanding,
            architecture=architecture,
            tech_stack=["Native Codex CLI response"] if cli_res["success"] and cli_res["output"] else [],
            implementation_plan=["Review the native Codex response"] if cli_res["success"] and cli_res["output"] else [],
            risks=["Native Codex analysis unavailable; no Codex risk review was produced"] if not (cli_res["success"] and cli_res["output"]) else [],
            missing_requirements=[],
            complexity="UNKNOWN" if not (cli_res["success"] and cli_res["output"]) else "MEDIUM",
            runtime_evidence=dict(self.last_runtime_evidence),
        )

    async def generate_discussion_turn(
        self,
        project_id: str,
        project_name: str,
        brief: str,
        room_messages: List[Dict[str, Any]],
        turn_index: int
    ) -> str:
        prompt = (
            f"You are ChatGPT Codex, Chief Software Architect. In a Switch room debate for '{project_name}', "
            f"provide your architectural proposal in under 100 words prioritizing Pony Tail standard library simplicity."
        )
        with db.get_connection() as conn:
            project_row = conn.execute("SELECT project_md_path FROM projects WHERE id = ?", (project_id,)).fetchone()
        discussion_workspace = str(Path(project_row["project_md_path"]).parent) if project_row else None
        cli_res = await self._run_codex_cli(
            prompt, discussion_workspace, timeout=35, read_only=True, retry_safe=True
        ) if discussion_workspace else {
            "success": False, "reason": "Project workspace not found; native discussion analysis not started",
            "output": "", "exit_code": None, "session_id": None,
        }
        if cli_res["success"] and len(cli_res["output"]) > 40:
            self.last_runtime_evidence = {
                "runtime_mode": "native_codex_cli",
                "session_id": cli_res.get("session_id"),
                "request_id": None,
                "process_id": cli_res.get("process_id"),
                "exit_status": cli_res.get("exit_code"),
                "error_reason": None,
            }
            return f"### [ARCHITECTURAL PROPOSAL] Turn {turn_index}\n**Speaker:** ChatGPT Codex (Native Codex CLI)\n\n{cli_res['output'][:400]}"

        self.last_runtime_evidence = {
            "runtime_mode": "codex_fallback",
            "session_id": cli_res.get("session_id"),
            "request_id": None,
            "process_id": cli_res.get("process_id"),
            "exit_status": cli_res.get("exit_code"),
            "error_reason": cli_res.get("reason") or "Native Codex invocation did not produce a successful response",
        }

        return (
            f"### [RUNTIME UNAVAILABLE] Turn {turn_index}\n"
            "**Speaker:** ChatGPT Codex (LOCAL FALLBACK — NOT EXECUTED)\n"
            "The native Codex CLI did not produce a successful response. No architectural proposal was generated. "
            f"Recorded reason: {redact_secrets(str(cli_res.get('reason') or cli_res.get('error') or 'native response unavailable'))[:240]}"
        )

    async def execute_task(self, task: TaskItem, workspace_dir: str) -> Dict[str, Any]:
        """Execute task inside the isolated runner."""
        require_owner_approved_task(task, workspace_dir)
        from agenthive.engine.execution import runner
        return await runner.execute_task_isolated(task, workspace_dir)
