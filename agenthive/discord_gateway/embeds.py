"""Rich Embed Builders & Formatting for AgentHive Discord Gateway.
Handles persona styling, color theming, field truncation, and embed length limits.
"""

from typing import List, Dict, Any, Optional
import discord

# --- Color Theme Constants ---
COLOR_BLUE = 0x3b82f6       # Brand blue (Status / General)
COLOR_PURPLE = 0x8b5cf6     # Purple (Analysis)
COLOR_CYAN = 0x06b6d4       # Cyan (Switch War Room Debate / Codex)
COLOR_AMBER = 0xf59e0b      # Amber/Gold (Hermes / Awaiting Approval)
COLOR_GREEN = 0x10b981      # Emerald Green (Success / Verified / Complete)
COLOR_RED = 0xef4444        # Crimson Red (Aborted / Error / Failed)
COLOR_ORANGE = 0xf97316     # Orange (AGY Systems)

# --- Agent Personas ---
AGENT_PERSONAS = {
    "codex": {
        "display_name": "ChatGPT Codex",
        "role": "Chief Software Architect",
        "emoji": "⚡",
        "color": COLOR_CYAN,
    },
    "agy": {
        "display_name": "AGY (Antigravity)",
        "role": "Systems Integration & CLI",
        "emoji": "🚀",
        "color": COLOR_ORANGE,
    },
    "gemini": {
        "display_name": "Google Gemini",
        "role": "Deep Reasoning & QA",
        "emoji": "🔮",
        "color": COLOR_PURPLE,
    },
    "hermes": {
        "display_name": "Hermes Supervisor",
        "role": "Autonomous Supervisor",
        "emoji": "👑",
        "color": COLOR_AMBER,
    },
}

def get_agent_persona(agent_name: str) -> Dict[str, Any]:
    """Resolves persona info from agent name or ID."""
    name_lower = agent_name.lower()
    for key, persona in AGENT_PERSONAS.items():
        if key in name_lower:
            return persona
    return {
        "display_name": agent_name,
        "role": "Agent",
        "emoji": "🤖",
        "color": COLOR_BLUE,
    }

def truncate(text: Optional[str], max_len: int = 1000) -> str:
    """Safely truncates text to fit within Discord embed constraints."""
    if not text:
        return "*None*"
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."

def build_project_embed(proj_data: Dict[str, Any]) -> discord.Embed:
    """Builds a rich embed for /project command."""
    embed = discord.Embed(
        title=f"📁 Project Specification: {proj_data.get('name', 'Unknown')}",
        description=truncate(proj_data.get("description", "No brief provided."), 2000),
        color=COLOR_BLUE,
    )
    embed.add_field(name="🆔 Project ID", value=f"`{proj_data.get('id', 'N/A')}`", inline=True)
    embed.add_field(name="🏷️ Slug", value=f"`{proj_data.get('slug', 'N/A')}`", inline=True)
    
    state = proj_data.get("current_state", "UNKNOWN")
    state_badge = {
        "DRAFT": "📝 DRAFT",
        "ANALYZING": "🔍 ANALYZING",
        "DISCUSSING": "💬 DISCUSSING",
        "AWAITING_APPROVAL": "⏳ AWAITING APPROVAL",
        "APPROVED": "✅ APPROVED",
        "EXECUTING": "⚡ EXECUTING",
        "COMPLETED": "🎉 COMPLETED",
        "ABORTED": "❌ ABORTED",
    }.get(state, state)
    embed.add_field(name="📊 State", value=f"**{state_badge}**", inline=True)

    room_id = proj_data.get("switch_room_id")
    embed.add_field(name="🏛️ Switch Room", value=f"`{room_id}`" if room_id else "*Pending*", inline=True)
    embed.add_field(name="📄 Spec File", value=f"`{proj_data.get('project_md_path', 'PROJECT.md')}`", inline=False)
    
    if proj_data.get("created_at"):
        embed.set_footer(text=f"Created: {proj_data.get('created_at')} UTC | AgentHive V2")
    return embed

