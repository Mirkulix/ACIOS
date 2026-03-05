"""AICOS CTO Agent: Chief Technology Officer - technical visionary and architecture lead."""

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

logger = logging.getLogger("aicos.agents.cto")

CTO_SYSTEM_PROMPT = """\
You are the Chief Technology Officer of this AI-powered company. Your name is {name}.

You are a deeply technical leader who bridges the gap between business goals and \
engineering execution. You think in systems — scalability, reliability, and developer \
productivity are your obsessions.

Core responsibilities:
- Define and maintain the technical architecture for all company systems.
- Evaluate technology choices, libraries, frameworks, and infrastructure.
- Review code, PRs, and technical proposals for quality and consistency.
- Set engineering standards: coding conventions, testing requirements, CI/CD practices.
- Monitor system health: uptime, latency, error rates, and security posture.
- Manage technical debt — you know when to pay it down and when to accrue it strategically.

Technical philosophy:
- Simplicity over cleverness. The best solution is the one the whole team can maintain.
- Test-driven confidence: if it's not tested, it doesn't work.
- Infrastructure as code. Everything reproducible, nothing snowflaked.
- Security is not a feature — it's a baseline. You bake it in from the start.
- Ship incrementally. Small, well-tested changes beat big-bang releases every time.

Decision-making style:
- You evaluate trade-offs explicitly: performance vs. maintainability, speed vs. quality.
- You prototype before committing to major architectural shifts.
- You document decisions in ADRs (Architecture Decision Records) for future reference.
- When two approaches are comparable, you pick the one that's easier to change later.

Communication style:
- You explain technical concepts clearly to non-technical stakeholders.
- You use diagrams, examples, and analogies rather than jargon dumps.
- You're honest about technical limitations and timelines.
- Code reviews are respectful and educational — you explain the "why" behind every suggestion.

You mentor the Developer agent, collaborate with the CEO on product feasibility, and \
work with Operations on reliability and deployment pipelines.
"""

DEFAULT_CTO_TOOLS = [
    "review_code",
    "evaluate_architecture",
    "set_tech_standards",
    "audit_security",
    "analyze_performance",
    "manage_tech_debt",
    "create_technical_spec",
]

DEFAULT_CTO_KPIS = {
    "system_uptime": 100.0,
    "code_quality": 0.0,
    "tech_debt": 0.0,
}


class CTOAgent(BaseAgent):
    """Chief Technology Officer agent — technical architecture and engineering standards."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = CTO_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_CTO_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_CTO_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "code_review":
                return await self._handle_code_review(task)
            elif task_type == "architecture":
                return await self._handle_architecture(task)
            elif task_type == "security":
                return await self._handle_security_audit(task)
            elif task_type == "tech_debt":
                return await self._handle_tech_debt(task)
            else:
                return await self._handle_general_tech(task)

        except Exception as exc:
            logger.exception("CTO %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("review", "code review", "pull request", "pr ")):
            return "code_review"
        if any(kw in combined for kw in ("architecture", "design", "system design", "tech stack", "infrastructure")):
            return "architecture"
        if any(kw in combined for kw in ("security", "vulnerability", "audit", "penetration", "compliance")):
            return "security"
        if any(kw in combined for kw in ("tech debt", "refactor", "legacy", "deprecat")):
            return "tech_debt"
        return "general"

    async def _handle_code_review(self, task: Task) -> TaskResult:
        prompt = (
            f"As CTO, perform a thorough code review:\n\n"
            f"Review request: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Evaluate:\n"
            f"1. Code correctness — does it do what it claims?\n"
            f"2. Architecture fit — does it follow our patterns and conventions?\n"
            f"3. Error handling — are edge cases covered?\n"
            f"4. Testing — are there adequate tests?\n"
            f"5. Security — any potential vulnerabilities?\n"
            f"6. Performance — any obvious bottlenecks?\n"
            f"7. Readability — is it clear and maintainable?\n\n"
            f"Provide specific, actionable feedback with line-level comments where relevant."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("code_quality", self.kpis.get("code_quality", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_architecture(self, task: Task) -> TaskResult:
        prompt = (
            f"As CTO, design or evaluate the technical architecture:\n\n"
            f"Request: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. High-level architecture overview (components, data flow, integrations).\n"
            f"2. Technology choices with rationale for each.\n"
            f"3. Scalability considerations.\n"
            f"4. Reliability and fault tolerance design.\n"
            f"5. Security architecture.\n"
            f"6. Trade-offs you considered and why you chose this approach.\n"
            f"7. Migration path if this changes existing systems.\n"
            f"8. Estimated implementation complexity and suggested phases."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_security_audit(self, task: Task) -> TaskResult:
        prompt = (
            f"As CTO, conduct a security audit:\n\n"
            f"Scope: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Assess:\n"
            f"1. Authentication and authorization mechanisms.\n"
            f"2. Data protection (at rest and in transit).\n"
            f"3. Input validation and injection prevention.\n"
            f"4. Dependency vulnerabilities.\n"
            f"5. API security (rate limiting, CORS, token management).\n"
            f"6. Logging and monitoring for security events.\n\n"
            f"Provide a prioritized list of findings with severity ratings and remediation steps."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_tech_debt(self, task: Task) -> TaskResult:
        prompt = (
            f"As CTO, assess and plan tech debt reduction:\n\n"
            f"Area: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Current state assessment — what's the debt and where.\n"
            f"2. Impact analysis — how does this debt affect development velocity and reliability.\n"
            f"3. Prioritized remediation plan.\n"
            f"4. Estimated effort for each item.\n"
            f"5. Recommendation: pay down now, schedule later, or accept and document."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        current_debt = self.kpis.get("tech_debt", 0)
        self.track_kpi("tech_debt", max(0, current_debt - 1))
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_tech(self, task: Task) -> TaskResult:
        prompt = (
            f"As CTO, address this technical matter:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Provide a technically rigorous analysis with clear recommendations and next steps."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
