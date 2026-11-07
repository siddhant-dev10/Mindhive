"""Base Agent Class for all AgentHive participants."""

import abc
import logging
from typing import Dict, Any, List, Optional
from agenthive.models.project import IndependentAnalysis, TaskItem
from agenthive.models.events import SwitchAgentRegistration
from agenthive.switch.client import SwitchAgentClient
from agenthive.config import settings

logger = logging.getLogger("agenthive.agents.base")

class BaseAgent(abc.ABC):
    def __init__(self, agent_id: str, name: str, role: str, description: str, capabilities: List[str]):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.description = description
        self.capabilities = capabilities
        
        self.registration = SwitchAgentRegistration(
            agent_id=agent_id,
            name=name,
            role=role,
            description=description,
            capabilities=capabilities
        )
        self.client: Optional[SwitchAgentClient] = None

    async def connect_to_switch(self, switch_url: Optional[str] = None):
        url = switch_url or settings.switch_core_url
        if self.client and self.client.is_connected:
            return
        if self.client:
            await self.client.disconnect()
        self.client = SwitchAgentClient(
            url,
            self.registration,
            registration_token=settings.switch_registration_token or settings.switch_api_key,
            mode=settings.switch_mode,
        )
        await self.client.connect()

    async def join_room(self, room_id: str):
        if not self.client:
            raise RuntimeError(f"Agent {self.name} is not connected to Switch")
        await self.client.join_room(room_id)

    async def send_room_message(self, room_id: str, content: str, reply_to: Optional[str] = None):
        if not self.client:
            raise RuntimeError(f"Agent {self.name} is not connected to Switch")
        return await self.client.send_message(room_id, content, reply_to)

    @abc.abstractmethod
    async def perform_independent_analysis(self, project_id: str, project_name: str, brief: str) -> IndependentAnalysis:
        """Phase 4: Performs isolated analysis of the project brief before entering any discussion."""
        pass

    @abc.abstractmethod
    async def generate_discussion_turn(
        self,
        project_id: str,
        project_name: str,
        brief: str,
        room_messages: List[Dict[str, Any]],
        turn_index: int
    ) -> str:
        """Phase 5: Generates a debate turn or peer critique in the Switch Room."""
        pass

    @abc.abstractmethod
    async def execute_task(self, task: TaskItem, workspace_dir: str) -> Dict[str, Any]:
        """Phase 8: Executes assigned WBS task within container or sandboxed environment."""
        pass
