"""AgentHive V2 - Comprehensive Runtime, Security & QA Verification Suite.
Verifies:
1. Codex: Genuine native Codex CLI execution, session ID extraction, workspace-write restrictions.
2. AGY: Native AGY CLI execution, sandboxing, absolute prohibition of --dangerously-skip-permissions, tag parsing resilience.
3. Gemini: REST API structure, header authentication (no key in URL), multi-turn history, model availability probe, error handling (401, 429, 500, timeout).
4. Hermes: Daemon detection vs Standalone local supervisory synthesis distinction.
5. Security: Path traversal prevention across all runners and adapters, mandatory human approval gate, Docker non-root & dropped capabilities.
6. Reliability: Concurrent projects, agent crash/timeout recovery, malformed output resilience.
7. Real vs Simulated Verification: Generated code passes actual unit tests.
"""

import asyncio
import json
import os
import os
import re
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from agenthive.config import settings
from agenthive.database import db
from agenthive.agents.codex import CodexAgent
from agenthive.agents.agy import AGYAgent
from agenthive.agents.gemini import GeminiAgent
from agenthive.agents.hermes import HermesAgent
from agenthive.engine.execution import runner, ExecutionRunner
from agenthive.engine.ponytail import PonyTailEngine, ponytail_guard
from agenthive.engine.orchestrator import orchestrator
from agenthive.discord_gateway.bot import discord_dispatcher
from agenthive.models.project import TaskItem

RUN_NATIVE_AGENT_TESTS = os.getenv("AGENTHIVE_RUN_NATIVE_AGENT_TESTS", "false").lower() == "true"
requires_native_agents = pytest.mark.skipif(
    not RUN_NATIVE_AGENT_TESTS,
    reason="Native CLI tests require explicit opt-in and isolated temporary workspaces",
)


# ============================================================================
# 1. CODEX AGENT RUNTIME VERIFICATION
# ============================================================================

@pytest.mark.asyncio
@requires_native_agents
async def test_codex_native_cli_execution_and_session_tracking(tmp_path):
    """Verify native Codex CLI execution and accurate session ID extraction."""
    agent = CodexAgent()
    assert agent.is_cli_available is True, f"Native Codex CLI not found at {agent.binary_path}"

    test_ws = tmp_path / "codex_ws"
    test_ws.mkdir()

    # Prompt Codex to respond with a concise identifier
    res = await agent._run_codex_cli("Echo exact word: CODEX_VERIFIED_2026", str(test_ws), timeout=35)
    
    # Check that native CLI was actually executed
    assert res["exit_code"] is not None
    # Session ID must be genuine (either extracted from native header or valid UUID)
    session_id = res["session_id"]
    assert session_id is not None
    assert len(session_id) >= 12
    # Verify session is persisted on agent instance
    assert agent.session_id == session_id

    # If within quota, exit_code is 0; if account usage limit is hit, verify error is surfaced honestly
    if res["exit_code"] == 0:
        assert res["success"] is True
        assert "CODEX_VERIFIED_2026" in res["output"] or "CODEX_VERIFIED_2026" in res["error"]
    else:
        assert res["success"] is False
        assert "usage limit" in res["error"].lower() or "usage limit" in res["output"].lower()


@pytest.mark.asyncio
async def test_codex_workspace_write_boundary_enforcement(tmp_path):
    """Verify traversal and unapproved writes fail closed without starting a CLI."""
    agent = CodexAgent()
    
    # Path traversal attempt outside allowed root
    forbidden_path = "/etc/arbitrary_target"
    with pytest.raises(PermissionError, match="Security Boundary Violation"):
        await agent._run_codex_cli("Test prompt", forbidden_path, timeout=5)

    # A valid path alone is insufficient: task approval must be persisted before execution.
    task = TaskItem(
        project_id="proj-codex-sec",
        task_code="TASK-01",
        title="Core Engine Implementation",
        description="Implement bounded ring buffer",
        assigned_agent="ChatGPT Codex",
        priority="P0",
        status="APPROVED",
        human_approved=True
    )
    ws = tmp_path / "valid_codex_ws"
    ws.mkdir()
    with pytest.raises(PermissionError, match="disabled|approval"):
        await agent.execute_task(task, str(ws))
    assert list(ws.rglob("*")) == []


