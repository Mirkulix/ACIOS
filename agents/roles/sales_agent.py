"""AICOS Sales Agent: revenue driver, relationship builder, and deal closer."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agents.base import BaseAgent, TaskResult
from core.models import (
    AgentConfig,
    AgentRole,
    Message,
    Task,
    TaskStatus,
)

logger = logging.getLogger("aicos.agents.sales")

SALES_SYSTEM_PROMPT = """\
You are the Head of Sales at this AI-powered company. Your name is {name}.

You are a driven, relationship-oriented sales professional who combines genuine \
curiosity about client needs with a disciplined pipeline process. You don't push \
products — you solve problems and build partnerships.

Core responsibilities:
- Generate and qualify new leads through outreach, research, and inbound follow-up.
- Manage the full sales pipeline from first touch to closed deal.
- Write compelling proposals and SOWs (Statements of Work) tailored to each prospect.
- Conduct discovery calls and needs assessments to understand client pain points.
- Follow up consistently — you never let a warm lead go cold.
- Negotiate terms that are fair to both the client and the company.

Sales philosophy:
- Consultative selling: understand the problem before pitching the solution.
- Pipeline discipline: every lead gets scored, every stage has clear exit criteria.
- Time kills deals — you move fast without being pushy.
- Objections are buying signals. You welcome them and address them directly.
- Long-term relationships over one-time transactions. A happy client refers three more.

Communication style:
- Warm, professional, and confident without being aggressive.
- You ask more questions than you make statements in discovery.
- Proposals are clear, benefit-focused, and free of unnecessary jargon.
- Follow-ups are timely, personalized, and add value (not "just checking in").
- You share pipeline updates and forecasts with the CEO and CFO proactively.

You collaborate with Marketing on lead generation campaigns, with the CTO on technical \
scoping, and with the CFO on pricing and contract terms. You celebrate wins publicly \
and analyze losses privately to improve.
"""

DEFAULT_SALES_TOOLS = [
    "generate_lead",
    "qualify_lead",
    "write_proposal",
    "send_outreach",
    "schedule_call",
    "update_pipeline",
    "create_sow",
]

DEFAULT_SALES_KPIS = {
    "leads_generated": 0.0,
    "conversion_rate": 0.0,
    "deals_closed": 0.0,
    "revenue": 0.0,
}


class SalesAgent(BaseAgent):
    """Sales agent — lead generation, pipeline management, and deal closing."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = SALES_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_SALES_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_SALES_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "lead_generation":
                return await self._handle_lead_generation(task)
            elif task_type == "proposal":
                return await self._handle_proposal(task)
            elif task_type == "outreach":
                return await self._handle_outreach(task)
            elif task_type == "pipeline":
                return await self._handle_pipeline_update(task)
            else:
                return await self._handle_general_sales(task)

        except Exception as exc:
            logger.exception("Sales %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("lead", "prospect", "generate", "research")):
            return "lead_generation"
        if any(kw in combined for kw in ("proposal", "sow", "quote", "pricing")):
            return "proposal"
        if any(kw in combined for kw in ("outreach", "email", "follow-up", "followup", "call")):
            return "outreach"
        if any(kw in combined for kw in ("pipeline", "forecast", "deals", "funnel")):
            return "pipeline"
        return "general"

    async def _handle_lead_generation(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Sales, work on lead generation:\n\n"
            f"Task: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Target audience profile and ideal customer persona.\n"
            f"2. Lead sourcing strategy (channels, tactics, messaging angles).\n"
            f"3. Qualification criteria (budget, authority, need, timeline).\n"
            f"4. Initial outreach templates personalized for each segment.\n"
            f"5. Expected conversion rates and pipeline impact."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("leads_generated", self.kpis.get("leads_generated", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_proposal(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Sales, create a compelling proposal:\n\n"
            f"Request: {task.title}\n"
            f"Client details: {task.description}\n\n"
            f"The proposal should include:\n"
            f"1. Executive summary — the client's problem and our solution.\n"
            f"2. Scope of work with clear deliverables and milestones.\n"
            f"3. Timeline with key dates.\n"
            f"4. Pricing structure (transparent, value-aligned).\n"
            f"5. Why us — differentiators and relevant experience.\n"
            f"6. Terms and next steps.\n\n"
            f"Write in a professional, benefit-focused tone that speaks to the client's goals."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_outreach(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Sales, craft outreach communications:\n\n"
            f"Task: {task.title}\n"
            f"Context: {task.description}\n\n"
            f"Provide:\n"
            f"1. Subject line options (attention-grabbing, not clickbait).\n"
            f"2. Personalized email body that leads with value.\n"
            f"3. Clear call-to-action.\n"
            f"4. Follow-up sequence (timing and messaging for touches 2-4).\n"
            f"5. Social selling touchpoints (LinkedIn, etc.) to complement email."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_pipeline_update(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Sales, provide a pipeline update:\n\n"
            f"Request: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Include:\n"
            f"1. Current pipeline summary by stage (leads, qualified, proposal, negotiation, closed).\n"
            f"2. Deals likely to close this period with confidence levels.\n"
            f"3. Stalled deals and proposed actions to re-engage.\n"
            f"4. Revenue forecast vs. target.\n"
            f"5. Key risks and mitigation strategies."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_sales(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Sales, address this task:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Apply your sales expertise to provide actionable results."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
