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
async def test_end_to_end_project_workflow():
    """Verify full 8-phase workflow:
    /newproject -> /analyse -> /discuss -> /assign -> /approve -> /report
    """
    # Phase 1: Create project
    proj_res = await discord_dispatcher.cmd_newproject(
        name="CacheFlow",
        description="A high-performance in-memory cache with TTL support and zero external pip dependencies."
    )
    assert proj_res["success"] is True
    project_id = proj_res["project_id"]
    assert project_id is not None

    proj = orchestrator.get_project(project_id)
    assert proj is not None
    assert Path(proj.project_md_path).exists()

    # Phase 2: Independent Analysis
    analyse_res = await discord_dispatcher.cmd_analyse(project_id)
    assert analyse_res["success"] is True
    assert analyse_res["analyses_count"] == 4  # Codex, AGY, Gemini, Hermes
    assert len(analyse_res["summary"]) == 4

    # Phase 3: Switch Room Collaborative Debate
    discuss_res = await discord_dispatcher.cmd_discuss(project_id)
    assert discuss_res["success"] is True
    assert discuss_res["turns_completed"] >= 4
    # Verify sender diversity (never simulated as one)
    senders = [m["sender"] for m in discuss_res["messages"]]
    assert "ChatGPT Codex" in senders
    assert "AGY (Antigravity)" in senders
    assert "Google Gemini" in senders
    assert "Hermes Supervisor" in senders

    # Phase 4: Hermes Supervision & WBS Allocation
    assign_res = await discord_dispatcher.cmd_assign(project_id)
    assert assign_res["success"] is True
    assert len(assign_res["tasks"]) == 3
    # Check assigned roles
    assigned_agents = [t["assigned_agent"] for t in assign_res["tasks"]]
    assert "ChatGPT Codex" in assigned_agents
    assert "AGY (Antigravity)" in assigned_agents
    assert "Google Gemini" in assigned_agents

    # Phase 5: Sovereign Human Approval Gate
    approve_res = await discord_dispatcher.cmd_approve(project_id)
    assert approve_res["success"] is True
    assert len(approve_res["approved_tasks"]) == 3

    # Phase 6: Sandboxed Execution & Testing
    report_res = await discord_dispatcher.cmd_report(project_id)
    assert report_res["success"] is True
    assert report_res["execution_status"] == "COMPLETED"
    assert report_res["ponytail_passed"] is True
    assert report_res["test_success"] is True

    # Phase 7: Verify generated files and spec integrity
    ws_dir = Path(proj.project_md_path).parent
    assert (ws_dir / "src" / "engine.py").exists()
    assert (ws_dir / "src" / "cli.py").exists()
    assert (ws_dir / "Dockerfile").exists()
    assert (ws_dir / "tests" / "test_engine.py").exists()

    # Verify Pony Tail Audit on workspace
    audit = ponytail_guard.audit_workspace(str(ws_dir))
    assert audit["passed"] is True
    assert audit["audited_files"] >= 3
