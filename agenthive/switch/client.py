"""Switch Protocol Agent Client.
Used by agent adapters to connect, stream events via SSE, and send actions via HTTP.
"""

import asyncio
import json
import logging
import httpx
from typing import Callable, Optional, Dict, Any
from agenthive.models.events import SwitchAgentRegistration, SwitchHeartbeat, SwitchMessageSend

logger = logging.getLogger("agenthive.switch.client")

class SwitchAgentClient:
    def __init__(self, base_url: str, agent_registration: SwitchAgentRegistration):
        self.base_url = base_url.rstrip("/")
        self.agent = agent_registration
        self.is_connected = False
        self._sse_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self.on_message_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    async def connect(self):
        """Registers the agent and establishes connection & heartbeat."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}/switch/api/v1/agents/register",
                json=self.agent.model_dump()
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to register Switch agent: {resp.text}")

        self.is_connected = True
        logger.info("Agent %s successfully connected to Switch at %s", self.agent.name, self.base_url)

        # Launch heartbeat daemon
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self):
        """Sends periodic heartbeats to maintain presence via official or local endpoint."""
        while self.is_connected:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # Try official Switch route first: POST /agents/{id}/connection/beat
                    r = await client.post(f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/connection/beat")
                    if r.status_code != 200:
                        await client.post(
                            f"{self.base_url}/switch/api/v1/connection/beat",
                            json=SwitchHeartbeat(agent_id=self.agent.agent_id).model_dump()
                        )
            except Exception as e:
                logger.warning("Heartbeat notice for %s: %s", self.agent.agent_id, e)
            await asyncio.sleep(10)

    async def join_room(self, room_id: str):
        """Joins a Switch Room using official subscribe endpoint."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/connection/subscribe",
                json={"room_id": room_id}
            )
            if resp.status_code != 200:
                resp = await client.post(
                    f"{self.base_url}/switch/api/v1/rooms/{room_id}/join?agent_id={self.agent.agent_id}"
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to join room {room_id}: {resp.text}")
        logger.info("Agent %s joined room %s", self.agent.name, room_id)

    async def send_message(self, room_id: str, content: str, reply_to: Optional[str] = None) -> Dict[str, Any]:
        """Sends an outgoing message into a Switch Room via official Switch HTTP POST."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/message",
                json={"room_id": room_id, "content": content, "reply_to": reply_to}
            )
            if resp.status_code != 200:
                msg = SwitchMessageSend(
                    room_id=room_id,
                    sender_id=self.agent.agent_id,
                    sender_name=self.agent.name,
                    sender_role=self.agent.role,
                    content=content,
                    reply_to=reply_to
                )
                resp = await client.post(
                    f"{self.base_url}/switch/api/v1/rooms/{room_id}/messages",
                    json=msg.model_dump()
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to post message: {resp.text}")
            return resp.json()

    async def start_event_listener(self, on_event: Callable[[Dict[str, Any]], Any]):
        """Connects to the Server-Sent Events stream for this agent."""
        self.on_message_callback = on_event
        self._sse_task = asyncio.create_task(self._listen_sse())

    async def _listen_sse(self):
        """Consumes the SSE event stream."""
        url = f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/events"
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream("GET", url) as response:
                    logger.info("Agent %s listening to Switch SSE stream", self.agent.agent_id)
                    current_event_type = "message"
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("event:"):
                            current_event_type = line[len("event:"):].strip()
                        elif line.startswith("data:"):
                            data_str = line[len("data:"):].strip()
                            try:
                                data = json.loads(data_str)
                                if current_event_type == "message.created" and self.on_message_callback:
                                    asyncio.create_task(self.on_message_callback(data))
                            except Exception as parse_err:
                                logger.debug("Error parsing SSE data: %s", parse_err)
            except Exception as e:
                logger.error("SSE connection closed for %s: %s", self.agent.agent_id, e)

    async def disconnect(self):
        self.is_connected = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._sse_task:
            self._sse_task.cancel()
