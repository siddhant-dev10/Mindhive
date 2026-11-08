"""Google Gemini Agent Adapter.
Specializes in Deep Reasoning, Edge-Case Discovery, Adversarial QA Strategy, and Risk Mitigation.
Supports live Google Gemini REST API execution with multi-turn session state,
utilizing currently supported models (gemini-2.5-pro, gemini-2.5-flash, gemini-1.5-pro).
"""

import asyncio
import json
import logging
import time
import httpx
from pathlib import Path
from typing import Dict, Any, List, Optional
from agenthive.agents.base import BaseAgent
from agenthive.models.project import IndependentAnalysis, TaskItem
from agenthive.config import settings
from agenthive.security import validate_workspace_path, validate_project_workspace, require_owner_approved_task

logger = logging.getLogger("agenthive.agents.gemini")

class GeminiAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent-gemini",
            name="Google Gemini",
            role="Deep Reasoning & QA Strategist",
            description="Focuses on risk audits, boundary stress testing, edge-case discovery, and adversarial verification.",
            capabilities=["deep_reasoning", "edge_case_discovery", "adversarial_testing", "risk_mitigation", "research"]
        )
        self.session_id = None
        self.last_runtime_evidence: Dict[str, Any] = {
            "runtime_mode": "gemini_local_fallback", "session_id": None,
            "request_id": None, "exit_status": None,
            "error_reason": "No Gemini API request has been made",
        }
        self.api_key = settings.gemini_api_key
        # Default to supported model gemini-3.5-flash / gemini-3.8-flash
        self.model = settings.gemini_model_pro or "gemini-3.5-flash"
        self.is_live = bool(self.api_key and not self.api_key.startswith("your_"))
        self.session_history: List[Dict[str, Any]] = []
        self.last_health_check = 0.0
        self.last_health_status: Dict[str, Any] = {
            "available": False,
            "mode": "Local fallback (not yet verified)",
        }

        if self.is_live:
            logger.info("Google Gemini Agent initialized with live API key using model %s", self.model)
        else:
            logger.info("Google Gemini Agent initialized in local adversarial QA engine mode (live key not set)")

    def reset_session(self):
        """Initializes a new independent reasoning session."""
        self.session_id = None
        self.session_history = []

    async def check_model_availability(self, *, force: bool = False) -> Dict[str, Any]:
        """Probes Gemini API connectivity, key validity, and model readiness."""
        if not self.is_live:
            self.last_health_status = {
                "available": False,
                "model": self.model,
                "status_code": None,
                "reason": "GEMINI_API_KEY environment variable not configured",
                "mode": "Local fallback (API credential missing)",
            }
            self.last_health_check = time.monotonic()
            return dict(self.last_health_status)
        if not force and self.last_health_check and time.monotonic() - self.last_health_check < 60:
            return dict(self.last_health_status)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"
        headers = {"x-goog-api-key": self.api_key}
        self.last_health_check = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    model_data = res.json()
                    methods = model_data.get("supportedGenerationMethods", [])
                    available = "generateContent" in methods
                    self.last_health_status = {
                        "available": available,
                        "model": self.model,
                        "status_code": 200,
                        "reason": None if available else "Configured model does not support generateContent",
                        "mode": f"Live Gemini API ({self.model})" if available else "Local fallback (model unavailable)",
                    }
                    return dict(self.last_health_status)
                logger.warning("Gemini model probe failed with HTTP %d", res.status_code)
                self.last_health_status = {
                    "available": False,
                    "model": self.model,
                    "status_code": res.status_code,
                    "reason": "Gemini API rejected the configured credential or model",
                    "mode": "Local fallback (API unavailable)",
                }
                return dict(self.last_health_status)
        except Exception as e:
            logger.error("Gemini API health check failed (%s)", type(e).__name__)
            self.last_health_status = {
                "available": False,
                "model": self.model,
                "status_code": None,
                "reason": type(e).__name__,
                "mode": "Local fallback (API unreachable)",
            }
            return dict(self.last_health_status)

    def get_runtime_status(self) -> Dict[str, Any]:
        """Reports configured credentials separately from verified API availability."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "model": self.model,
            "credential_configured": self.is_live,
            "api_available": bool(self.last_health_status.get("available")),
            "runtime_mode": self.last_health_status.get("mode", "Local fallback (not verified)"),
            "last_health_check": self.last_health_check or None,
        }

    @staticmethod
    def _local_qa_findings(brief: str) -> Dict[str, List[str]]:
        """Return deterministic text-presence checks, not an LLM analysis."""
        text = (brief or "").lower()
        checks = {
            "acceptance criteria": ("acceptance", "success criteria", "definition of done"),
            "test strategy": ("test", "verification", "validate"),
            "security requirements": ("security", "authentication", "authorization", "privacy"),
            "failure handling": ("failure", "retry", "timeout", "error handling"),
            "operational constraints": ("deployment", "monitoring", "backup", "recovery"),
        }
        observed = [label for label, terms in checks.items() if any(term in text for term in terms)]
        return {"observed": observed, "missing": [label for label in checks if label not in observed]}

    async def _call_gemini_api(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """Calls official Google Gemini REST API with independent multi-turn session history.
        Security: API key passed in x-goog-api-key header to prevent query parameter exposure in access logs.
        """
        if not self.is_live:
            self.last_runtime_evidence = {
                "runtime_mode": "gemini_local_fallback", "session_id": None,
                "request_id": None, "exit_status": None,
                "error_reason": "GEMINI_API_KEY is not configured; no API request made",
            }
            return None

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }
        
        # Append user prompt to session history
        user_turn = {"role": "user", "parts": [{"text": prompt}]}
        contents = self.session_history + [user_turn]

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1500
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0]["content"]["parts"][0]["text"]
                        # Persist turns in multi-turn session history
                        self.session_history.append(user_turn)
                        self.session_history.append({"role": "model", "parts": [{"text": text}]})
                        self.last_health_check = time.monotonic()
                        self.last_health_status = {
                            "available": True,
                            "model": self.model,
                            "status_code": 200,
                            "mode": f"Live Gemini API ({self.model})",
                        }
                        self.last_runtime_evidence = {
                            "runtime_mode": "gemini_api", "session_id": None,
                            "request_id": res.headers.get("x-request-id") or res.headers.get("x-goog-request-id"),
                            "exit_status": 200, "error_reason": None,
                        }
                        return text
                    self.last_health_check = time.monotonic()
                    self.last_health_status = {
                        "available": False,
                        "model": self.model,
                        "status_code": 200,
                        "reason": "No candidate returned",
                        "mode": "Local fallback (empty model response)",
                    }
                elif res.status_code in (401, 403):
                    self.last_health_check = time.monotonic()
                    self.last_health_status = {"available": False, "model": self.model, "status_code": res.status_code, "mode": "Local fallback (credential rejected)"}
                    logger.error("Gemini API authentication/permission failure (%d): Key invalid or unauthorized.", res.status_code)
                elif res.status_code == 429:
                    self.last_health_check = time.monotonic()
                    self.last_health_status = {"available": False, "model": self.model, "status_code": 429, "mode": "Local fallback (rate limited)"}
                    logger.warning("Gemini API rate limit exceeded (429): Quota exhausted or throttled.")
                elif res.status_code == 400:
                    self.last_health_check = time.monotonic()
                    self.last_health_status = {"available": False, "model": self.model, "status_code": 400, "mode": "Local fallback (invalid request)"}
                    logger.warning("Gemini API bad request (400): Content filtered or malformed request payload.")
                else:
                    self.last_health_check = time.monotonic()
                    self.last_health_status = {"available": False, "model": self.model, "status_code": res.status_code, "mode": "Local fallback (API error)"}
                    logger.warning("Gemini API returned unexpected HTTP %d", res.status_code)
        except httpx.TimeoutException:
            self.last_health_check = time.monotonic()
            self.last_health_status = {"available": False, "model": self.model, "mode": "Local fallback (API timeout)"}
            logger.warning("Gemini API request timed out after 25s.")
        except Exception as e:
            self.last_health_check = time.monotonic()
            self.last_health_status = {"available": False, "model": self.model, "mode": "Local fallback (API error)"}
            logger.error("Gemini API call failed (%s)", type(e).__name__)
        self.last_runtime_evidence = {
            "runtime_mode": "gemini_local_fallback", "session_id": None,
            "request_id": None, "exit_status": self.last_health_status.get("status_code"),
            "error_reason": self.last_health_status.get("reason") or self.last_health_status.get("mode", "Gemini API request failed"),
        }
        return None

    async def perform_independent_analysis(self, project_id: str, project_name: str, brief: str) -> IndependentAnalysis:
        logger.info("Gemini performing independent analysis for %s (Live API: %s, Model: %s)", project_name, self.is_live, self.model)
        
        sys_prompt = "You are Google Gemini, Deep Reasoning and Adversarial QA Strategist in AgentHive. Prioritize Pony Tail minimalism (pure standard library)."
        user_prompt = (
            f"Critically analyze this project brief for risks, concurrency flaws, and edge cases:\n"
            f"Project: {project_name}\nBrief: {brief}\n\n"
            f"Identify potential race conditions, memory leaks, and bounded validation rules."
        )

        llm_response = await self._call_gemini_api(user_prompt, system_instruction=sys_prompt)

        findings = self._local_qa_findings(brief)
        understanding = (
            "[Google Gemini LOCAL FALLBACK — deterministic text checks only] No Gemini API response was produced. "
            f"The brief explicitly mentions: {', '.join(findings['observed']) or 'none of the checked QA topics'}."
        )
        architecture = "No architecture proposal: the local QA fallback does not perform model reasoning."
        if llm_response:
            understanding = f"[Live Gemini Reasoning] {llm_response[:220]}..."
            architecture = f"[Gemini Resilient Architecture] {llm_response[:280]}..."

        return IndependentAnalysis(
            project_id=project_id,
            agent_id=self.agent_id,
            agent_name=self.name,
            understanding=understanding,
            architecture=architecture,
            tech_stack=[],
            implementation_plan=[f"Confirm that the brief defines {item}" for item in findings["missing"]],
            risks=[f"The brief does not explicitly define {item}" for item in findings["missing"]],
            missing_requirements=list(findings["missing"]),
            complexity="UNKNOWN" if not llm_response else "HIGH",
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
        prompt = (
            f"You are Google Gemini in a Switch collaboration room debating architecture for '{project_name}'. "
            f"Previous turn: {room_messages[-1]['sender_name'] if room_messages else 'None'}. "
            f"Challenge any potential flaws in data structures or concurrency in 80 words."
        )
        llm_response = await self._call_gemini_api(prompt)
        if llm_response and self.last_runtime_evidence.get("runtime_mode") == "gemini_api":
            return f"### [CHALLENGE & RISK AUDIT] Turn {turn_index}\n**Speaker:** Google Gemini (Live Gemini API - {self.model})\n\n{llm_response[:350]}"

        findings = self._local_qa_findings(brief)
        previous_senders = [str(item.get("sender_name", "unknown")) for item in room_messages]
        return (
            f"### [DETERMINISTIC LOCAL QA CHECK] Turn {turn_index}\n"
            "**Speaker:** Google Gemini (LOCAL FALLBACK — NO API REQUEST)\n"
            f"Explicitly mentioned QA topics: {', '.join(findings['observed']) or 'none detected by the local text checks'}.\n"
            f"Topics not explicitly found in the brief: {', '.join(findings['missing']) or 'none of the checked topics'}.\n"
            f"Prior room senders observed: {', '.join(previous_senders) or 'none'}. This rule-based check does not review code or produce model reasoning."
        )

    async def execute_task(self, task: TaskItem, workspace_dir: str) -> Dict[str, Any]:
        """Execute task inside the isolated runner."""
        require_owner_approved_task(task, workspace_dir)
        from agenthive.engine.execution import runner
        return await runner.execute_task_isolated(task, workspace_dir)
