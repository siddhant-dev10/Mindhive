"""AgentHive Local Protocol Server (Switch Agent Protocol Compatible).
NOTE: This is AgentHive's local in-process protocol-compatible bridge implementation
used for self-contained execution, CI validation, and zero-dependency local workflows.
Official Switch infrastructure runs externally via switch-core or Switch Console
(https://docs.switchagents.ai/ and https://github.com/sandbox-quantum/switch).

Transports:
- HTTP REST for actions, registrations, messages, heartbeats.
- Server-Sent Events (SSE) for real-time event streaming to agents.
"""

import asyncio
import json
import logging
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from agenthive.models.events import (
    SwitchAgentRegistration,
    SwitchHeartbeat,
    SwitchRoomCreate,
    SwitchMessageSend,
    SwitchRoomEvent,
)

logger = logging.getLogger("agenthive.switch.server")

router = APIRouter(prefix="/switch/api/v1", tags=["Switch Agent Bridge"])

class SwitchServerState:
    def __init__(self):
        # Registered agents: agent_id -> SwitchAgentRegistration
        self.agents: Dict[str, SwitchAgentRegistration] = {}
        # Agent heartbeats: agent_id -> last_seen iso timestamp
        self.heartbeats: Dict[str, str] = {}
        # Rooms: room_id -> SwitchRoomCreate
        self.rooms: Dict[str, SwitchRoomCreate] = {}
        # Room participants: room_id -> set of agent_ids
        self.room_members: Dict[str, Set[str]] = {}
        # Room messages: room_id -> list of SwitchMessageSend
        self.room_messages: Dict[str, List[SwitchMessageSend]] = {}
        # Event queues for active SSE agent subscribers: agent_id -> asyncio.Queue[SwitchRoomEvent]
        self.agent_queues: Dict[str, asyncio.Queue] = {}
        # Room broadcast queues: room_id -> list of queues
        self.room_subscribers: Dict[str, List[asyncio.Queue]] = {}

    def get_or_create_agent_queue(self, agent_id: str) -> asyncio.Queue:
        if agent_id not in self.agent_queues:
            self.agent_queues[agent_id] = asyncio.Queue()
        return self.agent_queues[agent_id]

switch_state = SwitchServerState()

@router.get("/health/ready")
async def health_ready():
    """Health readiness check matching official Switch Core format."""
    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": {"healthy": True},
            "bridges": {"healthy": True},
            "message_listener": {"healthy": True},
            "signal_bus": {"healthy": True}
        }
    }

@router.post("/agents", response_model=Dict[str, Any])
async def register_agent_official(payload: Dict[str, Any]):
    """Official Switch route: POST /agents (with IntegrationProfile)."""
    name = payload.get("name") or payload.get("display_name") or "agent"
    agent_id = payload.get("agent_id") or f"agent-{name.lower().replace(' ', '-')}"
    desc = payload.get("description", "")
    metadata = payload.get("metadata", {})
    role = metadata.get("role", "AGENT")
    capabilities = metadata.get("capabilities", [])

    reg = SwitchAgentRegistration(
        agent_id=agent_id,
        name=name,
        role=role,
        description=desc,
        capabilities=capabilities
    )
    switch_state.agents[agent_id] = reg
    switch_state.heartbeats[agent_id] = datetime.utcnow().isoformat()
    switch_state.get_or_create_agent_queue(agent_id)

    return {
        "id": agent_id,
        "name": name,
        "status": "registered",
        "agent": reg.model_dump()
    }

@router.post("/agents/register", response_model=Dict[str, Any])
async def register_agent(reg: SwitchAgentRegistration):
    """Register an agent with Switch Agent Bridge."""
    switch_state.agents[reg.agent_id] = reg
    switch_state.heartbeats[reg.agent_id] = datetime.utcnow().isoformat()
    switch_state.get_or_create_agent_queue(reg.agent_id)
    
    logger.info("Registered Switch Agent: %s (%s, role: %s)", reg.name, reg.agent_id, reg.role)
    
    # Broadcast registration event
    event = SwitchRoomEvent(
        event_type="agent.registered",
        agent_id=reg.agent_id,
        payload=reg.model_dump()
    )
    return {
        "status": "success",
        "message": f"Agent {reg.name} registered successfully",
        "agent": reg.model_dump()
    }

@router.get("/agents")
async def list_agents():
    """List all registered agents and their statuses."""
    result = []
    for agent_id, agent in switch_state.agents.items():
        result.append({
            "agent_id": agent_id,
            "name": agent.name,
            "role": agent.role,
            "capabilities": agent.capabilities,
            "last_heartbeat": switch_state.heartbeats.get(agent_id, "unknown")
        })
    return {"agents": result}

@router.post("/connection/beat")
async def agent_heartbeat(beat: SwitchHeartbeat):
    """Heartbeat endpoint for connected agents to maintain liveness and cursor."""
    if beat.agent_id in switch_state.agents:
        switch_state.heartbeats[beat.agent_id] = datetime.utcnow().isoformat()
        return {"status": "ok", "agent_id": beat.agent_id, "timestamp": beat.timestamp}
    raise HTTPException(status_code=404, detail="Agent not registered")

