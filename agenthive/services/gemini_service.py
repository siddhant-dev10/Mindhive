"""Google Gemini Conversational Service & Engineering Manager.
Provides natural conversation, codebase reasoning, workflow prioritization,
and multi-turn session coordination using the official Google Gen AI capabilities.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional
import httpx

from agenthive.config import settings
from agenthive.security import redact_secrets
from agenthive.services.github_service import CodebaseInventory

logger = logging.getLogger("agenthive.services.gemini")

ENGINEERING_MANAGER_SYSTEM_PROMPT = """You are MindHive, an elite AI Engineering Manager coordinating a multi-agent software engineering team (ChatGPT Codex, Antigravity AGY, Google Gemini, and Nous Hermes) connected via the Official Switch Protocol.

Core Principles:
1. Persona: Decisive, concise, rigorous, and technical. You speak like a senior engineering manager, not a generic corporate chatbot.
2. Codebase Understanding: When analyzing a repository, cite real observed files, architecture patterns, dependencies, and test states. Distinguish hard facts from inferred conclusions.
3. Decision-Making: When asked "what should we work on next?", propose prioritized, concrete engineering workflows with explicit acceptance criteria, agent assignments, and risk mitigation.
4. Human-in-the-Loop: You propose plans and coordinate execution, but you NEVER execute code without human owner approval.
5. Honest Provenance: If an agent runtime or tool is unavailable or in fallback mode, state it plainly. Never hallucinate fake executions or simulated consensus.
6. Tone: Direct and actionable. Avoid fluffy filler text, generic disclaimers, or excessive emojis. Focus on technical deliverables and architectural integrity.
"""


class ConversationSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: List[Dict[str, Any]] = []
        self.active_repo: Optional[CodebaseInventory] = None
        self.last_interaction = time.monotonic()

    def add_turn(self, role: str, text: str):
        self.history.append({"role": role, "parts": [{"text": text}]})
        self.last_interaction = time.monotonic()
        # Keep sliding window of last 20 turns for token safety
        if len(self.history) > 20:
            self.history = self.history[-20:]


class GeminiConversationalService:
    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_conversational_model or "gemini-3.5-flash"
        self.sessions: Dict[str, ConversationSession] = {}
        self.sdk_client = None

        # Attempt to initialize official google-genai SDK if available
        if self.api_key and not self.api_key.startswith("your_"):
            try:
                from google import genai
                self.sdk_client = genai.Client(api_key=self.api_key)
                logger.info("Initialized official Google Gen AI SDK client with model %s", self.model)
            except Exception as e:
                logger.warning("Could not initialize google-genai SDK (%s); using direct REST fallback", type(e).__name__)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))

    def get_or_create_session(self, session_id: str) -> ConversationSession:
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationSession(session_id)
        return self.sessions[session_id]

    async def check_availability(self) -> Dict[str, Any]:
        """Probes Gemini API connectivity, key validity, and model responsiveness."""
        if not self.is_configured:
            return {
                "available": False,
                "model": self.model,
                "reason": "GEMINI_API_KEY environment variable is not configured",
                "mode": "Conversational AI Offline (API key missing)",
            }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"
        headers = {"x-goog-api-key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return {
                        "available": True,
                        "model": self.model,
                        "reason": None,
                        "mode": f"Live Gemini Conversational API ({self.model})",
                    }
                return {
                    "available": False,
                    "model": self.model,
                    "reason": f"API returned HTTP {res.status_code}",
                    "mode": "Conversational AI Offline (credential/model error)",
                }
        except Exception as e:
            return {
                "available": False,
                "model": self.model,
                "reason": type(e).__name__,
                "mode": "Conversational AI Offline (network unreachable)",
            }

    async def chat(
        self,
        session_id: str,
        user_message: str,
        codebase_inventory: Optional[CodebaseInventory] = None,
        retries: int = 2
    ) -> str:
        """Send a natural conversational query to Gemini with session memory and codebase context."""
        session = self.get_or_create_session(session_id)
        if codebase_inventory:
            session.active_repo = codebase_inventory

        if not self.is_configured:
            return (
                "⚠️ **Conversational AI Offline:** `GEMINI_API_KEY` is not configured on the MindHive server.\n\n"
                "To enable conversational responses, set a valid `GEMINI_API_KEY` in `.env` and restart the backend. "
                "You can still use registered slash commands such as `/newproject`, `/status`, and `/approve`."
            )

        # Build context prompt
        system_instruction = ENGINEERING_MANAGER_SYSTEM_PROMPT
        if session.active_repo:
            repo_summary = json.dumps(session.active_repo.to_dict(), indent=2)
            system_instruction += f"\n\nActive Repository Context ({session.active_repo.repo_name}):\n```json\n{repo_summary}\n```\n"

        # Try SDK first if available
        for attempt in range(1, retries + 2):
            try:
                if self.sdk_client:
                    response_text = await self._call_sdk(session, user_message, system_instruction)
                else:
                    response_text = await self._call_rest(session, user_message, system_instruction)

                if response_text:
                    clean_reply = redact_secrets(response_text.strip())
                    session.add_turn("user", user_message)
                    session.add_turn("model", clean_reply)
                    return clean_reply
            except Exception as e:
                logger.warning("Gemini chat attempt %d failed (%s)", attempt, type(e).__name__)
                if attempt <= retries:
                    await asyncio.sleep(1.0 * attempt)
                else:
                    return f"⚠️ **Gemini API Error:** Could not complete conversational request ({type(e).__name__}). Please try again."

        return "⚠️ **Gemini API Error:** No response received from conversational model."

    async def _call_sdk(self, session: ConversationSession, prompt: str, system_instruction: str) -> Optional[str]:
        """Async SDK call using official google-genai client in thread pool."""
        loop = asyncio.get_running_loop()

        def sync_call():
            contents = []
            for item in session.history:
                contents.append(item)
            contents.append({"role": "user", "parts": [{"text": prompt}]})

            response = self.sdk_client.models.generate_content(
                model=self.model,
                contents=contents,
                config={
                    "system_instruction": system_instruction,
                    "temperature": 0.3,
                    "max_output_tokens": 2048,
                }
            )
            return response.text if response else None

        return await asyncio.wait_for(loop.run_in_executor(None, sync_call), timeout=45.0)

    async def _call_rest(self, session: ConversationSession, prompt: str, system_instruction: str) -> Optional[str]:
        """Direct REST API fallback using httpx with x-goog-api-key header."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        user_turn = {"role": "user", "parts": [{"text": prompt}]}
        contents = session.history + [user_turn]

        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2048,
            }
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    return candidates[0]["content"]["parts"][0]["text"]
            elif res.status_code == 429:
                logger.error("Gemini API rate limit exceeded (HTTP 429)")
                raise PermissionError("Gemini API rate limit exceeded. Please back off and retry.")
            else:
                logger.error("Gemini REST API returned error %d: %s", res.status_code, res.text[:200])
                raise RuntimeError(f"Gemini API returned status {res.status_code}")
        return None

    def explain_codebase_deterministic(self, inventory: CodebaseInventory) -> str:
        """Deterministic fallback explanation when live LLM API is unreachable."""
        arch = inventory.architecture_overview
        rec_lines = "\n".join(
            f"**{r['priority']} — {r['title']}**\n- *Rationale:* {r['rationale']}\n- *Estimated Complexity:* {r['estimated_complexity']}\n- *Lead Agent:* {r['responsible_agent']}"
            for r in inventory.improvement_recommendations
        )
        assess = inventory.engineering_assessment
        features = "\n".join(f"- {f}" for f in assess.get("existing_functionality", []))
        incomplete = "\n".join(f"- {i}" for i in assess.get("incomplete_functionality", []))

        return (
            f"## 🏛️ Codebase Analysis: `{inventory.repo_name}`\n\n"
            f"{inventory.description}\n\n"
            f"### ⚙️ Technical Architecture\n{arch}\n\n"
            f"### 🔍 Observed Capabilities\n{features}\n\n"
            f"### ⚠️ Gaps & Technical Debt\n{incomplete}\n\n"
            f"### 🎯 Recommended Development Workflow\n{rec_lines}\n\n"
            f"> *Note: Analysis derived directly from codebase inventory and manifest citations.*"
        )


gemini_service = GeminiConversationalService()
