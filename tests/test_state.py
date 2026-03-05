"""Tests for SharedState singleton and its operations."""

import asyncio
import pytest
from core.state import SharedState
from core.models import Task, TaskStatus, TaskPriority, KPI, Message, MessageType


class TestSharedStateSingleton:
    def test_singleton_returns_same_instance(self):
        s1 = SharedState()
        s2 = SharedState()
        assert s1 is s2

    def test_reset_creates_new_instance(self):
        s1 = SharedState()
        SharedState.reset()
        s2 = SharedState()
        assert s1 is not s2


class TestSharedStateTasks:
    def test_add_and_get_task(self):
        state = SharedState()
        task = Task(title="Test task", description="A test")
        state.add_task(task)
        assert state.get_task(task.id) is task

    def test_list_tasks_by_status(self):
        state = SharedState()
        t1 = Task(title="Pending", status=TaskStatus.PENDING)
        t2 = Task(title="Done", status=TaskStatus.COMPLETED)
        state.add_task(t1)
        state.add_task(t2)

        pending = state.list_tasks(TaskStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].title == "Pending"

    def test_complete_task(self):
        state = SharedState()
        task = Task(title="To complete")
        state.add_task(task)

        result = asyncio.get_event_loop().run_until_complete(
            state.complete_task(task.id, "Done!")
        )
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.result == "Done!"
        assert result.completed_at is not None

    def test_fail_task(self):
        state = SharedState()
        task = Task(title="Will fail")
        state.add_task(task)

        result = asyncio.get_event_loop().run_until_complete(
            state.fail_task(task.id, "Error occurred")
        )
        assert result.status == TaskStatus.FAILED
        assert result.result == "Error occurred"

    def test_mark_task_in_progress(self):
        state = SharedState()
        task = Task(title="Starting")
        state.add_task(task)

        result = asyncio.get_event_loop().run_until_complete(
            state.mark_task_in_progress(task.id)
        )
        assert result.status == TaskStatus.IN_PROGRESS


class TestSharedStateMessages:
    def test_add_and_get_messages(self):
        state = SharedState()
        msg = Message(from_agent="CEO", to_agent="CTO", content="Hello")
        state.add_message(msg)

        messages = state.get_messages()
        assert len(messages) == 1
        assert messages[0].content == "Hello"


class TestSharedStateKPIs:
    def test_add_and_get_kpis(self):
        state = SharedState()
        kpi = KPI(name="revenue", value=1000, target=5000)
        state.add_kpi(kpi)

        kpis = state.get_kpis("revenue")
        assert len(kpis) == 1
        assert kpis[0].value == 1000


class TestSharedStateObserver:
    def test_observer_called_on_task_complete(self):
        state = SharedState()
        events = []

        async def observer(event, payload):
            events.append(event)

        state.add_observer(observer)
        task = Task(title="Observable")
        state.add_task(task)

        asyncio.get_event_loop().run_until_complete(
            state.complete_task(task.id, "Result")
        )
        assert "task_completed" in events

    def test_observer_removed(self):
        state = SharedState()
        events = []

        async def observer(event, payload):
            events.append(event)

        state.add_observer(observer)
        state.remove_observer(observer)

        task = Task(title="No observer")
        state.add_task(task)
        asyncio.get_event_loop().run_until_complete(
            state.complete_task(task.id, "Result")
        )
        assert len(events) == 0


class TestSharedStateSnapshot:
    def test_snapshot_structure(self):
        state = SharedState()
        state.company_name = "Test Corp"
        state.add_task(Task(title="T1"))
        state.add_kpi(KPI(name="sales", value=100))

        snap = state.snapshot()
        assert snap["company"] == "Test Corp"
        assert len(snap["tasks"]) == 1
        assert len(snap["kpis"]) == 1
        assert "updated_at" in snap