# --- Official Switch Bridge Route Aliases (sandbox-quantum/switch) ---

@router.post("/agents/{agent_id}/connection/beat")
async def official_agent_beat(agent_id: str):
    """Official Switch route: POST /agents/{agent_id}/connection/beat"""
    beat = SwitchHeartbeat(agent_id=agent_id)
    res = await agent_heartbeat(beat)
    return {"status": "ok", "ok": True, "agent_id": agent_id, "timestamp": beat.timestamp}

@router.post("/agents/{agent_id}/connection/subscribe")
async def official_agent_subscribe(agent_id: str, payload: Dict[str, Any]):
    """Official Switch route: POST /agents/{agent_id}/connection/subscribe"""
    room_id = payload.get("room_id")
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id required in subscribe payload")
    await join_room(room_id, agent_id)
    return {"ok": True, "rooms": [room_id]}

@router.post("/agents/{agent_id}/moderation/rooms")
async def official_create_room(agent_id: str, payload: Dict[str, Any]):
    """Official Switch route: POST /agents/{agent_id}/moderation/rooms"""
    name = payload.get("name", "collaborative-room")
    desc = payload.get("description", "")
    agent_names = payload.get("agent_names", [])
    room_id = f"room-{name.lower().replace(' ', '-')}"
    room = SwitchRoomCreate(room_id=room_id, name=name, topic=desc)
    await create_room(room)
    # Auto-add specified agents
    for aid, ag in switch_state.agents.items():
        if ag.name in agent_names or aid in agent_names:
            switch_state.room_members[room_id].add(aid)
    return {
        "id": room_id,
        "name": name,
        "transport_room_id": f"sw_{room_id}",
        "matrix_room_id": f"sw_{room_id}",
        "failed_attachments": []
    }

@router.get("/agents/{agent_id}/moderation/rooms")
async def official_list_rooms(agent_id: str):
    """Official Switch route: GET /agents/{agent_id}/moderation/rooms"""
    return await list_rooms()

@router.post("/agents/{agent_id}/message")
async def official_agent_message(agent_id: str, payload: Dict[str, Any]):
    """Official Switch route: POST /agents/{agent_id}/message"""
    room_id = payload.get("room_id")
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id required")
    agent = switch_state.agents.get(agent_id)
    sender_name = agent.name if agent else agent_id
    sender_role = agent.role if agent else "AGENT"
    metadata = payload.get("metadata", {})
    reply_to = payload.get("reply_to") or metadata.get("reply_to")
    msg = SwitchMessageSend(
        room_id=room_id,
        sender_id=agent_id,
        sender_name=sender_name,
        sender_role=sender_role,
        content=payload.get("content", ""),
        reply_to=reply_to
    )
    res = await post_room_message(room_id, msg)
    import uuid
    return {"ok": True, "event_id": f"sw_{uuid.uuid4().hex[:32]}", "message": res.get("message")}

@router.get("/agents/{agent_id}/rooms/{room_id}/history")
async def official_room_history(agent_id: str, room_id: str):
    """Official Switch route: GET /agents/{agent_id}/rooms/{room_id}/history"""
    res = await get_room_messages(room_id)
    events = []
    for m in res.get("messages", []):
        events.append({
            "sender": f"@{m.get('sender_id')}:switch.local",
            "sender_name": m.get("sender_name"),
            "body": m.get("content"),
            "timestamp": int(datetime.utcnow().timestamp() * 1000)
        })
    return {"events": events, "has_more": False}

@router.post("/rooms")
async def create_room(room: SwitchRoomCreate):
    """Creates a shared collaborative room."""
    switch_state.rooms[room.room_id] = room
    if room.room_id not in switch_state.room_members:
        switch_state.room_members[room.room_id] = set()
    if room.room_id not in switch_state.room_messages:
        switch_state.room_messages[room.room_id] = []
    if room.room_id not in switch_state.room_subscribers:
        switch_state.room_subscribers[room.room_id] = []

    logger.info("Created Switch Room: %s (%s)", room.name, room.room_id)
    return {"status": "success", "room": room.model_dump()}

@router.post("/rooms/{room_id}/join")
async def join_room(room_id: str, agent_id: str):
    """Adds an agent to a Switch Room."""
    if room_id not in switch_state.rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    if agent_id not in switch_state.agents:
        raise HTTPException(status_code=404, detail="Agent not registered")

    switch_state.room_members[room_id].add(agent_id)
    logger.info("Agent %s joined room %s", agent_id, room_id)
    return {"status": "joined", "room_id": room_id, "agent_id": agent_id}

@router.get("/rooms")
async def list_rooms():
    """List all collaborative rooms."""
    rooms = []
    for r_id, room in switch_state.rooms.items():
        rooms.append({
            "room_id": r_id,
            "name": room.name,
            "topic": room.topic,
            "members": list(switch_state.room_members.get(r_id, set())),
            "message_count": len(switch_state.room_messages.get(r_id, []))
        })
    return {"rooms": rooms}

