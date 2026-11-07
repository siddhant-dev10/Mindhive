"""Interactive UI Components for AgentHive Discord Gateway.
Provides interactive Approval/Rejection buttons, modals, authorization checks,
anti-tamper double-click guards, and timeout handlers.
"""

import logging
from typing import Optional
from agenthive.discord_gateway.dispatcher import discord_dispatcher
from agenthive.discord_gateway.embeds import (
    build_report_embed,
    build_error_embed,
    COLOR_GREEN,
    COLOR_RED,
)

logger = logging.getLogger("agenthive.discord_gateway.views")

try:
    import discord
    from discord import ui
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False


if HAS_DISCORD:
    class RejectionModal(ui.Modal, title="Reject Project Proposal"):
        reason_input = ui.TextInput(
            label="Reason for Rejection",
            style=discord.TextStyle.paragraph,
            placeholder="Explain why the architecture or WBS proposal is rejected...",
            required=True,
            max_length=500
        )

        def __init__(self, project_id: str, parent_view: "ApprovalView"):
            super().__init__()
            self.project_id = project_id
            self.parent_view = parent_view

        async def on_submit(self, interaction: discord.Interaction):
            reason = self.reason_input.value.strip()
            self.parent_view.disable_all()
            if self.parent_view.message:
                try:
                    await self.parent_view.message.edit(view=self.parent_view)
                except Exception:
                    pass

            res = await discord_dispatcher.cmd_reject(
                self.project_id,
                reason=reason,
                actor_id=str(interaction.user.id),
            )
            if res.get("success"):
                embed = discord.Embed(
                    title="❌ Proposal Rejected",
                    description=f"Project `{self.project_id}` has been aborted.",
                    color=COLOR_RED
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.set_footer(text=f"Rejected by {interaction.user.display_name}")
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ Failed to abort project: {res.get('error')}", ephemeral=True)


    class ApprovalView(ui.View):
        """Interactive View providing sovereign human approval or rejection buttons."""

        def __init__(
            self,
            project_id: str,
            po_discord_id: Optional[str] = None,
            project_name: Optional[str] = None,
            timeout: float = 600.0
        ):
            super().__init__(timeout=timeout)
            self.project_id = project_id
            self.po_discord_id = po_discord_id
            self.project_name = project_name or project_id
            self.is_processing = False
            self.message: Optional[discord.Message] = None

        def disable_all(self):
            """Disables all buttons in the view."""
            for child in self.children:
                if isinstance(child, ui.Button):
                    child.disabled = True

        def _is_authorized(self, interaction: discord.Interaction) -> bool:
            """Checks whether the configured Discord owner is signing off."""
            from agenthive.config import settings
            return bool(
                settings.discord_owner_id
                and str(interaction.user.id) == str(settings.discord_owner_id)
                and self.po_discord_id == str(settings.discord_owner_id)
            )

        @ui.button(label="Approve Plan", style=discord.ButtonStyle.green, emoji="✅", custom_id="agenthive_approve_btn")
        async def approve_button(self, interaction: discord.Interaction, button: ui.Button):
            if not self._is_authorized(interaction):
                await interaction.response.send_message(
                    f"⛔ **Unauthorized:** Only the configured Project Owner (<@{self.po_discord_id}>) can sign off on this plan.",
                    ephemeral=True
                )
                return

            if self.is_processing:
                await interaction.response.send_message("⏳ Approval is already being recorded. Please wait.", ephemeral=True)
                return

            self.is_processing = True
            self.disable_all()
            button.label = "Approval Recorded"
            button.style = discord.ButtonStyle.secondary

            await interaction.response.edit_message(view=self)

            app_res = await discord_dispatcher.cmd_approve(
                self.project_id,
                actor_id=str(interaction.user.id),
            )
            if not app_res.get("success"):
                self.is_processing = False
                await interaction.followup.send(f"❌ Failed to record task approval: {app_res.get('error')}")
                return
            self.is_processing = False
            await interaction.followup.send(
                f"✅ **Owner approval recorded by {interaction.user.mention}.** "
                "No tasks were executed. Use `/report` as a separate action when you are ready."
            )

        @ui.button(label="Reject Proposal", style=discord.ButtonStyle.red, emoji="❌", custom_id="agenthive_reject_btn")
        async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
            if not self._is_authorized(interaction):
                await interaction.response.send_message(
                    f"⛔ **Unauthorized:** Only the Project Owner (<@{self.po_discord_id}>) can reject this proposal.",
                    ephemeral=True
                )
                return

            if self.is_processing:
                await interaction.response.send_message("⏳ Action in progress. Please wait.", ephemeral=True)
                return

            # Open rejection modal
            modal = RejectionModal(self.project_id, self)
            await interaction.response.send_modal(modal)

        async def on_timeout(self):
            """Handles view timeout gracefully by disabling buttons."""
            self.disable_all()
            if self.message:
                try:
                    await self.message.edit(
                        content="⚠️ *(Proposal interaction timed out. Use `/assign` or `/approve` to resume)*",
                        view=self
                    )
                except Exception as e:
                    logger.debug("Failed to update message on timeout: %s", e)

        async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
            logger.error("Error in ApprovalView component %s: %s", item, error, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An unexpected error occurred handling this interaction.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An unexpected error occurred handling this interaction.", ephemeral=True)
else:
    class ApprovalView:
        def __init__(self, *args, **kwargs):
            pass
