"""AGY (Google Antigravity CLI) Agent Adapter.
Connects via Switch and executes real analysis, diagnostics, and tooling tasks using the native `agy` CLI binary.
Security Hardened:
- Strict project workspace scoping (`--add-dir <project_workspace>`)
- Zero unrestricted bypasses (no `--dangerously-skip-permissions`)
- Granular permission allow-lists passed via `--settings`
- Native sandboxing enabled (`--sandbox`)
"""

import asyncio
import json
import logging
import os
import re
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional
from agenthive.agents.base import BaseAgent
from agenthive.models.project import IndependentAnalysis, TaskItem
from agenthive.config import settings
from agenthive.database import db
from agenthive.security import validate_workspace_path, validate_project_workspace, require_owner_approved_task, prohibit_dangerous_cli_flags, redact_secrets, agent_subprocess_env

logger = logging.getLogger("agenthive.agents.agy")

class AGYAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent-agy",
            name="AGY (Antigravity)",
            role="Systems Integration & Assistant",
            description="Focuses on practical system integration, CLI tools, Docker sandboxing, and repository diagnostics.",
            capabilities=["cli_automation", "docker_sandboxing", "diagnostics", "build_tooling"]
        )
        self.session_id: Optional[str] = None
        self.last_runtime_evidence: Dict[str, Any] = {
            "runtime_mode": "agy_fallback",
            "session_id": None,
            "request_id": None,
            "exit_status": None,
            "error_reason": "AGY CLI not invoked",
        }
        self.binary_path = settings.agy_binary_path
        self.is_cli_available = os.path.exists(self.binary_path) and os.access(self.binary_path, os.X_OK)
        if self.is_cli_available:
            logger.info("AGY Agent detected native CLI at %s", self.binary_path)
        else:
            logger.info("AGY Agent running in local adapter mode (CLI not found at %s)", self.binary_path)

    async def _run_agy_cli(self, prompt: str, workspace_dir: Optional[str] = None, timeout: int = 35) -> str:
        """Executes the native agy CLI binary with strict workspace isolation and granular permissions."""
        if not self.is_cli_available:
            self.last_runtime_evidence = {
                "runtime_mode": "agy_fallback", "session_id": None,
                "request_id": None, "exit_status": None,
                "error_reason": "AGY CLI binary unavailable",
            }
            return self._fallback_response(prompt)

        if not workspace_dir:
            self.last_runtime_evidence = {
                "runtime_mode": "agy_fallback", "session_id": None,
                "request_id": None, "exit_status": None,
                "error_reason": "Project workspace was not supplied; native invocation not started",
            }
            return self._fallback_response(prompt)
        ws = validate_workspace_path(workspace_dir)
        ws.mkdir(parents=True, exist_ok=True)

        # Grant workspace file access only to this project workspace. Commands
        # stay inside AGY's terminal sandbox; no command-wide auto-approval is used.
        settings_payload = json.dumps({
            "toolPermission": "proceed-in-sandbox",
            "permissions": {
                "allow": [f"write_file({ws})"],
                "deny": [
                    f"write_file({ws / '.git'})",
                    f"write_file({ws / '.env'})",
                ],
            }
        })

        cmd = [
            self.binary_path,
            "--sandbox",
            "--add-dir", str(ws),
            "--settings", settings_payload,
            "--output-format", "json",
            "--print-timeout", f"{timeout}s",
            "-p", prompt
        ]

        # Security Guarantee: Absolutely prohibit --dangerously-skip-permissions
        prohibit_dangerous_cli_flags(cmd)

        process = None
        try:
            logger.info("Executing native AGY CLI (sandbox enabled, scoped to %s)...", ws)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(ws),
                env=agent_subprocess_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            # Give process an extra 10s grace period past CLI print-timeout to flush buffers and cleanly exit
            process_timeout = timeout + 10
            communication = asyncio.create_task(process.communicate())
            stdout, stderr = await asyncio.wait_for(asyncio.shield(communication), timeout=process_timeout)
            stdout_text = redact_secrets(stdout.decode(errors="replace").strip())
            stderr_text = redact_secrets(stderr.decode(errors="replace").strip())
            out_text = stdout_text
            status = "UNKNOWN"
            response_text = ""
            envelope = {}
            try:
                envelope = json.loads(stdout_text)
                if not isinstance(envelope, dict):
                    raise json.JSONDecodeError("AGY response is not a JSON object", stdout_text, 0)
                status = str(envelope.get("status", "UNKNOWN"))
                response_text = str(envelope.get("response") or "")
                if status != "SUCCESS" or process.returncode != 0 or not response_text.strip():
                    self.last_runtime_evidence = {
                        "runtime_mode": "agy_fallback", "session_id": envelope.get("session_id"),
                        "request_id": envelope.get("request_id"), "process_id": process.pid,
                        "exit_status": process.returncode,
                        "error_reason": redact_secrets(str(envelope.get("error") or f"AGY returned status {status}")),
                    }
                    logger.warning(
                        "AGY headless CLI returned status=%s exit=%s: %s",
                        status,
                        process.returncode,
                        redact_secrets(str(envelope.get("error") or stderr_text))[:500],
                    )
                    return self._fallback_response(prompt)
                out_text = response_text.strip()
            except (TypeError, json.JSONDecodeError):
                self.last_runtime_evidence = {
                    "runtime_mode": "agy_fallback", "session_id": None,
                    "request_id": None, "process_id": process.pid,
                    "exit_status": process.returncode, "error_reason": "AGY CLI returned malformed JSON output",
                }
                logger.warning("AGY headless CLI returned malformed JSON (exit=%s)", process.returncode)
                return self._fallback_response(prompt)
            if out_text and "no output produced" not in out_text:
                self.last_runtime_evidence = {
                    "runtime_mode": "native_agy_cli", "session_id": envelope.get("session_id") if isinstance(envelope, dict) else None,
                    "request_id": envelope.get("request_id") if isinstance(envelope, dict) else None,
                    "process_id": process.pid, "exit_status": process.returncode, "error_reason": None,
                }
                self.session_id = self.last_runtime_evidence.get("session_id")
                return out_text
            self.last_runtime_evidence = {
                "runtime_mode": "agy_fallback", "session_id": None,
                "request_id": None, "process_id": process.pid,
                "exit_status": process.returncode, "error_reason": "AGY CLI completed without a usable response",
            }
            logger.info("AGY CLI completed without usable response (status=%s)", status)
            return self._fallback_response(prompt)
        except asyncio.TimeoutError:
            logger.warning("AGY CLI execution timed out after %ds", timeout)
            try:
                if process and process.returncode is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    await asyncio.wait_for(process.wait(), timeout=2)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    if process:
                        os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            partial_stdout = partial_stderr = b""
            if "communication" in locals() and not communication.done():
                try:
                    await asyncio.wait_for(asyncio.shield(communication), timeout=1)
                except asyncio.TimeoutError:
                    communication.cancel()
                    await asyncio.gather(communication, return_exceptions=True)
            self.last_runtime_evidence = {
                "runtime_mode": "agy_fallback", "session_id": None,
                "request_id": None, "process_id": getattr(process, "pid", None),
                "exit_status": getattr(process, "returncode", None), "error_reason": f"Timed out after {timeout}s",
            }
            if "communication" in locals() and communication.done() and not communication.cancelled():
                try:
                    partial_stdout, partial_stderr = communication.result()
                except Exception:
                    pass
            self.last_runtime_evidence["partial_output_chars"] = len(partial_stdout) + len(partial_stderr)
            return self._fallback_response(prompt)
        except asyncio.CancelledError:
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
            raise
        except Exception as e:
            self.last_runtime_evidence = {
                "runtime_mode": "agy_fallback", "session_id": None,
                "request_id": None, "process_id": getattr(process, "pid", None),
                "exit_status": getattr(process, "returncode", None), "error_reason": type(e).__name__,
            }
            logger.error("Error executing AGY CLI (%s)", type(e).__name__)
            return self._fallback_response(prompt)

    def _fallback_response(self, prompt: str) -> str:
        reason = self.last_runtime_evidence.get("error_reason") or "Native AGY CLI did not complete successfully"
        return (
            "[AGY LOCAL FALLBACK — NOT EXECUTED]\n"
            "The native AGY CLI did not produce an analysis or discussion response. "
            f"No AGY recommendation was generated. Reason: {redact_secrets(str(reason))[:240]}"
        )

    def _parse_field(self, text: str, field_name: str, default: str) -> str:
        def _clean_val(v: str) -> str:
            # Strip markdown code delimiters, headers, and bullet noise
            cleaned = v.strip().lstrip("*#: \t`").rstrip("` \t")
            # Escape backslashes so downstream regex substitutions (e.g. re.sub in markdown formatters)
            # do not fail on escape patterns like \l (LaTeX \log) or regex characters \s, \d
            return cleaned.replace("\\", "\\\\")

        # 1. Match XML-style tags: <FIELD_NAME>...</FIELD_NAME> or <FIELD_NAME>...<OTHER_TAG>
        tag_match = re.search(rf"<{field_name}>(.*?)(?:</{field_name}>|(?=<\w+>)|\Z)", text, re.DOTALL | re.IGNORECASE)
        if tag_match:
            val = _clean_val(tag_match.group(1))
            if val:
                return val
        # 2. Match Markdown or plain key-value: **FIELD_NAME:** ... or FIELD_NAME: ...
        colon_match = re.search(rf"^[#*\s]*{field_name}[*#\s]*:[*#\s]*(.*?)(?=\n[#*\s]*[A-Z_]+[*#\s]*:|\Z)", text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if colon_match:
            val = _clean_val(colon_match.group(1))
            if val:
                return val
        # 3. Fallback standard regex
        match = re.search(rf"{field_name}:\s*(.*?)(?=\n[A-Z_]+:|\Z)", text, re.DOTALL | re.IGNORECASE)
        if match:
            val = _clean_val(match.group(1))
            if val:
                return val
        return default

    async def perform_independent_analysis(self, project_id: str, project_name: str, brief: str) -> IndependentAnalysis:
        prompt = (
            f"You are AGY, Systems Integration Engineer. Analyze this brief:\n"
            f"Project: {project_name}\nBrief: {brief}\n"
            f"Output with tags: UNDERSTANDING, ARCHITECTURE, TECH_STACK, PLAN, RISKS, MISSING, COMPLEXITY."
        )
        with db.get_connection() as conn:
            project_row = conn.execute("SELECT project_md_path FROM projects WHERE id = ?", (project_id,)).fetchone()
        analysis_workspace = str(Path(project_row["project_md_path"]).parent) if project_row else None
        if analysis_workspace:
            raw_output = await self._run_agy_cli(prompt, workspace_dir=analysis_workspace, timeout=40)
        else:
            self.last_runtime_evidence = {
                "runtime_mode": "agy_fallback", "session_id": None,
                "request_id": None, "exit_status": None,
                "error_reason": "Project workspace not found; native analysis not started",
            }
            raw_output = self._fallback_response(prompt)

        if self.last_runtime_evidence.get("runtime_mode") != "native_agy_cli":
            return IndependentAnalysis(
                project_id=project_id,
                agent_id=self.agent_id,
                agent_name=self.name,
                understanding="AGY native analysis was not completed; no AGY recommendation is available.",
                architecture="No architecture proposal: native AGY CLI did not complete a successful analysis request.",
                tech_stack=[],
                implementation_plan=[],
                risks=["Native AGY analysis unavailable; no AGY risk review was produced"],
                missing_requirements=[],
                complexity="UNKNOWN",
                runtime_evidence=dict(self.last_runtime_evidence),
            )

        if self.last_runtime_evidence.get("runtime_mode") == "native_agy_cli" and not self._parse_field(raw_output, "UNDERSTANDING", ""):
            self.last_runtime_evidence = {
                **self.last_runtime_evidence,
                "runtime_mode": "agy_fallback",
                "error_reason": "Native AGY response did not contain the requested analysis fields",
            }

        understanding = self._parse_field(
            raw_output,
            "UNDERSTANDING",
            f"Systems-level integration review for {project_name}: ergonomics, CLI entry points, and environment dependencies."
        )
        if self.last_runtime_evidence.get("runtime_mode") != "native_agy_cli":
            understanding = f"[AGY LOCAL FALLBACK] {understanding}"
        architecture = self._parse_field(
            raw_output,
            "ARCHITECTURE",
            "Lightweight CLI runner utilizing standard library primitives with containerized Docker packaging."
        )

        tech_raw = self._parse_field(raw_output, "TECH_STACK", "Python 3.11, argparse, sys, json, Docker, unittest")
        tech_stack = [t.strip().strip("-*•") for t in tech_raw.replace("\n", ",").split(",") if t.strip()]

        plan_raw = self._parse_field(
            raw_output,
            "PLAN",
            "Create minimal project layout, Implement CLI parsing with argparse, Author Dockerfile for non-root execution, Add automated verification script"
        )
        plan = [p.strip().strip("-*•") for p in plan_raw.replace("\n", ",").split(",") if p.strip()]

        risks_raw = self._parse_field(
            raw_output,
            "RISKS",
            "Host environment path dependencies, Unbounded memory consumption under massive streaming inputs, File permission issues when mounting volumes inside containers"
        )
        risks = [r.strip().strip("-*•") for r in risks_raw.replace("\n", ",").split(",") if r.strip()]

        missing_raw = self._parse_field(
            raw_output,
            "MISSING",
            "Spec on CLI stdout serialization format, Non-root UID requirements for container"
        )
        missing = [m.strip().strip("-*•") for m in missing_raw.replace("\n", ",").split(",") if m.strip()]

        complexity = self._parse_field(raw_output, "COMPLEXITY", "LOW").upper()
        if complexity not in ["LOW", "MEDIUM", "HIGH"]:
            complexity = "LOW"

        return IndependentAnalysis(
            project_id=project_id,
            agent_id=self.agent_id,
            agent_name=self.name,
            understanding=understanding,
            architecture=architecture,
            tech_stack=tech_stack,
            implementation_plan=plan,
            risks=risks,
            missing_requirements=missing,
            complexity=complexity,
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
            f"You are AGY in a Switch room debate for '{project_name}'. "
            f"Provide a 75-word response emphasizing standard library CLI ergonomics and non-root Docker sandboxing."
        )
        with db.get_connection() as conn:
            project_row = conn.execute("SELECT project_md_path FROM projects WHERE id = ?", (project_id,)).fetchone()
        discussion_workspace = str(Path(project_row["project_md_path"]).parent) if project_row else None
        cli_response = await self._run_agy_cli(prompt, workspace_dir=discussion_workspace, timeout=35)
        if self.last_runtime_evidence.get("runtime_mode") == "native_agy_cli" and cli_response:
            return f"### [INTEGRATION & TOOLING EVALUATION] Turn {turn_index}\n**Speaker:** AGY (Native Antigravity CLI)\n\n{cli_response[:350]}"

        return cli_response

    async def execute_task(self, task: TaskItem, workspace_dir: str) -> Dict[str, Any]:
        """Execute task inside the isolated runner."""
        require_owner_approved_task(task, workspace_dir)
        from agenthive.engine.execution import runner
        return await runner.execute_task_isolated(task, workspace_dir)
