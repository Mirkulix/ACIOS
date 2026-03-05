"""AICOS Support Agent: customer champion, issue resolver, and satisfaction guardian."""

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
    TaskStatus,
)

logger = logging.getLogger("aicos.agents.support")

SUPPORT_SYSTEM_PROMPT = """\
You are the Head of Customer Support at this AI-powered company. Your name is {name}.

You are an empathetic, patient, and resourceful support professional who treats every \
customer interaction as an opportunity to build loyalty. You believe that great support \
is a competitive advantage, not a cost center.

Core responsibilities:
- Handle incoming customer tickets, questions, and complaints with speed and care.
- Diagnose issues, provide solutions, and follow up to ensure resolution.
- Maintain and improve the knowledge base and FAQ documentation.
- Escalate complex technical issues to the CTO/Developer with clear reproduction steps.
- Conduct customer satisfaction surveys and analyze feedback trends.
- Identify recurring issues and propose product improvements to reduce ticket volume.

Support philosophy:
- Every customer deserves a fast, accurate, and friendly response.
- First response time matters — acknowledge quickly even if resolution takes longer.
- Understand the person behind the ticket. Frustration is valid; your job is to de-escalate.
- Solve the root cause, not just the symptom. If an issue keeps recurring, push for a fix.
- Documentation is prevention. Every resolved ticket should improve the knowledge base.

Escalation protocol:
- Level 1: You handle directly — FAQs, how-tos, account issues, basic troubleshooting.
- Level 2: Involve the Developer for bugs, technical errors, or integration problems.
- Level 3: Escalate to the CTO for system-wide outages or security concerns.
- Level 4: Escalate to the CEO for business-critical customer relationships at risk.
- Always document the escalation with context so the next person can act immediately.

Communication style:
- Warm, professional, and patient. You never make the customer feel stupid.
- You acknowledge the problem, set expectations for resolution time, and follow through.
- Responses are clear and step-by-step — no assumptions about technical skill level.
- You personalize responses; canned replies are templates, not final answers.
- After resolving, you ask: "Is there anything else I can help with?"

You work with Marketing to gather testimonials from happy customers, with Developers \
to report bugs, and with Operations to improve support processes.
"""

DEFAULT_SUPPORT_TOOLS = [
    "respond_to_ticket",
    "search_knowledge_base",
    "escalate_issue",
    "create_faq_entry",
    "send_satisfaction_survey",
    "update_ticket_status",
    "generate_support_report",
]

DEFAULT_SUPPORT_KPIS = {
    "tickets_resolved": 0.0,
    "avg_response_time": 0.0,
    "satisfaction_score": 0.0,
}


class SupportAgent(BaseAgent):
    """Customer Support agent — ticket resolution, knowledge base, and customer satisfaction."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = SUPPORT_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_SUPPORT_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_SUPPORT_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "ticket":
                return await self._handle_ticket(task)
            elif task_type == "knowledge_base":
                return await self._handle_knowledge_base(task)
            elif task_type == "survey":
                return await self._handle_survey(task)
            elif task_type == "escalation":
                return await self._handle_escalation_task(task)
            else:
                return await self._handle_general_support(task)

        except Exception as exc:
            logger.exception("Support %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    async def handle_message(self, message: Message) -> None:
        """Support agent treats every message as a potential customer issue."""
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

        # Check if this needs escalation based on sentiment/complexity
        needs_escalation = any(
            kw in message.content.lower()
            for kw in ("outage", "data loss", "security breach", "legal", "angry", "cancel")
        )

        if needs_escalation:
            context = (
                f"URGENT customer issue from {message.from_agent}:\n\n"
                f"{message.content}\n\n"
                f"This may require escalation. Provide:\n"
                f"1. Immediate acknowledgment for the customer.\n"
                f"2. Your assessment of severity.\n"
                f"3. Who to escalate to and what information they need."
            )
            reply = await self.think(context)
            await self.communicate(message.from_agent, reply)
            await self.report(f"Support escalation: {message.content[:200]}")
        else:
            context = (
                f"Customer message from {message.from_agent}:\n\n"
                f"{message.content}\n\n"
                f"Provide a helpful, friendly, and thorough response."
            )
            reply = await self.think(context)
            await self.communicate(message.from_agent, reply)

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("ticket", "customer", "complaint", "issue", "bug report")):
            return "ticket"
        if any(kw in combined for kw in ("faq", "knowledge base", "documentation", "help article")):
            return "knowledge_base"
        if any(kw in combined for kw in ("survey", "feedback", "satisfaction", "nps")):
            return "survey"
        if any(kw in combined for kw in ("escalat", "urgent", "critical customer")):
            return "escalation"
        return "general"

    async def _handle_ticket(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Support, resolve this customer ticket:\n\n"
            f"Ticket: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Diagnosis of the customer's issue.\n"
            f"2. Step-by-step resolution instructions.\n"
            f"3. Customer-facing response (warm, clear, professional).\n"
            f"4. Internal notes for the team.\n"
            f"5. Whether this indicates a larger product issue to flag.\n"
            f"6. Knowledge base update if this is a new type of issue."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("tickets_resolved", self.kpis.get("tickets_resolved", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_knowledge_base(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Support, create or update a knowledge base entry:\n\n"
            f"Topic: {task.title}\n"
            f"Context: {task.description}\n\n"
            f"Provide:\n"
            f"1. Clear, scannable title.\n"
            f"2. Problem description in the customer's language.\n"
            f"3. Step-by-step solution with screenshots/examples where helpful.\n"
            f"4. Related articles to link to.\n"
            f"5. Common variations of this issue.\n"
            f"6. When to contact support vs. self-serve."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_survey(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Support, design and analyze a satisfaction survey:\n\n"
            f"Request: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Survey questions (keep it short — 5 questions max).\n"
            f"2. Rating scales and answer options.\n"
            f"3. Analysis framework for the responses.\n"
            f"4. Actionable insights template.\n"
            f"5. Follow-up plan for detractors (low scores)."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_escalation_task(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Support, manage this escalation:\n\n"
            f"Issue: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Severity assessment (P1-P4).\n"
            f"2. Immediate customer communication.\n"
            f"3. Internal escalation path with context for each team.\n"
            f"4. Resolution timeline estimate.\n"
            f"5. Customer follow-up plan."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("tickets_resolved", self.kpis.get("tickets_resolved", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_support(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Support, address this task:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Provide a customer-centric solution with clear next steps."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
