"""Switch Protocol Agent Client.
Supports both:
1. Official Switch Infrastructure (ghcr.io/sandbox-quantum/switch-core / https://docs.switchagents.ai/)
   - Bearer token authentication & agent API keys.
   - Dynamic connection IDs & Server-Sent Events (SSE).
   - Official moderation rooms, subscriptions, heartbeats, and message routing.
2. Local Protocol Reference Bridge (offline / zero-dependency fallback)
   - /switch/api/v1 REST and SSE transport.
"""

import os
import uuid
import asyncio
import json
import logging
import re
import httpx
from typing import Callable, Optional, Dict, Any, List, Set
from agenthive.models.events import SwitchAgentRegistration, SwitchHeartbeat, SwitchMessageSend
from agenthive.switch.protocol import (
    OFFICIAL_HEALTH_READY,
    OFFICIAL_REGISTER_AGENT,
    OFFICIAL_AGENT_EVENTS,
    OFFICIAL_CONNECTION_BEAT,
    OFFICIAL_CONNECTION_SUBSCRIBE,
    OFFICIAL_AGENT_MESSAGE,
    OFFICIAL_MODERATION_ROOMS,
    OFFICIAL_ROOM_HISTORY,
    REGISTER_AGENT_ENDPOINT,
    AGENT_EVENTS_ENDPOINT,
    AGENT_HEARTBEAT_ENDPOINT,
    ROOMS_ENDPOINT,
    ROOM_MESSAGES_ENDPOINT,
)

logger = logging.getLogger("agenthive.switch.client")