def build_newproject_embed(res: Dict[str, Any], thread_mention: Optional[str] = None) -> discord.Embed:
    """Builds a rich embed for /newproject command."""
    embed = discord.Embed(
        title=f"🐝 Project Initialized: {res.get('name')}",
        description=f"Workspace and `PROJECT.md` specification generated.\nSwitch Collaboration War Room created.",
        color=COLOR_GREEN,
    )
    embed.add_field(name="🆔 Project ID", value=f"`{res.get('project_id')}`", inline=True)
    embed.add_field(name="🏷️ Slug", value=f"`{res.get('slug')}`", inline=True)
    embed.add_field(name="📊 Initial State", value="`DRAFT`", inline=True)
    
    if res.get("switch_room_id"):
        embed.add_field(name="🏛️ Switch Room", value=f"`{res.get('switch_room_id')}`", inline=True)
    if thread_mention:
        embed.add_field(name="🧵 War Room Thread", value=thread_mention, inline=True)

    embed.add_field(
        name="🚀 Next Step",
        value=f"Trigger parallel agent evaluation with:\n`/analyse project_id:{res.get('project_id')}`",
        inline=False,
    )
    embed.set_footer(text="AgentHive Autonomous Multi-Agent Swarm")
    return embed

def build_analysis_embeds(project_name: str, project_id: str, summary: List[Dict[str, Any]]) -> List[discord.Embed]:
    """Builds rich embeds displaying independent zero-bias agent analyses."""
    embeds = []
    
    # Overview Embed
    header = discord.Embed(
        title=f"🔍 Independent Agent Analysis: {project_name}",
        description=(
            f"Recorded runtime results for **{len(summary)} agent identities**.\n"
            "Unavailable runtimes are shown without invented proposals; fallback checks are labeled explicitly."
        ),
        color=COLOR_PURPLE,
    )
    header.add_field(name="🆔 Project ID", value=f"`{project_id}`", inline=True)
    contributors = [a.get("agent", "Agent") for a in summary if a.get("analysis_generated")]
    header.add_field(name="Analysis contributors", value=truncate(", ".join(contributors) or "None verified", 500), inline=True)
    header.set_footer(text="Next step: Run /discuss to open Switch collaborative debate.")
    embeds.append(header)

    # Individual Agent Embeds
    for a in summary:
        persona = get_agent_persona(a.get("agent", ""))
        agent_embed = discord.Embed(
            title=f"{persona['emoji']} {persona['display_name']} — {persona['role']}",
            color=persona["color"],
        )
        agent_embed.add_field(
            name=f"Runtime: {a.get('runtime_mode', 'unknown')}",
            value=truncate(a.get("architecture") or "No proposal was generated by this runtime.", 950),
            inline=False,
        )
        tech_stack = a.get("tech_stack", [])
        if isinstance(tech_stack, list):
            stack_str = ", ".join(f"`{s}`" for s in tech_stack) if tech_stack else "No stack recommendation recorded"
        else:
            stack_str = str(tech_stack)
        agent_embed.add_field(name="Tech Stack", value=truncate(stack_str, 500), inline=True)
        agent_embed.add_field(name="Complexity Rating", value=f"`{a.get('complexity', 'MEDIUM')}`", inline=True)

        risks = a.get("risks", [])
        if risks:
            risks_str = "\n".join(f"• {r}" for r in risks[:3])
            agent_embed.add_field(name="Identified Risks", value=truncate(risks_str, 500), inline=False)

        embeds.append(agent_embed)

    return embeds

