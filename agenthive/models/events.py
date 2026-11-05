"""Switch Agent Protocol and Event Data Models."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import uuid4

class SwitchAgentRegistration(BaseModel):
    agent_id: str
    name: str
    role: str
    description: str
    capabilities: List[str] = []
    avatar_url: Optional[str] = None

class SwitchHeartbeat(BaseModel):
    agent_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "active"

class SwitchRoomCreate(BaseModel):
    room_id: str = Field(default_factory=lambda: f"room-{uuid4().hex[:8]}")
    name: str
    topic: Optional[str] = None
    created_by: str = "agenthive"

class SwitchMessageSend(BaseModel):
    room_id: str
    sender_id: str
    sender_name: str
    sender_role: str = "AGENT"  # AGENT, SUPERVISOR, HUMAN_PO, SYSTEM
    content: str
    reply_to: Optional[str] = None
    metadata: Dict[str, Any] = {}

class SwitchRoomEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str  # message.created, agent.registered, room.created, task.assigned
    room_id: Optional[str] = None
    agent_id: Optional[str] = None
    payload: Dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