class SwitchAgentClient:
    """Client for connecting an AgentHive agent to the Switch Collaboration Infrastructure."""

    def __init__(
        self,
        base_url: str,
        agent_registration: SwitchAgentRegistration,
        registration_token: Optional[str] = None,
        mode: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent = agent_registration
        self.registration_token = (
            registration_token
            or os.getenv("SWITCH_REGISTRATION_TOKEN")
            or os.getenv("SWITCH_API_KEY")
            or None
        )
        self.mode = (mode or os.getenv("SWITCH_MODE", "official")).lower()

        # State
        self.connection_id: str = str(uuid.uuid4())
        self.official_agent_id: Optional[str] = None
        self.official_name: Optional[str] = None
        self.api_key: Optional[str] = None
        self.is_official_switch: bool = False
        self.is_connected: bool = False
        self.subscribed_rooms: Set[str] = set()

        # Background tasks & callbacks
        self._sse_ready: asyncio.Event = asyncio.Event()
        self._sse_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self.on_message_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.last_event_id: Optional[str] = None

    def _local_headers(self) -> Dict[str, str]:
        if not self.registration_token:
            raise RuntimeError("Local Switch transport requires a configured registration token")
        return {"Authorization": f"Bearer {self.registration_token}"}

    async def connect(self):
        """Register on the explicitly selected transport; never downgrade silently."""
        if self.mode == "official":
            await self._connect_official()
        elif self.mode == "local":
            await self._connect_local()
        else:
            raise ValueError("SWITCH_MODE must be 'official' or explicit 'local'; automatic fallback is not supported")

        self.is_connected = True
        logger.info(
            "Agent %s successfully connected to Switch (%s) at %s",
            self.agent.name,
            "OFFICIAL" if self.is_official_switch else "LOCAL_FALLBACK",
            self.base_url,
        )

        # Launch active SSE stream connection
        self._sse_ready.clear()
        self._sse_task = asyncio.create_task(self._listen_sse())
        try:
            await asyncio.wait_for(self._sse_ready.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.debug("SSE stream wait timed out for %s", self.agent.name)

        # Launch heartbeat daemon
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _probe_official_switch(self) -> bool:
        """Probes base_url to detect official Switch Core."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}{OFFICIAL_HEALTH_READY}")
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("status") == "ready"
        except Exception:
            pass
        return False

    async def _connect_official(self):
        """Registers with Official Switch Core via POST /agents."""
        if not self.registration_token:
            raise RuntimeError("Official Switch mode requires SWITCH_REGISTRATION_TOKEN or SWITCH_API_KEY")
        # Switch Core requires `name` to be a machine slug. Keep the persona label
        # intact in `display_name` so operators still see the friendly identity.
        slug = re.sub(r"[^a-z0-9._-]+", "-", self.agent.name.lower()).strip("-._")
        if not slug:
            slug = re.sub(r"[^a-z0-9._-]+", "-", self.agent.agent_id.lower()).strip("-._")
        payload = {
            "name": slug,
            "description": self.agent.description,
            "display_name": self.agent.name,
            "connector_type": "custom",
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
            },
            "metadata": {
                "role": self.agent.role,
                "capabilities": self.agent.capabilities,
                "agent_id": self.agent.agent_id,
            },
            "overwrite": True,
        }
        headers = {
            "Authorization": f"Bearer {self.registration_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}{OFFICIAL_REGISTER_AGENT}",
                json=payload,
                headers=headers,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"Official Switch registration failed ({resp.status_code}): {resp.text}"
                )
            data = resp.json()
            self.official_agent_id = data.get("id")
            self.api_key = data.get("api_key")
            self.official_name = slug
            if not self.official_agent_id or not self.api_key:
                raise RuntimeError("Official Switch registration response omitted agent id or API key")
            self.is_official_switch = True
            logger.info(
                "Official Switch agent registered: id=%s, name=%s",
                self.official_agent_id,
                self.agent.name,
            )

    async def _connect_local(self):
        """Registers with Local Protocol Reference Bridge."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}{REGISTER_AGENT_ENDPOINT}",
                json=self.agent.model_dump(),
                headers=self._local_headers(),
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Local Switch registration failed: {resp.text}")
            self.is_official_switch = False
            self.official_agent_id = self.agent.agent_id

    async def create_room(
        self,
        name: str,
        description: str,
        agent_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Creates a collaborative room via official moderation endpoint or local fallback."""
        if self.is_official_switch:
            target_agent_id = self.official_agent_id or self.agent.agent_id
            payload = {
                "name": name,
                "description": description,
                "agent_names": agent_names or [self.agent.name],
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/agents/{target_agent_id}/moderation/rooms",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to create official room: {resp.text}")
                data = resp.json()
                if not data.get("id") or not data.get("transport_room_id"):
                    raise RuntimeError("Official Switch room response omitted its room or transport ID")
                return data
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                room_id = f"room-{name.lower().replace(' ', '-')}"
                payload = {
                    "room_id": room_id,
                    "name": name,
                    "topic": description,
                }
                resp = await client.post(f"{self.base_url}{ROOMS_ENDPOINT}", json=payload, headers=self._local_headers())
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to create local room: {resp.text}")
                return {"id": room_id, "name": name, "transport_room_id": room_id}

    async def join_room(self, room_id: str):
        """Subscribes this agent connection to a Switch collaborative room."""
        if self.is_official_switch:
            # Ensure SSE stream is established before subscribing
            if not self._sse_ready.is_set():
                try:
                    await asyncio.wait_for(self._sse_ready.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
            target_agent_id = self.official_agent_id or self.agent.agent_id
            payload = {
                "connection_id": self.connection_id,
                "room_id": room_id,
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            last_error = None
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            f"{self.base_url}/agents/{target_agent_id}/connection/subscribe",
                            json=payload,
                            headers=headers,
                        )
                    if resp.status_code == 200:
                        self.subscribed_rooms.add(room_id)
                        last_error = None
                        break
                    if resp.status_code == 429 or resp.status_code >= 500:
                        last_error = RuntimeError(f"Switch subscribe returned HTTP {resp.status_code}")
                    else:
                        raise RuntimeError(
                            f"Official subscribe failed for {self.agent.name} ({resp.status_code}): {resp.text}"
                        )
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    last_error = exc
                if last_error and attempt < 2:
                    await asyncio.sleep(0.25 * (2 ** attempt))
            if last_error:
                raise RuntimeError(f"Official subscribe failed for {self.agent.name}: {last_error}")
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try official route alias on local bridge first
                resp = await client.post(
                    f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/connection/subscribe",
                    json={"room_id": room_id, "connection_id": self.connection_id},
                    headers=self._local_headers(),
                )
                if resp.status_code != 200:
                    resp = await client.post(
                        f"{self.base_url}/switch/api/v1/rooms/{room_id}/join?agent_id={self.agent.agent_id}",
                        headers=self._local_headers(),
                    )
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to join room {room_id}: {resp.text}")
                self.subscribed_rooms.add(room_id)

        logger.info("Agent %s successfully subscribed to room %s", self.agent.name, room_id)

    async def send_message(
        self, room_id: str, content: str, reply_to: Optional[str] = None,
        client_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends an outgoing message into a Switch Room."""
        if self.is_official_switch:
            target_agent_id = self.official_agent_id or self.agent.agent_id
            payload = {
                "room_id": room_id,
                "content": content,
                "metadata": {
                    **({"reply_to": reply_to} if reply_to else {}),
                    "agenthive_client_message_id": client_message_id or str(uuid.uuid4()),
                },
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            # Only retry failures known to happen before the request reached Switch.
            # A read timeout is ambiguous: resending could duplicate a delivered message.
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            f"{self.base_url}/agents/{target_agent_id}/message",
                            json=payload,
                            headers=headers,
                        )
                    if resp.status_code != 200:
                        raise RuntimeError(f"Official message send failed ({resp.status_code}): {resp.text}")
                    result = resp.json()
                    if result.get("ok") is False:
                        raise RuntimeError("Official Switch rejected the message")
                    return result
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.25 * (2 ** attempt))
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/message",
                    json={"room_id": room_id, "content": content, "reply_to": reply_to},
                    headers=self._local_headers(),
                )
                if resp.status_code != 200:
                    msg = SwitchMessageSend(
                        room_id=room_id,
                        sender_id=self.agent.agent_id,
                        sender_name=self.agent.name,
                        sender_role=self.agent.role,
                        content=content,
                        reply_to=reply_to,
                    )
                    resp = await client.post(
                        f"{self.base_url}/switch/api/v1/rooms/{room_id}/messages",
                        json=msg.model_dump(),
                        headers=self._local_headers(),
                    )
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to post message: {resp.text}")
                return resp.json()

    async def get_room_history(self, room_id: str) -> List[Dict[str, Any]]:
        """Retrieves room message history."""
        if self.is_official_switch:
            target_agent_id = self.official_agent_id or self.agent.agent_id
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/agents/{target_agent_id}/rooms/{room_id}/history",
                    headers=headers,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to fetch room history: {resp.text}")
                data = resp.json()
                return data.get("events", [])
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/switch/api/v1/rooms/{room_id}/messages",
                    headers=self._local_headers(),
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to fetch room history: {resp.text}")
                data = resp.json()
                return data.get("messages", [])

    async def list_rooms(self) -> List[Dict[str, Any]]:
        """List rooms visible to this registered official agent."""
        if not self.is_official_switch:
            raise RuntimeError("Official room listing is unavailable on the local protocol fallback")
        target_agent_id = self.official_agent_id or self.agent.agent_id
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.base_url}/agents/{target_agent_id}/moderation/rooms",
                headers=headers,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Official Switch room listing failed ({resp.status_code})")
        data = resp.json()
        return data.get("rooms", [])

    async def get_room_participants(self, room_id: str) -> List[Dict[str, Any]]:
        """Fetches server-confirmed room membership for an official room."""
        if not self.is_official_switch:
            raise RuntimeError("Room participant lookup is available only for Official Switch")
        target_agent_id = self.official_agent_id or self.agent.agent_id
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.base_url}/agents/rooms/{room_id}/participants",
                headers=headers,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to verify official room membership ({resp.status_code})")
        data = resp.json()
        return data.get("participants", data.get("agents", []))

    async def start_event_listener(self, on_event: Callable[[Dict[str, Any]], Any]):
        """Connects to the Server-Sent Events stream for this agent."""
        self.on_message_callback = on_event
        if not self._sse_task or self._sse_task.done():
            self._sse_task = asyncio.create_task(self._listen_sse())

    async def _listen_sse(self):
        """Consumes Switch SSE frames in order and reconnects with the last event cursor."""
        if self.is_official_switch:
            target_agent_id = self.official_agent_id or self.agent.agent_id
            url = f"{self.base_url}/agents/{target_agent_id}/events?connection_id={self.connection_id}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "text/event-stream",
            }
        else:
            url = f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/events"
            headers = {"Accept": "text/event-stream", **self._local_headers()}

        retry_delay = 0.5
        while self.is_connected:
            stream_headers = dict(headers)
            if self.last_event_id:
                stream_headers["Last-Event-ID"] = self.last_event_id
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", url, headers=stream_headers) as response:
                        if response.status_code != 200:
                            raise RuntimeError(f"Switch SSE returned HTTP {response.status_code}")
                        self._sse_ready.set()
                        retry_delay = 0.5
                        logger.info(
                            "Agent %s listening to Switch SSE stream (mode: %s)",
                            self.agent.agent_id,
                            "OFFICIAL" if self.is_official_switch else "LOCAL",
                        )
                        event_type = "message"
                        frame_id = None
                        data_lines: List[str] = []
                        async for raw_line in response.aiter_lines():
                            line = raw_line.rstrip("\r")
                            if not line:
                                await self._dispatch_sse_frame(event_type, frame_id, data_lines)
                                event_type, frame_id, data_lines = "message", None, []
                            elif line.startswith(":"):
                                continue
                            elif line.startswith("event:"):
                                event_type = line[6:].strip()
                                if event_type == "connection_state":
                                    self._sse_ready.set()
                            elif line.startswith("id:"):
                                frame_id = line[3:].strip()
                            elif line.startswith("data:"):
                                data_lines.append(line[5:].lstrip())
                        if data_lines:
                            await self._dispatch_sse_frame(event_type, frame_id, data_lines)
                if self.is_connected:
                    self._sse_ready.clear()
                    logger.warning("Switch SSE stream closed for %s; reconnecting", self.agent.agent_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._sse_ready.clear()
                logger.warning("Switch SSE connection interrupted for %s: %s", self.agent.agent_id, e)
            if self.is_connected:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 15.0)

    async def _dispatch_sse_frame(self, event_type: str, frame_id: Optional[str], data_lines: List[str]):
        if not data_lines:
            return
        try:
            data = json.loads("\n".join(data_lines))
        except (TypeError, json.JSONDecodeError):
            logger.warning("Ignoring malformed Switch SSE data frame for %s", self.agent.agent_id)
            return
        if frame_id:
            self.last_event_id = frame_id
        if event_type == "connection_state":
            self._sse_ready.set()
            return
        if event_type not in {"message", "message.created"} or not self.on_message_callback:
            return
        payload = data.get("payload") or data.get("message") or data
        normalized = {
            "event_id": frame_id or data.get("event_id") or payload.get("event_id"),
            "room_id": data.get("room_id") or payload.get("room_id"),
            "sender_name": payload.get("sender_name") or data.get("sender_name") or payload.get("sender"),
            "sender": payload.get("sender") or payload.get("sender_id"),
            "content": payload.get("body") or payload.get("content"),
            "message_id": payload.get("message_id") or data.get("message_id"),
            "timestamp": payload.get("timestamp") or data.get("timestamp"),
            "metadata": payload.get("metadata") or data.get("metadata") or {},
        }
        await self.on_message_callback(normalized)

    async def _heartbeat_loop(self):
        """Sends periodic heartbeats to maintain presence via official or local endpoint."""
        interval = 3.0 if self.is_official_switch else 10.0
        while self.is_connected:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    if self.is_official_switch:
                        target_agent_id = self.official_agent_id or self.agent.agent_id
                        await client.post(
                            f"{self.base_url}/agents/{target_agent_id}/connection/beat",
                            json={"connection_id": self.connection_id},
                            headers={"Authorization": f"Bearer {self.api_key}"},
                        )
                    else:
                        r = await client.post(
                            f"{self.base_url}/switch/api/v1/agents/{self.agent.agent_id}/connection/beat",
                            headers=self._local_headers(),
                        )
                        if r.status_code != 200:
                            await client.post(
                                f"{self.base_url}/switch/api/v1/connection/beat",
                                json=SwitchHeartbeat(agent_id=self.agent.agent_id).model_dump(),
                                headers=self._local_headers(),
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Heartbeat notice for %s: %s", self.agent.agent_id, e)
            await asyncio.sleep(interval)

    async def disconnect(self):
        """Gracefully disconnects the agent from Switch."""
        self.is_connected = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._sse_task:
            self._sse_task.cancel()
        logger.info("Agent %s disconnected from Switch", self.agent.name)
