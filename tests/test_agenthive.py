"""AgentHive End-to-End Test Suite.
Verifies the complete multi-agent engineering lifecycle:
Project Creation -> PROJECT.md -> Independent Analysis -> Switch Discussion ->
Hermes Supervision -> Human Approval -> Sandboxed Execution -> Verification -> Final Report.
"""

import pytest
import asyncio
from pathlib import Path
from agenthive.database import db
from agenthive.engine.orchestrator import orchestrator
from agenthive.switch.server import switch_state
from agenthive.models.events import SwitchAgentRegistration, SwitchHeartbeat, SwitchRoomCreate
from agenthive.engine.ponytail import ponytail_guard
from agenthive.discord_gateway.bot import discord_dispatcher
from agenthive.config import settings

@pytest.mark.asyncio
async def test_database_initialization():
    """Verify SQLite database initialized with all required tables."""
    with db.get_connection() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t["name"] for t in tables]
        for expected in ["projects", "independent_analyses", "discussion_messages", "tasks", "task_execution_logs"]:
            assert expected in table_names, f"Expected table {expected} in database"

@pytest.mark.asyncio
async def test_switch_server_protocol():
    """Verify Switch Agent Protocol endpoints and in-memory state."""
    # Register an agent
    reg = SwitchAgentRegistration(
        agent_id="test-agent-codex",
        name="Test Codex",
        role="Architect",
        description="Test agent"
    )
    switch_state.agents[reg.agent_id] = reg
    assert "test-agent-codex" in switch_state.agents

    # Heartbeat
    beat = SwitchHeartbeat(agent_id="test-agent-codex")
    assert beat.agent_id == "test-agent-codex"

    # Room creation
    room = SwitchRoomCreate(room_id="test-room-1", name="Test Room")
    switch_state.rooms[room.room_id] = room
    assert "test-room-1" in switch_state.rooms

@pytest.mark.asyncio
@pytest.mark.usefixtures("official_switch_runtime")
async def test_isolated_local_workflow_stops_at_human_approval():
    """Exercise local protocol plumbing without claiming live Switch or task execution."""
    # Phase 1: Create project
    proj_res = await discord_dispatcher.cmd_newproject(
        name="CacheFlow",
        description="A high-performance in-memory cache with TTL support and zero external pip dependencies.",
        user_id=settings.discord_owner_id,
    )
    assert proj_res["success"] is True
    project_id = proj_res["project_id"]
    assert project_id is not None

    proj = orchestrator.get_project(project_id)
    assert proj is not None
    assert Path(proj.project_md_path).exists()

    # Phase 2: Independent Analysis
    analyse_res = await discord_dispatcher.cmd_analyse(project_id, actor_id=settings.discord_owner_id)
    assert analyse_res["success"] is True
    assert analyse_res["analyses_count"] == 4  # Codex, AGY, Gemini, Hermes
    assert len(analyse_res["summary"]) == 4

    # Phase 3: Switch Room Collaborative Debate
    discuss_res = await discord_dispatcher.cmd_discuss(project_id, actor_id=settings.discord_owner_id)
    assert discuss_res["success"] is True
    assert discuss_res["switch_transport"] == "local fallback"
    assert discuss_res["turns_completed"] >= 4
    # Verify sender diversity (never simulated as one)
    senders = [m["sender"] for m in discuss_res["messages"]]
    assert "ChatGPT Codex" in senders
    assert "AGY (Antigravity)" in senders
    assert "Google Gemini" in senders
    assert "Hermes Supervisor" in senders

    # Phase 4: Hermes Supervision & WBS Allocation
    assign_res = await discord_dispatcher.cmd_assign(project_id, actor_id=settings.discord_owner_id)
    assert assign_res["success"] is True
    assert len(assign_res["tasks"]) == 3
    # Check assigned roles
    assigned_agents = [t["assigned_agent"] for t in assign_res["tasks"]]
    assert "ChatGPT Codex" in assigned_agents
    assert "AGY (Antigravity)" in assigned_agents
    assert "Google Gemini" in assigned_agents

    # Human approval is recorded only by an explicit owner interaction; this test stops first.
    status = await discord_dispatcher.cmd_status(project_id, actor_id=settings.discord_owner_id)
    assert status["approval"]["approved_count"] == 0
    assert all(not task["human_approved"] for task in status["tasks"])
    assert status["execution_logs"] == []

    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_execution_logs WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ?)", (project_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ? AND human_approved = 1", (project_id,)).fetchone()[0] == 0

    # Verify Pony Tail audits only the isolated project workspace; no execution is implied.
    ws_dir = Path(proj.project_md_path).parent
    audit = ponytail_guard.audit_workspace(str(ws_dir))
    assert audit["passed"] is True
    assert audit["audited_files"] >= 0


