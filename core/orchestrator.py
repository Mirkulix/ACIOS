"""AICOS Orchestrator: the brain of the AI company.

Features:
  - SharedState as single source of truth
  - Anthropic Tool-Calling API (agents execute real tools)
  - Task retry with exponential backoff
  - LLM call timeout
  - Workflow engine integration
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any

import anthropic
from rich.console import Console
from rich.table import Table

from core.communication import CommunicationBus
from core.config_loader import ConfigLoader
from core.memory import MemoryManager
from core.models import (
    AgentConfig,
    AgentRole,
    CompanyConfig,
    KPI,
    Message,
    MessageType,
    Task,
    TaskPriority,
    TaskStatus,
)
from core.state import SharedState
from core.tools import ToolExecutor, get_tools_for_role

console = Console()

# Retry and timeout defaults
MAX_RETRIES = 2
LLM_TIMEOUT_SECONDS = 120

# Task explosion safeguards
MAX_PENDING_TASKS = 50  # refuse new tasks beyond this
MAX_DELEGATION_DEPTH = 3  # max chain of delegate_task calls

# Map roles to the kind of tasks they should handle.
_ROLE_KEYWORDS: dict[AgentRole, list[str]] = {
    AgentRole.CEO: ["strategy", "decision", "escalat", "conflict", "priority"],
    AgentRole.CFO: ["budget", "financ", "invoice", "revenue", "cost", "forecast"],
    AgentRole.CTO: ["architect", "tech", "infra", "review", "security", "system design"],
    AgentRole.SALES: ["lead", "proposal", "deal", "client", "prospect", "pipeline"],
    AgentRole.MARKETING: ["content", "campaign", "seo", "social", "brand", "engagement"],
    AgentRole.SUPPORT: ["ticket", "issue", "customer", "bug report", "complaint"],
    AgentRole.OPERATIONS: ["workflow", "process", "deadline", "schedule", "coordinate"],
    AgentRole.DEVELOPER: ["code", "implement", "develop", "fix", "feature", "deploy", "test"],
    AgentRole.HR: ["hire", "recruit", "onboard", "culture", "team"],
}


_ROLE_COLORS: dict[str, str] = {
    "ceo": "#e74c3c", "cfo": "#2ecc71", "cto": "#3498db",
    "sales": "#f39c12", "marketing": "#9b59b6", "support": "#1abc9c",
    "operations": "#e67e22", "developer": "#2980b9", "hr": "#95a5a6",
}


def _agent_color(role: str) -> str:
    return _ROLE_COLORS.get(role.lower(), "#888888")


class Orchestrator:
    """Central controller that boots agents, routes tasks, and runs the main loop."""

    def __init__(self, shared_state: SharedState | None = None) -> None:
        self.config: CompanyConfig | None = None
        self.bus = CommunicationBus()
        self.memory = MemoryManager()
        self._llm = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

        self.state = shared_state or SharedState()
        self._agent_configs: dict[str, AgentConfig] = {}
        self._running = False

        # Concurrency control — initialized in boot_company() from config
        self._semaphore: asyncio.Semaphore | None = None

        # Tool executor (set up after boot)
        self._tool_executor: ToolExecutor | None = None

        # Workflow engine (lazy init)
        self._workflow_engine: Any = None

        # Integration manager (injected from main.py)
        self._integration_manager: Any = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_config(self, path: str | object) -> CompanyConfig:
        loader = ConfigLoader()
        self.config = loader.load_company_config(path)
        if not loader.validate_config(self.config):
            raise ValueError("Company configuration failed validation")
        self.state.company_name = self.config.company.name
        self.state.company_type = self.config.company.type
        console.log(f"[bold green]Orchestrator[/] loaded config: {self.config.company.name}")
        return self.config

    # ------------------------------------------------------------------
    # Boot / Shutdown
    # ------------------------------------------------------------------

    def boot_company(self) -> list[str]:
        if self.config is None:
            raise RuntimeError("Call load_config() before boot_company()")

        booted: list[str] = []
        for key, agent_cfg in self.config.agents.items():
            if not agent_cfg.enabled:
                continue
            self.bus.register_agent(agent_cfg.name)
            self._agent_configs[agent_cfg.name] = agent_cfg
            self.state.set_agent(agent_cfg.name, {
                "name": agent_cfg.name,
                "role": agent_cfg.role.value,
                "model": agent_cfg.model,
                "enabled": agent_cfg.enabled,
                "status": "idle",
                "current_task": None,
                "tasks_completed": 0,
                "active_tasks": 0,
                "pending_messages": 0,
            })
            booted.append(agent_cfg.name)

        self.memory.store("company_name", self.config.company.name)
        self.memory.store("company_type", self.config.company.type)
        self.memory.store("active_agents", booted)
        self.memory.save_to_disk()

        # Concurrency semaphore from config
        max_parallel = self.config.orchestration.max_parallel_tasks
        self._semaphore = asyncio.Semaphore(max_parallel)
        console.log(f"[bold green]Orchestrator[/] concurrency limit: {max_parallel} parallel tasks")

        # Initialize tool executor
        self._tool_executor = ToolExecutor(
            shared_state=self.state,
            memory=self.memory,
            comm_bus=self.bus,
            integration_manager=self._integration_manager,
        )

        self.state.booted_at = datetime.utcnow()
        console.log(f"[bold green]Orchestrator[/] booted {len(booted)} agents: {', '.join(booted)}")
        return booted

    def set_integration_manager(self, manager: Any) -> None:
        """Inject the IntegrationManager (called from main.py after boot)."""
        self._integration_manager = manager
        if self._tool_executor:
            self._tool_executor._integrations = manager

    def shutdown(self) -> None:
        self._running = False
        self.memory.save_to_disk()
        self.bus.save_log_snapshot()
        console.log("[bold red]Orchestrator[/] shutdown complete")

    # ------------------------------------------------------------------
    # Main event loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        if self.config is None:
            raise RuntimeError("Call load_config() and boot_company() first")
        self._running = True
        tick = self.config.orchestration.tick_interval_seconds
        console.log("[bold green]Orchestrator[/] entering main loop")

        while self._running:
            await self._process_escalations()
            await self._auto_assign_pending_tasks()
            await self._execute_ready_tasks()
            self._refresh_agent_status()
            await asyncio.sleep(tick)

    async def run_once(self) -> None:
        await self._process_escalations()
        await self._auto_assign_pending_tasks()
        await self._execute_ready_tasks()

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def assign_task(self, task: Task) -> Task:
        # Backpressure: reject new tasks when queue is overloaded
        pending_count = len(self.state.list_tasks(TaskStatus.PENDING))
        in_progress_count = len(self.state.list_tasks(TaskStatus.IN_PROGRESS))
        if pending_count + in_progress_count >= MAX_PENDING_TASKS:
            console.log(f"[bold red]Task rejected[/] (queue full: {pending_count + in_progress_count}): \"{task.title}\"")
            task.status = TaskStatus.FAILED
            task.result = f"Rejected: task queue full ({pending_count + in_progress_count}/{MAX_PENDING_TASKS})"
            self.state.add_task(task)
            return task

        if not task.assigned_to and self.config and self.config.orchestration.auto_assign:
            best = self._find_best_agent(task)
            if best:
                task.assigned_to = best
        self.state.add_task(task)
        console.log(
            f"[blue]Task[/] [{task.priority.upper()}] \"{task.title}\" -> "
            f"{task.assigned_to or 'unassigned'}"
        )
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self.state.get_task(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        return self.state.list_tasks(status)

    async def complete_task(self, task_id: str, result: str = "") -> Task | None:
        task = await self.state.complete_task(task_id, result)
        if task:
            console.log(f"[green]Task completed[/] \"{task.title}\"")
        return task

    async def fail_task(self, task_id: str, reason: str = "") -> Task | None:
        task = await self.state.fail_task(task_id, reason)
        if task:
            console.log(f"[red]Task failed[/] \"{task.title}\": {reason}")
        return task

    # ------------------------------------------------------------------
    # KPI tracking
    # ------------------------------------------------------------------

    def track_kpi(self, kpi: KPI) -> None:
        self.state.add_kpi(kpi)
        self.memory.store(
            f"kpi:{kpi.name}:latest",
            {"value": kpi.value, "target": kpi.target, "ts": kpi.timestamp.isoformat()},
        )
        console.log(f"[yellow]KPI[/] {kpi.name} = {kpi.value} (target {kpi.target})")

    def get_kpis(self, name: str | None = None) -> list[KPI]:
        return self.state.get_kpis(name)

    # ------------------------------------------------------------------
    # Workflow execution
    # ------------------------------------------------------------------

    async def execute_workflow(self, workflow_name: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Trigger a workflow by name."""
        from workflows.engine import WorkflowEngine, load_workflow

        if self._workflow_engine is None:
            self._workflow_engine = WorkflowEngine(orchestrator=self)

        try:
            wf = load_workflow(workflow_name)
            result = await self._workflow_engine.execute(wf, context)
            return {"status": result.status.value, "summary": result.summary}
        except FileNotFoundError:
            return {"error": f"Workflow '{workflow_name}' not found"}
        except Exception as exc:
            return {"error": str(exc)}

    async def execute_agent_action(
        self,
        agent_role: str,
        action: str,
        input_data: str = "",
        context: dict[str, Any] | None = None,
    ) -> str:
        """Execute an agent action (called by WorkflowEngine)."""
        # Find the agent config for this role
        cfg = None
        for c in self._agent_configs.values():
            if c.role.value == agent_role.lower():
                cfg = c
                break
        if cfg is None:
            return f"[Error] No agent with role '{agent_role}'"

        prompt = f"Action: {action}\nInput: {input_data}\n\nExecute this action and provide the result."
        return await self._run_agent_task(cfg, prompt_override=prompt)

    # ------------------------------------------------------------------
    # Escalation handling
    # ------------------------------------------------------------------

    async def handle_escalation(self, message: Message) -> str:
        ceo_cfg = self._get_ceo_config()
        system = ceo_cfg.system_prompt if ceo_cfg else "You are the CEO. Make a clear decision."
        context_facts = self.memory.search(message.content[:80])
        context_block = "\n".join(
            f"- [{f['scope']}] {f['key']}: {f['value']}" for f in context_facts[:5]
        )
        user_prompt = (
            f"ESCALATION from {message.from_agent}:\n"
            f"{message.content}\n\n"
            f"Relevant company context:\n{context_block}\n\n"
            "What is your decision? Be concise and actionable."
        )
        try:
            response = self._llm.messages.create(
                model=ceo_cfg.model if ceo_cfg else "claude-sonnet-4-5-20250929",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
            decision = response.content[0].text
        except Exception as exc:
            decision = f"[Escalation auto-response] Unable to reach CEO LLM: {exc}"

        self.memory.store(
            f"escalation:{message.id}",
            {"from": message.from_agent, "content": message.content, "decision": decision},
        )
        await self.bus.send("CEO", message.from_agent, f"CEO Decision: {decision}")
        console.log(f"[bold red]Escalation resolved[/] for {message.from_agent}")
        return decision

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        return self.state.snapshot()

    def print_status(self) -> None:
        table = Table(title=f"{self.state.company_name} — Status")
        table.add_column("Agent", style="cyan")
        table.add_column("Role")
        table.add_column("Active Tasks", justify="right")
        table.add_column("Status")
        for agent_data in self.state.get_agents():
            table.add_row(
                agent_data["name"], agent_data["role"],
                str(agent_data.get("active_tasks", 0)), agent_data.get("status", "unknown"),
            )
        console.print(table)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_best_agent(self, task: Task) -> str | None:
        text = f"{task.title} {task.description}".lower()
        best_name: str | None = None
        best_score: float = -1.0
        for name, cfg in self._agent_configs.items():
            keywords = _ROLE_KEYWORDS.get(cfg.role, [])
            match_score = sum(1 for kw in keywords if kw in text)
            current_load = len([
                t for t in self.state.tasks.values()
                if t.assigned_to == name and t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
            ])
            final_score = match_score - current_load * 0.3
            if final_score > best_score:
                best_score = final_score
                best_name = name
        return best_name

    def _get_ceo_config(self) -> AgentConfig | None:
        for cfg in self._agent_configs.values():
            if cfg.role == AgentRole.CEO:
                return cfg
        return None

    async def _process_escalations(self) -> None:
        ceo_cfg = self._get_ceo_config()
        if ceo_cfg is None:
            return
        messages = self.bus.get_inbox(ceo_cfg.name)
        for msg in messages:
            if msg.message_type == MessageType.ESCALATION:
                await self.handle_escalation(msg)

    async def _auto_assign_pending_tasks(self) -> None:
        for task in self.state.list_tasks(TaskStatus.PENDING):
            if not task.assigned_to:
                self.assign_task(task)

    async def _execute_ready_tasks(self) -> None:
        """Move pending tasks to in_progress, then call LLM with semaphore-limited concurrency."""
        # Backpressure: skip scheduling if too many tasks are already in-flight
        in_progress_count = len(self.state.list_tasks(TaskStatus.IN_PROGRESS))
        max_parallel = self.config.orchestration.max_parallel_tasks if self.config else 3
        if in_progress_count >= max_parallel:
            return

        ready: list[tuple[Task, AgentConfig]] = []
        slots_available = max_parallel - in_progress_count

        for task in self.state.list_tasks(TaskStatus.PENDING):
            if len(ready) >= slots_available:
                break
            if not task.assigned_to:
                continue
            deps_met = all(
                self.state.get_task(dep_id) and self.state.get_task(dep_id).status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
            )
            if not deps_met:
                continue
            agent_cfg = self._agent_configs.get(task.assigned_to)
            if agent_cfg is None:
                continue
            await self.state.mark_task_in_progress(task.id)
            console.log(f"[bold yellow]Agent {task.assigned_to} startet Task:[/] \"{task.title}\"")
            ready.append((task, agent_cfg))

        if not ready:
            return

        self._refresh_agent_status()

        # Emit activity event for each task start
        for task, agent_cfg in ready:
            await self.state.add_activity({
                "event_type": "agent_task_started",
                "agent": task.assigned_to,
                "detail": task.title,
                "color": _agent_color(agent_cfg.role.value),
            })

        async def _run_one(task: Task, cfg: AgentConfig) -> None:
            async with self._semaphore:
                result = await self._run_agent_task_with_retry(cfg, task)
                if result is not None:
                    await self.complete_task(task.id, result)
                else:
                    await self.fail_task(task.id, "Agent returned no result after retries")
                self._refresh_agent_status()

        await asyncio.gather(*[_run_one(t, c) for t, c in ready])

    def _refresh_agent_status(self) -> None:
        for name, cfg in self._agent_configs.items():
            assigned = [t for t in self.state.tasks.values() if t.assigned_to == name]
            active = [t for t in assigned if t.status == TaskStatus.IN_PROGRESS]
            completed = [t for t in assigned if t.status == TaskStatus.COMPLETED]
            current_task = active[0].title if active else None
            status = "working" if active else ("idle" if cfg.enabled else "disabled")
            self.state.set_agent(name, {
                "name": name,
                "role": cfg.role.value,
                "model": cfg.model,
                "enabled": cfg.enabled,
                "status": status,
                "current_task": current_task,
                "tasks_completed": len(completed),
                "active_tasks": len(active),
                "pending_messages": self.bus._inboxes.get(name, asyncio.Queue()).qsize(),
            })

    # ------------------------------------------------------------------
    # LLM execution with Tool Calling, Retry, and Timeout
    # ------------------------------------------------------------------

    async def _run_agent_task_with_retry(self, agent_cfg: AgentConfig, task: Task) -> str | None:
        """Retry wrapper around _run_agent_task."""
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    self._run_agent_task(agent_cfg, task),
                    timeout=LLM_TIMEOUT_SECONDS,
                )
                if result is not None:
                    return result
            except asyncio.TimeoutError:
                last_error = f"Timeout after {LLM_TIMEOUT_SECONDS}s"
                console.log(f"[yellow]Timeout[/] {agent_cfg.name} attempt {attempt}/{MAX_RETRIES}")
            except Exception as exc:
                last_error = str(exc)
                console.log(f"[yellow]Retry[/] {agent_cfg.name} attempt {attempt}/{MAX_RETRIES}: {exc}")

            if attempt < MAX_RETRIES:
                await asyncio.sleep(min(2 ** attempt, 10))

        console.log(f"[red]All retries exhausted[/] for {agent_cfg.name}: {last_error}")
        return None

    async def _run_agent_task(
        self,
        agent_cfg: AgentConfig,
        task: Task | None = None,
        prompt_override: str | None = None,
    ) -> str | None:
        """Call the LLM with tool-calling support.

        The agent can invoke tools mid-conversation. The loop continues
        until the LLM produces a final text response (end_turn).
        """
        # Reset delegation counter for this execution
        if self._tool_executor:
            self._tool_executor.reset_delegation_count(agent_cfg.name)

        system = agent_cfg.system_prompt

        # Add company context so agents know about the team
        team_info = []
        for a in self.state.get_agents():
            status_str = a.get("status", "unknown")
            current = f" (working on: {a['current_task']})" if a.get("current_task") else ""
            team_info.append(f"- {a['name']} ({a['role']}): {status_str}{current}")
        if team_info:
            system += "\n\nYour company team:\n" + "\n".join(team_info)
            system += "\n\nIMPORTANT: Use get_agent_status and list_active_tasks before delegating. Limit delegation — prefer completing work yourself when possible."

        facts = self.memory.get_facts(agent_cfg.name)
        context_lines = [f"- {f}" for f in facts[:10]]
        if context_lines:
            system += "\n\nRelevant knowledge:\n" + "\n".join(context_lines)

        if prompt_override:
            user_prompt = prompt_override
        elif task:
            user_prompt = (
                f"Task: {task.title}\n"
                f"Description: {task.description}\n"
                f"Priority: {task.priority}\n\n"
                "Complete this task. You can use your available tools if needed. "
                "Provide a clear, structured result."
            )
        else:
            return None

        # Get role-specific tools
        tools = get_tools_for_role(agent_cfg.role.value)

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]

        agent_name = agent_cfg.name
        color = _agent_color(agent_cfg.role.value)

        try:
            # Tool-calling loop (max 5 tool rounds)
            for _ in range(5):
                # Emit "thinking" event before LLM call
                await self.state.add_activity({
                    "event_type": "agent_thinking",
                    "agent": agent_name,
                    "detail": "Anfrage an LLM...",
                    "color": color,
                })

                response = self._llm.messages.create(
                    model=agent_cfg.model,
                    max_tokens=2048,
                    system=system,
                    messages=messages,
                    tools=tools if tools else None,
                )

                # Collect all content blocks
                text_parts: list[str] = []
                tool_uses: list[dict[str, Any]] = []

                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_uses.append({
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                # If no tool calls, we're done
                if not tool_uses:
                    result = "\n".join(text_parts)
                    preview = result[:120] + "..." if len(result) > 120 else result
                    size_kb = f"{len(result) / 1024:.1f}KB"
                    await self.state.add_activity({
                        "event_type": "agent_response",
                        "agent": agent_name,
                        "detail": f"{preview} ({size_kb})",
                        "color": color,
                    })
                    if task:
                        self.memory.append_conversation(agent_cfg.name, "user", user_prompt)
                        self.memory.append_conversation(agent_cfg.name, "assistant", result)
                    return result

                # Execute tools and build tool_result messages
                # First, add the assistant's response to messages
                assistant_content: list[dict[str, Any]] = []
                for tp in text_parts:
                    assistant_content.append({"type": "text", "text": tp})
                for tu in tool_uses:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tu["id"],
                        "name": tu["name"],
                        "input": tu["input"],
                    })
                messages.append({"role": "assistant", "content": assistant_content})

                # Execute each tool and create result messages
                tool_results: list[dict[str, Any]] = []
                for tu in tool_uses:
                    input_summary = json.dumps(tu["input"], ensure_ascii=False)[:80]
                    console.log(f"[cyan]Tool[/] {agent_name} -> {tu['name']}({input_summary})")

                    # Emit tool_call event
                    await self.state.add_activity({
                        "event_type": "agent_tool_call",
                        "agent": agent_name,
                        "detail": f"{tu['name']}: {input_summary}",
                        "color": color,
                    })

                    if self._tool_executor:
                        tool_result = await self._tool_executor.execute(
                            tu["name"], tu["input"], agent_name=agent_name
                        )
                    else:
                        tool_result = json.dumps({"status": "ok"})

                    # Emit tool_result event
                    result_preview = str(tool_result)[:100]
                    await self.state.add_activity({
                        "event_type": "agent_tool_result",
                        "agent": agent_name,
                        "detail": f"{tu['name']}: {result_preview}",
                        "color": color,
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": tool_result,
                    })

                messages.append({"role": "user", "content": tool_results})

                # If the LLM stopped because of end_turn, break
                if response.stop_reason == "end_turn":
                    result = "\n".join(text_parts)
                    preview = result[:120] + "..." if len(result) > 120 else result
                    size_kb = f"{len(result) / 1024:.1f}KB"
                    await self.state.add_activity({
                        "event_type": "agent_response",
                        "agent": agent_name,
                        "detail": f"{preview} ({size_kb})",
                        "color": color,
                    })
                    if task:
                        self.memory.append_conversation(agent_cfg.name, "user", user_prompt)
                        self.memory.append_conversation(agent_cfg.name, "assistant", result)
                    return result

            # If we exhausted the tool loop, return what we have
            return "\n".join(text_parts) if text_parts else "[Agent completed task with tool actions]"

        except Exception as exc:
            console.log(f"[red]Agent error[/] {agent_name}: {exc}")
            raise
