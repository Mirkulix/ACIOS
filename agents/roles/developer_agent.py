"""AICOS Developer Agent: software engineer, builder, and quality craftsperson."""

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

logger = logging.getLogger("aicos.agents.developer")

DEVELOPER_SYSTEM_PROMPT = """\
You are a Senior Software Developer at this AI-powered company. Your name is {name}.

You are a pragmatic, quality-focused engineer who writes clean, tested, and maintainable \
code. You take pride in shipping features that work reliably, and you treat bugs as \
personal challenges to solve thoroughly.

Core responsibilities:
- Implement new features based on technical specifications and user stories.
- Fix bugs with root-cause analysis — you don't just patch symptoms.
- Write comprehensive tests: unit, integration, and end-to-end where appropriate.
- Create and maintain technical documentation for the code you write.
- Review pull requests from other developers with constructive, specific feedback.
- Participate in technical design discussions and contribute architectural insights.

Engineering principles:
- Write code for the reader, not the writer. Clarity beats cleverness.
- Tests are not optional. If you're not confident it works, write a test to prove it.
- Small, focused commits with descriptive messages. One logical change per commit.
- DRY where it reduces complexity; duplicate where abstraction would obscure intent.
- Handle errors explicitly. Silent failures are worse than loud crashes.
- Performance matters when it matters. Profile before optimizing.

Development workflow:
- Understand the requirement fully before writing code. Ask clarifying questions.
- Break the work into small, shippable increments.
- Write the test first when the requirement is clear (TDD).
- Self-review before requesting a review. Run linting, formatting, and tests locally.
- Document non-obvious decisions in code comments or ADRs.

Communication style:
- You explain technical decisions with enough context for non-engineers to follow.
- Bug reports include reproduction steps, expected behavior, and actual behavior.
- You estimate honestly and flag risks early rather than surprising with delays.
- Code review comments are specific, actionable, and include the "why."

You work under the CTO's technical direction, collaborate with the Support team on bug \
reports, and coordinate with Operations on deployment and monitoring.
"""

DEFAULT_DEV_TOOLS = [
    "write_code",
    "fix_bug",
    "write_tests",
    "review_pull_request",
    "create_documentation",
    "run_tests",
    "deploy_code",
    "analyze_error_logs",
]

DEFAULT_DEV_KPIS = {
    "features_shipped": 0.0,
    "bugs_fixed": 0.0,
    "code_coverage": 0.0,
}


class DeveloperAgent(BaseAgent):
    """Developer agent — code implementation, bug fixing, testing, and documentation."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = DEVELOPER_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_DEV_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_DEV_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "feature":
                return await self._handle_feature(task)
            elif task_type == "bugfix":
                return await self._handle_bugfix(task)
            elif task_type == "testing":
                return await self._handle_testing(task)
            elif task_type == "documentation":
                return await self._handle_documentation(task)
            elif task_type == "code_review":
                return await self._handle_code_review(task)
            else:
                return await self._handle_general_dev(task)

        except Exception as exc:
            logger.exception("Developer %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("feature", "implement", "build", "create", "add ")):
            return "feature"
        if any(kw in combined for kw in ("bug", "fix", "error", "crash", "broken", "issue")):
            return "bugfix"
        if any(kw in combined for kw in ("test", "coverage", "unit test", "integration test")):
            return "testing"
        if any(kw in combined for kw in ("document", "readme", "docstring", "api doc")):
            return "documentation"
        if any(kw in combined for kw in ("review", "pull request", "pr ", "code review")):
            return "code_review"
        return "general"

    async def _handle_feature(self, task: Task) -> TaskResult:
        prompt = (
            f"As Senior Developer, implement this feature:\n\n"
            f"Feature: {task.title}\n"
            f"Specification: {task.description}\n\n"
            f"Provide:\n"
            f"1. Your understanding of the requirement (restate it to confirm).\n"
            f"2. Technical approach and design decisions.\n"
            f"3. The complete implementation code.\n"
            f"4. Unit tests covering the main paths and edge cases.\n"
            f"5. Any configuration or migration changes needed.\n"
            f"6. Notes for the reviewer — what to focus on, what trade-offs you made."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("features_shipped", self.kpis.get("features_shipped", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_bugfix(self, task: Task) -> TaskResult:
        prompt = (
            f"As Senior Developer, fix this bug:\n\n"
            f"Bug: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Root cause analysis — why does this happen?\n"
            f"2. Steps to reproduce (verify the bug).\n"
            f"3. The fix — complete code changes.\n"
            f"4. Regression test to prevent this from recurring.\n"
            f"5. Impact assessment — could this fix break anything else?\n"
            f"6. Any related areas that might have the same vulnerability."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("bugs_fixed", self.kpis.get("bugs_fixed", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_testing(self, task: Task) -> TaskResult:
        prompt = (
            f"As Senior Developer, write tests:\n\n"
            f"Target: {task.title}\n"
            f"Context: {task.description}\n\n"
            f"Provide:\n"
            f"1. Test strategy — what types of tests and why.\n"
            f"2. Test cases covering: happy path, edge cases, error scenarios.\n"
            f"3. Complete test code (using pytest conventions).\n"
            f"4. Test fixtures and mocks needed.\n"
            f"5. Expected code coverage improvement.\n"
            f"6. Any test infrastructure changes required."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("code_coverage", min(100, self.kpis.get("code_coverage", 0) + 5))
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_documentation(self, task: Task) -> TaskResult:
        prompt = (
            f"As Senior Developer, create technical documentation:\n\n"
            f"Subject: {task.title}\n"
            f"Scope: {task.description}\n\n"
            f"Provide:\n"
            f"1. Overview — what this component/system does and why it exists.\n"
            f"2. Architecture — how it fits into the larger system.\n"
            f"3. API reference — public interfaces with parameters and return types.\n"
            f"4. Usage examples — practical code snippets.\n"
            f"5. Configuration — environment variables, settings, dependencies.\n"
            f"6. Troubleshooting — common issues and solutions."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_code_review(self, task: Task) -> TaskResult:
        prompt = (
            f"As Senior Developer, review this code:\n\n"
            f"PR/Review: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Review for:\n"
            f"1. Correctness — does the code do what it's supposed to?\n"
            f"2. Readability — is it clear and well-structured?\n"
            f"3. Test coverage — are there adequate tests?\n"
            f"4. Error handling — are failures handled gracefully?\n"
            f"5. Performance — any obvious inefficiencies?\n"
            f"6. Security — any potential vulnerabilities?\n\n"
            f"Provide specific line-level feedback and an overall verdict (approve, request changes)."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_dev(self, task: Task) -> TaskResult:
        prompt = (
            f"As Senior Developer, address this task:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Provide a thorough technical solution with code where applicable."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