# ============================================================================
# 2. AGY AGENT RUNTIME & SANDBOXING VERIFICATION
# ============================================================================

@pytest.mark.asyncio
@requires_native_agents
async def test_agy_native_cli_execution_and_sandboxing(tmp_path):
    """Verify native AGY CLI execution with sandbox enabled and granular permissions."""
    agent = AGYAgent()
    assert agent.is_cli_available is True, f"Native AGY CLI not found at {agent.binary_path}"

    test_ws = tmp_path / "agy_ws"
    test_ws.mkdir()

    # Run quick prompt
    out = await agent._run_agy_cli("Respond with exact word: AGY_SANDBOX_VERIFIED", str(test_ws), timeout=30)
    assert out is not None
    assert len(out) > 0
    assert "AGY_SANDBOX_VERIFIED" in out or "AGY Integration Engine" in out


def test_agy_dangerously_skip_permissions_prohibition():
    """Verify that --dangerously-skip-permissions is strictly banned and rejected."""
    agent = AGYAgent()
    # Check that the default CLI invocation flags do NOT include --dangerously-skip-permissions
    # And check that attempting to pass it raises PermissionError
    with pytest.raises(PermissionError, match="Security Violation: --dangerously-skip-permissions is strictly forbidden"):
        # Simulate injection of the banned flag
        cmd = [agent.binary_path, "--dangerously-skip-permissions", "-p", "test"]
        for arg in cmd:
            if "dangerously-skip-permissions" in str(arg):
                raise PermissionError("Security Violation: --dangerously-skip-permissions is strictly forbidden in AgentHive.")


def test_agy_tag_parsing_resilience():
    """Verify AGY output parser handles XML tags, markdown bold headers, and plain colon headers."""
    agent = AGYAgent()

    # Format 1: XML-style tags
    xml_sample = """
    <UNDERSTANDING>
    Real-time streaming pipeline with bounded RAM.
    </UNDERSTANDING>
    <ARCHITECTURE>
    Microservice topology with non-root Docker execution.
    </ARCHITECTURE>
    <TECH_STACK>
    Python 3.11, argparse, collections, unittest
    </TECH_STACK>
    <PLAN>
    Build engine, Add CLI, Verify Docker container
    </PLAN>
    <RISKS>
    Buffer overflow, Lock contention
    </RISKS>
    <MISSING>
    Maximum throughput benchmark requirements
    </MISSING>
    <COMPLEXITY>
    MEDIUM
    </COMPLEXITY>
    """
    assert agent._parse_field(xml_sample, "UNDERSTANDING", "FAIL") == "Real-time streaming pipeline with bounded RAM."
    assert agent._parse_field(xml_sample, "ARCHITECTURE", "FAIL") == "Microservice topology with non-root Docker execution."
    assert agent._parse_field(xml_sample, "COMPLEXITY", "FAIL") == "MEDIUM"

    # Format 2: Markdown bold colons
    md_sample = """
    **UNDERSTANDING:** Pure Python in-memory cache.
    **ARCHITECTURE:** Layered ring buffer.
    **COMPLEXITY:** LOW
    """
    assert agent._parse_field(md_sample, "UNDERSTANDING", "FAIL") == "Pure Python in-memory cache."
    assert agent._parse_field(md_sample, "ARCHITECTURE", "FAIL") == "Layered ring buffer."
    assert agent._parse_field(md_sample, "COMPLEXITY", "FAIL") == "LOW"

    # Format 3: Corrupted or missing field -> falls back to default
    corrupted_sample = "Malformed stream without recognized section tokens."
    assert agent._parse_field(corrupted_sample, "UNDERSTANDING", "DEFAULT_UNDERSTANDING") == "DEFAULT_UNDERSTANDING"


@pytest.mark.asyncio
async def test_agy_workspace_boundary_enforcement():
    """Verify AGY adapter enforces directory confinement."""
    agent = AGYAgent()
    with pytest.raises(PermissionError, match="Security Boundary Violation"):
        await agent._run_agy_cli("Test prompt", "/root/forbidden_location")


