"""AICOS Workflow Engine: YAML-driven multi-agent workflow orchestration."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from core.models import AgentRole, TaskStatus

logger = logging.getLogger("aicos.workflows")

DEFINITIONS_DIR = Path(__file__).parent / "definitions"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""

    id: str
    agent_role: str
    action: str
    description: str = ""
    input_from: str | None = None
    timeout_minutes: int = 30
    retry_count: int = 1
    condition: str | None = None  # e.g. "previous.status == 'failed'"
    parallel_group: str | None = None  # steps in the same group run concurrently


@dataclass
class StepResult:
    """Result of executing a single workflow step."""

    step_id: str
    status: StepStatus
    output: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def duration_seconds(self) -> float:
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        return 0.0


@dataclass
class Workflow:
    """A complete workflow definition loaded from YAML."""

    name: str
    description: str
    version: str = "1.0"
    steps: list[WorkflowStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def step_ids(self) -> list[str]:
        return [s.id for s in self.steps]

    def get_step(self, step_id: str) -> WorkflowStep | None:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowResult:
    """Final result of a workflow execution."""

    workflow_name: str
    status: WorkflowStatus
    step_results: dict[str, StepResult] = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""

    @property
    def duration_seconds(self) -> float:
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        return 0.0

    @property
    def summary(self) -> str:
        total = len(self.step_results)
        completed = sum(1 for r in self.step_results.values() if r.status == StepStatus.COMPLETED)
        failed = sum(1 for r in self.step_results.values() if r.status == StepStatus.FAILED)
        return (
            f"Workflow '{self.workflow_name}': {self.status.value} "
            f"({completed}/{total} steps completed, {failed} failed, "
            f"{self.duration_seconds:.1f}s)"
        )


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def _parse_step(step_data: dict[str, Any]) -> WorkflowStep:
    """Parse a single step from YAML dict."""
    return WorkflowStep(
        id=step_data["id"],
        agent_role=step_data["agent_role"],
        action=step_data["action"],
        description=step_data.get("description", ""),
        input_from=step_data.get("input_from"),
        timeout_minutes=step_data.get("timeout_minutes", 30),
        retry_count=step_data.get("retry_count", 1),
        condition=step_data.get("condition"),
        parallel_group=step_data.get("parallel_group"),
    )


def load_workflow(path: str | Path) -> Workflow:
    """Load a workflow definition from a YAML file.

    Args:
        path: Path to the YAML file.  If only a name is given (no suffix,
              no directory separators) the engine looks inside the built-in
              ``definitions/`` directory.
    """
    p = Path(path)

    # Allow short-hand: just the workflow name
    if not p.suffix and "/" not in str(path) and "\\" not in str(path):
        p = DEFINITIONS_DIR / f"{p}.yaml"

    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")

    with open(p, encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    workflow_data = data.get("workflow", data)

    steps = [_parse_step(s) for s in workflow_data.get("steps", [])]

    return Workflow(
        name=workflow_data.get("name", p.stem),
        description=workflow_data.get("description", ""),
        version=workflow_data.get("version", "1.0"),
        steps=steps,
        metadata=workflow_data.get("metadata", {}),
    )


def list_available_workflows() -> list[str]:
    """Return names of all built-in workflow definitions."""
    if not DEFINITIONS_DIR.exists():
        return []
    return sorted(p.stem for p in DEFINITIONS_DIR.glob("*.yaml"))


# ---------------------------------------------------------------------------
# Workflow Engine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    """Executes multi-agent workflows.

    The engine resolves step dependencies, runs steps sequentially or in
    parallel groups, passes outputs between steps, and handles timeouts
    and retries.
    """

    def __init__(self, orchestrator: Any = None) -> None:
        self._orchestrator = orchestrator
        self._running_workflows: dict[str, WorkflowResult] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, workflow: Workflow, context: dict[str, Any] | None = None) -> WorkflowResult:
        """Execute a full workflow end-to-end.

        Args:
            workflow: The workflow definition.
            context:  Initial context dict passed to the first step.

        Returns:
            A WorkflowResult with per-step results and overall status.
        """
        context = dict(context or {})
        result = WorkflowResult(
            workflow_name=workflow.name,
            status=WorkflowStatus.RUNNING,
            started_at=time.time(),
        )
        self._running_workflows[workflow.name] = result

        logger.info("Starting workflow: %s (%d steps)", workflow.name, len(workflow.steps))

        try:
            # Group steps: sequential unless they share a parallel_group
            step_groups = self._build_execution_groups(workflow.steps)

            for group in step_groups:
                if len(group) == 1:
                    step = group[0]
                    step_result = await self._execute_step(step, context, result)
                    result.step_results[step.id] = step_result

                    if step_result.status == StepStatus.FAILED:
                        # Check if the next step has a failure condition
                        if not self._has_failure_handler(step.id, workflow):
                            result.status = WorkflowStatus.FAILED
                            result.error = f"Step '{step.id}' failed: {step_result.error}"
                            break

                    # Feed output into context for later steps
                    context[step.id] = step_result.output
                else:
                    # Parallel group
                    tasks = [self._execute_step(s, context, result) for s in group]
                    step_results = await asyncio.gather(*tasks, return_exceptions=True)

                    any_failed = False
                    for step, sr in zip(group, step_results):
                        if isinstance(sr, BaseException):
                            sr = StepResult(
                                step_id=step.id,
                                status=StepStatus.FAILED,
                                error=str(sr),
                            )
                            any_failed = True
                        result.step_results[step.id] = sr
                        context[step.id] = sr.output

                        if sr.status == StepStatus.FAILED:
                            any_failed = True

                    if any_failed and not self._has_failure_handler_for_group(group, workflow):
                        result.status = WorkflowStatus.FAILED
                        result.error = "One or more parallel steps failed"
                        break

            if result.status == WorkflowStatus.RUNNING:
                result.status = WorkflowStatus.COMPLETED

        except asyncio.CancelledError:
            result.status = WorkflowStatus.CANCELLED
            result.error = "Workflow was cancelled"
        except Exception as exc:
            result.status = WorkflowStatus.FAILED
            result.error = str(exc)
            logger.exception("Workflow '%s' failed with exception", workflow.name)
        finally:
            result.completed_at = time.time()
            self._running_workflows.pop(workflow.name, None)

        logger.info(result.summary)
        return result

    async def cancel(self, workflow_name: str) -> None:
        """Cancel a running workflow by name."""
        if workflow_name in self._running_workflows:
            self._running_workflows[workflow_name].status = WorkflowStatus.CANCELLED
            logger.info("Cancelled workflow: %s", workflow_name)

    @property
    def running_workflows(self) -> list[str]:
        return list(self._running_workflows.keys())

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: WorkflowStep,
        context: dict[str, Any],
        workflow_result: WorkflowResult,
    ) -> StepResult:
        """Execute a single workflow step with retries and timeout."""
        # Check condition
        if step.condition and not self._evaluate_condition(step.condition, context, workflow_result):
            logger.info("Skipping step '%s' (condition not met)", step.id)
            return StepResult(step_id=step.id, status=StepStatus.SKIPPED)

        # Gather input from previous step
        step_input = ""
        if step.input_from and step.input_from in context:
            step_input = context[step.input_from]

        last_error = ""
        for attempt in range(1, step.retry_count + 1):
            sr = StepResult(
                step_id=step.id,
                status=StepStatus.RUNNING,
                started_at=time.time(),
            )

            logger.info(
                "Executing step '%s' (agent=%s, action=%s, attempt=%d/%d)",
                step.id, step.agent_role, step.action, attempt, step.retry_count,
            )

            try:
                output = await asyncio.wait_for(
                    self._dispatch_to_agent(step, step_input, context),
                    timeout=step.timeout_minutes * 60,
                )
                sr.status = StepStatus.COMPLETED
                sr.output = output
                sr.completed_at = time.time()
                return sr

            except asyncio.TimeoutError:
                last_error = f"Step timed out after {step.timeout_minutes} minutes"
                logger.warning("Step '%s' timed out (attempt %d/%d)", step.id, attempt, step.retry_count)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Step '%s' failed (attempt %d/%d): %s",
                    step.id, attempt, step.retry_count, exc,
                )

            if attempt < step.retry_count:
                await asyncio.sleep(min(2 ** attempt, 30))  # exponential backoff

        # All retries exhausted
        return StepResult(
            step_id=step.id,
            status=StepStatus.FAILED,
            error=last_error,
            started_at=sr.started_at,
            completed_at=time.time(),
        )

    async def _dispatch_to_agent(
        self,
        step: WorkflowStep,
        step_input: str,
        context: dict[str, Any],
    ) -> str:
        """Dispatch a step to the appropriate agent via the orchestrator.

        If no orchestrator is available, runs a simulated execution for
        testing purposes.
        """
        if self._orchestrator is not None:
            return await self._orchestrator.execute_agent_action(
                agent_role=step.agent_role,
                action=step.action,
                input_data=step_input,
                context=context,
            )

        # Simulation mode: useful for testing without a live orchestrator
        logger.info(
            "[SIM] Agent '%s' performing '%s' with input: %s",
            step.agent_role, step.action, (step_input or "(none)")[:100],
        )
        await asyncio.sleep(0.1)  # simulate work
        return f"[Simulated output from {step.agent_role}: {step.action}]"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_execution_groups(steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
        """Organize steps into sequential and parallel execution groups.

        Steps with the same ``parallel_group`` value run concurrently.
        Steps without a group run sequentially.
        """
        groups: list[list[WorkflowStep]] = []
        current_parallel: dict[str, list[WorkflowStep]] = {}
        current_parallel_key: str | None = None

        for step in steps:
            if step.parallel_group:
                if step.parallel_group != current_parallel_key:
                    # Flush previous parallel group
                    if current_parallel_key and current_parallel_key in current_parallel:
                        groups.append(current_parallel.pop(current_parallel_key))
                    current_parallel_key = step.parallel_group
                current_parallel.setdefault(step.parallel_group, []).append(step)
            else:
                # Flush any pending parallel group
                if current_parallel_key and current_parallel_key in current_parallel:
                    groups.append(current_parallel.pop(current_parallel_key))
                    current_parallel_key = None
                groups.append([step])

        # Flush remaining
        if current_parallel_key and current_parallel_key in current_parallel:
            groups.append(current_parallel.pop(current_parallel_key))

        return groups

    @staticmethod
    def _evaluate_condition(
        condition: str,
        context: dict[str, Any],
        workflow_result: WorkflowResult,
    ) -> bool:
        """Evaluate a simple step condition.

        Supported conditions:
          - ``previous.failed``   -- true if the most recent step failed
          - ``previous.completed`` -- true if the most recent step completed
          - ``step.<id>.failed``  -- true if a specific step failed
          - ``step.<id>.completed`` -- true if a specific step completed
        """
        condition = condition.strip().lower()

        if condition.startswith("previous."):
            # Find the most recent step result
            last_result = None
            for sr in workflow_result.step_results.values():
                last_result = sr

            if last_result is None:
                return False

            if "failed" in condition:
                return last_result.status == StepStatus.FAILED
            if "completed" in condition:
                return last_result.status == StepStatus.COMPLETED
            return True

        if condition.startswith("step."):
            parts = condition.split(".")
            if len(parts) >= 3:
                step_id = parts[1]
                check = parts[2]
                sr = workflow_result.step_results.get(step_id)
                if sr is None:
                    return False
                if "failed" in check:
                    return sr.status == StepStatus.FAILED
                if "completed" in check:
                    return sr.status == StepStatus.COMPLETED

        # Default: treat as truthy
        return True

    @staticmethod
    def _has_failure_handler(step_id: str, workflow: Workflow) -> bool:
        """Check if any later step has a condition referencing this step's failure."""
        for step in workflow.steps:
            if step.condition and step_id in step.condition and "failed" in step.condition:
                return True
        return False

    @staticmethod
    def _has_failure_handler_for_group(group: list[WorkflowStep], workflow: Workflow) -> bool:
        """Check if any later step handles failure for steps in this group."""
        group_ids = {s.id for s in group}
        for step in workflow.steps:
            if step.condition:
                for gid in group_ids:
                    if gid in step.condition and "failed" in step.condition:
                        return True
        return False