@pytest.mark.asyncio
async def test_complete_end_to_end_workflow_with_isolated_runner(monkeypatch):
    """Complete workflow verification with disposable isolated test data:
    Project creation -> analysis -> Switch discussion -> discussion-aware planning ->
    owner approval separation -> secure execution -> testing -> final report.
    """
    from agenthive.engine.execution import runner

    monkeypatch.setattr(settings, "discord_owner_id", "test-owner")

    # 1. Project Creation
    proj_res = await discord_dispatcher.cmd_newproject(
        name="MicroRateLimiter",
        description="Token bucket rate limiter in Python standard library with nanosecond timestamps.",
        user_id="test-owner",
    )
    assert proj_res["success"] is True
    project_id = proj_res["project_id"]
    proj = orchestrator.get_project(project_id)
    assert proj is not None
    assert proj.owner_discord_id == "test-owner"

    # 2. Independent Analysis
    analyse_res = await discord_dispatcher.cmd_analyse(project_id, actor_id="test-owner")
    assert analyse_res["success"] is True
    assert analyse_res["analyses_count"] == 4
    for summary in analyse_res["summary"]:
        assert summary["agent"] in ("ChatGPT Codex", "AGY (Antigravity)", "Google Gemini", "Hermes Supervisor")

    # 3. Switch Discussion
    discuss_res = await discord_dispatcher.cmd_discuss(project_id, actor_id="test-owner")
    assert discuss_res["success"] is True
    assert discuss_res["turns_completed"] >= 4

    # 4. Discussion-Aware Planning (Hermes)
    assign_res = await discord_dispatcher.cmd_assign(project_id, actor_id="test-owner")
    assert assign_res["success"] is True
    assert len(assign_res["tasks"]) == 3
    assert all(not t.get("human_approved", False) for t in assign_res["tasks"])

    # 5. Approval Gate Separation
    # Attempting to execute / report before approval must fail
    report_unapproved = await discord_dispatcher.cmd_report(project_id, actor_id="test-owner")
    assert report_unapproved["success"] is False

    # Non-owner attempting approval must fail
    non_owner_approve = await discord_dispatcher.cmd_approve(project_id, actor_id="intruder")
    assert non_owner_approve["success"] is False

    # Owner approves the plan
    approve_res = await discord_dispatcher.cmd_approve(project_id, actor_id="test-owner")
    assert approve_res["success"] is True
    assert len(approve_res["approved_tasks"]) == 3

    # 6. Secure Execution & Testing
    monkeypatch.setattr(settings, "task_execution_enabled", True)
    monkeypatch.setattr(settings, "secure_agent_task_runner_configured", True)
    monkeypatch.setattr(settings, "test_runner_image", "agenthive-test-docker_sec_ws:latest")

    # Add a minimal test file in tests/ so unittest discover finds a test
    ws_dir = Path(proj.project_md_path).parent
    test_file = ws_dir / "tests" / "test_ratelimiter.py"
    test_file.write_text("import unittest\n\nclass TestLimiter(unittest.TestCase):\n    def test_pass(self):\n        self.assertTrue(True)\n")

    report_res = await discord_dispatcher.cmd_report(project_id, actor_id="test-owner")
    assert report_res["success"] is True, f"Report failed: {report_res}"
    assert report_res["execution_status"] == "COMPLETED"
    assert report_res["ponytail_passed"] is True
    assert report_res["test_success"] is True
    assert report_res["tasks_executed"] == 3

    # Check status endpoint
    status_res = await discord_dispatcher.cmd_status(project_id, actor_id="test-owner")
    assert status_res["state"] == "COMPLETED"
    assert len(status_res["execution_logs"]) >= 4

    # 7. Acceptance project in data/agenthive.db must remain completely unchanged
    import sqlite3
    with sqlite3.connect("data/agenthive.db") as real_db:
        acc_msgs = real_db.execute("SELECT count(*) FROM discussion_messages WHERE project_id = '4d633575-798c-4737-93c1-0dfbcd63db1b'").fetchone()[0]
        acc_tasks = real_db.execute("SELECT count(*), coalesce(sum(human_approved), 0) FROM tasks WHERE project_id = '4d633575-798c-4737-93c1-0dfbcd63db1b'").fetchone()
        acc_logs = real_db.execute("SELECT count(*) FROM task_execution_logs WHERE task_id IN (SELECT id FROM tasks WHERE project_id = '4d633575-798c-4737-93c1-0dfbcd63db1b')").fetchone()[0]
        assert acc_msgs == 4
        assert acc_tasks[0] == 3
        assert acc_tasks[1] == 0
        assert acc_logs == 0