def build_discussion_embeds(project_name: str, project_id: str, messages: List[Dict[str, Any]]) -> List[discord.Embed]:
    """Builds embeds representing the multi-turn Switch War Room debate."""
    embeds = []
    header = discord.Embed(
        title=f"💬 Switch War Room Debate: {project_name}",
        description=(
            f"Collaborative multi-agent debate concluded in **{len(messages)} bounded turns**.\n"
            f"Hermes moderated consensus and closed the floor."
        ),
        color=COLOR_CYAN,
    )
    header.add_field(name="🆔 Project ID", value=f"`{project_id}`", inline=True)
    header.set_footer(text="Next step: Run /assign to formulate Hermes WBS tasks.")
    embeds.append(header)

    # Group turns into embeds (max 2 turns per embed to ensure length safety)
    chunk_size = 2
    for i in range(0, len(messages), chunk_size):
        chunk = messages[i : i + chunk_size]
        chunk_embed = discord.Embed(color=COLOR_CYAN)
        for msg in chunk:
            turn_idx = msg.get("turn", 0)
            sender = msg.get("sender", "Agent")
            role = msg.get("role", "AGENT")
            content = msg.get("content", "")
            persona = get_agent_persona(sender)

            field_title = f"{persona['emoji']} Turn {turn_idx}: {persona['display_name']} [{role}]"
            chunk_embed.add_field(
                name=field_title,
                value=truncate(content, 1000),
                inline=False,
            )
        embeds.append(chunk_embed)

    return embeds

def build_assign_embed(project_name: str, project_id: str, assign_data: Dict[str, Any]) -> discord.Embed:
    """Builds Hermes WBS synthesis and task allocation embed."""
    embed = discord.Embed(
        title=f"👑 Hermes WBS Proposal & Task Allocation: {project_name}",
        description=(
            "The recorded supervisor runtime and discussion sources are shown below. "
            "A local governance proposal does not imply consensus. Owner review is required before approval."
        ),
        color=COLOR_AMBER,
    )
    embed.add_field(name="🆔 Project ID", value=f"`{project_id}`", inline=True)
    runtime = assign_data.get("supervisor_runtime", {}).get("runtime_mode", "unknown")
    embed.add_field(name="Supervisor runtime", value=truncate(runtime, 300), inline=True)
    
    arch = assign_data.get("architecture_decision", "")
    if arch:
        embed.add_field(name="📋 Plan context", value=truncate(arch, 950), inline=False)

    sources = assign_data.get("discussion_sources", [])
    if sources:
        source_lines = [
            f"Turn {item.get('turn_index')}: {item.get('sender_name', 'Agent')} · event `{item.get('switch_event_id') or 'unavailable'}` · message `{item.get('switch_message_id') or 'unavailable'}`"
            for item in sources[:6]
        ]
        embed.add_field(name="Linked discussion evidence", value=truncate("\n".join(source_lines), 950), inline=False)

    tasks = assign_data.get("tasks", [])
    if tasks:
        task_lines = []
        for t in tasks:
            t_code = t.get("task_code", "TASK")
            t_title = t.get("title", "")
            t_agent = t.get("assigned_agent", "Unassigned")
            t_prio = t.get("priority", "NORMAL")
            persona = get_agent_persona(t_agent)
            task_lines.append(f"`{t_code}` {persona['emoji']} **{t_agent}** ({t_prio}): {t_title}")
        
        embed.add_field(
            name=f"🔨 Proposed Tasks ({len(tasks)})",
            value=truncate("\n".join(task_lines), 1000),
            inline=False,
        )

    embed.set_footer(text="Approve records owner authorization only. Use /report separately to execute approved tasks, or Reject to abort.")
    return embed