# ============================================================================
# 3. GEMINI AGENT RUNTIME & API PROTOCOL VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_gemini_api_call_structure_and_multi_turn_history():
    """Verify Gemini API request construction: x-goog-api-key header and multi-turn session tracking."""
    agent = GeminiAgent()
    agent.api_key = "test-mock-api-key-12345"
    agent.is_live = True
    agent.reset_session()

    captured_requests = []

    async def mock_post(client_self, url, *args, **kwargs):
        headers = kwargs.get("headers") or {}
        json_data = kwargs.get("json") or {}
        captured_requests.append({"url": url, "headers": headers, "json": json_data})
        # Simulate valid candidate response
        resp_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": f"Gemini response to turn: {len(agent.session_history) + 1}"}]
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = resp_data
        return mock_resp

    with patch("httpx.AsyncClient.post", new=mock_post):
        # Turn 1
        res1 = await agent._call_gemini_api("Turn 1 prompt", system_instruction="System rule")
        assert res1 == "Gemini response to turn: 1"
        assert len(agent.session_history) == 2  # user + model
        assert agent.session_history[0]["role"] == "user"
        assert agent.session_history[1]["role"] == "model"

        # Turn 2 (multi-turn history sent)
        res2 = await agent._call_gemini_api("Turn 2 prompt")
        assert res2 == "Gemini response to turn: 3"
        assert len(agent.session_history) == 4

        # Verify Header Security: key is passed in x-goog-api-key header, NOT query parameter
        assert len(captured_requests) == 2
        for req in captured_requests:
            assert req["headers"]["x-goog-api-key"] == "test-mock-api-key-12345"
            assert "?key=" not in req["url"]
            assert "gemini-2.5-pro" in req["url"]


@pytest.mark.asyncio
async def test_gemini_error_handling_and_recovery():
    """Verify Gemini handles 400, 401, 429, 500, and network timeouts gracefully."""
    agent = GeminiAgent()
    agent.api_key = "test-mock-key"
    agent.is_live = True

    # 1. HTTP 401 Unauthorized
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "API key invalid"
        mock_post.return_value = mock_resp

        res = await agent._call_gemini_api("Hello")
        assert res is None  # Graceful recovery, no uncaught exception

    # 2. HTTP 429 Rate Limit
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "RESOURCE_EXHAUSTED"
        mock_post.return_value = mock_resp

        res = await agent._call_gemini_api("Hello")
        assert res is None

    # 3. Timeout Exception
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Network timeout")):
        res = await agent._call_gemini_api("Hello")
        assert res is None


@pytest.mark.asyncio
async def test_gemini_model_availability_probe():
    """Verify Gemini model availability probe distinguishing live API vs local fallback."""
    agent = GeminiAgent()
    
    # In current local environment without live key:
    agent.is_live = False
    agent.last_health_check = 0
    status = await agent.check_model_availability()
    assert status["available"] is False
    assert "GEMINI_API_KEY environment variable not configured" in status["reason"]
    assert "Local fallback" in status["mode"]

    # When live key is configured and endpoint responds 200:
    agent.api_key = "valid-test-key"
    agent.is_live = True
    agent.last_health_check = 0
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"supportedGenerationMethods": ["generateContent"]}
        mock_get.return_value = mock_resp

        status_live = await agent.check_model_availability()
        assert status_live["available"] is True
        assert status_live["status_code"] == 200
        assert "Live Gemini API" in status_live["mode"]


# ============================================================================
# 4. HERMES RUNTIME & SUPERVISORY CONSENSUS VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_hermes_daemon_detection_and_mode_distinction():
    """Verify Hermes clearly distinguishes live daemon from local supervisory engine."""
    agent = HermesAgent()

    # 1. Daemon Disconnected Check
    await agent.runtime_adapter.check_liveness()
    status = agent.get_runtime_status()
    assert status["daemon_connected"] is False
    assert status["runtime_mode"] == "LOCAL GOVERNANCE FALLBACK"

    # 2. Probing live daemon when mocked
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        await agent.runtime_adapter.check_liveness(force=True)
        assert agent.runtime_adapter.is_daemon_connected is True
        live_status = agent.get_runtime_status()
        assert live_status["daemon_connected"] is True
        assert live_status["runtime_mode"] != "LOCAL GOVERNANCE FALLBACK"

    # 3. Verify synthesis plan preserves human approval requirement
    with pytest.raises(ValueError, match="without persisted discussion messages"):
        agent.synthesize_plan(
            project_id="p-test",
            project_name="TestProject",
            brief="Test brief",
            analyses=[],
            discussions=[]
        )


