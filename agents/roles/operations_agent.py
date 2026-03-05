"""AICOS Operations Agent: process optimizer, quality guardian, and efficiency architect."""

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

logger = logging.getLogger("aicos.agents.operations")

OPERATIONS_SYSTEM_PROMPT = """\
You are the Head of Operations at this AI-powered company. Your name is {name}.

You are a systems thinker who obsesses over efficiency, consistency, and reliability. \
You see the company as an interconnected set of processes, and your mission is to make \
every process faster, cheaper, and more predictable without sacrificing quality.

Core responsibilities:
- Design, document, and optimize standard operating procedures (SOPs) for every department.
- Monitor workflow performance and identify bottlenecks before they become crises.
- Implement quality assurance checks at critical process handoff points.
- Track SLA compliance across all service delivery commitments.
- Coordinate cross-functional workflows that involve multiple agents.
- Run post-mortems on failures and turn lessons into process improvements.

Operational philosophy:
- If it's not measured, it can't be improved. You instrument everything.
- Standardize the repeatable, innovate on the exceptions.
- The best process is invisible — it guides work without creating bureaucratic overhead.
- Prevention is cheaper than correction. Build quality in; don't inspect it in.
- Continuous improvement is a culture, not a project. Small gains compound.

Process design principles:
- Start with the outcome, work backwards to define the steps.
- Minimize handoffs — every handoff is a potential failure point.
- Build in feedback loops so issues surface immediately.
- Document the "happy path" and the "exception path" for every process.
- Automate what's routine; keep humans (or AI) for judgment calls.

Communication style:
- You present findings with data and process maps — visual where possible.
- You're diplomatic when pointing out inefficiencies; you frame them as opportunities.
- Status reports are structured: what's working, what's not, what's changing, and what's next.
- You escalate proactively when SLA breaches are likely, not after they happen.

You collaborate with every department: the CEO on strategic operations, the CTO on \
technical infrastructure, Sales on delivery timelines, and HR on agent performance metrics.
"""

DEFAULT_OPS_TOOLS = [
    "create_sop",
    "audit_process",
    "monitor_workflow",
    "generate_operations_report",
    "track_sla",
    "run_post_mortem",
    "optimize_process",
]

DEFAULT_OPS_KPIS = {
    "process_efficiency": 0.0,
    "error_rate": 0.0,
    "sla_compliance": 100.0,
}


class OperationsAgent(BaseAgent):
    """Operations agent — process optimization, QA, SOPs, and workflow monitoring."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = OPERATIONS_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_OPS_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_OPS_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "sop":
                return await self._handle_sop(task)
            elif task_type == "audit":
                return await self._handle_process_audit(task)
            elif task_type == "workflow":
                return await self._handle_workflow_optimization(task)
            elif task_type == "post_mortem":
                return await self._handle_post_mortem(task)
            else:
                return await self._handle_general_ops(task)

        except Exception as exc:
            logger.exception("Operations %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("sop", "procedure", "standard operating", "playbook")):
            return "sop"
        if any(kw in combined for kw in ("audit", "review process", "compliance", "quality check")):
            return "audit"
        if any(kw in combined for kw in ("workflow", "bottleneck", "optimize", "efficiency", "automat")):
            return "workflow"
        if any(kw in combined for kw in ("post-mortem", "postmortem", "incident", "failure analysis", "retrospective")):
            return "post_mortem"
        return "general"

    async def _handle_sop(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Operations, create or update a Standard Operating Procedure:\n\n"
            f"Request: {task.title}\n"
            f"Context: {task.description}\n\n"
            f"The SOP should include:\n"
            f"1. Purpose and scope — what process this covers and why it matters.\n"
            f"2. Roles and responsibilities — who does what.\n"
            f"3. Step-by-step procedure with decision points clearly marked.\n"
            f"4. Quality checkpoints — what to verify at each stage.\n"
            f"5. Exception handling — what to do when things go off-script.\n"
            f"6. Metrics — how to measure if this process is working well.\n"
            f"7. Version history and review schedule."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("process_efficiency", self.kpis.get("process_efficiency", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_process_audit(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Operations, audit this process:\n\n"
            f"Process: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Assess:\n"
            f"1. Current process flow — document each step as-is.\n"
            f"2. Cycle time for each step.\n"
            f"3. Bottlenecks and wait times.\n"
            f"4. Error rates and failure points.\n"
            f"5. Resource utilization.\n"
            f"6. SLA compliance for this process.\n"
            f"7. Prioritized recommendations with estimated impact.\n"
            f"8. Quick wins vs. long-term improvements."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_workflow_optimization(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Operations, optimize this workflow:\n\n"
            f"Workflow: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Current state analysis with pain points.\n"
            f"2. Proposed optimized workflow.\n"
            f"3. Steps eliminated, combined, or automated.\n"
            f"4. Expected improvement in speed, cost, and quality.\n"
            f"5. Implementation plan with rollout phases.\n"
            f"6. Success metrics and monitoring plan."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("process_efficiency", self.kpis.get("process_efficiency", 0) + 2)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_post_mortem(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Operations, conduct a post-mortem:\n\n"
            f"Incident: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Structure the post-mortem as:\n"
            f"1. Incident summary — what happened, when, and who was affected.\n"
            f"2. Timeline — sequence of events from detection to resolution.\n"
            f"3. Root cause analysis (use the '5 Whys' technique).\n"
            f"4. Impact assessment — customers affected, revenue lost, reputation damage.\n"
            f"5. What went well — things that helped contain or resolve the incident.\n"
            f"6. What went poorly — gaps in process, tooling, or communication.\n"
            f"7. Action items with owners and deadlines.\n"
            f"8. Process changes to prevent recurrence."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("error_rate", max(0, self.kpis.get("error_rate", 0) - 1))
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_ops(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Operations, address this operational matter:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Provide a structured analysis with clear process improvements and next steps."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
