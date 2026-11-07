"""Official Switch Collaboration Infrastructure Integration Test Suite.

Validates genuine integration against the live official Switch Core container:
(ghcr.io/sandbox-quantum/switch-core / https://docs.switchagents.ai/)

Distinction:
- Mocked tests: None in this file (no mock responses permitted).
- Local fallback tests: tests/test_switch_protocol.py
- Official Switch live integration tests: This test suite (tests/test_switch_official.py)
"""

import pytest
import asyncio
import httpx
import os
from typing import Dict, Any, List
from agenthive.models.events import SwitchAgentRegistration
from agenthive.switch.client import SwitchAgentClient

RUN_ISOLATED_SWITCH_TESTS = (
    os.getenv("AGENTHIVE_RUN_OFFICIAL_SWITCH_TESTS", "false").lower() == "true"
    and os.getenv("AGENTHIVE_TEST_SWITCH_ISOLATED", "false").lower() == "true"
)
OFFICIAL_SWITCH_URL = os.getenv("AGENTHIVE_TEST_SWITCH_URL", "").rstrip("/")
REGISTRATION_TOKEN = os.getenv("AGENTHIVE_TEST_SWITCH_REGISTRATION_TOKEN")


def is_official_switch_running() -> bool:
    """Probes the live official Switch Core readiness endpoint."""
    if not RUN_ISOLATED_SWITCH_TESTS or not OFFICIAL_SWITCH_URL or not REGISTRATION_TOKEN:
        return False
    try:
        resp = httpx.get(f"{OFFICIAL_SWITCH_URL}/health/ready", timeout=2.0)
        return resp.status_code == 200 and resp.json().get("status") == "ready"
    except Exception:
        return False


skip_if_no_switch = pytest.mark.skipif(
    not RUN_ISOLATED_SWITCH_TESTS or not is_official_switch_running(),
    reason="Opt in with an explicitly isolated Official Switch test stack and dedicated test credential",
)


