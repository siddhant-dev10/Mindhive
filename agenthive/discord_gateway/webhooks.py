"""Discord Webhook Broadcaster for AgentHive Multi-Agent Persona Mirroring.
Broadcasts agent messages to a designated Discord webhook with distinct persona
names, avatars, and rate-limit throttling.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import httpx
from agenthive.discord_gateway.embeds import get_agent_persona

logger = logging.getLogger("agenthive.discord_gateway.webhooks")

class DiscordWebhookBroadcaster:
    """Manages rate-limited webhook delivery for multi-agent persona rendering."""

    def __init__(self, default_webhook_url: Optional[str] = None, min_interval: float = 1.2):
        self.default_webhook_url = default_webhook_url
        self.min_interval = min_interval
        self._last_send_time = 0.0
        self._lock = asyncio.Lock()

    async def send_agent_message(
        self,
        agent_name: str,
        content: str,
        webhook_url: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> bool:
        """Sends an agent message via Discord Webhook with custom persona name and avatar."""
        target_url = webhook_url or self.default_webhook_url
        if not target_url:
            logger.debug("No webhook URL configured; skipping webhook broadcast.")
            return False

        persona = get_agent_persona(agent_name)
        display_name = f"{persona['emoji']} {persona['display_name']}"

        async with self._lock:
            # Enforce 1.2s cadence to avoid Discord 429 rate limit
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_send_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)

            payload: Dict[str, Any] = {
                "username": display_name,
                "content": content[:2000],
            }
            if avatar_url:
                payload["avatar_url"] = avatar_url

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(target_url, json=payload)
                    self._last_send_time = asyncio.get_event_loop().time()
                    if resp.status_code in (200, 204):
                        return True
                    else:
                        logger.warning("Discord webhook returned status %d: %s", resp.status_code, resp.text)
                        return False
            except Exception as e:
                logger.warning("Failed to send agent webhook message: %s", e)
                return False

webhook_broadcaster = DiscordWebhookBroadcaster()