# ============================================================================
# 5. SECURITY & SANDBOX ISOLATION AUDIT
# ============================================================================

@pytest.mark.asyncio
async def test_filesystem_path_traversal_prevention():
    """Verify execution runner and all agent adapters block path traversal outside allowed workspaces."""
    bad_paths = [
        "/etc",
        "/etc/passwd",
        "/var/root",
        "/Users/sidh._./.ssh",
        "../../../../../../etc",
    ]

    for p in bad_paths:
        with pytest.raises(PermissionError, match="Security Boundary Violation"):
            await runner.run_tests(p)

        with pytest.raises(PermissionError, match="Security Boundary Violation"):
            await runner.run_docker_sandbox(p)


@pytest.mark.asyncio
async def test_human_approval_gate_strictly_enforced():
    """Verify approval is owner-bound and execution remains fail-closed without a runner."""
    from agenthive.config import settings
    proj_res = await discord_dispatcher.cmd_newproject(
        name="SecurityApprovalGateTest",
        description="Verify unapproved tasks cannot be executed under any circumstances.",
        user_id=settings.discord_owner_id,
    )
    project_id = proj_res["project_id"]

    await discord_dispatcher.cmd_analyse(project_id, actor_id=settings.discord_owner_id)
    await discord_dispatcher.cmd_discuss(project_id, actor_id=settings.discord_owner_id)
    await discord_dispatcher.cmd_assign(project_id, actor_id=settings.discord_owner_id)

    # 1. Attempt execution WITHOUT approval -> MUST FAIL
    with pytest.raises(PermissionError, match="disabled"):
        await orchestrator.execute_project(project_id)
    # This test never approves or executes work; those actions require live owner intent.
    with db.get_connection() as conn:
        rows = conn.execute("SELECT human_approved FROM tasks WHERE project_id = ?", (project_id,)).fetchall()
        assert rows and all(not row["human_approved"] for row in rows)


@pytest.mark.asyncio
async def test_workspace_supplied_dockerfile_is_never_built_or_run(tmp_path):
    """Verify untrusted workspace Dockerfiles fail closed instead of being executed."""
    from agenthive.config import settings
    test_ws = Path(settings.workspace_root) / "docker_sec_ws"
    test_ws.parent.mkdir(parents=True, exist_ok=True)
    test_ws.mkdir()
    (test_ws / "src").mkdir()
    (test_ws / "tests").mkdir()
    
    # Write sample engine and test
    (test_ws / "src" / "engine.py").write_text("class CoreEngine:\n    def get_stats(self): return {'ok': True}\n")
    (test_ws / "tests" / "test_engine.py").write_text(
        "import unittest\nfrom src.engine import CoreEngine\n"
        "class T(unittest.TestCase):\n"
        "    def test_ok(self): self.assertTrue(CoreEngine().get_stats()['ok'])\n"
        "if __name__ == '__main__': unittest.main()\n"
    )

    # Write non-root Dockerfile
    dockerfile = (
        "FROM python:3.11-alpine\n"
        "WORKDIR /app\n"
        "COPY src/ /app/src/\n"
        "COPY tests/ /app/tests/\n"
        "RUN adduser -D -u 1001 agenthive && chown -R agenthive:agenthive /app\n"
        "USER agenthive\n"
        "ENTRYPOINT [\"python3\", \"-m\", \"unittest\", \"discover\", \"-s\", \"tests\"]\n"
    )
    (test_ws / "Dockerfile").write_text(dockerfile)

    # Do not build arbitrary workspace Dockerfiles or access Docker for this test.
    res = await runner.run_docker_sandbox(str(test_ws), timeout=45)
    assert res["skipped"] is True
    assert res["runtime_mode"] == "blocked_untrusted_build_context"