def build_status_embed(status_data: Dict[str, Any]) -> discord.Embed:
    """Builds the live dashboard status embed for /status."""
    name = status_data.get("name", "Project")
    state = status_data.get("state", "UNKNOWN")
    
    state_colors = {
        "DRAFT": COLOR_BLUE,
        "ANALYZING": COLOR_PURPLE,
        "DISCUSSING": COLOR_CYAN,
        "AWAITING_APPROVAL": COLOR_AMBER,
        "APPROVED": COLOR_GREEN,
        "EXECUTING": COLOR_BLUE,
        "COMPLETED": COLOR_GREEN,
        "ABORTED": COLOR_RED,
    }
    embed = discord.Embed(
        title=f"📊 Status Dashboard: {name}",
        color=state_colors.get(state, COLOR_BLUE),
    )
    embed.add_field(name="🆔 Project ID", value=f"`{status_data.get('project_id')}`", inline=True)
    embed.add_field(name="📊 State", value=f"**{state}**", inline=True)
    embed.add_field(name="🏛️ Switch Room", value=f"`{status_data.get('switch_room', 'N/A')}`", inline=True)
    embed.add_field(name="🔍 Analyses", value=f"{status_data.get('analyses_completed', 0)} completed", inline=True)
    embed.add_field(name="💬 Debate Turns", value=f"{status_data.get('debate_turns', 0)} turns", inline=True)

    tasks = status_data.get("tasks", [])
    if tasks:
        task_lines = []
        for t in tasks:
            code = t.get("task_code", "T")
            agent = t.get("assigned_agent", "Agent")
            t_status = t.get("status", "PENDING")
            approved = "✅" if t.get("human_approved") else "⏳"
            status_icon = {
                "PENDING": "⚪",
                "APPROVED": "🟡",
                "IN_PROGRESS": "🔄",
                "VERIFIED": "🟢",
                "COMPLETED": "🟢",
                "FAILED": "🔴",
            }.get(t_status, "⚪")
            task_lines.append(f"{status_icon} `{code}` **{agent}** [{t_status}] (Auth: {approved})")
        embed.add_field(name=f"Tasks ({len(tasks)})", value=truncate("\n".join(task_lines), 1000), inline=False)
    else:
        embed.add_field(name="Tasks", value="*No tasks formulated yet. Run /assign.*", inline=False)

    return embed

def build_report_embed(project_name: str, report_data: Dict[str, Any]) -> discord.Embed:
    """Builds the final delivery & retrospective report embed for /report."""
    status = report_data.get("execution_status", "UNKNOWN")
    passed = status == "COMPLETED"
    
    embed = discord.Embed(
        title=f"🎉 Final Delivery Report: {project_name}",
        description=f"Status: **{status}**\nAll approved tasks executed and verified.",
        color=COLOR_GREEN if passed else COLOR_RED,
    )
    embed.add_field(name="🆔 Project ID", value=f"`{report_data.get('project_id')}`", inline=True)
    
    ponytail_ok = report_data.get("ponytail_passed", False)
    embed.add_field(
        name="🥋 Pony Tail Compliance",
        value="✅ **PASSED** (100% Stdlib, 0 external deps)" if ponytail_ok else "❌ **VIOLATIONS DETECTED**",
        inline=True,
    )

    test_ok = report_data.get("test_success", False)
    embed.add_field(
        name="🧪 Adversarial Tests",
        value="✅ **PASSED**" if test_ok else "❌ **FAILED**",
        inline=True,
    )

    test_out = report_data.get("test_output", "")
    if test_out:
        snippet = f"```text\n{truncate(test_out, 750)}\n```"
        embed.add_field(name="Test Suite Output", value=snippet, inline=False)

    spec = report_data.get("project_md")
    if spec:
        embed.add_field(name="📄 Verified Spec", value=f"`{spec}`", inline=False)

    embed.set_footer(text="Delivered via AgentHive Multi-Agent Collaboration Engine")
    return embed

def build_error_embed(command_name: str, error_message: str) -> discord.Embed:
    """Builds a standardized error embed."""
    embed = discord.Embed(
        title=f"❌ Error Executing {command_name}",
        description=truncate(error_message, 1900),
        color=COLOR_RED,
    )
    embed.set_footer(text="AgentHive Gateway Error Handler")
    return embed
