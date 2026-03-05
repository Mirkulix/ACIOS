"""Tests for SQLite persistence layer."""

import tempfile
from pathlib import Path

import pytest
from core.models import Task, TaskStatus, TaskPriority, KPI, AgentRole
from core.persistence import Persistence


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    p = Persistence(db_path=db_path)
    p.connect()
    yield p
    p.close()
    db_path.unlink(missing_ok=True)


class TestTaskPersistence:
    def test_save_and_load_task(self, db):
        task = Task(title="Persistent Task", description="Survives restart",
                    assigned_to="CEO", priority=TaskPriority.HIGH)
        db.save_task(task)

        loaded = db.load_tasks()
        assert len(loaded) == 1
        assert loaded[0].title == "Persistent Task"
        assert loaded[0].id == task.id
        assert loaded[0].priority == TaskPriority.HIGH

    def test_update_task(self, db):
        task = Task(title="To update")
        db.save_task(task)

        task.status = TaskStatus.COMPLETED
        task.result = "Done"
        db.save_task(task)

        loaded = db.load_tasks()
        assert len(loaded) == 1
        assert loaded[0].status == TaskStatus.COMPLETED
        assert loaded[0].result == "Done"

    def test_delete_task(self, db):
        task = Task(title="To delete")
        db.save_task(task)
        db.delete_task(task.id)

        loaded = db.load_tasks()
        assert len(loaded) == 0

    def test_multiple_tasks(self, db):
        for i in range(5):
            db.save_task(Task(title=f"Task {i}"))
        loaded = db.load_tasks()
        assert len(loaded) == 5


class TestKPIPersistence:
    def test_save_and_load_kpi(self, db):
        kpi = KPI(name="revenue", value=42000, target=50000, agent_role=AgentRole.CFO)
        db.save_kpi(kpi)

        loaded = db.load_kpis()
        assert len(loaded) == 1
        assert loaded[0].name == "revenue"
        assert loaded[0].value == 42000
        assert loaded[0].agent_role == AgentRole.CFO
