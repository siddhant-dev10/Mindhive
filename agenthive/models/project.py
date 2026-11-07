"""Data models for Projects, Analyses, Discussions, and Tasks."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str = Field(..., min_length=5)
    po_discord_id: Optional[str] = "po_admin"
    guild_id: Optional[str] = "default_guild"

class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str
    description: str
    current_state: str = "DRAFT"  # DRAFT, ANALYZING, DISCUSSING, AWAITING_APPROVAL, EXECUTING, COMPLETED, ABORTED
    switch_room_id: Optional[str] = None
    owner_discord_id: Optional[str] = None
    project_md_path: str
    discord_channel_id: Optional[str] = None
    discord_thread_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class IndependentAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    agent_id: str
    agent_name: str
    understanding: str
    architecture: str
    tech_stack: List[str]
    implementation_plan: List[str]
    risks: List[str]
    missing_requirements: List[str]
    complexity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    runtime_evidence: Dict[str, Any] = Field(default_factory=dict)

class DiscussionMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    turn_index: int
    sender_id: str
    sender_name: str
    sender_role: str = "AGENT"  # AGENT, SUPERVISOR, HUMAN_PO, SYSTEM
    reply_to_agent: Optional[str] = None
    content: str
    switch_event_id: Optional[str] = None
    switch_message_id: Optional[str] = None
    switch_room_id: Optional[str] = None
    runtime_evidence: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None

class TaskItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    task_code: str  # e.g., TASK-01
    title: str
    description: str
    assigned_agent: str
    priority: str = "MEDIUM"  # P0, P1, P2 / HIGH, MEDIUM, LOW
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, APPROVED, IN_PROGRESS, VERIFIED, FAILED, ESCALATED
    human_approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    approved_task_hash: Optional[str] = None
    dependencies: List[str] = []
    acceptance_criteria: List[str] = []
    completion_report: Optional[str] = None

class HermesSupervisorPlan(BaseModel):
    project_id: str
    recommended_architecture: str
    agreements: List[str]
    disagreements: List[str]
    evaluated_arguments: str
    proposed_roles: Dict[str, str]
    tasks: List[TaskItem]
    discussion_sources: List[Dict[str, Any]] = Field(default_factory=list)
    requires_human_approval: bool = True
