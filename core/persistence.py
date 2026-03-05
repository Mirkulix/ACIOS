"""AICOS Persistence: SQLite-backed storage for tasks and KPIs.

Automatically saves state changes and restores them on restart,
so tasks and KPIs survive process restarts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.models import KPI, Task, TaskPriority, TaskStatus

DB_PATH = Path("data/state/aicos.db")


class Persistence:
    """SQLite persistence layer for AICOS state."""

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Open the database and create tables if needed."""
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        assert self._conn is not None
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                assigned_to TEXT DEFAULT '',
                created_by TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                result TEXT DEFAULT '',
                created_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS kpis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                value REAL NOT NULL,
                target REAL DEFAULT 0.0,
                agent_role TEXT,
                timestamp TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_kpis_name ON kpis(name);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def save_task(self, task: Task) -> None:
        """Insert or update a task."""
        assert self._conn is not None
        self._conn.execute("""
            INSERT OR REPLACE INTO tasks
                (id, title, description, assigned_to, created_by, status, priority, result, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.id,
            task.title,
            task.description,
            task.assigned_to,
            task.created_by,
            task.status.value,
            task.priority.value,
            task.result or "",
            task.created_at.isoformat() if task.created_at else None,
            task.completed_at.isoformat() if task.completed_at else None,
        ))
        self._conn.commit()

    def load_tasks(self) -> list[Task]:
        """Load all tasks from the database."""
        assert self._conn is not None
        rows = self._conn.execute("SELECT * FROM tasks").fetchall()
        tasks: list[Task] = []
        for row in rows:
            tasks.append(Task(
                id=row["id"],
                title=row["title"],
                description=row["description"] or "",
                assigned_to=row["assigned_to"] or "",
                created_by=row["created_by"] or "",
                status=TaskStatus(row["status"]),
                priority=TaskPriority(row["priority"]),
                result=row["result"] or "",
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            ))
        return tasks

    def delete_task(self, task_id: str) -> None:
        assert self._conn is not None
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    def save_kpi(self, kpi: KPI) -> None:
        assert self._conn is not None
        self._conn.execute("""
            INSERT INTO kpis (name, value, target, agent_role, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (
            kpi.name,
            kpi.value,
            kpi.target,
            kpi.agent_role.value if kpi.agent_role else None,
            kpi.timestamp.isoformat() if kpi.timestamp else None,
        ))
        self._conn.commit()

    def load_kpis(self) -> list[KPI]:
        assert self._conn is not None
        rows = self._conn.execute("SELECT * FROM kpis ORDER BY id DESC LIMIT 100").fetchall()
        kpis: list[KPI] = []
        for row in rows:
            from core.models import AgentRole
            kpis.append(KPI(
                name=row["name"],
                value=row["value"],
                target=row["target"],
                agent_role=AgentRole(row["agent_role"]) if row["agent_role"] else None,
                timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.utcnow(),
            ))
        return list(reversed(kpis))

    # ------------------------------------------------------------------
    # Observer callback for SharedState
    # ------------------------------------------------------------------

    async def on_state_change(self, event: str, payload: dict[str, Any]) -> None:
        """Observer callback — persists task changes to SQLite."""
        if event in ("task_completed", "task_failed", "task_in_progress", "task_updated", "task_created"):
            task_id = payload.get("task_id")
            if task_id:
                # We need to get the task from SharedState
                from core.state import SharedState
                state = SharedState()
                task = state.get_task(task_id)
                if task:
                    self.save_task(task)
