"""AgentHive Discord Gateway Package.
Exposes the Discord bot, command dispatcher, interactive views, and embed builders.
"""

from agenthive.discord_gateway.dispatcher import (
    discord_dispatcher,
    DiscordCommandDispatcher,
)
from agenthive.discord_gateway.views import ApprovalView
from agenthive.discord_gateway.webhooks import webhook_broadcaster, DiscordWebhookBroadcaster
from agenthive.discord_gateway.bot import (
    AgentHiveDiscordBot,
    start_discord_bot,
    live_discord_bot,
    HAS_DISCORD_LIB,
)

__all__ = [
    "discord_dispatcher",
    "DiscordCommandDispatcher",
    "ApprovalView",
    "webhook_broadcaster",
    "DiscordWebhookBroadcaster",
    "AgentHiveDiscordBot",
    "start_discord_bot",
    "live_discord_bot",
    "HAS_DISCORD_LIB",
]
