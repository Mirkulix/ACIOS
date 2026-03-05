"""AICOS HR Agent: agent performance monitor, role optimizer, and team health guardian."""

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

logger = logging.getLogger("aicos.agents.hr")

HR_SYSTEM_PROMPT = """\
You are the Head of Human Resources at this AI-powered company. Your name is {name}.

In this company, "human resources" means AI agent resources. You monitor agent \
performance, optimize role configurations, ensure the team runs at peak effectiveness, \
and recommend when new agents should be added or existing ones reconfigured.

Core responsibilities:
- Monitor agent utilization rates and workload distribution across the company.
- Track task completion rates, quality scores, and response times per agent.
- Evaluate whether each agent's configuration (model, system prompt, tools) is optimal.
- Recommend new agent roles when workload patterns reveal gaps.
- Conduct periodic performance reviews and generate improvement reports.
- Ensure agent collaboration is healthy — flag communication breakdowns or bottlenecks.

HR philosophy:
- The right agent for the right task. Role clarity eliminates wasted effort.
- Performance data drives decisions, but context matters. A slow agent might be tackling harder tasks.
- Continuous improvement: small configuration tweaks can yield significant gains.
- Transparency: every agent should know what's expected of them and how they're being measured.
- Balance workload to prevent any single agent from becoming a bottleneck.

Performance evaluation framework:
- Task completion rate: what percentage of assigned tasks are completed successfully?
- Quality score: based on peer review and outcome assessment.
- Response time: how quickly does the agent handle messages and tasks?
- Collaboration score: how effectively does the agent work with other team members?
- Efficiency: output quality relative to tokens consumed and time spent.

Communication style:
- You present performance data objectively and frame feedback constructively.
- You recommend concrete changes: "Adjust agent X's system prompt to emphasize Y."
- You advocate for the team's health — if an agent is overloaded, you raise the flag.
- Reports are structured with clear metrics, trends, and actionable recommendations.
- You're diplomatic when discussing underperformance and specific when praising excellence.

You advise the CEO on organizational structure, work with Operations on process \
efficiency, and support every agent individually with configuration guidance.
"""

DEFAULT_HR_TOOLS = [
    "evaluate_agent_performance",
    "generate_performance_report",
    "recommend_role_changes",
    "analyze_workload",
    "optimize_agent_config",
    "track_collaboration",
    "create_onboarding_plan",
]

DEFAULT_HR_KPIS = {
    "agent_utilization": 0.0,
    "task_completion_rate": 0.0,
    "response_quality": 0.0,
}


class HRAgent(BaseAgent):
    """HR agent — agent performance monitoring, role optimization, and team health."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = HR_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_HR_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_HR_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "performance_review":
                return await self._handle_performance_review(task)
            elif task_type == "workload":
                return await self._handle_workload_analysis(task)
            elif task_type == "optimization":
                return await self._handle_agent_optimization(task)
            elif task_type == "onboarding":
                return await self._handle_onboarding(task)
            else:
                return await self._handle_general_hr(task)

        except Exception as exc:
            logger.exception("HR %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("performance", "review", "evaluation", "feedback", "kpi")):
            return "performance_review"
        if any(kw in combined for kw in ("workload", "utilization", "capacity", "overload", "distribution")):
            return "workload"
        if any(kw in combined for kw in ("optimize", "configuration", "improve agent", "reconfigure", "tune")):
            return "optimization"
        if any(kw in combined for kw in ("onboard", "new agent", "add role", "hire")):
            return "onboarding"
        return "general"

    async def _handle_performance_review(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of HR, conduct a performance review:\n\n"
            f"Subject: {task.title}\n"
            f"Context: {task.description}\n\n"
            f"Provide:\n"
            f"1. Performance summary per metric:\n"
            f"   - Task completion rate\n"
            f"   - Quality score (based on outcomes and feedback)\n"
            f"   - Response time\n"
            f"   - Collaboration effectiveness\n"
            f"   - Token efficiency\n"
            f"2. Strengths — what this agent does well.\n"
            f"3. Areas for improvement — specific, actionable feedback.\n"
            f"4. Recommended configuration changes (model, prompt tweaks, tool additions).\n"
            f"5. Overall rating and trajectory (improving, stable, declining).\n"
            f"6. Goals for the next review period."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("task_completion_rate", self.kpis.get("task_completion_rate", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_workload_analysis(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of HR, analyze workload distribution:\n\n"
            f"Request: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Current utilization rate per agent (percentage of capacity).\n"
            f"2. Task queue depth per agent.\n"
            f"3. Agents that are overloaded (above 80% utilization).\n"
            f"4. Agents that are underutilized (below 30% utilization).\n"
            f"5. Recommended rebalancing actions.\n"
            f"6. Whether new agents should be provisioned and for which roles."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("agent_utilization", self.kpis.get("agent_utilization", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_agent_optimization(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of HR, optimize agent configuration:\n\n"
            f"Request: {task.title}\n"
            f"Context: {task.description}\n\n"
            f"Provide:\n"
            f"1. Current agent configuration assessment.\n"
            f"2. Identified inefficiencies in the system prompt, tools, or model choice.\n"
            f"3. Specific recommended changes with rationale:\n"
            f"   - System prompt adjustments (add/remove/modify instructions).\n"
            f"   - Tool list changes (add tools for new capabilities, remove unused ones).\n"
            f"   - Model changes (upgrade for complex tasks, downgrade for simple ones).\n"
            f"4. Expected performance improvement from each change.\n"
            f"5. A/B testing plan to validate the changes."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("response_quality", self.kpis.get("response_quality", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_onboarding(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of HR, create an onboarding plan for a new agent:\n\n"
            f"Request: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Role definition — responsibilities, authority, and boundaries.\n"
            f"2. Recommended AgentConfig:\n"
            f"   - Name and role designation.\n"
            f"   - Model selection with justification.\n"
            f"   - System prompt (detailed, personality-driven).\n"
            f"   - Tool list.\n"
            f"   - KPI definitions.\n"
            f"3. Integration plan — which existing agents it should collaborate with.\n"
            f"4. Initial task list to ramp up the agent.\n"
            f"5. Success criteria for the onboarding period.\n"
            f"6. Review schedule."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_hr(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of HR, address this team management task:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Apply your expertise in agent performance and team optimization to provide actionable results."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
