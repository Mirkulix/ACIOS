"""AICOS Core Models: Pydantic v2 models for agents, messages, tasks, and company config."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """All possible agent roles in an AICOS company."""

    CEO = "ceo"
    CFO = "cfo"
    CTO = "cto"
    SALES = "sales"
    MARKETING = "marketing"
    SUPPORT = "support"
    OPERATIONS = "operations"
    DEVELOPER = "developer"
    HR = "hr"


class MessageType(StrEnum):
    DIRECT = "direct"
    BROADCAST = "broadcast"
    ESCALATION = "escalation"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    """Configuration for a single AI agent/employee."""

    name: str = Field(..., description="Unique display name for the agent")
    role: AgentRole
    model: str = Field(default="claude-sonnet-4-5-20250929", description="Anthropic model ID")
    system_prompt: str = Field(default="", description="System prompt injected into every LLM call")
    tools: list[str] = Field(default_factory=list, description="Tool names this agent can use")
    enabled: bool = True
    max_concurrent_tasks: int = Field(default=3, ge=1)


# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------

class Message(BaseModel):
    """A single message flowing through the communication bus."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    from_agent: str
    to_agent: str = Field(default="", description="Empty string means broadcast")
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_type: MessageType = MessageType.DIRECT
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class Task(BaseModel):
    """A unit of work assigned to an agent."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    description: str = ""
    assigned_to: str = Field(default="", description="Agent name or empty if unassigned")
    created_by: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: list[str] = Field(default_factory=list, description="Task IDs that must complete first")
    result: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# KPI tracking
# ---------------------------------------------------------------------------

class KPI(BaseModel):
    """A single KPI measurement."""

    name: str
    value: float
    target: float = 0.0
    agent_role: AgentRole | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Company configuration (loaded from YAML)
# ---------------------------------------------------------------------------

class OrchestrationSettings(BaseModel):
    """How the orchestrator should behave."""

    tick_interval_seconds: float = Field(default=5.0, description="Main loop sleep interval")
    max_parallel_tasks: int = Field(default=10, ge=1)
    escalation_enabled: bool = True
    auto_assign: bool = True


class CompanyInfo(BaseModel):
    """Top-level company metadata."""

    name: str = "AICOS Company"
    type: str = "agency"
    description: str = ""


class CompanyConfig(BaseModel):
    """Root configuration object — mirrors company.yaml."""

    company: CompanyInfo = Field(default_factory=CompanyInfo)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    workflows: list[str] = Field(default_factory=list)
    focus_kpis: list[str] = Field(default_factory=list)
    orchestration: OrchestrationSettings = Field(default_factory=OrchestrationSettings)
