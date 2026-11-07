"""AgentHive Master Orchestrator.
Governs the complete multi-agent engineering lifecycle:
Project Creation -> PROJECT.md -> Independent Analysis -> Switch Discussion ->
Hermes Supervision -> Human Approval -> Sandboxed Execution -> Verification -> Final Report.
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import uuid4

from agenthive.config import settings
from agenthive.database import db
from agenthive.models.project import (
    Project,
    IndependentAnalysis,
    DiscussionMessage,
    TaskItem,
    HermesSupervisorPlan,
)
from agenthive.models.events import SwitchRoomCreate
from agenthive.switch.server import switch_state
from agenthive.agents.codex import CodexAgent
from agenthive.agents.agy import AGYAgent
from agenthive.agents.gemini import GeminiAgent
from agenthive.agents.hermes import HermesAgent
from agenthive.engine.ponytail import ponytail_guard
from agenthive.engine.execution import runner
from agenthive.security import redact_secrets
from agenthive.security import validate_workspace_path

logger = logging.getLogger("agenthive.engine.orchestrator")

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")

def _row_to_task(row) -> TaskItem:
    d = dict(row)
    if isinstance(d.get("dependencies"), str):
        try:
            d["dependencies"] = json.loads(d["dependencies"])
        except Exception:
            d["dependencies"] = []
    if isinstance(d.get("acceptance_criteria"), str):
        try:
            d["acceptance_criteria"] = json.loads(d["acceptance_criteria"])
        except Exception:
            d["acceptance_criteria"] = []
    d["human_approved"] = bool(d.get("human_approved", 0))
    return TaskItem(**d)


def _task_approval_hash(row) -> str:
    """Bind an approval to the exact immutable task proposal fields."""
    keys = ("id", "project_id", "task_code", "title", "description", "assigned_agent", "priority", "dependencies", "acceptance_criteria")
    payload = {}
    for key in keys:
        value = row[key]
        if key in ("dependencies", "acceptance_criteria") and isinstance(value, str):
            value = json.loads(value)
        payload[key] = value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

class Orchestrator:
    def __init__(self):
        self.codex = CodexAgent()
        self.agy = AGYAgent()
        self.gemini = GeminiAgent()
        self.hermes = HermesAgent()
        self.agents = [self.codex, self.agy, self.gemini, self.hermes]

    def create_project(self, name: str, description: str, po_discord_id: str = "po_admin") -> Project:
        """Phase 1: Project Initialization & Workspace Creation."""
        project_id = str(uuid4())
        slug = f"{slugify(name)}-{project_id[:6]}"
        workspace_dir = Path(settings.workspace_root) / slug
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "src").mkdir(exist_ok=True)
        (workspace_dir / "tests").mkdir(exist_ok=True)
        (workspace_dir / "docs").mkdir(exist_ok=True)

        # Generate PROJECT.md
        project_md_path = workspace_dir / "PROJECT.md"
        content = (
            f"# Project: {name}\n\n"
            f"> **Status:** INITIATED (DRAFT)\n"
            f"> **Project ID:** `{project_id}`\n"
            f"> **Owner Discord ID:** `{po_discord_id}`\n"
            f"> **Date Created:** {datetime.utcnow().isoformat()} UTC\n\n"
            f"## 1. Project Brief & Vision\n\n"
            f"{description}\n\n"
            f"## 2. Independent Analysis Summary\n\n"
            f"*Awaiting parallel agent submissions...*\n\n"
            f"## 3. Switch Discussion Minutes\n\n"
            f"*Discussion pending...*\n\n"
            f"## 4. Hermes Supervision & Architecture Consensus\n\n"
            f"*Pending Hermes synthesis...*\n\n"
            f"## 5. Work Breakdown Structure (WBS)\n\n"
            f"*Pending human approval gate...*\n\n"
            f"## 6. Execution & Test Verification\n\n"
            f"*Pending task execution...*\n"
        )
        project_md_path.write_text(content)

        proj = Project(
            id=project_id,
            name=name,
            slug=slug,
            description=description,
            current_state="DRAFT",
            owner_discord_id=po_discord_id,
            project_md_path=str(project_md_path),
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )

        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, slug, description, current_state, owner_discord_id, project_md_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (proj.id, proj.name, proj.slug, proj.description, proj.current_state, po_discord_id, proj.project_md_path, proj.created_at, proj.updated_at)
            )
            conn.commit()

        logger.info("Created project %s (%s) at %s", name, project_id, project_md_path)
        return proj

    def get_project(self, project_id_or_slug: str) -> Optional[Project]:
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ? OR slug = ?",
                (project_id_or_slug, project_id_or_slug)
            ).fetchone()
            if row:
                return Project(**dict(row))
        return None

    async def create_project_switch_room(self, project: Project) -> str:
        """Create and verify the project's room on the explicitly selected Switch transport."""
        if settings.switch_mode == "official":
            clients = [agent.client for agent in self.agents]
            if len(clients) != 4 or not all(
                client and client.is_connected and client.is_official_switch and client._sse_ready.is_set()
                for client in clients
            ):
                raise RuntimeError("Official Switch is unavailable for one or more agents; no local room was substituted")

            lead = clients[0]
            assert lead is not None
            room_info = await lead.create_room(
                name=f"war-room-{project.slug}",
                description=f"AgentHive project collaboration room for {project.name}",
                agent_names=[client.official_name for client in clients if client and client.official_name],
            )
            room_id = room_info.get("id")
            if not room_id:
                raise RuntimeError("Official Switch room creation returned no room ID")
            for client in clients:
                assert client is not None
                await client.join_room(room_id)
            participants = await lead.get_room_participants(room_id)
            participant_names = {
                str(item.get("name") or item.get("agent_name") or item.get("display_name") or "").lower()
                for item in participants
            }
            expected_names = {client.official_name.lower() for client in clients if client and client.official_name}
            if not expected_names or not expected_names.issubset(participant_names):
                raise RuntimeError("Official Switch did not confirm membership for all four agents")
        elif settings.switch_mode == "local":
            # Local transport is available only when explicitly selected for development/tests.
            room_id = f"local-switch-room-{project.slug}"
            switch_state.rooms[room_id] = SwitchRoomCreate(
                room_id=room_id,
                name=f"War Room: {project.name}",
                topic=f"Local development collaboration room for {project.name}",
            )
            switch_state.room_members[room_id] = {agent.agent_id for agent in self.agents}
            switch_state.room_messages[room_id] = []
        else:
            raise RuntimeError("SWITCH_MODE must explicitly select 'official' or 'local'")

        with db.get_connection() as conn:
            conn.execute(
                "UPDATE projects SET switch_room_id = ? WHERE id = ?",
                (room_id, project.id),
            )
            conn.commit()
        project.switch_room_id = room_id
        return room_id

    async def run_independent_analyses(self, project_id: str) -> List[IndependentAnalysis]:
        """Phase 4: Run isolated parallel independent analysis sessions across all available agents.
        Only after all submissions complete are results compiled.
        """
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        # Update project state
        with db.get_connection() as conn:
            conn.execute("UPDATE projects SET current_state = 'ANALYZING' WHERE id = ?", (project_id,))
            conn.commit()

        logger.info("Triggering independent analysis for all agents on project %s", proj.name)
        
        # Parallel execution: separate sessions per agent
        results: List[IndependentAnalysis] = await asyncio.gather(
            self.codex.perform_independent_analysis(project_id, proj.name, proj.description),
            self.agy.perform_independent_analysis(project_id, proj.name, proj.description),
            self.gemini.perform_independent_analysis(project_id, proj.name, proj.description),
            self.hermes.perform_independent_analysis(project_id, proj.name, proj.description)
        )

        # Store results separately in DB
        with db.get_connection() as conn:
            for analysis in results:
                analysis.understanding = redact_secrets(analysis.understanding)
                analysis.architecture = redact_secrets(analysis.architecture)
                analysis.tech_stack = [redact_secrets(item) for item in analysis.tech_stack]
                analysis.implementation_plan = [redact_secrets(item) for item in analysis.implementation_plan]
                analysis.risks = [redact_secrets(item) for item in analysis.risks]
                analysis.missing_requirements = [redact_secrets(item) for item in analysis.missing_requirements]
                conn.execute(
                    """
                    INSERT INTO independent_analyses 
                    (id, project_id, agent_id, agent_name, understanding, architecture, tech_stack, implementation_plan, risks, missing_requirements, complexity, runtime_evidence_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        analysis.id,
                        analysis.project_id,
                        analysis.agent_id,
                        analysis.agent_name,
                        analysis.understanding,
                        analysis.architecture,
                        json.dumps(analysis.tech_stack),
                        json.dumps(analysis.implementation_plan),
                        json.dumps(analysis.risks),
                        json.dumps(analysis.missing_requirements),
                        analysis.complexity,
                        redact_secrets(json.dumps(analysis.runtime_evidence))
                    )
                )
            conn.commit()

        # Update PROJECT.md with Independent Analysis Section
        analysis_md_lines = ["\n## 2. Independent Analysis Summary\n"]
        for a in results:
            analysis_md_lines.append(f"### {a.agent_name} Analysis\n")
            analysis_md_lines.append(f"- **Runtime mode:** `{a.runtime_evidence.get('runtime_mode', 'unknown')}`\n")
            analysis_md_lines.append(f"- **Invocation error:** {redact_secrets(str(a.runtime_evidence.get('error_reason') or 'none recorded'))}\n")
            analysis_md_lines.append(f"- **Understanding:** {a.understanding}\n")
            analysis_md_lines.append(f"- **Suggested Architecture:** {a.architecture}\n")
            analysis_md_lines.append(f"- **Recommended Tech Stack:** {', '.join(a.tech_stack)}\n")
            analysis_md_lines.append(f"- **Estimated Complexity:** `{a.complexity}`\n")
            analysis_md_lines.append(f"- **Identified Risks:**\n")
            for r in a.risks:
                analysis_md_lines.append(f"  - {r}\n")
            analysis_md_lines.append(f"- **Missing Requirements:**\n")
            for m in a.missing_requirements:
                analysis_md_lines.append(f"  - {m}\n")
            analysis_md_lines.append("\n")

        p_path = Path(proj.project_md_path)
        existing = p_path.read_text()
        updated = re.sub(
            r"## 2\. Independent Analysis Summary.*?(?=## 3\. Switch Discussion Minutes)",
            "".join(analysis_md_lines),
            existing,
            flags=re.DOTALL
        )
        p_path.write_text(updated)

        return results

    async def run_switch_discussion(self, project_id: str) -> List[DiscussionMessage]:
        """Phase 5: Collaborative Switch Room Discussion with Bounded Turns."""
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        clients = [agent.client for agent in self.agents]
        official = bool(clients) and all(
            client and client.is_connected and client.is_official_switch for client in clients
        )
        if settings.switch_mode.lower() == "official" and not official:
            raise RuntimeError("Official Switch discussion requires live official connections for all four agents")

        queues: List[asyncio.Queue] = []
        if official:
            lead = clients[0]
            assert lead is not None
            if proj.switch_room_id:
                visible_rooms = await lead.list_rooms()
                if not any(str(room.get("id")) == str(proj.switch_room_id) for room in visible_rooms):
                    raise RuntimeError("The project's recorded Official Switch room is not visible to its registered lead agent")
                room_id = proj.switch_room_id
            else:
                room_info = await lead.create_room(
                    name=f"war-room-{proj.slug}",
                    description=f"AgentHive project discussion for {proj.name}",
                    agent_names=[client.official_name for client in clients if client and client.official_name],
                )
                # Switch moderation `id` is the room ID consumed by subscriptions and messages.
                room_id = room_info["id"]
            for client in clients:
                assert client is not None
                queue: asyncio.Queue = asyncio.Queue()

                async def on_event(event: Dict[str, Any], *, target=queue):
                    await target.put(event)

                await client.start_event_listener(on_event)
                await client.join_room(room_id)
                queues.append(queue)

            participants = await lead.get_room_participants(room_id)
            participant_names = {
                str(p.get("name") or p.get("agent_name") or p.get("display_name") or "").lower()
                for p in participants
            }
            expected_names = {client.official_name.lower() for client in clients if client and client.official_name}
            if not participants or not expected_names.issubset(participant_names):
                raise RuntimeError("Official Switch did not confirm all four expected room participants")
        else:
            room_id = proj.switch_room_id or f"local-switch-room-{proj.slug}"
            if room_id not in switch_state.rooms:
                switch_state.rooms[room_id] = SwitchRoomCreate(
                    room_id=room_id,
                    name=f"War Room: {proj.name}",
                    topic=f"Local development collaboration room for {proj.name}",
                )
            switch_state.room_members.setdefault(room_id, set()).update(agent.agent_id for agent in self.agents)
            switch_state.room_messages.setdefault(room_id, [])

        # Update project state
        with db.get_connection() as conn:
            conn.execute("UPDATE projects SET current_state = 'DISCUSSING', switch_room_id = ? WHERE id = ?", (room_id, project_id))
            conn.commit()

        messages: List[DiscussionMessage] = []
        for index, agent in enumerate(self.agents, start=1):
            context = [message.model_dump() for message in messages]
            content = await agent.generate_discussion_turn(project_id, proj.name, proj.description, context, index)
            content = redact_secrets(content)
            reply_to = messages[-1].sender_name if messages else None
            event_id = None
            message_id = None
            if official:
                client = clients[index - 1]
                assert client is not None
                response = await client.send_message(
                    room_id,
                    content,
                    reply_to=reply_to,
                    client_message_id=f"{project_id}:{index}",
                )
                message_id = response.get("event_id")
                received = []
                for receiver_index, receiver_queue in enumerate(queues):
                    if receiver_index == index - 1:
                        continue
                    deadline = asyncio.get_running_loop().time() + 12.0
                    while True:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise RuntimeError(
                                f"Official Switch delivery timed out for turn {index} to {self.agents[receiver_index].name}"
                            )
                        event = await asyncio.wait_for(receiver_queue.get(), timeout=remaining)
                        if event.get("room_id") in (None, room_id) and event.get("content") == content:
                            received.append(event)
                            break
                event_id = next((event.get("event_id") for event in received if event.get("event_id")), None)
                if not event_id:
                    raise RuntimeError(f"Official Switch delivered turn {index} without a verifiable SSE event ID")
            elif clients and clients[index - 1]:
                await agent.send_room_message(room_id, content, reply_to)
            messages.append(DiscussionMessage(
                project_id=project_id,
                turn_index=index,
                sender_id=agent.agent_id,
                sender_name=agent.name,
                sender_role="SUPERVISOR" if agent is self.hermes else agent.role,
                reply_to_agent=reply_to,
                content=content,
                switch_event_id=event_id,
                switch_message_id=message_id,
                switch_room_id=room_id,
                runtime_evidence=dict(getattr(agent, "last_runtime_evidence", {}) or {}),
            ))

        # Persist messages in DB
        with db.get_connection() as conn:
            for m in messages:
                conn.execute(
                    """
                    INSERT INTO discussion_messages 
                    (id, project_id, turn_index, sender_id, sender_name, sender_role, reply_to_agent, content, switch_event_id, switch_message_id, switch_room_id, runtime_evidence_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (m.id, m.project_id, m.turn_index, m.sender_id, m.sender_name, m.sender_role, m.reply_to_agent, m.content, m.switch_event_id, m.switch_message_id, m.switch_room_id, redact_secrets(json.dumps(m.runtime_evidence)), datetime.utcnow().isoformat())
                )
            conn.commit()

        # Update PROJECT.md
        discussion_md_lines = ["\n## 3. Switch Discussion Minutes\n"]
        for m in messages:
            discussion_md_lines.append(f"#### Turn {m.turn_index}: {m.sender_name}\n")
            discussion_md_lines.append(f"{m.content}\n\n")

        p_path = Path(proj.project_md_path)
        existing = p_path.read_text()
        updated = re.sub(
            r"## 3\. Switch Discussion Minutes.*?(?=## 4\. Hermes Supervision & Architecture Consensus)",
            "".join(discussion_md_lines),
            existing,
            flags=re.DOTALL
        )
        p_path.write_text(updated)

        return messages

    async def generate_hermes_plan(self, project_id: str) -> HermesSupervisorPlan:
        """Phase 6 & 7: Hermes analyzes proposals, resolves conflicts, and produces WBS with role assignments."""
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        # Fetch independent analyses from DB
        with db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM independent_analyses WHERE project_id = ? ORDER BY created_at, id", (project_id,)).fetchall()
            analyses = [
                IndependentAnalysis(
                    id=r["id"],
                    project_id=r["project_id"],
                    agent_id=r["agent_id"],
                    agent_name=r["agent_name"],
                    understanding=r["understanding"],
                    architecture=r["architecture"],
                    tech_stack=json.loads(r["tech_stack"]),
                    implementation_plan=json.loads(r["implementation_plan"]),
                    risks=json.loads(r["risks"]),
                    missing_requirements=json.loads(r["missing_requirements"]),
                    complexity=r["complexity"],
                    runtime_evidence=json.loads(r["runtime_evidence_json"] or "{}")
                )
                for r in rows
            ]

            discussion_rows = conn.execute(
                "SELECT * FROM discussion_messages WHERE project_id = ? ORDER BY turn_index, created_at, id",
                (project_id,),
            ).fetchall()

        if not discussion_rows:
            raise ValueError("Cannot create a discussion-informed plan: no persisted discussion messages are available")
        if not proj.switch_room_id:
            raise ValueError("Cannot create a discussion-informed plan: project has no verified Switch room association")
        discussions: List[Dict[str, Any]] = []
        for row in discussion_rows:
            item = dict(row)
            if item.get("project_id") != project_id or item.get("switch_room_id") != proj.switch_room_id:
                raise ValueError("Cannot create a discussion-informed plan: a persisted message is not verifiably associated with this project room")
            if not item.get("content") or not item.get("sender_id") or item.get("turn_index") is None:
                raise ValueError("Cannot create a discussion-informed plan: persisted discussion record is incomplete")
            if settings.switch_mode.lower() == "official" and (not item.get("switch_event_id") or not item.get("switch_message_id")):
                raise ValueError("Cannot create a discussion-informed plan: Official Switch event and message evidence is missing")
            item["runtime_evidence"] = json.loads(item.get("runtime_evidence_json") or "{}")
            discussions.append(item)

        plan = self.hermes.synthesize_plan(project_id, proj.name, proj.description, analyses, discussions)

        # Persist planning evidence and tasks as PENDING_APPROVAL.
        with db.get_connection() as conn:
            evidence = {
                "runtime_mode": "local_governance_fallback",
                "discussion_sources": plan.discussion_sources,
                "analysis_count": len(analyses),
            }
            conn.execute(
                "INSERT INTO audit_logs (id, project_id, event_name, actor, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid4()), project_id, "discussion_aware_plan_created", "hermes_local_governance", redact_secrets(json.dumps(evidence)), datetime.utcnow().isoformat()),
            )
            # Clear old tasks if any
            conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
            for t in plan.tasks:
                conn.execute(
                    """
                    INSERT INTO tasks 
                    (id, project_id, task_code, title, description, assigned_agent, priority, status, human_approved, dependencies, acceptance_criteria, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t.id,
                        t.project_id,
                        t.task_code,
                        t.title,
                        t.description,
                        t.assigned_agent,
                        t.priority,
                        t.status,
                        0,
                        json.dumps(t.dependencies),
                        json.dumps(t.acceptance_criteria),
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat()
                    )
                )
            conn.execute("UPDATE projects SET current_state = 'AWAITING_APPROVAL' WHERE id = ?", (project_id,))
            conn.commit()

        # Update PROJECT.md
        supervision_md = (
            f"\n## 4. Hermes Supervision & Architecture Consensus\n\n"
            f"{plan.recommended_architecture}\n\n"
            f"### Evaluated Trade-offs & Conflict Resolutions:\n"
            f"{plan.evaluated_arguments}\n\n"
            f"### Identified Agreements:\n"
            + "".join(f"- {a}\n" for a in plan.agreements) + "\n"
            f"### Resolved Disagreements:\n"
            + "".join(f"- {d}\n" for d in plan.disagreements) + "\n\n"
            f"## 5. Work Breakdown Structure (WBS)\n\n"
            f"| Task Code | Assigned Agent | Priority | Status | Description |\n"
            f"|---|---|---|---|---|\n"
            + "".join(f"| `{t.task_code}` | **{t.assigned_agent}** | `{t.priority}` | `{t.status}` | {t.title} |\n" for t in plan.tasks)
            + "\n"
        )

        p_path = Path(proj.project_md_path)
        existing = p_path.read_text()
        updated = re.sub(
            r"## 4\. Hermes Supervision & Architecture Consensus.*?(?=## 6\. Execution & Test Verification)",
            supervision_md,
            existing,
            flags=re.DOTALL
        )
        p_path.write_text(updated)

        return plan

    def approve_tasks(self, project_id: str, actor_id: Optional[str], task_code: Optional[str] = None) -> List[TaskItem]:
        """Phase 7: Sovereign Human Approval Gate.
        Grants explicit human authorization for task execution.
        """
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")
        if not settings.discord_owner_id or str(actor_id) != str(settings.discord_owner_id):
            raise PermissionError("Approval requires an authenticated action from the configured project owner")
        if not proj.owner_discord_id or str(actor_id) != str(proj.owner_discord_id):
            raise PermissionError("Approver does not match the owner recorded for this project")

        with db.get_connection() as conn:
            if task_code:
                rows = conn.execute("SELECT * FROM tasks WHERE project_id = ? AND task_code = ?", (project_id, task_code)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tasks WHERE project_id = ? AND status = 'PENDING_APPROVAL'", (project_id,)).fetchall()
            if not rows:
                raise ValueError("No pending task proposals matched this approval request")
            if any(row["status"] != "PENDING_APPROVAL" or bool(row["human_approved"]) for row in rows):
                raise ValueError("Only unapproved pending task proposals can be approved")
            if task_code:
                targets = rows
            else:
                targets = rows
            for row in targets:
                task_hash = _task_approval_hash(row)
                conn.execute(
                    "UPDATE tasks SET human_approved = 1, status = 'APPROVED', approved_by = ?, approved_at = ?, approved_task_hash = ? WHERE id = ? AND project_id = ? AND status = 'PENDING_APPROVAL' AND human_approved = 0",
                    (str(actor_id), datetime.utcnow().isoformat(), task_hash, row["id"], project_id),
                )
            remaining = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status = 'PENDING_APPROVAL'",
                (project_id,),
            ).fetchone()[0]
            if remaining == 0:
                conn.execute("UPDATE projects SET current_state = 'APPROVED' WHERE id = ?", (project_id,))
            conn.commit()

            rows = conn.execute("SELECT * FROM tasks WHERE project_id = ?", (project_id,)).fetchall()
            tasks = [_row_to_task(r) for r in rows]

        return tasks

    def reject_project(self, project_id: str, actor_id: Optional[str], reason: str) -> None:
        """Record owner rejection without changing approved or executed work."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        if not settings.discord_owner_id or str(actor_id) != str(settings.discord_owner_id):
            raise PermissionError("Rejection requires an authenticated action from the configured project owner")
        if not project.owner_discord_id or str(actor_id) != str(project.owner_discord_id):
            raise PermissionError("Rejector does not match the owner recorded for this project")

        with db.get_connection() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status IN ('APPROVED', 'RUNNING', 'EXECUTING', 'VERIFIED')",
                (project_id,),
            ).fetchone()[0]
            if active:
                raise ValueError("A project with approved or executed tasks cannot be rejected as a pending proposal")
            conn.execute(
                "UPDATE tasks SET status = 'REJECTED', updated_at = ? WHERE project_id = ? AND status = 'PENDING_APPROVAL' AND human_approved = 0",
                (datetime.utcnow().isoformat(), project_id),
            )
            conn.execute("UPDATE projects SET current_state = 'ABORTED' WHERE id = ?", (project_id,))
            conn.execute(
                "INSERT INTO audit_logs (id, project_id, event_name, actor, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    project_id,
                    "project_proposal_rejected",
                    str(actor_id),
                    redact_secrets(reason),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    async def execute_project(self, project_id: str) -> Dict[str, Any]:
        """Phase 8: Execution, Pony Tail Audit & Adversarial Testing."""
        if not settings.task_execution_enabled:
            raise PermissionError("Task execution is disabled until a secure agent runner is explicitly configured")
        if not settings.secure_agent_task_runner_configured:
            raise PermissionError("Secure isolated native-agent runner is not implemented; no host task execution will be attempted")
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        ws_path = validate_workspace_path(Path(proj.project_md_path).parent)
        expected_md = (ws_path / "PROJECT.md").resolve()
        if Path(proj.project_md_path).resolve() != expected_md:
            raise PermissionError("Security Boundary Violation: project specification must be at the workspace root")

        workspace_dir = str(ws_path)

        with db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE project_id = ? AND human_approved = 1", (project_id,)).fetchall()
            for row in rows:
                if row["status"] != "APPROVED" or not row["approved_by"] or not row["approved_at"] or not row["approved_task_hash"]:
                    raise PermissionError("Task approval evidence is incomplete; execution is blocked")
                if row["approved_by"] != settings.discord_owner_id or row["approved_by"] != proj.owner_discord_id:
                    raise PermissionError("Recorded task approver is not the configured project owner")
                if _task_approval_hash(row) != row["approved_task_hash"]:
                    raise PermissionError("Task changed after approval; execution is blocked pending fresh owner approval")
            approved_tasks = [_row_to_task(r) for r in rows]

        if not approved_tasks:
            raise ValueError("No tasks approved for execution. Project Owner must approve first.")

        non_native = [
            task.assigned_agent
            for task in approved_tasks
            if not settings.secure_agent_task_runner_configured and (
                "agy" in task.assigned_agent.lower()
                or "gemini" in task.assigned_agent.lower()
                or "hermes" in task.assigned_agent.lower()
            )
        ]
        if non_native:
            raise PermissionError(
                "Execution is blocked because the assigned task adapters are local fallbacks, not native task runtimes: "
                + ", ".join(sorted(set(non_native)))
            )
        if not await runner.secure_test_runner_available():
            raise PermissionError("Task execution is blocked because the vetted secure test-runner image is unavailable locally")

        with db.get_connection() as conn:
            conn.execute("UPDATE projects SET current_state = 'EXECUTING' WHERE id = ?", (project_id,))
            conn.commit()

        execution_results = []
        for task in approved_tasks:
            logger.info("Executing %s assigned to %s", task.task_code, task.assigned_agent)
            
            # Dispatch to assigned agent
            if "codex" in task.assigned_agent.lower():
                res = await self.codex.execute_task(task, workspace_dir)
            elif "agy" in task.assigned_agent.lower():
                res = await self.agy.execute_task(task, workspace_dir)
            elif "gemini" in task.assigned_agent.lower():
                res = await self.gemini.execute_task(task, workspace_dir)
            else:
                res = await self.hermes.execute_task(task, workspace_dir)

            execution_results.append(res)

            with db.get_connection() as conn:
                conn.execute(
                    """INSERT INTO task_execution_logs
                       (id, task_id, exit_code, stdout, stderr, diff_patch, executed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid4()),
                        task.id,
                        res.get("exit_code"),
                        redact_secrets(json.dumps(res, default=str)),
                        redact_secrets(str(res.get("error") or "")),
                        redact_secrets(json.dumps({"session_id": res.get("session_id"), "created_files": res.get("created_files", [])})),
                        datetime.utcnow().isoformat(),
                    ),
                )
                conn.commit()
            
            # Update task status in DB
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE tasks SET status = 'IN_PROGRESS', completion_report = ? WHERE id = ?",
                    (res.get("report"), task.id)
                )
                conn.commit()

        # Run Pony Tail Audit on workspace
        audit_res = ponytail_guard.audit_workspace(workspace_dir)
        logger.info("Pony Tail Audit: %s (Audited: %d files)", audit_res["passed"], audit_res["audited_files"])

        # Run Adversarial Test Suite
        test_res = await runner.run_tests(workspace_dir)
        logger.info("Test Run Result: %s", test_res["success"])

        audit_and_test_evidence = {
            "ponytail_audit": audit_res,
            "test_command": test_res.get("command"),
            "test_success": test_res.get("success"),
        }
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO task_execution_logs
                   (id, task_id, container_id, exit_code, stdout, stderr, diff_patch, executed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()),
                    approved_tasks[0].id,
                    "agenthive-test-runner",
                    test_res.get("exit_code"),
                    redact_secrets(str(test_res.get("stdout") or "")),
                    redact_secrets(str(test_res.get("stderr") or "")),
                    redact_secrets(json.dumps(audit_and_test_evidence)),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

        # Final state determination
        final_state = "COMPLETED" if (audit_res["passed"] and test_res["success"]) else "FAILED"

        with db.get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE project_id = ? AND human_approved = 1",
                ("VERIFIED" if test_res["success"] and audit_res["passed"] else "FAILED", project_id)
            )
            conn.execute("UPDATE projects SET current_state = ? WHERE id = ?", (final_state, project_id))
            conn.commit()

        # Update PROJECT.md with final retrospective
        generated_files = sorted({
            str(path)
            for result in execution_results
            for path in (result.get("created_files") or result.get("generated_files") or [])
        })
        generated_file_lines = "\n".join(f"- `{path}`" for path in generated_files) or "- No generated files recorded."
        retro_md = (
            f"\n## 6. Execution & Test Verification\n\n"
            f"> **Final Status:** `{final_state}`\n"
            f"> **Execution Verified At:** {datetime.utcnow().isoformat()} UTC\n\n"
            f"### Pony Tail Skill Compliance Report:\n"
            f"- **Standard Library Only:** `{'PASSED' if audit_res['passed'] else 'VIOLATIONS DETECTED'}`\n"
            f"- **Audited Files:** {audit_res['audited_files']} Python modules\n\n"
            f"### Adversarial Test Suite Output:\n"
            f"```text\n"
            f"Command: {test_res.get('command')}\n"
            f"Exit Code: {test_res.get('exit_code')}\n"
            f"{test_res.get('stderr')}\n"
            f"{test_res.get('stdout')}\n"
            f"```\n\n"
            f"### Generated files recorded:\n{generated_file_lines}\n"
        )

        p_path = Path(proj.project_md_path)
        existing = p_path.read_text()
        updated = re.sub(
            r"## 6\. Execution & Test Verification.*",
            retro_md,
            existing,
            flags=re.DOTALL
        )
        p_path.write_text(updated)

        return {
            "project_id": project_id,
            "status": final_state,
            "ponytail_audit": audit_res,
            "test_results": test_res,
            "tasks_executed": len(execution_results),
            "project_md": str(p_path)
        }

orchestrator = Orchestrator()
