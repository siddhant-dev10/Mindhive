"""AgentHive V2 - Security Enforcement Module.
Defines security boundary validations, path traversal guards, command allow-lists,
and credential redaction rules across all agent runtimes and execution planes.
"""

import os
import re
import hashlib
import json
from pathlib import Path
from typing import List, Union
from agenthive.config import settings

def get_allowed_roots() -> List[Path]:
    """Return only the explicitly configured project workspace boundary."""
    roots = []
    if settings.workspace_root:
        roots.append(Path(settings.workspace_root).resolve())
    return roots

def validate_workspace_path(path: Union[str, Path]) -> Path:
    """Enforces filesystem confinement to prevent path traversal outside authorized roots.
    Raises PermissionError if the target path resolves outside allowed boundaries.
    """
    if not path:
        raise PermissionError("Security Boundary Violation: Empty workspace path.")

    resolved = Path(path).resolve()
    allowed_roots = get_allowed_roots()

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    raise PermissionError(
        f"Security Boundary Violation: Path '{resolved}' resolves outside authorized roots: "
        f"{[str(r) for r in allowed_roots]}"
    )


def validate_project_workspace(project_id: str, path: Union[str, Path]) -> Path:
    """Require an agent path to match the recorded workspace for this exact project."""
    if not project_id:
        raise PermissionError("Security Boundary Violation: Project ID is required")
    from agenthive.database import db
    with db.get_connection() as conn:
        row = conn.execute("SELECT project_md_path FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise PermissionError("Security Boundary Violation: Project workspace is not registered")
    expected = Path(row["project_md_path"]).resolve().parent
    actual = validate_workspace_path(path)
    if actual != expected:
        raise PermissionError("Security Boundary Violation: Workspace does not belong to the requested project")
    return actual


def require_owner_approved_task(task, workspace_path: Union[str, Path]) -> Path:
    """Fail closed unless an enabled task has durable owner approval for its exact version."""
    if not settings.task_execution_enabled:
        raise PermissionError("Task execution is disabled")
    if not settings.secure_agent_task_runner_configured:
        raise PermissionError("Secure isolated native-agent runner is not implemented; host task execution is disabled")
    workspace = validate_project_workspace(task.project_id, workspace_path)
    from agenthive.database import db
    with db.get_connection() as conn:
        row = conn.execute(
            """SELECT t.*, p.owner_discord_id FROM tasks AS t
               JOIN projects AS p ON p.id = t.project_id
               WHERE t.id = ? AND t.project_id = ?""",
            (task.id, task.project_id),
        ).fetchone()
    if not row or row["status"] != "APPROVED" or not row["human_approved"]:
        raise PermissionError("Task has no persisted owner approval")
    if not settings.discord_owner_id or row["approved_by"] != settings.discord_owner_id:
        raise PermissionError("Task approval was not recorded by the configured owner")
    if row["owner_discord_id"] != row["approved_by"] or not row["approved_at"]:
        raise PermissionError("Task approval is not bound to the recorded project owner")
    keys = ("id", "project_id", "task_code", "title", "description", "assigned_agent", "priority", "dependencies", "acceptance_criteria")
    payload = {}
    for key in keys:
        value = row[key]
        if key in ("dependencies", "acceptance_criteria") and isinstance(value, str):
            value = json.loads(value)
        payload[key] = value
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if not row["approved_task_hash"] or digest != row["approved_task_hash"]:
        raise PermissionError("Task was changed after owner approval")
    return workspace

def prohibit_dangerous_cli_flags(cmd: List[str]) -> None:
    """Hard security assertion: absolutely forbids unrestricted bypass flags like --dangerously-skip-permissions."""
    for arg in cmd:
        arg_str = str(arg).lower()
        if "dangerously-skip-permissions" in arg_str:
            raise PermissionError(
                "Security Violation: --dangerously-skip-permissions is strictly forbidden in AgentHive production runtimes."
            )


def agent_subprocess_env() -> dict:
    """Expose only the basic runtime environment to native agent CLIs.

    Credentials loaded by AgentHive remain in its process and are not inherited by child CLIs.
    Native CLI authentication continues to use each tool's own local credential store.
    """
    allowed = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "XDG_CONFIG_HOME")
    return {key: os.environ[key] for key in allowed if os.environ.get(key)}

def redact_secrets(text: str) -> str:
    """Redacts potential secrets, bearer tokens, or API keys from logs and console output."""
    if not text:
        return text
    # Redact Google API keys (AIza...)
    text = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_GEMINI_KEY]", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.~=+/]{12,}", r"\1[REDACTED_TOKEN]", text)
    text = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret|token)(\s*[=:]\s*)(['\"])(.*?)(\3)",
        r"\1\2\3[REDACTED_SECRET]\5",
        text,
    )
    text = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret|token)(\s*[=:]\s*)([^\s,;\"']+)",
        r"\1\2[REDACTED_SECRET]",
        text,
    )
    # Discord bot tokens have three base64url-like sections.
    text = re.sub(r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_.-])", "[REDACTED_DISCORD_TOKEN]", text)
    text = re.sub(r"(?i)\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b", "[REDACTED_OPENAI_KEY]", text)
    text = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]", text)
    text = re.sub(r"(?i)(://[^:/@\s]+:)[^@/\s]+(@)", r"\1[REDACTED_PASSWORD]\2", text)
    text = re.sub(
        r"(?i)(https?://(?:canary\.)?discord(?:app)?\.com/api/webhooks/\d+/)[A-Za-z0-9._-]+",
        r"\1[REDACTED_WEBHOOK_TOKEN]",
        text,
    )
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]", text, flags=re.DOTALL)
    text = re.sub(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b", "[REDACTED_GITHUB_TOKEN]", text)
    text = re.sub(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b", "[REDACTED_SLACK_TOKEN]", text)
    text = re.sub(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", "[REDACTED_ANTHROPIC_KEY]", text)
    return text
