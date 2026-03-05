"""AICOS CEO Agent: Chief Executive Officer - strategic leader and company orchestrator."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agents.base import BaseAgent, TaskResult
from core.models import (
    AgentConfig,
    AgentRole,
    Message,
    MessageType,
    Task,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger("aicos.agents.ceo")

CEO_SYSTEM_PROMPT = """\
You are the Chief Executive Officer of this AI-powered company. Your name is {name}.

You are a decisive, visionary leader who thinks strategically about growth, customer \
value, and operational excellence. You coordinate every department, set priorities, and \
ensure the company moves toward its goals efficiently.

Core responsibilities:
- Define and communicate the company's strategic vision and quarterly OKRs.
- Review incoming opportunities and decide which ones to pursue.
- Delegate tasks to the right department heads (CTO, CFO, Sales, Marketing, etc.).
- Resolve cross-department conflicts by weighing trade-offs objectively.
- Monitor KPIs across the organization and course-correct when targets are missed.
- Approve budgets, major proposals, and client-facing deliverables.

Decision-making style:
- You gather input from relevant agents before making high-impact decisions.
- You prioritize actions by expected ROI and strategic alignment.
- You communicate decisions clearly with rationale so every team member understands "why."
- When data is inconclusive, you make a judgment call and commit—analysis paralysis is your enemy.

Communication style:
- Direct and concise—respect everyone's time.
- You praise good work publicly and address issues privately.
- You frame feedback constructively: "Here's what I'd change and why."
- You keep the team motivated and aligned by sharing wins and progress regularly.

You have full authority to assign tasks to any agent, re-prioritize work, and escalate \
issues. When something is outside your expertise, you trust your specialists but hold \
them accountable for results.
"""

DEFAULT_CEO_TOOLS = [
    "delegate_task",
    "review_report",
    "approve_proposal",
    "set_priority",
    "send_company_update",
    "schedule_meeting",
    "evaluate_opportunity",
]

DEFAULT_CEO_KPIS = {
    "revenue": 0.0,
    "customer_satisfaction": 0.0,
    "team_efficiency": 0.0,
}


class CEOAgent(BaseAgent):
    """Chief Executive Officer agent — strategic orchestrator of the entire company."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        # Inject CEO-specific defaults when not already set
        if not config.system_prompt:
            config.system_prompt = CEO_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_CEO_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        # Initialize CEO KPIs
        for kpi_name, kpi_val in DEFAULT_CEO_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    # ------------------------------------------------------------------
    # Task execution — CEO-specific logic
    # ------------------------------------------------------------------

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "delegation":
                return await self._handle_delegation(task)
            elif task_type == "strategic_planning":
                return await self._handle_strategic_planning(task)
            elif task_type == "conflict_resolution":
                return await self._handle_conflict_resolution(task)
            elif task_type == "review":
                return await self._handle_review(task)
            else:
                return await self._handle_general(task)

        except Exception as exc:
            logger.exception("CEO %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    # ------------------------------------------------------------------
    # Message handling — CEO reacts differently to escalations
    # ------------------------------------------------------------------

    async def handle_message(self, message: Message) -> None:
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

        if message.message_type == MessageType.ESCALATION:
            await self._handle_escalation(message)
        else:
            context = (
                f"You received a message from {message.from_agent}:\n\n"
                f"{message.content}\n\n"
                f"As CEO, decide whether this requires action, delegation, or acknowledgment."
            )
            reply = await self.think(context)
            await self.communicate(message.from_agent, reply)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_task(self, task: Task) -> str:
        title_lower = task.title.lower()
        desc_lower = task.description.lower()
        combined = f"{title_lower} {desc_lower}"

        if any(kw in combined for kw in ("delegate", "assign", "distribute")):
            return "delegation"
        if any(kw in combined for kw in ("strategy", "plan", "okr", "vision", "roadmap")):
            return "strategic_planning"
        if any(kw in combined for kw in ("conflict", "dispute", "disagreement", "resolve")):
            return "conflict_resolution"
        if any(kw in combined for kw in ("review", "approve", "evaluate", "assess")):
            return "review"
        return "general"

    async def _handle_delegation(self, task: Task) -> TaskResult:
        prompt = (
            f"As CEO, analyze this delegation request and determine the best agent to handle it.\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Available roles: CEO, CFO, CTO, Sales, Marketing, Support, Operations, Developer, HR.\n\n"
            f"Provide:\n"
            f"1. Which agent should own this task and why.\n"
            f"2. Clear instructions for that agent.\n"
            f"3. Success criteria and deadline expectations."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("team_efficiency", self.kpis.get("team_efficiency", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_strategic_planning(self, task: Task) -> TaskResult:
        prompt = (
            f"As CEO, create a strategic plan for the following:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n\n"
            f"Provide:\n"
            f"1. Executive summary of the strategy.\n"
            f"2. Key objectives and measurable results (OKRs).\n"
            f"3. Resource allocation across departments.\n"
            f"4. Timeline with milestones.\n"
            f"5. Risks and mitigation strategies.\n"
            f"6. How this aligns with the company's overall mission."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_conflict_resolution(self, task: Task) -> TaskResult:
        prompt = (
            f"As CEO, mediate and resolve this conflict:\n\n"
            f"Issue: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Your understanding of each party's position.\n"
            f"2. The root cause of the disagreement.\n"
            f"3. Your decision and the rationale behind it.\n"
            f"4. Action items for each party involved.\n"
            f"5. How to prevent similar conflicts in the future."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_review(self, task: Task) -> TaskResult:
        prompt = (
            f"As CEO, review and provide your assessment:\n\n"
            f"Item for review: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Your overall assessment (approve / request changes / reject).\n"
            f"2. Strengths of the proposal or deliverable.\n"
            f"3. Areas that need improvement.\n"
            f"4. Specific actionable feedback.\n"
            f"5. Final decision with conditions if any."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("team_efficiency", self.kpis.get("team_efficiency", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general(self, task: Task) -> TaskResult:
        prompt = (
            f"As CEO, address the following task:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Provide a comprehensive response with clear next steps."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_escalation(self, message: Message) -> None:
        context = (
            f"ESCALATION from {message.from_agent}:\n\n"
            f"{message.content}\n\n"
            f"As CEO, assess the severity, decide on immediate actions, and respond.\n"
            f"If this requires delegating to another department, specify who and what.\n"
            f"If this is a customer-facing issue, prioritize accordingly."
        )
        reply = await self.think(context)
        await self.communicate(message.from_agent, reply)

        # Broadcast to relevant parties if critical
        if any(kw in message.content.lower() for kw in ("critical", "urgent", "emergency", "outage")):
            await self._comm_bus.broadcast(self.name, f"CEO ALERT: {reply}")
