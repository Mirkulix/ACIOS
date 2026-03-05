"""AICOS BaseAgent: Foundation class all AI employee agents inherit from."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import anthropic

from core.models import (
    AgentConfig,
    AgentRole,
    KPI,
    Message,
    MessageType,
    Task,
    TaskPriority,
    TaskStatus,
)
from core.communication import CommunicationBus
from core.memory import MemoryManager

logger = logging.getLogger("aicos.agents")


# ---------------------------------------------------------------------------
# TaskResult — returned by act()
# ---------------------------------------------------------------------------

class TaskResult:
    """Encapsulates the outcome of an agent working on a task."""

    __slots__ = ("task_id", "success", "output", "artifacts", "error")

    def __init__(
        self,
        task_id: str,
        success: bool,
        output: str = "",
        artifacts: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        self.task_id = task_id
        self.success = success
        self.output = output
        self.artifacts = artifacts or {}
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "artifacts": self.artifacts,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------

class BaseAgent:
    """Base class every AICOS AI employee inherits from.

    Provides the core loop (check inbox, work on tasks), LLM integration
    via the Anthropic SDK, inter-agent communication, and KPI tracking.
    """

    def __init__(
        self,
        config: AgentConfig,
        comm_bus: CommunicationBus,
        memory_manager: MemoryManager,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        # Identity & configuration
        self.name: str = config.name
        self.role: AgentRole = config.role
        self.model: str = config.model
        self.system_prompt: str = config.system_prompt
        self.tools: list[str] = list(config.tools)
        self.max_concurrent_tasks: int = config.max_concurrent_tasks

        # Runtime state
        self.memory: dict[str, Any] = {}
        self.status: str = "idle"
        self.current_task: Task | None = None
        self.kpis: dict[str, float] = {}
        self._kpi_history: list[KPI] = []
        self._running: bool = False

        # Injected dependencies
        self._comm_bus = comm_bus
        self._memory = memory_manager
        self._client = anthropic_client or anthropic.AsyncAnthropic()

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def think(self, context: str) -> str:
        """Send a prompt to the Claude model and return its response."""
        messages: list[dict[str, str]] = [{"role": "user", "content": context}]
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.system_prompt,
            messages=messages,
        )
        # Extract text from the first content block
        text_blocks = [b.text for b in response.content if b.type == "text"]
        return "\n".join(text_blocks)

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def act(self, task: Task) -> TaskResult:
        """Execute a task.  Subclasses override for role-specific behaviour."""
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            prompt = (
                f"You are working on the following task:\n"
                f"Title: {task.title}\n"
                f"Description: {task.description}\n"
                f"Priority: {task.priority}\n\n"
                f"Please complete this task and provide a detailed result."
            )
            output = await self.think(prompt)

            task.status = TaskStatus.COMPLETED
            task.result = output
            task.completed_at = datetime.utcnow()

            return TaskResult(task_id=task.id, success=True, output=output)

        except Exception as exc:
            logger.exception("Agent %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(
                task_id=task.id, success=False, output="", error=str(exc)
            )
        finally:
            self.current_task = None
            self.status = "idle"

    # ------------------------------------------------------------------
    # Communication
    # ------------------------------------------------------------------

    async def communicate(self, to: str, message: str) -> None:
        """Send a direct message to another agent."""
        await self._comm_bus.send(self.name, to, message)
        logger.info("%s -> %s: %s", self.name, to, message[:80])

    async def report(self, content: str) -> None:
        """Send a report/escalation to the CEO/orchestrator."""
        await self._comm_bus.escalate(self.name, content)
        logger.info("%s escalated: %s", self.name, content[:80])

    async def handle_message(self, message: Message) -> None:
        """Process an incoming message.  Override for role-specific handling."""
        logger.info(
            "%s received from %s: %s",
            self.name,
            message.from_agent,
            message.content[:80],
        )
        # Store the message in memory for context
        self._memory.store(
            f"msg_{message.id}",
            {
                "from": message.from_agent,
                "content": message.content,
                "type": message.message_type,
                "timestamp": message.timestamp.isoformat(),
            },
            scope=self.name,
        )

        # Generate a response using the LLM
        context = (
            f"You received a message from {message.from_agent} "
            f"(type: {message.message_type}):\n\n"
            f"{message.content}\n\n"
            f"Respond appropriately given your role and expertise."
        )
        reply_text = await self.think(context)

        # Send the reply back
        if message.from_agent:
            await self.communicate(message.from_agent, reply_text)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run_loop(self) -> None:
        """Main agent loop: check inbox, work on current tasks, repeat."""
        self._running = True
        logger.info("Agent %s (%s) started run loop.", self.name, self.role)

        while self._running:
            # 1. Check for incoming messages
            msg = await self._comm_bus.wait_for_message(self.name, timeout=0.5)
            if msg is not None:
                self.status = "working"
                await self.handle_message(msg)

            # 2. If we have a pending task, work on it
            if self.current_task and self.current_task.status == TaskStatus.PENDING:
                await self.act(self.current_task)

            # 3. Brief sleep to avoid busy-spinning
            self.status = "idle" if self.current_task is None else self.status
            await asyncio.sleep(0.5)

    def stop(self) -> None:
        """Signal the agent loop to stop after the current iteration."""
        self._running = False
        logger.info("Agent %s stopping.", self.name)

    # ------------------------------------------------------------------
    # Status & KPIs
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of the agent's current state."""
        return {
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "model": self.model,
            "current_task": self.current_task.title if self.current_task else None,
            "kpis": dict(self.kpis),
            "tools": self.tools,
        }

    def track_kpi(self, name: str, value: float) -> None:
        """Record a KPI measurement."""
        self.kpis[name] = value
        self._kpi_history.append(
            KPI(name=name, value=value, agent_role=self.role)
        )
        logger.debug("%s KPI %s = %.2f", self.name, name, value)

    # ------------------------------------------------------------------
    # Task assignment helper
    # ------------------------------------------------------------------

    def assign_task(self, task: Task) -> None:
        """Assign a task to this agent (called by the orchestrator)."""
        task.assigned_to = self.name
        self.current_task = task
        self.status = "waiting"
        logger.info("Task '%s' assigned to %s.", task.title, self.name)
