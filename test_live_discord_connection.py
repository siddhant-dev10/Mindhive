import asyncio
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from agenthive.config import settings
import discord
from agenthive.discord_gateway.bot import AgentHiveDiscordBot

async def verify_gateway():
    bot = AgentHiveDiscordBot()
    token = settings.discord_bot_token
    print(f"Loaded token (length: {len(token) if token else 0})")
    
    @bot.event
    async def on_ready():
        print(f"SUCCESS: Logged in as {bot.user} (ID: {bot.user.id})")
        print(f"Connected guilds ({len(bot.guilds)}):")
        for g in bot.guilds:
            print(f"  - Guild: {g.name} (ID: {g.id}) | Members: {g.member_count}")
        
        # Test finding the lounge channel
        ch = bot.get_channel(int(settings.discord_lounge_channel_id))
        if ch:
            print(f"Found target channel: #{ch.name} (ID: {ch.id})")
            embed = discord.Embed(
                title="🐝 AgentHive V2 Swarm — Gateway Activated",
                description=(
                    "**AgentHive V2** is now **ONLINE** and synchronized with the **MindHive** command centre!\n\n"
                    "⚡ **ChatGPT Codex** (Chief Software Architect)\n"
                    "🚀 **AGY** (Systems Integration & Sandboxing)\n"
                    "🔮 **Google Gemini** (Deep Reasoning & QA)\n"
                    "👑 **Hermes Supervisor** (Synthesis & Consensus)\n\n"
                    "Type `/newproject` to initialize a project swarm."
                ),
                color=0x10b981
            )
            embed.set_footer(text="AgentHive V2 • Sovereign Human-in-the-Loop Multi-Agent Platform")
            msg = await ch.send(embed=embed)
            print(f"Sent activation announcement to #{ch.name}! (Message ID: {msg.id})")
        else:
            print(f"Channel ID {settings.discord_lounge_channel_id} not found in cache. Attempting fetch...")
            try:
                ch = await bot.fetch_channel(int(settings.discord_lounge_channel_id))
                print(f"Fetched channel: #{ch.name}")
            except Exception as e:
                print(f"Could not fetch channel: {e}")
        
        # Keep alive briefly then exit test
        await asyncio.sleep(2)
        await bot.close()

    try:
        await bot.start(token)
    except Exception as e:
        print(f"Gateway connection error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_gateway())
