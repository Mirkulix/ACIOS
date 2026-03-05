"""AICOS SharedState: Central in-memory state store with Observer pattern.

Both the Orchestrator and the Dashboard share this single instance.
State changes trigger callbacks so the Dashboard can push WebSocket updates
without polling or file I/O.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from typing import Any, Callable, Coroutine

from core.models import KPI, Message, Task, TaskStatus


# Type alias for observer callbacks: async def callback(event: str, payload: dict)
ObserverCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class SharedState:
    """Singleton state store shared by Orchestrator and Dashboard."""

    _instance: SharedState | None = None

    def __new__(cls) -> SharedState:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Core data
        self.tasks: dict[str, Task] = {}
        self.messages: list[Message] = []
        self.kpis: list[KPI] = []
        self.agents: dict[str, dict[str, Any]] = {}

        # Company info
        self.company_name: str = "AICOS"
        self.company_type: str = "custom"
        self.booted_at: datetime | None = None

        # Observer callbacks
        self._observers: list[ObserverCallback] = []

        # Activity feed ring buffer (max 200 entries)
        self.activity_feed: deque[dict[str, Any]] = deque(maxlen=200)

    # ------------------------------------------------------------------
    # Observer pattern
    # ------------------------------------------------------------------

    def add_observer(self, callback: ObserverCallback) -> None:
        """Register a callback for state changes."""
        self._observers.append(callback)

    def remove_observer(self, callback: ObserverCallback) -> None:
        """Unregister a callback."""
        self._observers = [o for o in self._observers if o is not callback]

    async def _notify(self, event: str, payload: dict[str, Any] | None = None) -> None:
        """Fire all observer callbacks (non-blocking)."""
        for cb in self._observers:
            try:
                await cb(event, payload or {})
            except Exception:
                pass  # Don't let a bad observer break the system

    # ------------------------------------------------------------------
    # Activity feed
    # ------------------------------------------------------------------

    async def add_activity(self, entry: dict[str, Any]) -> None:
        """Append an activity entry and push it via WebSocket."""
        entry.setdefault("timestamp", datetime.utcnow().isoformat())
        self.activity_feed.append(entry)
        await self._notify(entry.get("event_type", "activity"), entry)

    def get_activity_feed(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return the last *limit* activity entries (newest last)."""
        items = list(self.activity_feed)
        return items[-limit:]

    # ------------------------------------------------------------------
    # Agent state
    # ------------------------------------------------------------------

    def set_agent(self, name: str, data: dict[str, Any]) -> None:
        """Register or update an agent's runtime info."""
        self.agents[name] = data

    def get_agents(self) -> list[dict[str, Any]]:
        """Return all agent snapshots."""
        return list(self.agents.values())

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def add_task(self, task: Task) -> Task:
        self.tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        tasks = list(self.tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    async def update_task(self, task_id: str, **kwargs: Any) -> Task | None:
        """Update task fields and notify observers."""
        task = self.tasks.get(task_id)
        if task is None:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        await self._notify("task_updated", {"task_id": task_id, "changes": kwargs})
        return task

    async def complete_task(self, task_id: str, result: str = "") -> Task | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.utcnow()
        await self._notify("task_completed", {
            "task_id": task_id,
            "task": _task_to_dict(task),
        })
        return task

    async def fail_task(self, task_id: str, reason: str = "") -> Task | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        task.status = TaskStatus.FAILED
        task.result = reason
        await self._notify("task_failed", {"task_id": task_id, "reason": reason})
        return task

    async def mark_task_in_progress(self, task_id: str) -> Task | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        task.status = TaskStatus.IN_PROGRESS
        await self._notify("task_in_progress", {
            "task_id": task_id,
            "task": _task_to_dict(task),
        })
        return task

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, message: Message) -> None:
        self.messages.append(message)

    def get_messages(self, limit: int = 50) -> list[Message]:
        return self.messages[-limit:]

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    def add_kpi(self, kpi: KPI) -> None:
        self.kpis.append(kpi)

    def get_kpis(self, name: str | None = None) -> list[KPI]:
        if name:
            return [k for k in self.kpis if k.name == name]
        return list(self.kpis)

    # ------------------------------------------------------------------
    # Full snapshot (for REST API and persistence)
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return the complete state as a JSON-serialisable dict."""
        return {
            "company": self.company_name,
            "type": self.company_type,
            "booted_at": self.booted_at.isoformat() if self.booted_at else None,
            "updated_at": datetime.utcnow().isoformat(),
            "agents": self.get_agents(),
            "tasks": [_task_to_dict(t) for t in self.tasks.values()],
            "messages": [_message_to_dict(m) for m in self.messages[-50:]],
            "kpis": [_kpi_to_dict(k) for k in self.kpis[-20:]],
        }

    # ------------------------------------------------------------------
    # Reset (for tests)
    # ------------------------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton — only for tests."""
        cls._instance = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _task_to_dict(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "assigned_to": t.assigned_to,
        "created_by": t.created_by,
        "status": t.status.value,
        "priority": t.priority.value,
        "result": t.result or "",
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


def _message_to_dict(m: Message) -> dict[str, Any]:
    return {
        "id": m.id,
        "from_agent": m.from_agent,
        "to_agent": m.to_agent,
        "content": m.content,
        "message_type": m.message_type.value,
        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
    }


def _kpi_to_dict(k: KPI) -> dict[str, Any]:
    return {
        "name": k.name,
        "value": k.value,
        "target": k.target,
        "agent_role": k.agent_role.value if k.agent_role else None,
        "timestamp": k.timestamp.isoformat() if k.timestamp else None,
    }