@pytest.mark.asyncio
@skip_if_no_switch
async def test_official_switch_readiness_and_subsystems():
    """Verify official Switch Core health and subsystem state (database, signal_bus, bridges)."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{OFFICIAL_SWITCH_URL}/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        checks = data.get("checks", {})
        assert checks.get("database", {}).get("healthy") is True
        assert checks.get("signal_bus", {}).get("healthy") is True
        assert checks.get("bridges", {}).get("healthy") is True
        assert checks.get("message_listener", {}).get("healthy") is True


@pytest.mark.asyncio
@skip_if_no_switch
async def test_official_switch_agent_registration_quad():
    """Verify registering all four AgentHive agents directly with Official Switch Core."""
    agents = [
        SwitchAgentRegistration(
            agent_id="agenthive-codex-test",
            name="agenthive-codex",
            role="Chief Architect",
            description="OpenAI Codex Engine",
            capabilities=["architecture", "implementation"],
        ),
        SwitchAgentRegistration(
            agent_id="agenthive-agy-test",
            name="agenthive-agy",
            role="Systems Integrator",
            description="Antigravity Native CLI Engine",
            capabilities=["cli_automation", "docker_sandboxing"],
        ),
        SwitchAgentRegistration(
            agent_id="agenthive-gemini-test",
            name="agenthive-gemini",
            role="QA Strategist",
            description="Google Gemini Reasoning Engine",
            capabilities=["deep_reasoning", "adversarial_testing"],
        ),
        SwitchAgentRegistration(
            agent_id="agenthive-hermes-test",
            name="agenthive-hermes",
            role="Autonomous Supervisor",
            description="Nous Research Hermes Supervision",
            capabilities=["consensus_synthesis", "wbs_allocation"],
        ),
    ]

    clients = []
    try:
        for ag in agents:
            client = SwitchAgentClient(
                base_url=OFFICIAL_SWITCH_URL,
                agent_registration=ag,
                registration_token=REGISTRATION_TOKEN,
                mode="official",
            )
            await client.connect()
            assert client.is_connected is True
            assert client.is_official_switch is True
            assert client.official_agent_id is not None
            assert client.api_key is not None
            clients.append(client)
    finally:
        for c in clients:
            await c.disconnect()


@pytest.mark.asyncio
@skip_if_no_switch
async def test_official_switch_room_creation_and_membership():
    """Verify shared collaborative room creation and multi-agent membership in Official Switch."""
    codex_reg = SwitchAgentRegistration(
        agent_id="agenthive-codex-room",
        name="agenthive-codex",
        role="Chief Architect",
        description="OpenAI Codex Engine",
        capabilities=["architecture"],
    )
    client_codex = SwitchAgentClient(
        base_url=OFFICIAL_SWITCH_URL,
        agent_registration=codex_reg,
        registration_token=REGISTRATION_TOKEN,
        mode="official",
    )
    await client_codex.connect()

    try:
        room_info = await client_codex.create_room(
            name="agenthive-war-room",
            description="AgentHive Multi-Agent Collaboration Room",
            agent_names=["agenthive-codex", "agenthive-agy", "agenthive-gemini", "agenthive-hermes"],
        )
        assert room_info is not None
        room_id = room_info.get("id")
        assert room_id is not None
        assert room_info.get("name") == "agenthive-war-room"
        assert "transport_room_id" in room_info

        visible_rooms = await client_codex.list_rooms()
        assert any(room.get("id") == room_id for room in visible_rooms)

        # Verify joining the room
        await client_codex.join_room(room_id)
        assert room_id in client_codex.subscribed_rooms
        participants = await client_codex.get_room_participants(room_id)
        assert any(p.get("name") == "agenthive-codex" for p in participants)
    finally:
        await client_codex.disconnect()


@pytest.mark.asyncio
@skip_if_no_switch
async def test_official_switch_sse_streaming_and_cross_agent_messaging():
    """Verify live Server-Sent Events (SSE) streaming and real-time message delivery across agents."""
    codex_reg = SwitchAgentRegistration(
        agent_id="agenthive-codex-sse",
        name="agenthive-codex",
        role="Chief Architect",
        description="Codex",
        capabilities=["architecture"],
    )
    agy_reg = SwitchAgentRegistration(
        agent_id="agenthive-agy-sse",
        name="agenthive-agy",
        role="Systems Integrator",
        description="AGY",
        capabilities=["cli"],
    )

    client_codex = SwitchAgentClient(
        base_url=OFFICIAL_SWITCH_URL,
        agent_registration=codex_reg,
        registration_token=REGISTRATION_TOKEN,
        mode="official",
    )
    client_agy = SwitchAgentClient(
        base_url=OFFICIAL_SWITCH_URL,
        agent_registration=agy_reg,
        registration_token=REGISTRATION_TOKEN,
        mode="official",
    )

    await client_codex.connect()
    await client_agy.connect()

    try:
        # 1. Create shared room
        room_info = await client_codex.create_room(
            name="agenthive-sse-verification",
            description="SSE verification room",
            agent_names=["agenthive-codex", "agenthive-agy"],
        )
        room_id = room_info["id"]

        # 2. Setup AGY event listener
        received_messages: List[Dict[str, Any]] = []

        async def on_agy_event(event_data: Dict[str, Any]):
            received_messages.append(event_data)

        await client_agy.start_event_listener(on_agy_event)
        # Give SSE stream a moment to establish
        await asyncio.sleep(0.5)

        # 3. Join room for both agents
        await client_agy.join_room(room_id)
        await client_codex.join_room(room_id)

        # 4. Codex sends a message
        test_content = "Official Switch SSE live delivery verified from Codex to AGY."
        send_resp = await client_codex.send_message(room_id=room_id, content=test_content)
        assert send_resp.get("ok") is True
        assert send_resp.get("event_id") is not None

        # 5. Wait for AGY to receive over SSE
        for _ in range(20):
            if any(test_content in m.get("content", "") for m in received_messages):
                break
            await asyncio.sleep(0.2)

        matching = [m for m in received_messages if test_content in m.get("content", "")]
        assert len(matching) > 0
        assert matching[0]["sender_name"] == "agenthive-codex"
        assert matching[0].get("event_id")

        # Exercise the reverse direction through the same official room and SSE streams.
        reverse_content = "Official Switch SSE live delivery verified from AGY to Codex."
        reverse_received = []
        async def on_codex_event(event_data: Dict[str, Any]):
            reverse_received.append(event_data)
        await client_codex.start_event_listener(on_codex_event)
        reverse_resp = await client_agy.send_message(room_id=room_id, content=reverse_content)
        assert reverse_resp.get("event_id") is not None
        for _ in range(20):
            if any(reverse_content in m.get("content", "") for m in reverse_received):
                break
            await asyncio.sleep(0.2)
        assert any(reverse_content in m.get("content", "") for m in reverse_received)
    finally:
        await client_agy.disconnect()
        await client_codex.disconnect()


@pytest.mark.asyncio
@skip_if_no_switch
async def test_official_switch_quad_agent_discussion_and_history():
    """Verify all four agents (Codex, AGY, Gemini, Hermes) conduct a collaborative discussion in Official Switch."""
    agent_specs = [
        ("agenthive-codex", "Chief Architect", "Codex proposes standard-library micro-engine with 0 pip dependencies."),
        ("agenthive-agy", "Systems Integrator", "AGY validates restricted Docker workspace isolation and non-root execution."),
        ("agenthive-gemini", "QA Strategist", "Gemini defines adversarial test plan covering concurrent cache evictions."),
        ("agenthive-hermes", "Autonomous Supervisor", "Hermes synthesizes architectural consensus and assigns 3 tasks to agents."),
    ]

    clients = []
    try:
        # Connect all 4 agents
        for name, role, _ in agent_specs:
            reg = SwitchAgentRegistration(
                agent_id=f"{name}-quad",
                name=name,
                role=role,
                description=f"{role} Agent",
                capabilities=[role.lower().replace(" ", "_")],
            )
            c = SwitchAgentClient(
                base_url=OFFICIAL_SWITCH_URL,
                agent_registration=reg,
                registration_token=REGISTRATION_TOKEN,
                mode="official",
            )
            await c.connect()
            clients.append(c)

        lead_client = clients[0]
        # Create quad collaboration room
        room_info = await lead_client.create_room(
            name="agenthive-quad-consensus-room",
            description="Quad-agent consensus room on Official Switch",
            agent_names=[name for name, _, _ in agent_specs],
        )
        room_id = room_info["id"]

        # All 4 join the room
        for c in clients:
            await c.join_room(room_id)

        # Each agent posts its message in order
        for (name, role, msg), c in zip(agent_specs, clients):
            send_resp = await c.send_message(room_id=room_id, content=msg)
            assert send_resp.get("ok") is True

        # Fetch room history from official Switch Core
        history = await lead_client.get_room_history(room_id)
        assert len(history) >= 4

        history_texts = [ev.get("body", "") for ev in history]
        for _, _, msg in agent_specs:
            assert any(msg in h for h in history_texts)

    finally:
        for c in clients:
            await c.disconnect()