@router.get("/rooms/{room_id}/messages")
async def get_room_messages(room_id: str):
    """Retrieve message history for a Switch Room."""
    if room_id not in switch_state.rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"room_id": room_id, "messages": [m.model_dump() for m in switch_state.room_messages[room_id]]}

@router.post("/rooms/{room_id}/messages")
async def post_room_message(room_id: str, msg: SwitchMessageSend):
    """Publishes a message into a Switch Room and distributes it via SSE to room members."""
    if room_id not in switch_state.rooms:
        raise HTTPException(status_code=404, detail="Room not found")

    switch_state.room_messages[room_id].append(msg)
    logger.info("[%s] %s (%s): %s", room_id, msg.sender_name, msg.sender_role, msg.content[:80])

    # Construct event frame
    event = SwitchRoomEvent(
        event_type="message.created",
        room_id=room_id,
        agent_id=msg.sender_id,
        payload=msg.model_dump()
    )

    # Deliver to all members of the room
    members = switch_state.room_members.get(room_id, set())
    for member_id in members:
        # Don't echo to the sender if they sent it
        if member_id != msg.sender_id:
            q = switch_state.get_or_create_agent_queue(member_id)
            await q.put(event)

    # Also deliver to active room SSE subscribers (e.g. UI or logger)
    for q in switch_state.room_subscribers.get(room_id, []):
        await q.put(event)

    return {"status": "delivered", "message": msg.model_dump()}

@router.get("/agents/{agent_id}/events")
async def agent_events_sse(agent_id: str, request: Request):
    """Official Switch Agent Protocol SSE Stream.
    Pushes real-time room events and instructions down to connected agents.
    """
    if agent_id not in switch_state.agents:
        # Auto-register stub if not present
        switch_state.agents[agent_id] = SwitchAgentRegistration(
            agent_id=agent_id,
            name=agent_id,
            role="AGENT",
            description="Auto-registered agent"
        )
    
    q = switch_state.get_or_create_agent_queue(agent_id)

    async def event_generator():
        # Send initial connected banner & official connection_state
        conn_id = request.query_params.get("connection_id", "local_conn")
        yield {
            "event": "connection_state",
            "data": json.dumps({
                "connection_id": conn_id,
                "agent_id": agent_id,
                "server": {"version": "0.31.0", "contracts": {"agent-protocol": {"speaks": 9, "accepts": 1}}},
                "status": "stream_active"
            })
        }
        yield {
            "event": "connected",
            "data": json.dumps({"agent_id": agent_id, "status": "stream_active"})
        }
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("Agent %s SSE disconnected", agent_id)
                    break
                
                try:
                    event: SwitchRoomEvent = await asyncio.wait_for(q.get(), timeout=15.0)
                    # Yield legacy/local event
                    yield {
                        "event": event.event_type,
                        "id": event.event_id,
                        "data": json.dumps(event.model_dump())
                    }
                    # Also yield official Switch event format if message
                    if event.event_type == "message.created":
                        payload = event.payload or {}
                        yield {
                            "event": "message",
                            "id": event.event_id,
                            "data": json.dumps({
                                "type": "message",
                                "room_id": event.room_id,
                                "payload": {
                                    "sender": f"@{event.agent_id}:switch.local",
                                    "sender_name": payload.get("sender_name", event.agent_id),
                                    "body": payload.get("content", ""),
                                    "message_id": event.event_id,
                                    "timestamp": int(datetime.utcnow().timestamp() * 1000)
                                }
                            })
                        }
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield {
                        "event": "ping",
                        "data": json.dumps({"timestamp": datetime.utcnow().isoformat()})
                    }
        except asyncio.CancelledError:
            logger.info("Agent %s SSE stream cancelled", agent_id)

    return EventSourceResponse(event_generator())

@router.get("/rooms/{room_id}/events")
async def room_events_sse(room_id: str, request: Request):
    """Real-time SSE stream for human monitoring (Discord or Web Dashboard)."""
    if room_id not in switch_state.rooms:
        raise HTTPException(status_code=404, detail="Room not found")

    q = asyncio.Queue()
    switch_state.room_subscribers[room_id].append(q)

    async def event_generator():
        yield {
            "event": "connected",
            "data": json.dumps({"room_id": room_id, "status": "observing"})
        }
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: SwitchRoomEvent = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield {
                        "event": event.event_type,
                        "id": event.event_id,
                        "data": json.dumps(event.model_dump())
                    }
                except asyncio.TimeoutError:
                    yield {
                        "event": "ping",
                        "data": json.dumps({"timestamp": datetime.utcnow().isoformat()})
                    }
        finally:
            if q in switch_state.room_subscribers.get(room_id, []):
                switch_state.room_subscribers[room_id].remove(q)

    return EventSourceResponse(event_generator())
