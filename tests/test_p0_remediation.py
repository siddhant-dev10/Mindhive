"""Isolated regression coverage for P0 security and planning safeguards."""

import json
import sqlite3
import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agenthive.config import settings
from agenthive.database import db
from agenthive.engine.orchestrator import Orchestrator, runner as execution_runner
from agenthive.engine.execution import ExecutionRunner
from agenthive.models.project import HermesSupervisorPlan, TaskItem
from agenthive.agents.agy import AGYAgent
from agenthive.agents.codex import CodexAgent
from agenthive.agents.gemini import GeminiAgent
from agenthive.agents.hermes import HermesAgent
from agenthive.security import redact_secrets, validate_workspace_path, validate_project_workspace, require_owner_approved_task, agent_subprocess_env


def _create_project(orchestrator, owner="owner-1"):
    project = orchestrator.create_project("P0 planning test", "Verify safe isolated planning behavior", owner)
    room_id = f"room-{project.id}"
    with db.get_connection() as conn:
        conn.execute("UPDATE projects SET switch_room_id = ? WHERE id = ?", (room_id, project.id))
        conn.commit()
    return project, room_id


def _insert_discussion(project_id, room_id, turn, sender, content, event_id=None, message_id=None):
    with db.get_connection() as conn:
        conn.execute(
            """INSERT INTO discussion_messages
            (id, project_id, turn_index, sender_id, sender_name, sender_role, content,
             switch_event_id, switch_message_id, switch_room_id, runtime_evidence_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"message-{project_id}-{turn}", project_id, turn, sender, sender, "AGENT", content,
             event_id, message_id, room_id, json.dumps({"runtime_mode": "test_stub"})),
        )
        conn.commit()


def _fake_plan(project_id, discussions):
    return HermesSupervisorPlan(
        project_id=project_id,
        recommended_architecture="Test-only plan",
        agreements=[], disagreements=[], evaluated_arguments="Test-only",
        proposed_roles={},
        discussion_sources=[{"turn_index": row["turn_index"], "sender_id": row["sender_id"]} for row in discussions],
        tasks=[TaskItem(project_id=project_id, task_code="TASK-01", title="test", description="test", assigned_agent="Codex")],
    )


@pytest.mark.asyncio
async def test_discussion_planning_preserves_order_room_and_switch_evidence(monkeypatch):
    orch = Orchestrator()
    project, room_id = _create_project(orch)
    _insert_discussion(project.id, room_id, 2, "agent-b", "second proposal", "event-2", "switch-2")
    _insert_discussion(project.id, room_id, 1, "agent-a", "first proposal", "event-1", "switch-1")
    captured = {}

    def synthesize(project_id, name, brief, analyses, discussions):
        captured.update(project_id=project_id, discussions=discussions)
        return _fake_plan(project_id, discussions)

    monkeypatch.setattr(orch.hermes, "synthesize_plan", synthesize)
    plan = await orch.generate_hermes_plan(project.id)

    assert captured["project_id"] == project.id
    assert [message["turn_index"] for message in captured["discussions"]] == [1, 2]
    assert all(message["project_id"] == project.id and message["switch_room_id"] == room_id for message in captured["discussions"])
    assert [message["switch_event_id"] for message in captured["discussions"]] == ["event-1", "event-2"]
    assert [source["sender_id"] for source in plan.discussion_sources] == ["agent-a", "agent-b"]
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ? AND human_approved = 1", (project.id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM task_execution_logs WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ?)", (project.id,)).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_empty_discussion_fails_without_replacing_tasks():
    orch = Orchestrator()
    project, _ = _create_project(orch)
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (id, project_id, task_code, title, description, assigned_agent, status, human_approved) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            ("preserved-task", project.id, "TASK-OLD", "keep", "existing", "Codex", "PENDING_APPROVAL"),
        )
        conn.commit()
    with pytest.raises(ValueError, match="no persisted discussion messages"):
        await orch.generate_hermes_plan(project.id)
    with db.get_connection() as conn:
        row = conn.execute("SELECT task_code, human_approved FROM tasks WHERE id = 'preserved-task'").fetchone()
        assert tuple(row) == ("TASK-OLD", 0)


@pytest.mark.asyncio
async def test_discussion_room_mismatch_fails_closed():
    orch = Orchestrator()
    project, room_id = _create_project(orch)
    _insert_discussion(project.id, "wrong-room", 1, "agent-a", "unverified", "event", "message")
    with pytest.raises(ValueError, match="not verifiably associated"):
        await orch.generate_hermes_plan(project.id)


def test_approval_is_owner_bound_and_task_version_bound(monkeypatch):
    orch = Orchestrator()
    project, _ = _create_project(orch, owner="owner-1")
    monkeypatch.setattr(settings, "discord_owner_id", "owner-1")
    monkeypatch.setattr(settings, "workspace_root", str(__import__("pathlib").Path(project.project_md_path).parents[1]))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (id, project_id, task_code, title, description, assigned_agent, status, human_approved) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            ("approval-task", project.id, "TASK-01", "original", "proposal", "Codex", "PENDING_APPROVAL"),
        )
        conn.commit()
    with pytest.raises(PermissionError, match="configured project owner"):
        orch.approve_tasks(project.id, "intruder")
    approved = orch.approve_tasks(project.id, "owner-1")
    assert approved[0].human_approved is True
    assert approved[0].approved_by == "owner-1"
    assert approved[0].approved_task_hash
    monkeypatch.setattr(settings, "task_execution_enabled", True)
    monkeypatch.setattr(settings, "secure_agent_task_runner_configured", True)
    assert require_owner_approved_task(approved[0], Path(project.project_md_path).parent) == Path(project.project_md_path).parent.resolve()
    with db.get_connection() as conn:
        conn.execute("UPDATE tasks SET description = 'tampered after approval' WHERE id = 'approval-task'")
        conn.commit()
    monkeypatch.setattr(execution_runner, "secure_test_runner_available", AsyncMock(return_value=True))
    with pytest.raises(PermissionError, match="changed after approval"):
        __import__("asyncio").run(orch.execute_project(project.id))
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_execution_logs WHERE task_id = 'approval-task'").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_execution_gate_blocks_before_agent_adapters(monkeypatch):
    orch = Orchestrator()
    project, _ = _create_project(orch)
    monkeypatch.setattr(settings, "task_execution_enabled", False)
    with pytest.raises(PermissionError, match="disabled"):
        await orch.execute_project(project.id)
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (project.id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM task_execution_logs WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ?)", (project.id,)).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_execution_remains_blocked_even_if_legacy_flag_is_enabled(monkeypatch):
    orch = Orchestrator()
    project, _ = _create_project(orch)
    monkeypatch.setattr(settings, "task_execution_enabled", True)
    monkeypatch.setattr(settings, "secure_agent_task_runner_configured", False)
    with pytest.raises(PermissionError, match="isolated native-agent runner is not implemented"):
        await orch.execute_project(project.id)


@pytest.mark.asyncio
async def test_agy_unavailable_binary_is_explicit_fallback(monkeypatch):
    agent = AGYAgent()
    monkeypatch.setattr(agent, "is_cli_available", False)
    text = await agent.generate_discussion_turn("p", "project", "brief", [], 1)
    assert "LOCAL FALLBACK" in text
    assert agent.last_runtime_evidence["runtime_mode"] == "agy_fallback"
    assert agent.last_runtime_evidence["session_id"] is None
    assert "No AGY recommendation was generated" in text
    assert "argparse" not in text and "Alpine" not in text


@pytest.mark.asyncio
async def test_agy_native_success_requires_success_envelope(monkeypatch, tmp_path):
    agent = AGYAgent()
    workspace = tmp_path / "project"
    workspace.mkdir()
    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    monkeypatch.setattr(agent, "is_cli_available", True)
    monkeypatch.setattr(agent, "binary_path", "agy-test-binary")

    class FakeProcess:
        pid = 50123
        returncode = 0
        async def communicate(self):
            return (json.dumps({"status": "SUCCESS", "response": "real-shaped test response", "session_id": "session-from-envelope"}).encode(), b"")

    monkeypatch.setattr("agenthive.agents.agy.asyncio.create_subprocess_exec", AsyncMock(return_value=FakeProcess()))
    response = await agent._run_agy_cli("test", str(workspace))
    assert response == "real-shaped test response"
    assert agent.last_runtime_evidence["runtime_mode"] == "native_agy_cli"
    assert agent.last_runtime_evidence["session_id"] == "session-from-envelope"


@pytest.mark.asyncio
async def test_agy_timeout_is_fallback_and_process_group_is_stopped(monkeypatch, tmp_path):
    agent = AGYAgent()
    workspace = tmp_path / "project"
    workspace.mkdir()
    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    monkeypatch.setattr(agent, "is_cli_available", True)
    monkeypatch.setattr(agent, "binary_path", "agy-test-binary")

    class FakeProcess:
        pid = 50124
        returncode = None
        def __init__(self):
            self.finished = None
        async def communicate(self):
            self.finished = asyncio.get_running_loop().create_future()
            return await self.finished
        async def wait(self):
            self.returncode = -15
            if self.finished and not self.finished.done():
                self.finished.set_result((b"partial", b""))
            return self.returncode

    fake_process = FakeProcess()
    monkeypatch.setattr("agenthive.agents.agy.asyncio.create_subprocess_exec", AsyncMock(return_value=fake_process))
    response = await agent._run_agy_cli("test", str(workspace), timeout=-9.99)
    assert "LOCAL FALLBACK — NOT EXECUTED" in response
    assert "No AGY recommendation was generated" in response
    assert agent.last_runtime_evidence["runtime_mode"] == "agy_fallback"
    assert "Timed out" in agent.last_runtime_evidence["error_reason"]
    assert fake_process.returncode == -15
    assert agent.last_runtime_evidence["partial_output_chars"] > 0


@pytest.mark.asyncio
async def test_gemini_missing_api_is_explicit_fallback():
    agent = GeminiAgent()
    agent.is_live = False
    text = await agent.generate_discussion_turn("p", "project", "brief", [], 1)
    assert "LOCAL FALLBACK" in text
    assert agent.last_runtime_evidence["runtime_mode"] == "gemini_local_fallback"
    assert agent.last_runtime_evidence["request_id"] is None
    assert "NO API REQUEST" in text
    assert "ring buffer" not in text.lower()


@pytest.mark.asyncio
async def test_gemini_api_error_is_not_reported_as_live(monkeypatch):
    agent = GeminiAgent()
    agent.api_key = "synthetic-test-key"
    agent.is_live = True
    response = type("Response", (), {"status_code": 429, "text": "rate limit"})()
    monkeypatch.setattr("httpx.AsyncClient.post", AsyncMock(return_value=response))
    result = await agent._call_gemini_api("test")
    assert result is None
    assert agent.last_runtime_evidence["runtime_mode"] == "gemini_local_fallback"
    assert agent.last_runtime_evidence["exit_status"] == 429


@pytest.mark.asyncio
async def test_hermes_unavailable_daemon_is_explicit_governance_fallback(monkeypatch):
    agent = HermesAgent()
    monkeypatch.setattr(agent.runtime_adapter, "check_liveness", AsyncMock(return_value=False))
    text = await agent.generate_discussion_turn("p", "project", "brief", [], 1)
    assert "LOCAL GOVERNANCE FALLBACK" in text
    assert agent.last_runtime_evidence["runtime_mode"] == "local_governance_fallback"
    assert agent.last_runtime_evidence["session_id"] is None


@pytest.mark.asyncio
async def test_codex_native_label_requires_successful_invocation(monkeypatch):
    project = Orchestrator().create_project("Codex provenance", "Verify invocation provenance", "owner-1")
    agent = CodexAgent()
    monkeypatch.setattr(agent, "_run_codex_cli", AsyncMock(return_value={"success": True, "output": "A sufficiently long native response for a unit test.", "exit_code": 0, "session_id": None, "process_id": 123}))
    native_text = await agent.generate_discussion_turn(project.id, "project", "brief", [], 1)
    assert "Native Codex CLI" in native_text
    assert agent.last_runtime_evidence["runtime_mode"] == "native_codex_cli"
    assert agent.last_runtime_evidence["session_id"] is None
    monkeypatch.setattr(agent, "_run_codex_cli", AsyncMock(return_value={"success": False, "output": "fallback", "exit_code": -1, "reason": "timeout", "session_id": None}))
    fallback_text = await agent.generate_discussion_turn(project.id, "project", "brief", [], 2)
    assert "Native Codex CLI" not in fallback_text
    assert "No architectural proposal was generated" in fallback_text
    assert agent.last_runtime_evidence["runtime_mode"] == "codex_fallback"


@pytest.mark.asyncio
async def test_unavailable_agents_do_not_publish_fabricated_project_analysis(monkeypatch):
    from agenthive.agents.hermes import HermesAgent
    project = Orchestrator().create_project("Fallback provenance", "A generic project brief", "owner-1")
    codex = CodexAgent()
    agy = AGYAgent()
    gemini = GeminiAgent()
    monkeypatch.setattr(codex, "is_cli_available", False)
    monkeypatch.setattr(agy, "is_cli_available", False)
    monkeypatch.setattr(gemini, "is_live", False)

    codex_analysis = await codex.perform_independent_analysis(project.id, project.name, project.description)
    agy_analysis = await agy.perform_independent_analysis(project.id, project.name, project.description)
    gemini_analysis = await gemini.perform_independent_analysis(project.id, project.name, project.description)
    hermes_analysis = await HermesAgent().perform_independent_analysis(project.id, project.name, project.description)

    assert "No Codex recommendation is available" in codex_analysis.understanding
    assert codex_analysis.tech_stack == []
    assert "no AGY recommendation is available" in agy_analysis.understanding
    assert agy_analysis.tech_stack == []
    assert "LOCAL FALLBACK" in gemini_analysis.understanding
    assert "ring buffer" not in gemini_analysis.understanding.lower()
    assert "does not claim an independent project review" in hermes_analysis.understanding


def test_workspace_confinement_and_secret_redaction(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(settings, "workspace_root", str(root))
    assert validate_workspace_path(root / "project") == (root / "project").resolve()
    with pytest.raises(PermissionError):
        validate_workspace_path(tmp_path / "outside")
    sanitized = redact_secrets("api_key=example-secret-value Bearer ABCDEFGHIJKLMNOPQRSTUV sk-proj-abcdefghijklmnopqrstuvwxyz1234567890")
    assert "example-secret-value" not in sanitized
    assert "ABCDEFGHIJKLMNOPQRSTUV" not in sanitized
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890" not in sanitized
    more_sanitized = redact_secrets(
        'password="unit-test-pass" postgres://user:unit-test-pass@host/db '
        'https://discord.com/api/webhooks/12345/unit-test-webhook-token'
    )
    assert "unit-test-pass" not in more_sanitized
    assert "unit-test-webhook-token" not in more_sanitized


def test_agent_workspace_is_bound_to_exact_project(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    monkeypatch.setattr(settings, "workspace_root", str(root))
    orch = Orchestrator()
    project_a, _ = _create_project(orch)
    project_b, _ = _create_project(orch)
    workspace_a = Path(project_a.project_md_path).parent
    workspace_b = Path(project_b.project_md_path).parent
    assert validate_project_workspace(project_a.id, workspace_a) == workspace_a.resolve()
    with pytest.raises(PermissionError, match="does not belong to the requested project"):
        validate_project_workspace(project_a.id, workspace_b)


def test_native_cli_environment_excludes_agenthive_credentials(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "synthetic-discord-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-secret")
    child_env = agent_subprocess_env()
    assert "PATH" in child_env
    assert "DISCORD_BOT_TOKEN" not in child_env
    assert "GEMINI_API_KEY" not in child_env


def test_wildcard_bind_requires_explicit_remote_bind_opt_in(monkeypatch):
    from agenthive.config import _effective_host
    monkeypatch.setenv("AGENTHIVE_HOST", "0.0.0.0")
    monkeypatch.delenv("AGENTHIVE_ALLOW_REMOTE_BIND", raising=False)
    assert _effective_host() == "127.0.0.1"
    monkeypatch.setenv("AGENTHIVE_ALLOW_REMOTE_BIND", "true")
    assert _effective_host() == "0.0.0.0"


@pytest.mark.asyncio
async def test_test_runner_fails_closed_without_configured_container(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    workspace = root / "project"
    (workspace / "tests").mkdir(parents=True)
    monkeypatch.setattr(settings, "workspace_root", str(root))
    monkeypatch.setattr(settings, "test_runner_image", None)
    result = await ExecutionRunner().run_tests(str(workspace))
    assert result["success"] is False
    assert result["runtime_mode"] == "blocked_no_secure_runner"
    assert "host execution is disabled" in result["stderr"]


@pytest.mark.asyncio
async def test_dashboard_mutations_fail_closed_without_local_api_token(monkeypatch):
    import httpx
    from agenthive.main import app
    from agenthive.config import settings

    monkeypatch.setattr(settings, "dashboard_api_token", None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        response = await client.post("/api/projects", json={"name": "mutation test", "description": "must be rejected"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Dashboard owner session required"


@pytest.mark.asyncio
async def test_local_switch_bridge_requires_internal_bearer(monkeypatch):
    import httpx
    from agenthive.main import app
    from agenthive.config import settings

    monkeypatch.setattr(settings, "switch_registration_token", "synthetic-local-switch-token")
    transport = httpx.ASGITransport(app=app)
    payload = {"agent_id": "isolated-auth-test", "name": "Isolated Auth Test", "role": "test", "description": "test"}
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        denied = await client.post("/switch/api/v1/agents/register", json=payload)
        allowed = await client.post(
            "/switch/api/v1/agents/register",
            json=payload,
            headers={"Authorization": "Bearer synthetic-local-switch-token"},
        )
    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_additive_database_migration_adds_provenance_and_owner_fields(tmp_path):
    legacy_db = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(legacy_db)
    connection.executescript("""
        CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
          description TEXT NOT NULL, current_state TEXT NOT NULL DEFAULT 'DRAFT', switch_room_id TEXT,
          project_md_path TEXT NOT NULL, discord_channel_id TEXT, discord_thread_id TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE independent_analyses (id TEXT PRIMARY KEY, project_id TEXT, agent_id TEXT, agent_name TEXT,
          understanding TEXT, architecture TEXT, tech_stack TEXT, implementation_plan TEXT, risks TEXT,
          missing_requirements TEXT, complexity TEXT, raw_payload TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE discussion_messages (id TEXT PRIMARY KEY, project_id TEXT, turn_index INTEGER, sender_id TEXT,
          sender_name TEXT, sender_role TEXT, reply_to_agent TEXT, content TEXT, switch_event_id TEXT,
          switch_message_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE tasks (id TEXT PRIMARY KEY, project_id TEXT, task_code TEXT, title TEXT, description TEXT,
          assigned_agent TEXT, priority TEXT DEFAULT 'MEDIUM', status TEXT DEFAULT 'PENDING_APPROVAL',
          human_approved INTEGER DEFAULT 0, dependencies TEXT DEFAULT '[]', acceptance_criteria TEXT DEFAULT '[]',
          completion_report TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    """)
    connection.commit()
    connection.close()

    from agenthive.database import Database
    migrated = Database(str(legacy_db))
    with migrated.get_connection() as conn:
        columns = {
            table: {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for table in ("projects", "independent_analyses", "discussion_messages", "tasks")
        }
    assert "owner_discord_id" in columns["projects"]
    assert "runtime_evidence_json" in columns["independent_analyses"]
    assert {"switch_room_id", "runtime_evidence_json"}.issubset(columns["discussion_messages"])
    assert {"approved_by", "approved_at", "approved_task_hash"}.issubset(columns["tasks"])


def test_discord_approval_button_does_not_execute_tasks():
    source = Path("agenthive/discord_gateway/views.py").read_text()
    tree = ast.parse(source)
    callback = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "approve_button")
    calls = [node.func.attr for node in ast.walk(callback) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert "cmd_approve" in calls
    assert "cmd_report" not in calls
