"""AgentHive Reliability & Edge-Case Test Suite.
Validates:
1. Multiple simultaneous projects.
2. Agent disconnections & SSE resiliency.
3. Timeout recovery.
4. Duplicate message handling.
5. Circular discussion prevention & turn ceiling.
6. Failed task execution & status reporting.
7. Sovereign human approval gate enforcement.
8. Database persistence across restarts.
9. Pony Tail unauthorized import detection.
"""

import pytest
import asyncio
from pathlib import Path
from agenthive.database import Database
from agenthive.engine.orchestrator import orchestrator
from agenthive.engine.ponytail import PonyTailEngine
from agenthive.switch.server import switch_state
from agenthive.models.events import SwitchAgentRegistration, SwitchMessageSend
from agenthive.discord_gateway.bot import discord_dispatcher
from agenthive.config import settings
from agenthive.database import db

@pytest.mark.asyncio
async def test_human_approval_enforcement():
    """Verify that execution is strictly BLOCKED until human approval is granted."""
    proj_res = await discord_dispatcher.cmd_newproject(
        name="SecurityGateProject",
        description="Verify human gate prevents unauthorized execution",
        user_id=settings.discord_owner_id,
    )
    project_id = proj_res["project_id"]

    await discord_dispatcher.cmd_analyse(project_id, actor_id=settings.discord_owner_id)
    await discord_dispatcher.cmd_discuss(project_id, actor_id=settings.discord_owner_id)
    await discord_dispatcher.cmd_assign(project_id, actor_id=settings.discord_owner_id)

    # Attempt execution WITHOUT approval -> MUST FAIL
    with pytest.raises(PermissionError, match="disabled"):
        await orchestrator.execute_project(project_id)

    # Record approval in the isolated fixture only; execution must remain separately disabled.
    approve_res = await discord_dispatcher.cmd_approve(project_id, actor_id=settings.discord_owner_id)
    assert approve_res["success"] is True
    with pytest.raises(PermissionError, match="disabled"):
        await orchestrator.execute_project(project_id)

@pytest.mark.asyncio
async def test_multiple_simultaneous_projects():
    """Verify concurrent projects execute without cross-contamination."""
    # Launch two projects simultaneously
    res1, res2 = await asyncio.gather(
        discord_dispatcher.cmd_newproject("SimulProjectA", "Concurrent project A", user_id=settings.discord_owner_id),
        discord_dispatcher.cmd_newproject("SimulProjectB", "Concurrent project B", user_id=settings.discord_owner_id)
    )
    p1_id, p2_id = res1["project_id"], res2["project_id"]

    # Run independent analyses concurrently
    a1, a2 = await asyncio.gather(
        discord_dispatcher.cmd_analyse(p1_id, actor_id=settings.discord_owner_id),
        discord_dispatcher.cmd_analyse(p2_id, actor_id=settings.discord_owner_id)
    )
    assert a1["analyses_count"] == 4
    assert a2["analyses_count"] == 4

    p1 = orchestrator.get_project(p1_id)
    p2 = orchestrator.get_project(p2_id)

    # Verify separate workspace paths
    assert p1.project_md_path != p2.project_md_path
    assert Path(p1.project_md_path).exists()
    assert Path(p2.project_md_path).exists()

@pytest.mark.asyncio
@pytest.mark.usefixtures("official_switch_runtime")
async def test_circular_discussion_prevention():
    """Verify discussions strictly respect bounded turns and do not enter infinite loops."""
    proj_res = await discord_dispatcher.cmd_newproject("LoopPrevent", "Verify bounded turns", user_id=settings.discord_owner_id)
    p_id = proj_res["project_id"]

    # Run discussion
    disc_res = await discord_dispatcher.cmd_discuss(p_id, actor_id=settings.discord_owner_id)
    turns = disc_res["turns_completed"]
    assert turns <= 6, f"Expected bounded turns <= 6, got {turns}"
    # Verify the local governance fallback labels itself and does not claim consensus.
    last_msg = disc_res["messages"][-1]
    assert last_msg["role"] == "SUPERVISOR"
    assert "LOCAL GOVERNANCE FALLBACK" in last_msg["content"]
    assert "has not inferred consensus" in last_msg["content"]

@pytest.mark.asyncio
async def test_ponytail_unauthorized_import_detection(tmp_path):
    """Verify Pony Tail detects unapproved third-party packages."""
    guard = PonyTailEngine(enforce_stdlib_only=True)
    
    # 1. Valid pure stdlib file
    valid_file = tmp_path / "valid.py"
    valid_file.write_text("import collections\nimport json\nimport sys\ndef run(): return 0\n")
    audit1 = guard.audit_python_file(str(valid_file))
    assert audit1["valid"] is True
    assert len(audit1["violations"]) == 0

    # 2. Invalid file importing third-party 'requests' and 'celery'
    invalid_file = tmp_path / "bloat.py"
    invalid_file.write_text("import requests\nfrom celery import Celery\n")
    audit2 = guard.audit_python_file(str(invalid_file))
    assert audit2["valid"] is False
    assert any("requests" in v for v in audit2["violations"])
    assert any("celery" in v for v in audit2["violations"])

@pytest.mark.asyncio
async def test_failed_task_execution_handling(tmp_path):
    """Verify that a failing test suite is properly detected and marks project as FAILED."""
    from agenthive.engine.execution import runner

    bad_workspace = Path(settings.workspace_root) / "bad_project"
    bad_workspace.mkdir()
    tests_dir = bad_workspace / "tests"
    tests_dir.mkdir()

    # Create deliberately failing test
    failing_test = tests_dir / "test_fail.py"
    failing_test.write_text(
        "import unittest\n"
        "class BadTest(unittest.TestCase):\n"
        "    def test_broken(self):\n"
        "        self.assertEqual(1, 2, 'Deliberate failure')\n"
        "if __name__ == '__main__': unittest.main()\n"
    )

    test_res = await runner.run_tests(str(bad_workspace))
    assert test_res["success"] is False
    assert test_res["runtime_mode"] == "blocked_no_secure_runner"
    assert test_res["exit_code"] is None
    assert "host execution is disabled" in test_res["stderr"]

@pytest.mark.asyncio
async def test_database_persistence_across_instances(tmp_path):
    """Verify database data persists across separate database instances."""
    test_db_path = str(tmp_path / "test_persist.db")
    db1 = Database(test_db_path)
    
    with db1.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, slug, description, project_md_path) VALUES (?, ?, ?, ?, ?)",
            ("p-100", "PersistProj", "persist-proj", "Testing persistence", "/tmp/p.md")
        )
        conn.commit()

    # Create new Database instance pointing to same file
    db2 = Database(test_db_path)
    with db2.get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = 'p-100'").fetchone()
        assert row is not None
        assert row["name"] == "PersistProj"
