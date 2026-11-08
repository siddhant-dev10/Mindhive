"""AgentHive Production-Ready Discord Gateway & Slash Command Interface.
Supports all 9 required commands:
/newproject, /project, /analyse, /discuss, /assign, /approve, /reject, /status, /report.
Integrates interactive approval/rejection buttons, rich multi-agent persona embeds,
Switch room creation, thread mirroring, and headless REST/CLI dispatch.
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict, Any, List

from agenthive.config import settings
from agenthive.database import db
from agenthive.discord_gateway.dispatcher import discord_dispatcher, DiscordCommandDispatcher
from agenthive.discord_gateway.embeds import (
    build_newproject_embed,
    build_project_embed,
    build_analysis_embeds,
    build_discussion_embeds,
    build_assign_embed,
    build_status_embed,
    build_report_embed,
    build_error_embed,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_BLUE,
)
from agenthive.discord_gateway.views import ApprovalView

logger = logging.getLogger("agenthive.discord_gateway.bot")

try:
    import discord
    from discord import app_commands
    HAS_DISCORD_LIB = True
except ImportError:
    HAS_DISCORD_LIB = False
    logger.warning("discord.py not installed. Discord Gateway will operate in headless dispatcher mode.")


if HAS_DISCORD_LIB:
    class AgentHiveDiscordBot(discord.Client):
        """Production Discord Bot Client powering the AgentHive command centre."""

        def __init__(self):
            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True
            super().__init__(intents=intents)
            self.tree = app_commands.CommandTree(self)
            self._processed_messages: Dict[int, float] = {}
            self._register_commands()

        def _cleanup_processed_messages(self, ttl_seconds: float = 60.0):
            now = time.monotonic()
            expired = [mid for mid, ts in self._processed_messages.items() if now - ts > ttl_seconds]
            for mid in expired:
                del self._processed_messages[mid]

        def _chunk_text(self, text: str, limit: int = 1950) -> List[str]:
            if not text:
                return [""]
            if len(text) <= limit:
                return [text]

            chunks = []
            current = ""
            for line in text.split("\n"):
                if len(current) + len(line) + 1 > limit:
                    if current:
                        chunks.append(current.strip())
                        current = ""
                    if len(line) > limit:
                        for sub in [line[i:i+limit] for i in range(0, len(line), limit)]:
                            chunks.append(sub)
                    else:
                        current = line + "\n"
                else:
                    current += line + "\n"
            if current.strip():
                chunks.append(current.strip())
            return chunks or [text[:limit]]

        def _is_project_owner(self, interaction: discord.Interaction) -> bool:
            """Fail closed unless the configured owner ID matches this Discord user."""
            return bool(settings.discord_owner_id and str(interaction.user.id) == str(settings.discord_owner_id))

        async def _require_project_owner(self, interaction: discord.Interaction) -> bool:
            if self._is_project_owner(interaction):
                return True
            await interaction.response.send_message(
                "⛔ Only the configured MindHive project owner can use AgentHive project commands.",
                ephemeral=True,
            )
            return False

        def _register_commands(self):
            """Registers all 9 AgentHive slash commands onto the command tree."""

            # 1. /newproject
            @self.tree.command(name="newproject", description="Initialize a new AgentHive multi-agent project")
            @app_commands.describe(name="Project Name (e.g. CacheFlow)", description="Detailed project brief and constraints")
            async def newproject_slash(interaction: discord.Interaction, name: str, description: str):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                user_id = str(interaction.user.id)
                res = await discord_dispatcher.cmd_newproject(name, description, user_id=user_id)

                if not res.get("success"):
                    err_embed = build_error_embed("/newproject", res.get("error", "Project creation failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                thread_mention = None
                if interaction.guild and hasattr(interaction.channel, "create_thread"):
                    try:
                        thread = await interaction.channel.create_thread(
                            name=f"🐝 {res['name']} War Room",
                            auto_archive_duration=1440,
                            reason=f"AgentHive War Room for {res['slug']}"
                        )
                        thread_mention = thread.mention
                        with db.get_connection() as conn:
                            conn.execute(
                                "UPDATE projects SET discord_channel_id = ?, discord_thread_id = ? WHERE id = ?",
                                (str(interaction.channel_id), str(thread.id), res["project_id"])
                            )
                            conn.commit()
                        logger.info("Created Discord War Room thread %s (%s)", thread.name, thread.id)
                    except Exception as te:
                        logger.debug("Discord thread creation notice: %s", te)

                embed = build_newproject_embed(res, thread_mention=thread_mention)
                await interaction.followup.send(embed=embed)

            # 2. /project
            @self.tree.command(name="project", description="Inspect an AgentHive project specification and metadata")
            @app_commands.describe(project_id="Project ID or slug")
            async def project_slash(interaction: discord.Interaction, project_id: str):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_project(project_id, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/project", res.get("error", "Project not found"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embed = build_project_embed(res.get("project", {}))
                await interaction.followup.send(embed=embed)

            # 3. /analyse
            @self.tree.command(name="analyse", description="Record available agent analyses and explicit fallback or unavailable statuses")
            @app_commands.describe(project_id="Project ID or slug")
            async def analyse_slash(interaction: discord.Interaction, project_id: str):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_analyse(project_id, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/analyse", res.get("error", "Analysis failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embeds = build_analysis_embeds(
                    project_name=res.get("project_name", project_id),
                    project_id=res.get("project_id", project_id),
                    summary=res.get("summary", [])
                )
                # Discord allows up to 10 embeds per message
                await interaction.followup.send(embeds=embeds[:10])

            # 4. /discuss
            @self.tree.command(name="discuss", description="Launch Switch collaboration room multi-agent debate")
            @app_commands.describe(project_id="Project ID or slug")
            async def discuss_slash(interaction: discord.Interaction, project_id: str):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_discuss(project_id, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/discuss", res.get("error", "Debate failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embeds = build_discussion_embeds(
                    project_name=res.get("project_name", project_id),
                    project_id=res.get("project_id", project_id),
                    messages=res.get("messages", [])
                )
                await interaction.followup.send(embeds=embeds[:10])

            # 5. /assign
            @self.tree.command(name="assign", description="Prepare a discussion-linked task proposal for owner review")
            @app_commands.describe(project_id="Project ID or slug")
            async def assign_slash(interaction: discord.Interaction, project_id: str):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_assign(project_id, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/assign", res.get("error", "Task allocation failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embed = build_assign_embed(
                    project_name=res.get("project_name", project_id),
                    project_id=res.get("project_id", project_id),
                    assign_data=res
                )
                view = ApprovalView(
                    project_id=res.get("project_id", project_id),
                    po_discord_id=str(settings.discord_owner_id or ""),
                    project_name=res.get("project_name", project_id)
                )
                msg = await interaction.followup.send(embed=embed, view=view)
                view.message = msg

            # 6. /approve
            @self.tree.command(name="approve", description="Sovereign Human Approval Gate: Authorize tasks for execution")
            @app_commands.describe(project_id="Project ID or slug", task_code="Optional specific task code (e.g. TASK-01)")
            async def approve_slash(interaction: discord.Interaction, project_id: str, task_code: Optional[str] = None):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_approve(project_id, task_code, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/approve", res.get("error", "Approval failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embed = discord.Embed(
                    title="✅ Sovereign Human Authorization Granted",
                    description=res.get("message", "Tasks unlocked."),
                    color=COLOR_GREEN
                )
                embed.add_field(name="Project ID", value=f"`{res.get('project_id')}`", inline=True)
                embed.add_field(name="Authorized Tasks", value=f"`{', '.join(res.get('approved_tasks', []))}`", inline=False)
                embed.add_field(name="Next Step", value="Run `/report` to execute tasks and verify results.", inline=False)
                await interaction.followup.send(embed=embed)

            # 7. /reject
            @self.tree.command(name="reject", description="Reject proposal and abort project execution")
            @app_commands.describe(project_id="Project ID or slug", reason="Reason for rejection")
            async def reject_slash(interaction: discord.Interaction, project_id: str, reason: str = "Plan rejected by Project Owner"):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_reject(project_id, reason, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/reject", res.get("error", "Rejection failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embed = discord.Embed(
                    title="❌ Project Aborted",
                    description=res.get("message", "Project aborted."),
                    color=COLOR_RED
                )
                embed.add_field(name="Project ID", value=f"`{res.get('project_id')}`", inline=True)
                embed.add_field(name="Reason", value=res.get("reason", reason), inline=False)
                await interaction.followup.send(embed=embed)

            # 8. /status
            @self.tree.command(name="status", description="Inspect active status dashboard for an AgentHive project")
            @app_commands.describe(project_id="Project ID or slug")
            async def status_slash(interaction: discord.Interaction, project_id: str):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_status(project_id, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/status", res.get("error", "Status fetch failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embed = build_status_embed(res)
                await interaction.followup.send(embed=embed)

            # 9. /report
            @self.tree.command(name="report", description="Execute approved tasks, run tests, and generate delivery report")
            @app_commands.describe(project_id="Project ID or slug")
            async def report_slash(interaction: discord.Interaction, project_id: str):
                if not await self._require_project_owner(interaction):
                    return
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_report(project_id, actor_id=str(interaction.user.id))
                if not res.get("success"):
                    err_embed = build_error_embed("/report", res.get("error", "Execution failed"))
                    await interaction.followup.send(embed=err_embed)
                    return

                embed = build_report_embed(
                    project_name=res.get("project_name", project_id),
                    report_data=res
                )
                await interaction.followup.send(embed=embed)

            # 10. /ask
            @self.tree.command(name="ask", description="Engage MindHive conversational Engineering Manager or request repository analysis")
            @app_commands.describe(query="Your question, instruction, or workflow request", repo="Optional GitHub repository URL or target path")
            async def ask_slash(interaction: discord.Interaction, query: str, repo: Optional[str] = None):
                await interaction.response.defer()
                user_id = str(interaction.user.id)
                res = await discord_dispatcher.handle_conversational_message(
                    text=query,
                    user_id=user_id,
                    context_id=f"channel_{interaction.channel_id}",
                    target_repo=repo,
                )
                reply = res.get("response_text", "No response generated.")
                chunks = self._chunk_text(reply)

                view = None
                if res.get("requires_approval") and res.get("project_id"):
                    view = ApprovalView(
                        project_id=res["project_id"],
                        po_discord_id=str(settings.discord_owner_id or ""),
                        project_name=res.get("project_name", res["project_id"])
                    )

                if len(chunks) == 1:
                    if view:
                        msg = await interaction.followup.send(chunks[0], view=view)
                        view.message = msg
                    else:
                        await interaction.followup.send(chunks[0])
                else:
                    await interaction.followup.send(chunks[0])
                    for i, chunk in enumerate(chunks[1:]):
                        is_last = (i == len(chunks) - 2)
                        if is_last and view:
                            msg = await interaction.channel.send(chunk, view=view)
                            view.message = msg
                        else:
                            await interaction.channel.send(chunk)

            # Global Tree Error Handler
            @self.tree.error
            async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
                logger.error("Unhandled slash command error for user %s: %s", interaction.user, error, exc_info=True)
                err_msg = str(getattr(error, "original", error))
                embed = build_error_embed("Slash Command", err_msg)
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logger.debug("Failed sending error response to interaction: %s", e)

        async def setup_hook(self):
            """Syncs slash commands to the configured guild or globally."""
            try:
                if settings.discord_guild_id and settings.discord_guild_id.strip():
                    guild = discord.Object(id=int(settings.discord_guild_id.strip()))
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    logger.info("Synchronized %d Discord slash commands to Guild ID: %s", len(synced), settings.discord_guild_id)
                else:
                    synced = await self.tree.sync()
                    logger.info("Synchronized %d global Discord slash commands.", len(synced))
            except Exception as e:
                logger.warning("Slash command synchronization notice: %s", e)

        async def on_ready(self):
            logger.info("AgentHive Discord Bot logged in as %s (ID: %s)", self.user, self.user.id)
            guild_names = [g.name for g in self.guilds]
            logger.info("Connected to %d guild(s): %s", len(self.guilds), ", ".join(guild_names) if guild_names else "None")
            try:
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Agent Swarm | /newproject"
                )
                await self.change_presence(status=discord.Status.online, activity=activity)
            except Exception as e:
                logger.debug("Failed setting bot presence: %s", e)

        async def on_message(self, message: discord.Message):
            """Listens for direct bot mentions or DMs to trigger conversational engineering management."""
            if message.author.bot or (self.user and message.author.id == self.user.id):
                return

            # Check if bot is mentioned or if it is a private DM
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = bool(self.user and self.user in message.mentions)
            if not is_dm and not is_mentioned:
                return

            # Deduplication check
            self._cleanup_processed_messages()
            if message.id in self._processed_messages:
                return
            self._processed_messages[message.id] = time.monotonic()

            # Strip mention tags from content
            raw_content = message.content or ""
            if self.user:
                clean_content = re.sub(rf"<@!?{self.user.id}>", "", raw_content).strip()
            else:
                clean_content = raw_content.strip()

            logger.info("Received conversational message from user %s (%s): %s", message.author, message.author.id, clean_content[:80])

            try:
                async with message.channel.typing():
                    res = await discord_dispatcher.handle_conversational_message(
                        text=clean_content or "hello",
                        user_id=str(message.author.id),
                        context_id=f"channel_{message.channel.id}",
                    )

                reply_text = res.get("response_text", "No response generated.")
                chunks = self._chunk_text(reply_text)

                view = None
                if res.get("requires_approval") and res.get("project_id"):
                    view = ApprovalView(
                        project_id=res["project_id"],
                        po_discord_id=str(settings.discord_owner_id or ""),
                        project_name=res.get("project_name", res["project_id"])
                    )

                for i, chunk in enumerate(chunks):
                    is_last = (i == len(chunks) - 1)
                    if is_last and view:
                        msg = await message.reply(chunk, view=view, mention_author=False)
                        view.message = msg
                    else:
                        await message.reply(chunk, mention_author=False)
            except Exception as e:
                logger.error("Error processing conversational message: %s", e, exc_info=True)
                try:
                    await message.reply(f"⚠️ **Error:** {str(e)}", mention_author=False)
                except Exception:
                    pass

    live_discord_bot: Optional[AgentHiveDiscordBot] = None

    async def start_discord_bot():
        global live_discord_bot
        if not settings.discord_bot_token or not settings.discord_bot_token.strip():
            logger.info("No DISCORD_BOT_TOKEN found in environment. Gateway running in headless dispatcher mode.")
            return

        try:
            live_discord_bot = AgentHiveDiscordBot()
            logger.info("Authenticating with Discord Gateway using configured bot token...")
            await live_discord_bot.start(settings.discord_bot_token.strip())
        except discord.errors.LoginFailure:
            logger.error("Authentication rejected by Discord: DISCORD_BOT_TOKEN appears invalid. Bot offline.")
        except discord.errors.PrivilegedIntentsRequired:
            logger.error("Gateway error: Privileged Message Content Intent not enabled in Discord Developer Portal.")
        except Exception as e:
            logger.error("Failed to connect live Discord bot: %s", e, exc_info=True)

else:
    class AgentHiveDiscordBot:
        pass

    live_discord_bot = None

    async def start_discord_bot():
        logger.info("discord.py is not installed. Gateway running in headless dispatcher mode.")
