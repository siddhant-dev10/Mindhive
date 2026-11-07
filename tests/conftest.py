"""Shared isolated fixtures for AgentHive tests.

The default suite always uses a fresh temporary SQLite database, a temporary
workspace, explicit local protocol mode, and no Discord credentials. Tests
that call a real external CLI or Official Switch require separate opt-in.
"""

import os
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix=f"agenthive-pytest-{os.getpid()}-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_ROOT / 'agenthive-test.db'}"
os.environ["WORKSPACE_ROOT"] = str(_TEST_ROOT / "workspaces")
os.environ["SWITCH_MODE"] = "local"
os.environ["SWITCH_CORE_URL"] = "http://127.0.0.1:1"
os.environ["SWITCH_REGISTRATION_TOKEN"] = "isolated-test-switch-registration-token-only"
os.environ["SWITCH_API_KEY"] = ""
os.environ["DISCORD_BOT_TOKEN"] = ""
os.environ["DISCORD_OWNER_ID"] = "test-owner"
os.environ["AGENTHIVE_TASK_EXECUTION_ENABLED"] = "false"
os.environ["AGENTHIVE_TEST_RUNNER_IMAGE"] = ""
os.environ["AGENTHIVE_DASHBOARD_API_TOKEN"] = "isolated-test-dashboard-token-at-least-32-chars"
os.environ["AGENTHIVE_DASHBOARD_COOKIE_SECURE"] = "false"
os.environ["AGENTHIVE_DASHBOARD_ALLOWED_ORIGINS"] = "http://testserver,http://127.0.0.1:8000,http://localhost:8000"
os.environ["AGENTHIVE_RUN_OFFICIAL_SWITCH_TESTS"] = "false"
os.environ["AGENTHIVE_RUN_NATIVE_AGENT_TESTS"] = "false"

import pytest_asyncio
from uuid import uuid4

from agenthive.config import settings
from agenthive.engine.orchestrator import orchestrator
from agenthive.models.events import SwitchAgentRegistration
from agenthive.switch.client import SwitchAgentClient


@pytest_asyncio.fixture(autouse=True)
async def isolated_runtime_configuration(monkeypatch):
    """Force global orchestrator adapters into explicit local fallback mode."""
    for agent in orchestrator.agents:
        if hasattr(agent, "is_cli_available"):
            monkeypatch.setattr(agent, "is_cli_available", False)
    yield


@pytest_asyncio.fixture
async def official_switch_runtime():
    """Connect the orchestrator's real Switch clients for dispatcher tests.

    These tests call the Discord dispatcher directly, so FastAPI's application
    startup hook does not run for them. In official mode, discussion must fail
    closed unless all four Official Switch sessions are connected.
    """
    if settings.switch_mode.lower() != "official":
        yield
        return

    connected_agents = []
    run_id = uuid4().hex
    try:
        for agent in orchestrator.agents:
            test_registration = SwitchAgentRegistration(
                agent_id=f"test-{agent.agent_id}-{run_id}",
                name=f"test-{agent.agent_id}-{run_id}",
                role=agent.role,
                description=f"Isolated test connection for {agent.description}",
                capabilities=list(agent.capabilities),
            )
            client = SwitchAgentClient(
                settings.switch_core_url,
                test_registration,
                registration_token=settings.switch_registration_token or settings.switch_api_key,
                mode=settings.switch_mode,
            )
            agent.client = client
            await client.connect()
            if not client.is_official_switch or not client.is_connected:
                raise RuntimeError(f"Official Switch connection unavailable for {agent.name}")
            connected_agents.append(agent)
        yield
    finally:
        for agent in reversed(connected_agents):
            if agent.client:
                await agent.client.disconnect()
                agent.client = None
