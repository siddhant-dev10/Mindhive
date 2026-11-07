"""Hermes Supervisor Agent Adapter.
Distinguishes the external Nous Research Hermes Agent runtime (daemon/binary)
from AgentHive's locally implemented supervisory consensus logic.
If the external Hermes daemon or binary is not active, cleanly operates in
Local Supervisory Engine mode with full transparency.
"""

import asyncio
import json
import logging
import os
import httpx
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from agenthive.agents.base import BaseAgent
from agenthive.models.project import IndependentAnalysis, TaskItem, HermesSupervisorPlan
from agenthive.config import settings
from agenthive.security import validate_workspace_path, validate_project_workspace, require_owner_approved_task

logger = logging.getLogger("agenthive.agents.hermes")

class HermesRuntimeAdapter:
    """Manages connection to the external Nous Research Hermes Agent daemon or CLI."""
    def __init__(self, daemon_url: str, binary_path: str, daemon_token: Optional[str] = None):
        self.daemon_url = daemon_url.rstrip("/")
        self.binary_path = binary_path
        self.daemon_token = daemon_token
        self.is_daemon_connected = False
        self.is_binary_available = os.path.exists(binary_path) and os.access(binary_path, os.X_OK)
        self.last_health_check = 0.0
        self.last_health_error: Optional[str] = None
        self.last_request_id: Optional[str] = None
        self.last_status_code: Optional[int] = None

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.daemon_token}"} if self.daemon_token else {}

    async def check_liveness(self, *, force: bool = False) -> bool:
        """Probes the Hermes daemon for health / liveness."""
        if not force and time.monotonic() - self.last_health_check < 10.0:
            return self.is_daemon_connected
        if not self.daemon_url:
            self.is_daemon_connected = False
            return False
        self.last_health_check = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.daemon_url}/health", headers=self.headers)
                self.is_daemon_connected = (res.status_code == 200)
                self.last_health_error = None if self.is_daemon_connected else f"HTTP {res.status_code}"
                return self.is_daemon_connected
        except Exception as exc:
            self.is_daemon_connected = False
            self.last_health_error = type(exc).__name__
            return False

    async def query_hermes_daemon(self, prompt: str) -> Optional[str]:
        """Dispatches reasoning request to live Hermes daemon if available."""
        if not self.is_daemon_connected:
            return None
        self.last_request_id = None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.daemon_url}/v1/supervise",
                    json={"prompt": prompt, "temperature": 0.2},
                    headers=self.headers,
                )
                if res.status_code == 200:
                    data = res.json()
                    response = data.get("response")
                    if response:
                        self.is_daemon_connected = True
                        self.last_health_error = None
                        self.last_status_code = res.status_code
                        self.last_request_id = res.headers.get("x-request-id") or data.get("request_id")
                        return response
                    self.last_health_error = "Empty daemon response"
                else:
                    self.is_daemon_connected = False
                    self.last_health_error = f"HTTP {res.status_code}"
                    self.last_status_code = res.status_code
                    self.last_status_code = res.status_code
        except Exception as e:
            self.is_daemon_connected = False
            self.last_health_error = type(e).__name__
            self.last_status_code = None
            logger.warning("Hermes daemon dispatch failed (%s)", type(e).__name__)
        return None

class HermesAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent-hermes",
            name="Hermes Supervisor",
            role="Autonomous Supervisor & Orchestrator",
            description="Executive coordinator: moderates debate, synthesizes consensus, arbitrates technical conflicts, and generates human-governed WBS plans.",
            capabilities=["moderation", "consensus_synthesis", "conflict_arbitration", "wbs_allocation", "progress_tracking"]
        )
        self.session_id = None
        self.last_runtime_evidence: Dict[str, Any] = {
            "runtime_mode": "local_governance_fallback",
            "session_id": None,
            "request_id": None,
            "exit_status": None,
            "error_reason": "Hermes daemon and CLI execution are unavailable",
        }
        self.runtime_adapter = HermesRuntimeAdapter(
            daemon_url=settings.hermes_daemon_url,
            binary_path=settings.hermes_binary_path,
            daemon_token=settings.hermes_daemon_token,
        )
        logger.info(
            "Hermes Agent initialized (Daemon URL: %s, Binary: %s, Daemon Active: %s)",
            settings.hermes_daemon_url,
            settings.hermes_binary_path,
            self.runtime_adapter.is_daemon_connected
        )

    def get_runtime_status(self) -> Dict[str, Any]:
        """Distinguishes live Hermes runtime from local supervisory engine."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "daemon_connected": self.runtime_adapter.is_daemon_connected,
            "binary_available": self.runtime_adapter.is_binary_available,
            "runtime_mode": "Live Hermes Daemon" if self.runtime_adapter.is_daemon_connected else "LOCAL GOVERNANCE FALLBACK"
        }

    async def perform_independent_analysis(self, project_id: str, project_name: str, brief: str) -> IndependentAnalysis:
        """Record transparent unavailability; governance fallback is not an independent analyst."""
        self.last_runtime_evidence = {
            "runtime_mode": "local_governance_fallback",
            "session_id": None,
            "request_id": None,
            "exit_status": None,
            "error_reason": "Hermes daemon/CLI was not invoked for independent analysis",
        }
        return IndependentAnalysis(
            project_id=project_id,
            agent_id=self.agent_id,
            agent_name=self.name,
            understanding="Hermes external analysis was not run. The local governance fallback does not claim an independent project review.",
            architecture="No architecture proposal was generated by Hermes independent analysis.",
            tech_stack=[],
            implementation_plan=[],
            risks=["Hermes daemon/CLI analysis is unavailable"],
            missing_requirements=[],
            complexity="UNKNOWN",
            runtime_evidence=dict(self.last_runtime_evidence),
        )

    async def generate_discussion_turn(
        self,
        project_id: str,
        project_name: str,
        brief: str,
        room_messages: List[Dict[str, Any]],
        turn_index: int
    ) -> str:
        # Check if live daemon is reachable
        await self.runtime_adapter.check_liveness()
        status = self.get_runtime_status()

        daemon_response = None
        if self.runtime_adapter.is_daemon_connected:
            prompt = f"Synthesize consensus for project {project_name}. Turn {turn_index}."
            daemon_response = await self.runtime_adapter.query_hermes_daemon(prompt)

        if daemon_response:
            self.last_runtime_evidence = {
                "runtime_mode": "hermes_daemon",
                "session_id": None,
                "request_id": self.runtime_adapter.last_request_id,
                "exit_status": self.runtime_adapter.last_status_code or 200,
                "error_reason": None,
            }
            return f"### [SUPERVISOR INTERVENTION & MODERATION] Turn {turn_index}\n**Speaker:** Hermes (Live Hermes Daemon)\n\n{daemon_response}"

        self.last_runtime_evidence = {
            "runtime_mode": "local_governance_fallback",
            "session_id": None,
            "request_id": None,
            "exit_status": None,
            "error_reason": self.runtime_adapter.last_health_error or "Hermes daemon request unavailable; local governance used",
        }

        observed = [str(item.get("sender_name") or "unknown") for item in room_messages]
        return (
            f"### [LOCAL GOVERNANCE STATUS] Turn {turn_index}\n"
            "**Speaker:** Hermes Supervisor (LOCAL GOVERNANCE FALLBACK — NO DAEMON RESPONSE)\n"
            f"The local coordinator received {len(room_messages)} earlier persisted messages from: "
            f"{', '.join(observed) or 'no prior senders'}. It has not inferred consensus or attributed proposals. "
            "The project owner should review the source messages and the proposed work breakdown before approval."
        )

    def synthesize_plan(
        self,
        project_id: str,
        project_name: str,
        brief: str,
        analyses: List[IndependentAnalysis],
        discussions: List[Dict[str, Any]]
    ) -> HermesSupervisorPlan:
        """Create a transparent, generic owner-review checklist from persisted sources."""
        if not discussions:
            raise ValueError("Hermes cannot produce a discussion-informed plan without persisted discussion messages")

        sources = [
            {
                "turn_index": item.get("turn_index"),
                "sender_id": item.get("sender_id"),
                "sender_name": item.get("sender_name"),
                "switch_event_id": item.get("switch_event_id"),
                "switch_message_id": item.get("switch_message_id"),
                "excerpt": str(item.get("content") or "")[:300],
                "runtime_evidence": item.get("runtime_evidence_json"),
            }
            for item in discussions
        ]
        ordered_sources = "\n".join(
            f"- Turn {source['turn_index']} from {source['sender_name']} "
            f"(event={source['switch_event_id'] or 'unavailable'}, message={source['switch_message_id'] or 'unavailable'}): {source['excerpt']}"
            for source in sources
        )
        evaluated = (
            "LOCAL GOVERNANCE FALLBACK: no Hermes daemon/CLI synthesis request was made. "
            "This is a generic owner-review work breakdown linked to the following persisted discussion messages; "
            "it does not assert consensus or native-agent agreement.\n" + ordered_sources
        )
        runtime_modes = {
            analysis.agent_name: analysis.runtime_evidence.get("runtime_mode", "unknown")
            for analysis in analyses
        }
        roles = {
            name: f"Proposed reviewer/implementer; observed analysis runtime: {runtime_modes.get(name, 'not recorded')}"
            for name in ("ChatGPT Codex", "AGY (Antigravity)", "Google Gemini")
        }
        roles["Hermes Supervisor"] = "Local governance fallback; external Hermes runtime not verified"
        tasks = [
            TaskItem(
                project_id=project_id,
                task_code="TASK-01",
                title="Implement the core project requirements",
                description=f"Implement the requirements recorded in the project brief: {brief}",
                assigned_agent="ChatGPT Codex",
                priority="P1",
                status="PENDING_APPROVAL",
                acceptance_criteria=[
                    "Implementation is traceable to the project brief",
                    "Changed files are listed with execution provenance",
                    "Any added dependency is identified for owner review",
                ],
            ),
            TaskItem(
                project_id=project_id,
                task_code="TASK-02",
                title="Review integration and operational requirements",
                description="Review interfaces, configuration, failure handling, and deployment requirements that apply to this project.",
                assigned_agent="AGY (Antigravity)",
                priority="P1",
                status="PENDING_APPROVAL",
                dependencies=["TASK-01"],
                acceptance_criteria=[
                    "Integration assumptions are documented",
                    "Operational risks and unresolved requirements are recorded",
                ],
            ),
            TaskItem(
                project_id=project_id,
                task_code="TASK-03",
                title="Define and run project-specific verification",
                description="Create verification cases from the project brief and the actual discussion risks; report test execution evidence.",
                assigned_agent="Google Gemini",
                priority="P1",
                status="PENDING_APPROVAL",
                dependencies=["TASK-01"],
                acceptance_criteria=[
                    "Tests map to stated acceptance criteria",
                    "Exact command, exit status, and output are recorded",
                ],
            ),
        ]
        return HermesSupervisorPlan(
            project_id=project_id,
            recommended_architecture=(
                "No architecture decision was generated. This local governance plan is a generic owner-review breakdown "
                "grounded in the project brief and the persisted discussion sources listed below."
            ),
            agreements=[],
            disagreements=["Consensus was not inferred by the local governance fallback."],
            evaluated_arguments=evaluated,
            proposed_roles=roles,
            tasks=tasks,
            discussion_sources=sources,
            requires_human_approval=True,
        )

    async def execute_task(self, task: TaskItem, workspace_dir: str) -> Dict[str, Any]:
        """Hermes is a governance runtime, not a task execution adapter."""
        require_owner_approved_task(task, workspace_dir)
        raise PermissionError("Hermes is a governance adapter, not a task execution runtime")
