"""Switch Collaboration Infrastructure & Agent Protocol Verification Suite.
Validates:
1. Official Switch Agent Protocol Endpoints.
2. Agent Registration (Codex, AGY, Gemini, Hermes).
3. Collaborative Room Creation & Context Bus.
4. Dynamic Room Subscriptions & Membership.
5. Real-time Message Routing & Correlation.
6. Liveness Heartbeats & Presence Tracking.
7. Server-Sent Events (SSE) Event Frame Delivery.
"""

import pytest
import asyncio
import json
from datetime import datetime
from agenthive.switch.server import switch_state, register_agent, create_room, join_room, post_room_message, official_agent_beat
from agenthive.models.events import SwitchAgentRegistration, SwitchRoomCreate, SwitchMessageSend, SwitchHeartbeat

@pytest.mark.asyncio
async def test_switch_agent_registration():
    """Verify registration of all four AgentHive agents with Switch Agent Bridge."""
    agents = [
        SwitchAgentRegistration(
            agent_id="agent-codex-v2",
            name="ChatGPT Codex",
            role="Chief Software Architect",
            description="OpenAI Codex Engine",
            capabilities=["architecture", "data_structures", "backend"]
        ),
        SwitchAgentRegistration(
            agent_id="agent-agy-v2",
            name="AGY (Antigravity)",
            role="Systems Integration & CLI",
            description="Antigravity Native CLI Engine",
            capabilities=["cli_automation", "docker_sandboxing"]
        ),
        SwitchAgentRegistration(
            agent_id="agent-gemini-v2",
            name="Google Gemini",
            role="Deep Reasoning & QA Strategist",
            description="Google Gemini Reasoning Engine",
            capabilities=["deep_reasoning", "adversarial_testing"]
        ),
        SwitchAgentRegistration(
            agent_id="agent-hermes-v2",
            name="Hermes Supervisor",
            role="Autonomous Supervisor",
            description="Nous Research Hermes Supervision",
            capabilities=["consensus_synthesis", "wbs_allocation"]
        ),
    ]

    for ag in agents:
        res = await register_agent(ag)
        assert res["status"] == "success"
        assert ag.agent_id in switch_state.agents
        assert switch_state.agents[ag.agent_id].name == ag.name

@pytest.mark.asyncio
async def test_switch_shared_room_creation():
    """Verify shared collaborative room creation for multi-agent swarm."""
    room = SwitchRoomCreate(
        room_id="room-switch-verify-01",
        name="Architectural Consensus Room",
        topic="Consensus debate on sliding-window buffer design"
    )
    res = await create_room(room)
    assert res["status"] == "success"
    assert "room-switch-verify-01" in switch_state.rooms

@pytest.mark.asyncio
async def test_switch_agent_room_subscription():
    """Verify multiple agents subscribe and join the collaborative room."""
    room_id = "room-switch-verify-01"
    agent_ids = ["agent-codex-v2", "agent-agy-v2", "agent-gemini-v2", "agent-hermes-v2"]

    for aid in agent_ids:
        res = await join_room(room_id, aid)
        assert res["status"] == "joined"
        assert aid in switch_state.room_members[room_id]

@pytest.mark.asyncio
async def test_switch_heartbeat_liveness():
    """Verify periodic heartbeat maintenance for connected agents."""
    agent_id = "agent-codex-v2"
    res = await official_agent_beat(agent_id)
    assert res["status"] == "ok"
    assert res["agent_id"] == agent_id
    assert agent_id in switch_state.heartbeats

@pytest.mark.asyncio
async def test_switch_message_routing_and_sse_distribution():
    """Verify message broadcast, routing, and SSE delivery across room members."""
    room_id = "room-switch-verify-01"
    
    # 1. Prepare agent event queues
    q_agy = switch_state.get_or_create_agent_queue("agent-agy-v2")
    q_gemini = switch_state.get_or_create_agent_queue("agent-gemini-v2")
    
    # Drain any existing events in queues
    while not q_agy.empty():
        q_agy.get_nowait()
    while not q_gemini.empty():
        q_gemini.get_nowait()

    # 2. Codex publishes proposal message into room
    msg = SwitchMessageSend(
        room_id=room_id,
        sender_id="agent-codex-v2",
        sender_name="ChatGPT Codex",
        sender_role="ARCHITECT",
        content="Proposal: Use collections.deque(maxlen=100000) for bounded memory and O(1) appends."
    )
    post_res = await post_room_message(room_id, msg)
    assert post_res["status"] == "delivered"

    # 3. Verify message is stored in room history
    assert len(switch_state.room_messages[room_id]) >= 1
    stored = switch_state.room_messages[room_id][-1]
    assert stored.content == msg.content

    # 4. Verify SSE event delivery to subscribed members (AGY and Gemini)
    event_agy = await asyncio.wait_for(q_agy.get(), timeout=2.0)
    assert event_agy.event_type == "message.created"
    assert event_agy.payload["sender_id"] == "agent-codex-v2"
    assert "collections.deque" in event_agy.payload["content"]

    event_gemini = await asyncio.wait_for(q_gemini.get(), timeout=2.0)
    assert event_gemini.event_type == "message.created"
    assert event_gemini.payload["sender_id"] == "agent-codex-v2"