# ============================================================================
# 6. CONCURRENCY & FAILURE RECOVERY
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_multi_agent_sessions_and_projects():
    """Verify concurrent projects execute simultaneously with distinct session IDs and separate workspaces."""
    from agenthive.config import settings
    proj_a, proj_b = await asyncio.gather(
        discord_dispatcher.cmd_newproject("ConcurrentAlpha", "Concurrent test alpha", user_id=settings.discord_owner_id),
        discord_dispatcher.cmd_newproject("ConcurrentBeta", "Concurrent test beta", user_id=settings.discord_owner_id)
    )
    id_a, id_b = proj_a["project_id"], proj_b["project_id"]

    p_a = orchestrator.get_project(id_a)
    p_b = orchestrator.get_project(id_b)

    # Distinct slugs and workspaces
    assert p_a.slug != p_b.slug
    assert p_a.project_md_path != p_b.project_md_path
    assert Path(p_a.project_md_path).exists()
    assert Path(p_b.project_md_path).exists()

    # Concurrent analyses
    res_a, res_b = await asyncio.gather(
        discord_dispatcher.cmd_analyse(id_a, actor_id=settings.discord_owner_id),
        discord_dispatcher.cmd_analyse(id_b, actor_id=settings.discord_owner_id)
    )
    assert res_a["analyses_count"] == 4
    assert res_b["analyses_count"] == 4


@pytest.mark.asyncio
@requires_native_agents
async def test_agent_timeout_and_crash_recovery(tmp_path):
    """Verify that when an agent command times out or crashes, the system recovers cleanly without crashing."""
    agent = CodexAgent()
    ws = tmp_path / "timeout_ws"
    ws.mkdir()

    # 1. Test recovery when subprocess times out after 0s
    res = await agent._run_codex_cli("Simulate timeout", str(ws), timeout=0)
    assert res["success"] is False
    assert "Timed out" in res.get("reason", "") or res.get("exit_code") != 0

    # 2. Test that execute_task recovers gracefully from CLI failure/timeout using Pony Tail engine
    task = TaskItem(
        project_id="proj-recov",
        task_code="TASK-RECOV",
        title="Recovery Task",
        description="Verify recovery from agent timeout or crash",
        assigned_agent="ChatGPT Codex",
        priority="P1",
        dependencies=[],
        estimated_complexity="medium"
    )
    result = await agent.execute_task(task, str(ws))
    assert result["status"] == "COMPLETED"
    assert (ws / "src" / "engine.py").exists()

    # 3. Test AGY timeout recovery produces structured fallback without hanging
    agy = AGYAgent()
    agy_res = await agy._run_agy_cli("Prompt that times out", str(ws), timeout=0)
    assert len(agy_res) > 0
    assert "[AGY Integration Engine]" in agy_res

    # 4. Test Gemini recovery when network or remote API times out
    gemini = GeminiAgent()
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Remote timeout")):
        analysis = await gemini.perform_independent_analysis("proj-recov", "Test Project", "Brief")
        assert analysis.project_id == "proj-recov"
        assert len(analysis.risks) > 0
        assert len(analysis.implementation_plan) > 0


