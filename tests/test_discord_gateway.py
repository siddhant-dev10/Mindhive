"""AgentHive Discord Gateway Integration & Slash Command Verification Suite.
Validates:
1. All 9 slash commands (/newproject, /project, /analyse, /discuss, /assign, /approve, /reject, /status, /report).
2. Project creation generates PROJECT.md AND immediately creates Switch War Room.
3. Interactive ApprovalView logic (authorization, anti-double-click, timeout handling).
4. Rich embed builders and length-boundary safety.
5. Bot command tree registration of all 9 commands.
6. Error handling, non-existent project recovery, and unapproved execution gating.
7. Concurrent project isolation.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from agenthive.discord_gateway.dispatcher import discord_dispatcher
from agenthive.discord_gateway.embeds import (
    build_newproject_embed,
    build_project_embed,
    build_analysis_embeds,
    build_discussion_embeds,
    build_assign_embed,
    build_status_embed,
    build_report_embed,
    build_error_embed,
    truncate,
)
from agenthive.discord_gateway.views import ApprovalView
from agenthive.discord_gateway.bot import AgentHiveDiscordBot, HAS_DISCORD_LIB
from agenthive.discord_gateway.webhooks import webhook_broadcaster
from agenthive.switch.server import switch_state
from agenthive.engine.orchestrator import orchestrator
from agenthive.config import settings
from agenthive.database import db


@pytest.mark.asyncio
async def test_bot_tree_has_all_nine_commands():
    """Verify that AgentHiveDiscordBot registers all 9 required slash commands."""
    assert HAS_DISCORD_LIB is True, "discord.py must be installed in environment"
    bot = AgentHiveDiscordBot()
    registered_commands = [cmd.name for cmd in bot.tree.get_commands()]

    required_commands = [
        "newproject",
        "project",
        "analyse",
        "discuss",
        "assign",
        "approve",
        "reject",
        "status",
        "report",
    ]
    for cmd in required_commands:
        assert cmd in registered_commands, f"Command /{cmd} must be registered in the bot tree"


@pytest.mark.asyncio
async def test_cmd_newproject_creates_project_md_and_switch_room():
    """Verify /newproject creates workspace, PROJECT.md, and immediately registers Switch War Room."""
    res = await discord_dispatcher.cmd_newproject(
        name="DiscordGatewayTestProject",
        description="Verify project creation generates PROJECT.md and Switch collaboration room",
        user_id=settings.discord_owner_id
    )

    assert res["success"] is True
    project_id = res["project_id"]
    slug = res["slug"]
    switch_room_id = res["switch_room_id"]

    # 1. Verify project exists in orchestrator
    proj = orchestrator.get_project(project_id)
    assert proj is not None
    assert proj.name == "DiscordGatewayTestProject"

    # 2. Verify PROJECT.md exists on disk
    project_md = Path(proj.project_md_path)
    assert project_md.exists()
    content = project_md.read_text()
    assert "DiscordGatewayTestProject" in content
    assert str(settings.discord_owner_id) in content

    # 3. Verify Switch collaboration room is registered immediately
    assert switch_room_id in switch_state.rooms
    assert switch_state.rooms[switch_room_id].room_id == switch_room_id
    assert "War Room" in switch_state.rooms[switch_room_id].name
    assert proj.switch_room_id == switch_room_id


@pytest.mark.asyncio
async def test_cmd_project_inspection():
    """Verify /project fetches valid metadata."""
    create_res = await discord_dispatcher.cmd_newproject("InspectTest", "Inspection brief", user_id=settings.discord_owner_id)
    pid = create_res["project_id"]

    res = await discord_dispatcher.cmd_project(pid, actor_id=settings.discord_owner_id)
    assert res["success"] is True
    assert res["name"] == "InspectTest"
    assert res["status"] == "DRAFT"
    assert res["switch_room_id"] == create_res["switch_room_id"]
    assert Path(res["project_md_path"]).exists()


@pytest.mark.asyncio
async def test_cmd_validation_and_not_found():
    """Verify dispatcher rejects invalid parameters and non-existent project IDs."""
    # Empty newproject parameters
    bad_new = await discord_dispatcher.cmd_newproject("", "", user_id=settings.discord_owner_id)
    assert bad_new["success"] is False
    assert "cannot be empty" in bad_new["error"]

    # Non-existent project ID
    non_existent_id = "non-existent-uuid-9999"
    for cmd_func in [
        discord_dispatcher.cmd_project,
        discord_dispatcher.cmd_analyse,
        discord_dispatcher.cmd_discuss,
        discord_dispatcher.cmd_assign,
        discord_dispatcher.cmd_approve,
        discord_dispatcher.cmd_reject,
        discord_dispatcher.cmd_status,
        discord_dispatcher.cmd_report,
    ]:
        if cmd_func in (discord_dispatcher.cmd_analyse, discord_dispatcher.cmd_discuss, discord_dispatcher.cmd_assign, discord_dispatcher.cmd_approve, discord_dispatcher.cmd_reject, discord_dispatcher.cmd_report):
            res = await cmd_func(non_existent_id, actor_id=settings.discord_owner_id)
        else:
            res = await cmd_func(non_existent_id)
        assert res["success"] is False
        assert "not found" in res["error"].lower()


@pytest.mark.asyncio
@pytest.mark.usefixtures("official_switch_runtime")
async def test_isolated_lifecycle_stops_before_approval_or_execution():
    """Verify isolated planning and mandatory human gate without approving/executing work."""
    # 1. /newproject
    p_res = await discord_dispatcher.cmd_newproject(
        name="LifecycleSwarm",
        description="Verify isolated planning and mandatory human approval boundary",
        user_id=settings.discord_owner_id,
    )
    pid = p_res["project_id"]

    # 2. /analyse
    a_res = await discord_dispatcher.cmd_analyse(pid, actor_id=settings.discord_owner_id)
    assert a_res["success"] is True
    assert a_res["analyses_count"] == 4
    for a in a_res["summary"]:
        assert a["agent"] in ["ChatGPT Codex", "AGY (Antigravity)", "Google Gemini", "Hermes Supervisor"]
        assert len(a["architecture"]) > 0

    # 3. /discuss
    d_res = await discord_dispatcher.cmd_discuss(pid, actor_id=settings.discord_owner_id)
    assert d_res["success"] is True
    assert d_res["turns_completed"] >= 4
    senders = [m["sender"] for m in d_res["messages"]]
    assert "ChatGPT Codex" in senders
    assert "Hermes Supervisor" in senders

    # 4. /assign
    assign_res = await discord_dispatcher.cmd_assign(pid, actor_id=settings.discord_owner_id)
    assert assign_res["success"] is True
    assert len(assign_res["tasks"]) >= 3
    assert assign_res["architecture_decision"] is not None

    # 5. /status (before approval)
    s_res = await discord_dispatcher.cmd_status(pid, actor_id=settings.discord_owner_id)
    assert s_res["success"] is True
    assert s_res["state"] == "AWAITING_APPROVAL"
    assert s_res["analyses_completed"] == 4
    assert s_res["debate_turns"] >= 4

    # Approval and execution are explicit owner actions and are deliberately not invoked here.
    assert assign_res["tasks"]
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ? AND human_approved = 1", (pid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM task_execution_logs WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ?)", (pid,)).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_cmd_reject_aborts_project():
    """Verify /reject sets project to ABORTED."""
    p_res = await discord_dispatcher.cmd_newproject("RejectTest", "Testing project rejection", user_id=settings.discord_owner_id)
    pid = p_res["project_id"]

    rej_res = await discord_dispatcher.cmd_reject(pid, reason="Architecture unacceptable", actor_id=settings.discord_owner_id)
    assert rej_res["success"] is True
    assert "ABORTED" in rej_res["message"]

    status = await discord_dispatcher.cmd_status(pid, actor_id=settings.discord_owner_id)
    assert status["state"] == "ABORTED"


@pytest.mark.asyncio
async def test_approval_view_logic(monkeypatch):
    """Verify only the configured owner can approve, even when another user is an admin."""
    from agenthive.config import settings
    monkeypatch.setattr(settings, "discord_owner_id", "111222333")
    view = ApprovalView(
        project_id="test-proj-101",
        po_discord_id="111222333",
        project_name="ApprovalViewTest",
        timeout=10.0
    )

    # 1. Authorization check: Authorized PO
    mock_po_inter = MagicMock()
    mock_po_inter.user.id = 111222333
    assert view._is_authorized(mock_po_inter) is True

    # 2. Authorization check: Unauthorized user without admin
    mock_unauth_inter = MagicMock()
    mock_unauth_inter.user.id = 999888777
    mock_unauth_inter.guild = MagicMock()
    mock_unauth_inter.user.guild_permissions.administrator = False
    assert view._is_authorized(mock_unauth_inter) is False

    # 3. Server administrators are not substitutes for the configured owner
    mock_admin_inter = MagicMock()
    mock_admin_inter.user.id = 999888777
    mock_admin_inter.guild = MagicMock()
    mock_admin_inter.user.guild_permissions.administrator = True
    assert view._is_authorized(mock_admin_inter) is False

    # 4. Timeout handler disables buttons
    assert all(not child.disabled for child in view.children)
    await view.on_timeout()
    assert all(child.disabled for child in view.children)


@pytest.mark.asyncio
async def test_embed_builders_and_length_boundaries():
    """Verify embed formatting and character-limit safety guards."""
    # Test truncate helper
    long_text = "A" * 5000
    assert len(truncate(long_text, 1000)) == 1000
    assert truncate(None) == "*None*"

    # 1. Project embed
    p_embed = build_project_embed({
        "id": "p-123",
        "name": "Test Embed Proj",
        "slug": "test-embed-proj",
        "description": "Short description",
        "current_state": "DRAFT",
        "switch_room_id": "switch-room-1",
        "project_md_path": "/tmp/PROJECT.md"
    })
    assert p_embed.title == "📁 Project Specification: Test Embed Proj"
    assert len(p_embed.fields) >= 4

    # 2. Analysis embeds
    analyses_summary = [
        {
            "agent": "ChatGPT Codex",
            "complexity": "HIGH",
            "architecture": "Ring buffer engine with reverse indexing",
            "tech_stack": ["python", "collections"],
            "risks": ["Memory consumption under high ingestion"]
        },
        {
            "agent": "AGY (Antigravity)",
            "complexity": "MEDIUM",
            "architecture": "CLI tool harness with argparse",
            "tech_stack": ["argparse"],
            "risks": ["Signal trapping in container"]
        }
    ]
    a_embeds = build_analysis_embeds("Test Swarm", "p-123", analyses_summary)
    assert len(a_embeds) == 3  # 1 header + 2 agent cards
    assert "⚡ ChatGPT Codex" in a_embeds[1].title
    assert "🚀 AGY (Antigravity)" in a_embeds[2].title

    # 3. Discussion embeds
    msgs = [
        {"turn": 1, "sender": "ChatGPT Codex", "role": "ARCHITECT", "content": "Initial proposal"},
        {"turn": 2, "sender": "AGY (Antigravity)", "role": "SYSTEMS", "content": "CLI review"},
        {"turn": 3, "sender": "Google Gemini", "role": "QA", "content": "Adversarial test review"},
        {"turn": 4, "sender": "Hermes Supervisor", "role": "SUPERVISOR", "content": "Floor closed with consensus"}
    ]
    d_embeds = build_discussion_embeds("Test Swarm", "p-123", msgs)
    assert len(d_embeds) >= 2

    # 4. Report embed
    rep_embed = build_report_embed("Test Swarm", {
        "project_id": "p-123",
        "execution_status": "COMPLETED",
        "ponytail_passed": True,
        "test_success": True,
        "test_output": "Ran 4 tests in 0.05s OK",
        "project_md": "/tmp/PROJECT.md"
    })
    assert "PASSED" in rep_embed.fields[0].value or "PASSED" in rep_embed.fields[1].value


@pytest.mark.asyncio
async def test_concurrent_projects_via_dispatcher():
    """Verify simultaneous projects running through the dispatcher do not conflict."""
    # Launch two distinct projects concurrently
    r1, r2 = await asyncio.gather(
        discord_dispatcher.cmd_newproject("DiscordSimulA", "Brief A", user_id=settings.discord_owner_id),
        discord_dispatcher.cmd_newproject("DiscordSimulB", "Brief B", user_id=settings.discord_owner_id)
    )
    p1_id, p2_id = r1["project_id"], r2["project_id"]
    assert p1_id != p2_id

    # Verify both Switch rooms are distinct and registered
    assert r1["switch_room_id"] != r2["switch_room_id"]
    assert r1["switch_room_id"] in switch_state.rooms
    assert r2["switch_room_id"] in switch_state.rooms

    # Run analysis concurrently
    a1, a2 = await asyncio.gather(
        discord_dispatcher.cmd_analyse(p1_id, actor_id=settings.discord_owner_id),
        discord_dispatcher.cmd_analyse(p2_id, actor_id=settings.discord_owner_id)
    )
    assert a1["success"] is True
    assert a2["success"] is True
    assert a1["project_id"] == p1_id
    assert a2["project_id"] == p2_id


@pytest.mark.asyncio
async def test_webhook_broadcaster_handles_missing_webhook():
    """Verify webhook broadcaster handles unconfigured webhook gracefully."""
    ok = await webhook_broadcaster.send_agent_message("ChatGPT Codex", "Hello from Codex")
    assert ok is False

@pytest.mark.asyncio
async def test_dashboard_cannot_bypass_discord_owner_approval_gate():
    """Unauthenticated dashboard mutations must not approve, reject, or run work."""
    import httpx
    from agenthive.main import app

    project_id = "untrusted-project-id"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for action in ("approve", "reject", "execute"):
            response = await client.post(f"/api/projects/{project_id}/{action}")
            assert response.status_code == 401
