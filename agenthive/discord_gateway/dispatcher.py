"""AgentHive Discord Command Dispatcher.
Bridges Discord Slash Commands and Interactive Components to the AgentHive Master Orchestrator.
Supports concurrent projects, parameter validation, structured error handling,
and immediate Switch Room registration.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from agenthive.config import settings
from agenthive.engine.orchestrator import orchestrator
from agenthive.database import db
from agenthive.security import redact_secrets
from agenthive.services.github_service import codebase_analyzer, parse_repo_target, CodebaseInventory
from agenthive.services.gemini_service import gemini_service

logger = logging.getLogger("agenthive.discord_gateway.dispatcher")

class DiscordCommandDispatcher:
    """Dispatches slash command actions to the AgentHive Orchestrator.
    Handles all 9 commands identically whether invoked from live Discord or test simulator.
    """

    def __init__(self):
        self._project_locks: Dict[str, asyncio.Lock] = {}
        self._conversational_sessions: Dict[str, Dict[str, Any]] = {}

    def _get_lock(self, project_id: str) -> asyncio.Lock:
        """Retrieves or creates a concurrency lock per project."""
        if project_id not in self._project_locks:
            self._project_locks[project_id] = asyncio.Lock()
        return self._project_locks[project_id]

    @staticmethod
    def _actor_owns_project(project, actor_id: Optional[str]) -> bool:
        return bool(
            project
            and settings.discord_owner_id
            and actor_id
            and str(actor_id) == str(settings.discord_owner_id)
            and project.owner_discord_id
            and str(actor_id) == str(project.owner_discord_id)
        )

    async def cmd_newproject(self, name: str, description: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """/newproject - Initializes a new project, generates PROJECT.md, and creates Switch War Room."""
        if not name or not name.strip():
            return {"command": "/newproject", "success": False, "error": "Project name cannot be empty."}
        if not description or not description.strip():
            return {"command": "/newproject", "success": False, "error": "Project description cannot be empty."}
        if not user_id or not settings.discord_owner_id or str(user_id) != str(settings.discord_owner_id):
            return {"command": "/newproject", "success": False, "error": "Project creation requires the configured MindHive owner."}

        proj = None
        try:
            name_clean = name.strip()
            desc_clean = description.strip()
            proj = orchestrator.create_project(name_clean, desc_clean, po_discord_id=user_id)
            room_id = await orchestrator.create_project_switch_room(proj)

            logger.info("Initialized project %s (%s) with Switch room %s", proj.name, proj.id, room_id)
            return {
                "command": "/newproject",
                "success": True,
                "project_id": proj.id,
                "slug": proj.slug,
                "name": proj.name,
                "status": proj.current_state,
                "switch_room_id": room_id,
                "project_md_path": proj.project_md_path,
                "message": f"🐝 AgentHive Project `{proj.name}` initialized! Workspace, `PROJECT.md`, and Switch War Room created."
            }
        except Exception as e:
            safe_error = redact_secrets(str(e))
            logger.error("Failed to initialize project%s: %s", f" {proj.id}" if proj else "", safe_error)
            return {
                "command": "/newproject",
                "success": False,
                "project_id": proj.id if proj else None,
                "workspace_preserved": bool(proj),
                "error": (
                    f"Project workspace was created but required Switch room setup failed. "
                    f"No local fallback was substituted. Project ID: {proj.id}. {safe_error}"
                    if proj else safe_error
                ),
            }

    async def cmd_project(self, project_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/project - Fetches project metadata and specification path."""
        if not project_id or not project_id.strip():
            return {"command": "/project", "success": False, "error": "Project ID must be specified."}

        proj = orchestrator.get_project(project_id.strip())
        if not proj:
            return {"command": "/project", "success": False, "error": f"Project `{project_id}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/project", "success": False, "error": "Only the recorded project owner may inspect this project."}

        return {
            "command": "/project",
            "success": True,
            "project_id": proj.id,
            "name": proj.name,
            "slug": proj.slug,
            "description": proj.description,
            "status": proj.current_state,
            "switch_room_id": proj.switch_room_id,
            "project_md_path": proj.project_md_path,
            "created_at": proj.created_at,
            "updated_at": proj.updated_at,
            "project": proj.model_dump()
        }

    async def cmd_analyse(self, project_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/analyse - Triggers parallel independent zero-bias analysis across all agents."""
        if not project_id or not project_id.strip():
            return {"command": "/analyse", "success": False, "error": "Project ID must be specified."}

        pid = project_id.strip()
        proj = orchestrator.get_project(pid)
        if not proj:
            return {"command": "/analyse", "success": False, "error": f"Project `{pid}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/analyse", "success": False, "error": "Only the recorded project owner may run analysis."}

        lock = self._get_lock(pid)
        async with lock:
            try:
                analyses = await orchestrator.run_independent_analyses(pid)
                return {
                    "command": "/analyse",
                    "success": True,
                    "project_id": pid,
                    "project_name": proj.name,
                    "analyses_count": len(analyses),
                    "summary": [
                        {
                            "agent": a.agent_name,
                            "complexity": a.complexity,
                            "architecture": a.architecture,
                            "tech_stack": a.tech_stack,
                            "risks": a.risks,
                            "missing_requirements": a.missing_requirements,
                            "runtime_evidence": a.runtime_evidence,
                            "runtime_mode": a.runtime_evidence.get("runtime_mode", "unknown"),
                            "analysis_generated": a.runtime_evidence.get("runtime_mode") in {
                                "native_codex_cli", "native_agy_cli", "gemini_api", "hermes_daemon"
                            } or a.runtime_evidence.get("runtime_mode") == "gemini_local_fallback",
                        }
                        for a in analyses
                    ],
                    "message": f"Recorded {len(analyses)} agent analysis statuses. Review each runtime label; unavailable runtimes did not contribute a proposal."
                }
            except Exception as e:
                logger.error("Analysis failed for project %s (%s)", pid, type(e).__name__)
                return {"command": "/analyse", "success": False, "error": redact_secrets(str(e))}

    async def cmd_discuss(self, project_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/discuss - Launches Switch Room debate with bounded turns and consensus floor closure."""
        if not project_id or not project_id.strip():
            return {"command": "/discuss", "success": False, "error": "Project ID must be specified."}

        pid = project_id.strip()
        proj = orchestrator.get_project(pid)
        if not proj:
            return {"command": "/discuss", "success": False, "error": f"Project `{pid}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/discuss", "success": False, "error": "Only the recorded project owner may start discussion."}

        lock = self._get_lock(pid)
        async with lock:
            try:
                messages = await orchestrator.run_switch_discussion(pid)
                return {
                    "command": "/discuss",
                    "success": True,
                    "project_id": pid,
                    "project_name": proj.name,
                    "turns_completed": len(messages),
                    "messages": [
                        {
                            "turn": m.turn_index,
                            "sender": m.sender_name,
                            "role": m.sender_role,
                            "content": m.content,
                            "switch_event_id": m.switch_event_id,
                            "switch_message_id": m.switch_message_id,
                        }
                        for m in messages
                    ],
                    "switch_transport": "official" if messages and all(m.switch_event_id for m in messages) else "local fallback",
                    "message": f"Discussion ended after {len(messages)} turns. Check each message's runtime label; consensus is not inferred by this command."
                }
            except Exception as e:
                logger.error("Discussion failed for project %s (%s)", pid, type(e).__name__)
                return {"command": "/discuss", "success": False, "error": redact_secrets(str(e))}

    async def cmd_assign(self, project_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/assign - Hermes synthesizes WBS tasks and allocates agent roles."""
        if not project_id or not project_id.strip():
            return {"command": "/assign", "success": False, "error": "Project ID must be specified."}

        pid = project_id.strip()
        proj = orchestrator.get_project(pid)
        if not proj:
            return {"command": "/assign", "success": False, "error": f"Project `{pid}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/assign", "success": False, "error": "Only the recorded project owner may request a plan."}

        lock = self._get_lock(pid)
        async with lock:
            try:
                plan = await orchestrator.generate_hermes_plan(pid)
                return {
                    "command": "/assign",
                    "success": True,
                    "project_id": pid,
                    "project_name": proj.name,
                    "architecture_decision": plan.recommended_architecture,
                    "agreements": plan.agreements,
                    "disagreements": plan.disagreements,
                    "tasks": [t.model_dump() for t in plan.tasks],
                    "roles": plan.proposed_roles,
                    "discussion_sources": plan.discussion_sources,
                    "supervisor_runtime": orchestrator.hermes.get_runtime_status(),
                    "message": "Local governance fallback prepared a discussion-linked task proposal. It does not assert consensus; owner review is required."
                }
            except Exception as e:
                logger.error("Task proposal failed for project %s (%s)", pid, type(e).__name__)
                return {"command": "/assign", "success": False, "error": redact_secrets(str(e))}

    async def cmd_approve(self, project_id: str, task_code: Optional[str] = None, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/approve records owner authorization only; /report is a separate execution action."""
        if not project_id or not project_id.strip():
            return {"command": "/approve", "success": False, "error": "Project ID must be specified."}

        pid = project_id.strip()
        proj = orchestrator.get_project(pid)
        if not proj:
            return {"command": "/approve", "success": False, "error": f"Project `{pid}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/approve", "success": False, "error": "Approval requires the recorded project owner."}

        lock = self._get_lock(pid)
        async with lock:
            try:
                tasks = orchestrator.approve_tasks(pid, actor_id, task_code)
                approved_codes = [t.task_code for t in tasks if t.human_approved]
                return {
                    "command": "/approve",
                    "success": True,
                    "project_id": pid,
                    "project_name": proj.name,
                    "approved_tasks": approved_codes,
                    "message": f"✅ Owner approval recorded for {len(approved_codes)} tasks. Run /report separately to start execution."
                }
            except Exception as e:
                logger.error("Approval failed for project %s (%s)", pid, type(e).__name__)
                return {"command": "/approve", "success": False, "error": redact_secrets(str(e))}

    async def cmd_reject(self, project_id: str, reason: str = "Plan rejected by Project Owner", actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/reject - Aborts project tasks and marks state as ABORTED."""
        if not project_id or not project_id.strip():
            return {"command": "/reject", "success": False, "error": "Project ID must be specified."}

        pid = project_id.strip()
        proj = orchestrator.get_project(pid)
        if not proj:
            return {"command": "/reject", "success": False, "error": f"Project `{pid}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/reject", "success": False, "error": "Rejection requires the recorded project owner."}

        lock = self._get_lock(pid)
        async with lock:
            try:
                orchestrator.reject_project(pid, actor_id, reason)
                return {
                    "command": "/reject",
                    "success": True,
                    "project_id": pid,
                    "project_name": proj.name,
                    "reason": redact_secrets(reason),
                    "message": f"❌ Project `{pid}` rejected by Project Owner. State set to ABORTED."
                }
            except Exception as e:
                logger.error("Rejection failed for project %s (%s)", pid, type(e).__name__)
                return {"command": "/reject", "success": False, "error": redact_secrets(str(e))}

    async def cmd_status(self, project_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/status - Live dashboard displaying status of project, agents, debate turns, and tasks."""
        if not project_id or not project_id.strip():
            return {"command": "/status", "success": False, "error": "Project ID must be specified."}

        pid = project_id.strip()
        proj = orchestrator.get_project(pid)
        if not proj:
            return {"command": "/status", "success": False, "error": f"Project `{pid}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/status", "success": False, "error": "Only the recorded project owner may inspect this project."}

        with db.get_connection() as conn:
            task_rows = conn.execute("SELECT * FROM tasks WHERE project_id = ?", (proj.id,)).fetchall()
            discussion_rows = conn.execute(
                "SELECT * FROM discussion_messages WHERE project_id = ? ORDER BY turn_index", (proj.id,)
            ).fetchall()
            analysis_rows = conn.execute(
                "SELECT * FROM independent_analyses WHERE project_id = ? ORDER BY rowid", (proj.id,)
            ).fetchall()
            execution_rows = conn.execute(
                """SELECT l.*, t.task_code, t.assigned_agent FROM task_execution_logs l
                   JOIN tasks t ON t.id = l.task_id WHERE t.project_id = ? ORDER BY l.executed_at""",
                (proj.id,),
            ).fetchall()

        def parse_list(value):
            try:
                return json.loads(value) if isinstance(value, str) else []
            except (TypeError, json.JSONDecodeError):
                return []

        analyses = []
        for row in analysis_rows:
            item = dict(row)
            for field in ("tech_stack", "implementation_plan", "risks", "missing_requirements"):
                item[field] = parse_list(item.get(field))
            analyses.append(item)
        project_md = ""
        try:
            project_md = Path(proj.project_md_path).read_text()
        except OSError:
            pass
        approved_count = sum(bool(row["human_approved"]) for row in task_rows)
        architecture_match = re.search(
            r"## 4\. Hermes Supervision & Architecture Consensus\s*(.*?)(?=### |## 5\.)",
            project_md,
            re.DOTALL,
        )

        return {
            "command": "/status",
            "success": True,
            "project_id": proj.id,
            "name": proj.name,
            "state": proj.current_state,
            "switch_room": proj.switch_room_id or "Not created",
            "analyses_completed": len(analyses),
            "analyses": analyses,
            "debate_turns": len(discussion_rows),
            "discussion_messages": [dict(row) for row in discussion_rows],
            "discussion_sources": [
                {
                    "turn_index": row["turn_index"],
                    "sender_id": row["sender_id"],
                    "sender_name": row["sender_name"],
                    "switch_event_id": row["switch_event_id"],
                    "switch_message_id": row["switch_message_id"],
                    "excerpt": str(row["content"] or "")[:300],
                }
                for row in discussion_rows
            ],
            "discussion_transport": "official" if discussion_rows and all(row["switch_event_id"] for row in discussion_rows) else ("local fallback" if discussion_rows else "not started"),
            "tasks": [dict(r) for r in task_rows],
            "execution_logs": [dict(row) for row in execution_rows],
            "approval": {
                "required": True,
                "approved_count": approved_count,
                "task_count": len(task_rows),
                "state": proj.current_state,
            },
            "project_md": project_md,
            "supervision_architecture": architecture_match.group(1).strip() if architecture_match else None,
            "supervisor_runtime": orchestrator.hermes.get_runtime_status(),
        }

    async def cmd_report(self, project_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """/report - Triggers execution of approved tasks, Pony Tail audit, testing & final report generation."""
        if not project_id or not project_id.strip():
            return {"command": "/report", "success": False, "error": "Project ID must be specified."}

        pid = project_id.strip()
        proj = orchestrator.get_project(pid)
        if not proj:
            return {"command": "/report", "success": False, "error": f"Project `{pid}` not found."}
        if not self._actor_owns_project(proj, actor_id):
            return {"command": "/report", "success": False, "error": "Execution requires the recorded project owner."}

        lock = self._get_lock(pid)
        async with lock:
            try:
                exec_res = await orchestrator.execute_project(pid)
                return {
                    "command": "/report",
                    "success": True,
                    "project_id": pid,
                    "project_name": proj.name,
                    "execution_status": exec_res["status"],
                    "ponytail_passed": exec_res["ponytail_audit"]["passed"],
                    "test_success": exec_res["test_results"]["success"],
                    "test_output": exec_res["test_results"].get("stderr") or exec_res["test_results"].get("stdout") or "",
                    "tasks_executed": exec_res.get("tasks_executed", 0),
                    "project_md": exec_res.get("project_md", ""),
                    "message": f"🎉 AgentHive Project verified and delivered! Status: {exec_res['status']}"
                }
            except Exception as e:
                logger.error("Execution/report failed for project %s (%s)", pid, type(e).__name__)
                return {"command": "/report", "success": False, "error": redact_secrets(str(e))}

    async def handle_conversational_message(
        self,
        text: str,
        user_id: Optional[str] = None,
        context_id: str = "default",
        target_repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Conversational entry point for MindHive AI Engineering Manager.
        Handles natural queries, repository analysis, workflow proposals, and Q&A.
        """
        raw_text = text.strip() if text else ""
        if not raw_text:
            raw_text = "hello"

        session = self._conversational_sessions.setdefault(context_id, {
            "active_repo": None,
            "last_project_id": None,
        })

        try:
            # Extract repository reference if present
            repo_candidate = None
            if target_repo and target_repo.strip():
                repo_candidate = target_repo.strip()
            else:
                url_match = re.search(r"https?://github\.com/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)", raw_text)
                if url_match:
                    repo_candidate = url_match.group(0)
                else:
                    repo_flag_match = re.search(r"(?:repo|repository)\s*[:=]?\s*([a-zA-Z0-9_\-\./]+)", raw_text, re.IGNORECASE)
                    if repo_flag_match:
                        repo_candidate = repo_flag_match.group(1).strip()
                    else:
                        slash_match = re.search(r"\b([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)\b", raw_text)
                        if slash_match and not slash_match.group(1).startswith("http"):
                            repo_candidate = slash_match.group(1)

            lower = raw_text.lower()
            is_workflow = any(k in lower for k in [
                "create a development plan", "development plan", "propose plan",
                "workflow", "what should we work on", "what work", "propose tasks",
                "wbs", "plan next", "create plan"
            ])
            is_repo_analysis = any(k in lower for k in [
                "analyse", "analyze", "connect", "inspect",
                "what does this project do", "what is this project",
                "explain codebase", "codebase", "architecture"
            ]) or ("github.com" in lower) or (repo_candidate is not None and not is_workflow)

            is_greeting = not is_workflow and not is_repo_analysis and (
                bool(re.match(r"^(hello|hi|hey|greetings|who are you|help)\b", lower))
                or lower in ["hello", "hi", "hey", "help", "who are you"]
            )

            # 1. GREETING INTENT
            if is_greeting:
                switch_status = f"Switch Core at {settings.switch_core_url}"
                gemini_status = f"Gemini ({gemini_service.model})" if gemini_service.is_configured else "Conversational AI Offline"
                greeting_text = (
                    "👋 **Hello! I am MindHive**, an autonomous AI Engineering Manager coordinating a multi-agent team "
                    "(ChatGPT Codex, Antigravity AGY, Google Gemini, and Nous Hermes) connected via the Official Switch Protocol.\n\n"
                    "Here is how I can help accelerate your engineering workflow:\n"
                    "1. **Analyze a Codebase:** Ask `@AgentHive analyse <github-url-or-path>` or `@AgentHive what does this project do?` "
                    "to inspect architectures, dependencies, entry points, and technical debt.\n"
                    "2. **Coordinate Multi-Agent Discussions:** Tell me `@AgentHive create a development plan` to start a debate "
                    "between agents in an Official Switch War Room.\n"
                    "3. **Propose Structured Workflows:** I synthesize agent proposals into a prioritized WBS with explicit acceptance criteria.\n"
                    "4. **Human-in-the-Loop Governance:** I enforce strict sovereign human owner approvals before any task execution begins.\n\n"
                    f"*Active Runtimes: {switch_status} | {gemini_status}*"
                )
                return {
                    "success": True,
                    "intent": "greeting",
                    "response_text": greeting_text,
                    "requires_approval": False,
                }

            # 2. WORKFLOW PROPOSAL INTENT
            if is_workflow:
                if settings.discord_owner_id and user_id and str(user_id) != str(settings.discord_owner_id):
                    return {
                        "success": False,
                        "intent": "workflow_proposal",
                        "response_text": (
                            "⛔ **Authorization Denied:** Only the configured MindHive project owner can initiate a development workflow. "
                            "Please ask the project administrator to authorize or trigger this plan."
                        ),
                        "error": "Unauthorized user",
                        "requires_approval": False,
                    }

                # Ensure codebase inventory exists
                inventory: Optional[CodebaseInventory] = session.get("active_repo")
                if not inventory:
                    target = repo_candidate or settings.github_default_repo or Path.cwd()
                    try:
                        inventory = await codebase_analyzer.analyze(str(target), github_token=settings.github_token)
                        session["active_repo"] = inventory
                    except Exception as e:
                        safe_err = redact_secrets(str(e))
                        return {
                            "success": False,
                            "intent": "workflow_proposal",
                            "response_text": f"⚠️ **Codebase Analysis Error:** Unable to analyze repository `{target}`: {safe_err}",
                            "error": safe_err,
                            "requires_approval": False,
                        }

                # Create isolated project and switch room
                clean_name = f"{inventory.repo_name}-DevPlan"[:40]
                proj_owner = user_id or settings.discord_owner_id or "owner"
                proj_desc = f"Autonomous development workflow for {inventory.repo_name}: {inventory.description[:120]}"
                proj = orchestrator.create_project(name=clean_name, description=proj_desc, po_discord_id=proj_owner)
                session["last_project_id"] = proj.id

                room_id = await orchestrator.create_project_switch_room(proj)
                analyses = await orchestrator.run_independent_analyses(proj.id)
                messages = await orchestrator.run_switch_discussion(proj.id)
                plan = await orchestrator.generate_hermes_plan(proj.id)

                wbs_lines = []
                for t in plan.tasks:
                    assigned = t.assigned_agent.value if hasattr(t.assigned_agent, "value") else str(t.assigned_agent)
                    wbs_lines.append(
                        f"• **`{t.task_code}` — {t.title}** ({t.priority})\n"
                        f"  - **Assigned Agent:** {assigned}\n"
                        f"  - **Acceptance Criteria:** {'; '.join(t.acceptance_criteria)}\n"
                        f"  - **Dependencies:** {', '.join(t.dependencies) if t.dependencies else 'None'}"
                    )
                wbs_text = "\n".join(wbs_lines)
                switch_mode = "Official Switch Core" if (messages and all(m.switch_event_id for m in messages)) else "Switch Protocol (Local Fallback)"

                plan_text = (
                    f"## 📋 Proposed Autonomous Development Workflow: `{proj.name}`\n\n"
                    f"**Project ID:** `{proj.id}`\n"
                    f"**Switch War Room:** `{room_id}` ({len(messages)} debate turns over {switch_mode})\n\n"
                    f"### 🏛️ Architectural Consensus\n"
                    f"{plan.recommended_architecture}\n\n"
                    f"### 👥 Agent Discussion Highlights\n"
                    f"- **Agreements:** {'; '.join(plan.agreements[:3]) if plan.agreements else 'Team aligned on architecture.'}\n"
                    f"- **Risks Identified:** {'; '.join(plan.disagreements[:3]) if plan.disagreements else 'No critical blocking disagreements.'}\n\n"
                    f"### 🎯 Work Breakdown Structure (WBS)\n"
                    f"{wbs_text}\n\n"
                    f"---\n"
                    f"🔒 **Sovereign Human Approval Gate Active**\n"
                    f"As an AI Engineering Manager, I **never execute code without human sign-off**. "
                    f"Review the proposed tasks above and click **Approve Plan** below (or run `/approve {proj.id}`) to unlock execution."
                )

                return {
                    "success": True,
                    "intent": "workflow_proposal",
                    "project_id": proj.id,
                    "project_name": proj.name,
                    "switch_room_id": room_id,
                    "response_text": plan_text,
                    "plan": plan.model_dump(),
                    "requires_approval": True,
                }

            # 3. REPOSITORY ANALYSIS INTENT
            if is_repo_analysis:
                target = repo_candidate or (session.get("active_repo").repo_name if session.get("active_repo") else None) or settings.github_default_repo or Path.cwd()
                try:
                    inventory = await codebase_analyzer.analyze(str(target), github_token=settings.github_token)
                    session["active_repo"] = inventory
                except Exception as e:
                    safe_err = redact_secrets(str(e))
                    return {
                        "success": False,
                        "intent": "repo_analysis",
                        "response_text": f"⚠️ **Codebase Analysis Error:** Unable to analyze repository `{target}`: {safe_err}",
                        "error": safe_err,
                        "requires_approval": False,
                    }

                if gemini_service.is_configured:
                    prompt = (
                        f"The user asked: '{raw_text}'. As the Engineering Manager, analyze this repository ({inventory.repo_name}) "
                        f"for the user. Explain:\n"
                        f"1. Project identity & core problem solved\n"
                        f"2. Technical architecture (languages, frameworks, entry points, directory scale)\n"
                        f"3. Engineering assessment (observed capabilities, gaps/technical debt, testing state)\n"
                        f"4. Improvement recommendations (priority, rationale, complexity, responsible agent)\n"
                        f"Reference real observed repository files and manifests."
                    )
                    reply = await gemini_service.chat(session_id=context_id, user_message=prompt, codebase_inventory=inventory)
                    if not reply or reply.startswith("⚠️"):
                        reply = gemini_service.explain_codebase_deterministic(inventory)
                else:
                    reply = gemini_service.explain_codebase_deterministic(inventory)

                return {
                    "success": True,
                    "intent": "repo_analysis",
                    "response_text": reply,
                    "repo_inventory": inventory.to_dict(),
                    "requires_approval": False,
                }

            # 4. GENERAL CHAT / FOLLOW-UP INTENT
            active_repo = session.get("active_repo")
            if gemini_service.is_configured:
                reply = await gemini_service.chat(
                    session_id=context_id,
                    user_message=raw_text,
                    codebase_inventory=active_repo,
                )
            elif active_repo:
                reply = (
                    f"I am actively tracking repository `{active_repo.repo_name}` ({active_repo.primary_language}).\n\n"
                    f"{gemini_service.explain_codebase_deterministic(active_repo)}\n\n"
                    f"> *To ask freeform conversational questions, configure `GEMINI_API_KEY` in `.env`.*"
                )
            else:
                reply = (
                    "👋 I am MindHive, your AI Engineering Manager. I can inspect your GitHub repository, "
                    "coordinate multi-agent discussions over Official Switch, and generate WBS development workflows.\n\n"
                    "Try asking:\n"
                    "- `@AgentHive analyse <github-url-or-path>`\n"
                    "- `@AgentHive create a development plan`\n"
                    "- Or use `/ask` with your query.\n\n"
                    "> *Note: For freeform conversational LLM answers, configure `GEMINI_API_KEY` in `.env`.*"
                )

            return {
                "success": True,
                "intent": "general_chat",
                "response_text": reply,
                "requires_approval": False,
            }

        except Exception as e:
            safe_error = redact_secrets(str(e))
            logger.error("Error in handle_conversational_message: %s", safe_error, exc_info=True)
            return {
                "success": False,
                "intent": "error",
                "response_text": f"⚠️ **MindHive Error:** {safe_error}",
                "error": safe_error,
                "requires_approval": False,
            }

discord_dispatcher = DiscordCommandDispatcher()
