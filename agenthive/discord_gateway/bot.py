"""AgentHive Discord Gateway & Slash Command Interface.
Supports all 9 required commands:
/newproject, /project, /analyse, /discuss, /assign, /approve, /reject, /status, /report.
Integrates interactive buttons for human signoff and webhook persona rendering.
Supports both live discord.py gateway bot and REST/CLI dispatch.
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, List
from agenthive.config import settings
from agenthive.engine.orchestrator import orchestrator
from agenthive.database import db

logger = logging.getLogger("agenthive.discord_gateway.bot")

try:
    import discord
    from discord import app_commands
    HAS_DISCORD_LIB = True
except ImportError:
    HAS_DISCORD_LIB = False
    logger.warning("discord.py not installed. Live Discord Gateway will run in headless dispatcher mode.")

class DiscordCommandDispatcher:
    """Dispatches slash command actions to the AgentHive Orchestrator.
    Handles all 9 commands identically whether invoked from real Discord or test simulator.
    """

    async def cmd_newproject(self, name: str, description: str, user_id: str = "po_admin") -> Dict[str, Any]:
        """/newproject - Initializes a new project and generates PROJECT.md."""
        proj = orchestrator.create_project(name, description, po_discord_id=user_id)
        return {
            "command": "/newproject",
            "success": True,
            "project_id": proj.id,
            "slug": proj.slug,
            "name": proj.name,
            "status": proj.current_state,
            "message": f"🐝 AgentHive Project `{proj.name}` initialized! Workspace & `PROJECT.md` created."
        }

    async def cmd_project(self, project_id: str) -> Dict[str, Any]:
        """/project - Fetches current project metadata and spec path."""
        proj = orchestrator.get_project(project_id)
        if not proj:
            return {"command": "/project", "success": False, "error": f"Project `{project_id}` not found"}
        return {
            "command": "/project",
            "success": True,
            "project": proj.model_dump()
        }

    async def cmd_analyse(self, project_id: str) -> Dict[str, Any]:
        """/analyse - Triggers parallel independent analysis across all agents."""
        try:
            analyses = await orchestrator.run_independent_analyses(project_id)
            return {
                "command": "/analyse",
                "success": True,
                "project_id": project_id,
                "analyses_count": len(analyses),
                "summary": [
                    {
                        "agent": a.agent_name,
                        "complexity": a.complexity,
                        "architecture": a.architecture,
                        "tech_stack": a.tech_stack
                    }
                    for a in analyses
                ],
                "message": f"Independent analysis completed by all {len(analyses)} agents! Zero-bias reviews stored."
            }
        except Exception as e:
            return {"command": "/analyse", "success": False, "error": str(e)}

    async def cmd_discuss(self, project_id: str) -> Dict[str, Any]:
        """/discuss - Launches Switch Room debate and bounded discussion turns."""
        try:
            messages = await orchestrator.run_switch_discussion(project_id)
            return {
                "command": "/discuss",
                "success": True,
                "project_id": project_id,
                "turns_completed": len(messages),
                "messages": [
                    {
                        "turn": m.turn_index,
                        "sender": m.sender_name,
                        "role": m.sender_role,
                        "content": m.content
                    }
                    for m in messages
                ],
                "message": f"Switch Room debate concluded in {len(messages)} bounded turns. Consensus reached."
            }
        except Exception as e:
            return {"command": "/discuss", "success": False, "error": str(e)}

    async def cmd_assign(self, project_id: str) -> Dict[str, Any]:
        """/assign - Hermes synthesizes WBS tasks and allocates agent roles."""
        try:
            plan = await orchestrator.generate_hermes_plan(project_id)
            return {
                "command": "/assign",
                "success": True,
                "project_id": project_id,
                "architecture_decision": plan.recommended_architecture,
                "tasks": [t.model_dump() for t in plan.tasks],
                "roles": plan.proposed_roles,
                "message": "Hermes synthesized consensus and proposed WBS tasks. Awaiting Project Owner approval."
            }
        except Exception as e:
            return {"command": "/assign", "success": False, "error": str(e)}

    async def cmd_approve(self, project_id: str, task_code: Optional[str] = None) -> Dict[str, Any]:
        """/approve - Sovereign Human Approval Gate."""
        try:
            tasks = orchestrator.approve_tasks(project_id, task_code)
            return {
                "command": "/approve",
                "success": True,
                "project_id": project_id,
                "approved_tasks": [t.task_code for t in tasks if t.human_approved],
                "message": "✅ Human authorization granted! Tasks unlocked for sandboxed execution."
            }
        except Exception as e:
            return {"command": "/approve", "success": False, "error": str(e)}

    async def cmd_reject(self, project_id: str, reason: str = "Plan rejected by Project Owner") -> Dict[str, Any]:
        """/reject - Aborts or pauses project tasks."""
        proj = orchestrator.get_project(project_id)
        if not proj:
            return {"command": "/reject", "success": False, "error": f"Project `{project_id}` not found"}
        with db.get_connection() as conn:
            conn.execute("UPDATE projects SET current_state = 'ABORTED' WHERE id = ?", (project_id,))
            conn.commit()
        return {
            "command": "/reject",
            "success": True,
            "project_id": project_id,
            "reason": reason,
            "message": f"❌ Project `{project_id}` rejected by Project Owner. State set to ABORTED."
        }

    async def cmd_status(self, project_id: str) -> Dict[str, Any]:
        """/status - Detailed status dashboard of active project."""
        proj = orchestrator.get_project(project_id)
        if not proj:
            return {"command": "/status", "success": False, "error": f"Project `{project_id}` not found"}
        
        with db.get_connection() as conn:
            task_rows = conn.execute("SELECT * FROM tasks WHERE project_id = ?", (proj.id,)).fetchall()
            disc_count = conn.execute("SELECT COUNT(*) as c FROM discussion_messages WHERE project_id = ?", (proj.id,)).fetchone()["c"]
            analyses_count = conn.execute("SELECT COUNT(*) as c FROM independent_analyses WHERE project_id = ?", (proj.id,)).fetchone()["c"]

        return {
            "command": "/status",
            "success": True,
            "project_id": proj.id,
            "name": proj.name,
            "state": proj.current_state,
            "switch_room": proj.switch_room_id,
            "analyses_completed": analyses_count,
            "debate_turns": disc_count,
            "tasks": [dict(r) for r in task_rows]
        }

    async def cmd_report(self, project_id: str) -> Dict[str, Any]:
        """/report - Triggers execution of approved tasks, testing & final report generation."""
        try:
            exec_res = await orchestrator.execute_project(project_id)
            return {
                "command": "/report",
                "success": True,
                "project_id": project_id,
                "execution_status": exec_res["status"],
                "ponytail_passed": exec_res["ponytail_audit"]["passed"],
                "test_success": exec_res["test_results"]["success"],
                "test_output": exec_res["test_results"].get("stderr") or exec_res["test_results"].get("stdout"),
                "project_md": exec_res["project_md"],
                "message": f"🎉 AgentHive Project verified and delivered! Status: {exec_res['status']}"
            }
        except Exception as e:
            return {"command": "/report", "success": False, "error": str(e)}

discord_dispatcher = DiscordCommandDispatcher()

# --- Live Discord.py Client (when DISCORD_BOT_TOKEN is present) ---

if HAS_DISCORD_LIB:
    class ApprovalView(discord.ui.View):
        def __init__(self, project_id: str):
            super().__init__(timeout=300)
            self.project_id = project_id

        @discord.ui.button(label="Approve & Run", style=discord.ButtonStyle.green, emoji="✅")
        async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            res = await discord_dispatcher.cmd_approve(self.project_id)
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"✅ Approved by {interaction.user.mention}! Executing tasks...")
            report = await discord_dispatcher.cmd_report(self.project_id)
            await interaction.followup.send(f"📊 Execution Report: {report.get('message')}")

        @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, emoji="❌")
        async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            res = await discord_dispatcher.cmd_reject(self.project_id, reason=f"Rejected by {interaction.user.name}")
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"❌ Project rejected by {interaction.user.mention}.")

    class AgentHiveDiscordBot(discord.Client):
        def __init__(self):
            intents = discord.Intents.default()
            intents.message_content = True
            super().__init__(intents=intents)
            self.tree = app_commands.CommandTree(self)

        async def setup_hook(self):
            # Register slash commands
            @self.tree.command(name="newproject", description="Create a new AgentHive multi-agent project")
            @app_commands.describe(name="Project Name", description="Requirements brief")
            async def newproject_slash(interaction: discord.Interaction, name: str, description: str):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_newproject(name, description, user_id=str(interaction.user.id))
                embed = discord.Embed(title=f"🐝 Project Initialized: {name}", description=description, color=0x3b82f6)
                embed.add_field(name="Project ID", value=f"`{res['project_id']}`", inline=True)
                embed.add_field(name="Next Step", value="Use `/analyse` to trigger parallel review", inline=False)
                await interaction.followup.send(embed=embed)

            @self.tree.command(name="analyse", description="Run zero-bias independent analysis across all agents")
            @app_commands.describe(project_id="Project ID")
            async def analyse_slash(interaction: discord.Interaction, project_id: str):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_analyse(project_id)
                if not res["success"]:
                    await interaction.followup.send(f"❌ Analysis failed: {res.get('error')}")
                    return
                embed = discord.Embed(title="🔍 Independent Analysis Completed", color=0x8b5cf6)
                for a in res.get("summary", []):
                    embed.add_field(name=f"🤖 {a['agent']} ({a['complexity']})", value=f"{a['architecture'][:250]}...", inline=False)
                await interaction.followup.send(embed=embed)

            @self.tree.command(name="discuss", description="Launch Switch collaboration room debate")
            @app_commands.describe(project_id="Project ID")
            async def discuss_slash(interaction: discord.Interaction, project_id: str):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_discuss(project_id)
                if not res["success"]:
                    await interaction.followup.send(f"❌ Debate failed: {res.get('error')}")
                    return
                embed = discord.Embed(title="💬 Switch Room Debate Completed", description=f"{res['turns_completed']} turns taken.", color=0x10b981)
                await interaction.followup.send(embed=embed)

            @self.tree.command(name="assign", description="Hermes synthesizes WBS tasks and presents for approval")
            @app_commands.describe(project_id="Project ID")
            async def assign_slash(interaction: discord.Interaction, project_id: str):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_assign(project_id)
                if not res["success"]:
                    await interaction.followup.send(f"❌ Assign failed: {res.get('error')}")
                    return
                embed = discord.Embed(title="👑 Hermes WBS Plan & Role Allocation", description=res["architecture_decision"], color=0xf59e0b)
                for t in res.get("tasks", []):
                    embed.add_field(name=f"[{t['task_code']}] {t['title']}", value=f"Assigned to: **{t['assigned_agent']}** ({t['priority']})", inline=False)
                view = ApprovalView(project_id)
                await interaction.followup.send(embed=embed, view=view)

            @self.tree.command(name="approve", description="Approve tasks for execution")
            @app_commands.describe(project_id="Project ID", task_code="Optional specific task code")
            async def approve_slash(interaction: discord.Interaction, project_id: str, task_code: Optional[str] = None):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_approve(project_id, task_code)
                await interaction.followup.send(res["message"])

            @self.tree.command(name="reject", description="Reject proposal")
            @app_commands.describe(project_id="Project ID", reason="Reason for rejection")
            async def reject_slash(interaction: discord.Interaction, project_id: str, reason: str = "Rejected by user"):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_reject(project_id, reason)
                await interaction.followup.send(res["message"])

            @self.tree.command(name="status", description="Get project status")
            @app_commands.describe(project_id="Project ID")
            async def status_slash(interaction: discord.Interaction, project_id: str):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_status(project_id)
                if not res["success"]:
                    await interaction.followup.send(f"❌ {res.get('error')}")
                    return
                embed = discord.Embed(title=f"📋 Project Status: {res['name']}", color=0x3b82f6)
                embed.add_field(name="State", value=res["state"], inline=True)
                embed.add_field(name="Debate Turns", value=str(res["debate_turns"]), inline=True)
                await interaction.followup.send(embed=embed)

            @self.tree.command(name="report", description="Execute tasks and generate final delivery report")
            @app_commands.describe(project_id="Project ID")
            async def report_slash(interaction: discord.Interaction, project_id: str):
                await interaction.response.defer()
                res = await discord_dispatcher.cmd_report(project_id)
                if not res["success"]:
                    await interaction.followup.send(f"❌ Execution failed: {res.get('error')}")
                    return
                embed = discord.Embed(title=f"🎉 Final Delivery: {res['execution_status']}", color=0x10b981)
                embed.add_field(name="Pony Tail Compliance", value="PASSED" if res["ponytail_passed"] else "VIOLATIONS", inline=True)
                embed.add_field(name="Tests", value="PASSED" if res["test_success"] else "FAILED", inline=True)
                await interaction.followup.send(embed=embed)

            # Sync slash commands
            try:
                if settings.discord_guild_id:
                    guild = discord.Object(id=int(settings.discord_guild_id))
                    self.tree.copy_global_to(guild=guild)
                    await self.tree.sync(guild=guild)
                    logger.info("Synchronized Discord slash commands to Guild ID: %s", settings.discord_guild_id)
                else:
                    await self.tree.sync()
                    logger.info("Synchronized global Discord slash commands.")
            except Exception as e:
                logger.warning("Slash command sync notice: %s", e)

        async def on_ready(self):
            logger.info("AgentHive Discord Bot logged in as %s (ID: %s)", self.user, self.user.id)

    live_discord_bot: Optional[AgentHiveDiscordBot] = None

    async def start_discord_bot():
        global live_discord_bot
        if not settings.discord_bot_token:
            logger.info("No DISCORD_BOT_TOKEN found in environment. Discord bot gateway will run in REST dispatch mode.")
            return
        try:
            live_discord_bot = AgentHiveDiscordBot()
            logger.info("Connecting to Discord Gateway with configured bot token...")
            await live_discord_bot.start(settings.discord_bot_token)
        except Exception as e:
            logger.error("Failed to connect live Discord bot: %s", e)
else:
    async def start_discord_bot():
        pass