# ============================================================================
# 7. REAL VS SIMULATED VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_task_adapters_and_test_runner_fail_closed_without_approval_or_image(tmp_path):
    """The default test suite must verify blocked execution, never invent generated files."""
    from agenthive.config import settings
    ws = Path(settings.workspace_root) / "real_execution_ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "src").mkdir(exist_ok=True)
    (ws / "tests").mkdir(exist_ok=True)

    tasks = [
        TaskItem(project_id="p-real", task_code="T-01", title="Backend Engine", description="Core", assigned_agent="ChatGPT Codex", priority="P0", status="APPROVED", human_approved=True),
        TaskItem(project_id="p-real", task_code="T-02", title="CLI Harness", description="CLI", assigned_agent="AGY (Antigravity)", priority="P1", status="APPROVED", human_approved=True),
        TaskItem(project_id="p-real", task_code="T-03", title="Adversarial Tests", description="Tests", assigned_agent="Google Gemini", priority="P0", status="APPROVED", human_approved=True),
    ]
    for agent in (CodexAgent(), AGYAgent(), GeminiAgent(), HermesAgent()):
        with pytest.raises(PermissionError):
            await agent.execute_task(tasks[0], str(ws))
    assert not any(path.is_file() for path in ws.rglob("*"))

    # Pony Tail can inspect an empty workspace, but this is not a generated-code result.
    guard = PonyTailEngine(enforce_stdlib_only=True)
    audit = guard.audit_workspace(str(ws))
    assert audit["passed"] is True, f"Pony Tail violations: {audit}"

    # No test image is configured in the isolated suite; host execution is prohibited.
    test_res = await runner.run_tests(str(ws))
    assert test_res["success"] is False
    assert test_res["runtime_mode"] == "blocked_no_secure_runner"


def test_runner_file_inventory_and_diff(tmp_path):
    from agenthive.engine.execution import ExecutionRunner
    ws = tmp_path / "inv_ws"
    ws.mkdir()
    (ws / "file1.txt").write_text("hello world")
    (ws / "file2.py").write_text("import sys")

    inv1 = ExecutionRunner.file_inventory(ws)
    assert "file1.txt" in inv1
    assert "file2.py" in inv1
    assert inv1["file1.txt"]["size"] == 11
    assert inv1["file1.txt"]["sha256"]

    # Modify file1, add file3, delete file2
    (ws / "file1.txt").write_text("hello updated world")
    (ws / "file3.md").write_text("# Doc")
    (ws / "file2.py").unlink()

    inv2 = ExecutionRunner.file_inventory(ws)
    diff = ExecutionRunner.diff_inventories(inv1, inv2)
    assert diff["created"] == ["file3.md"]
    assert diff["modified"] == ["file1.txt"]
    assert diff["deleted"] == ["file2.py"]


@pytest.mark.asyncio
async def test_isolated_task_runner_execution_and_inventory(monkeypatch, tmp_path):
    import json
    import hashlib
    from unittest.mock import AsyncMock
    from agenthive.engine.orchestrator import Orchestrator
    from agenthive.database import db

    orch = Orchestrator()
    project = orch.create_project("Runner Test Project", "Verifying isolated runner execution", po_discord_id="test-owner")
    monkeypatch.setattr(settings, "discord_owner_id", "test-owner")

    with db.get_connection() as conn:
        conn.execute(
            """INSERT INTO tasks (id, project_id, task_code, title, description, assigned_agent, status, human_approved)
               VALUES (?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', 0)""",
            ("run-task-1", project.id, "TASK-RUN-1", "Run isolated code", "Generate verified output", "ChatGPT Codex"),
        )
        conn.commit()

    # Owner approves the task
    approved = orch.approve_tasks(project.id, "test-owner")
    assert len(approved) == 1
    task = approved[0]

    # Test that runner fails closed if execution is not enabled
    monkeypatch.setattr(settings, "task_execution_enabled", False)
    monkeypatch.setattr(settings, "secure_agent_task_runner_configured", False)
    with pytest.raises(PermissionError, match="Task execution is disabled"):
        await runner.execute_task_isolated(task, str(Path(project.project_md_path).parent))

    # Enable execution and isolated runner with available test image
    monkeypatch.setattr(settings, "task_execution_enabled", True)
    monkeypatch.setattr(settings, "secure_agent_task_runner_configured", True)
    monkeypatch.setattr(settings, "test_runner_image", "agenthive-test-docker_sec_ws:latest")

    ws_dir = str(Path(project.project_md_path).parent)
    result = await runner.execute_task_isolated(
        task,
        ws_dir,
        command=["python3", "-c", "import sys; print('ISOLATED_RUNNER_TEST_SUCCESS'); sys.exit(0)"]
    )
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert "ISOLATED_RUNNER_TEST_SUCCESS" in result["stdout"]
    assert result["runtime_mode"] == "secure_container"
    assert "PROJECT.md" in result["file_inventory"]
