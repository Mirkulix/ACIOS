"""Tests for the tool execution system."""

import asyncio
import pytest
from core.state import SharedState
from core.memory import MemoryManager
from core.tools import ToolExecutor, get_tools_for_role, TOOL_SCHEMAS


class TestToolSchemas:
    def test_all_roles_have_tools(self):
        for role in ["ceo", "cfo", "cto", "sales", "marketing", "support", "operations", "developer", "hr"]:
            tools = get_tools_for_role(role)
            assert len(tools) > 0, f"Role {role} has no tools"

    def test_schemas_have_required_fields(self):
        for name, schema in TOOL_SCHEMAS.items():
            assert "name" in schema, f"Tool {name} missing 'name'"
            assert "description" in schema, f"Tool {name} missing 'description'"
            assert "input_schema" in schema, f"Tool {name} missing 'input_schema'"


class TestToolExecutor:
    def test_delegate_task(self):
        state = SharedState()
        state.set_agent("CEO", {"name": "CEO", "role": "ceo"})
        executor = ToolExecutor(shared_state=state)

        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("delegate_task", {
                "title": "Market Analysis",
                "description": "Analyze Q1 trends",
                "assign_to": "ceo",
            }, "CTO")
        )
        import json
        data = json.loads(result)
        assert data["status"] == "created"
        assert len(state.tasks) == 1

    def test_store_and_retrieve_knowledge(self):
        state = SharedState()
        memory = MemoryManager(data_dir="/tmp/aicos_test_mem")
        executor = ToolExecutor(shared_state=state, memory=memory)

        asyncio.get_event_loop().run_until_complete(
            executor.execute("store_knowledge", {
                "key": "test_fact",
                "value": "Python is great",
                "scope": "company",
            }, "CEO")
        )

        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("retrieve_knowledge", {
                "query": "Python",
            }, "CEO")
        )
        import json
        data = json.loads(result)
        assert len(data["results"]) > 0

    def test_track_kpi(self):
        state = SharedState()
        state.set_agent("CFO", {"name": "CFO", "role": "cfo"})
        executor = ToolExecutor(shared_state=state)

        asyncio.get_event_loop().run_until_complete(
            executor.execute("track_kpi", {
                "name": "monthly_revenue",
                "value": 50000,
                "target": 100000,
            }, "CFO")
        )
        assert len(state.kpis) == 1
        assert state.kpis[0].name == "monthly_revenue"

    def test_unknown_tool(self):
        executor = ToolExecutor()
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("nonexistent_tool", {}, "CEO")
        )
        import json
        data = json.loads(result)
        assert "error" in data

    def test_delegation_limit(self):
        """delegate_task should be blocked after MAX_DELEGATIONS_PER_TASK calls."""
        from core.tools import MAX_DELEGATIONS_PER_TASK
        state = SharedState()
        state.set_agent("CEO", {"name": "CEO", "role": "ceo"})
        state.set_agent("CTO", {"name": "CTO", "role": "cto"})
        executor = ToolExecutor(shared_state=state)

        import json
        for i in range(MAX_DELEGATIONS_PER_TASK):
            result = asyncio.get_event_loop().run_until_complete(
                executor.execute("delegate_task", {
                    "title": f"Task {i}",
                    "description": "test",
                    "assign_to": "cto",
                }, "CEO")
            )
            data = json.loads(result)
            assert data["status"] == "created"

        # Next delegation should be rejected
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("delegate_task", {
                "title": "One too many",
                "description": "should fail",
                "assign_to": "cto",
            }, "CEO")
        )
        data = json.loads(result)
        assert "error" in data
        assert "limit" in data["error"].lower()

    def test_self_delegation_blocked(self):
        """Agent should not be able to delegate to itself."""
        state = SharedState()
        state.set_agent("CEO", {"name": "CEO", "role": "ceo"})
        executor = ToolExecutor(shared_state=state)

        import json
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("delegate_task", {
                "title": "Self-loop",
                "description": "test",
                "assign_to": "ceo",
            }, "CEO")
        )
        data = json.loads(result)
        assert "error" in data

    def test_get_agent_status(self):
        """get_agent_status should return all agents."""
        state = SharedState()
        state.set_agent("CEO", {"name": "CEO", "role": "ceo", "status": "idle", "current_task": None, "active_tasks": 0, "tasks_completed": 2})
        state.set_agent("CTO", {"name": "CTO", "role": "cto", "status": "working", "current_task": "Build API", "active_tasks": 1, "tasks_completed": 5})
        executor = ToolExecutor(shared_state=state)

        import json
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("get_agent_status", {}, "CEO")
        )
        data = json.loads(result)
        assert len(data["agents"]) == 2
        cto = [a for a in data["agents"] if a["name"] == "CTO"][0]
        assert cto["status"] == "working"
        assert cto["current_task"] == "Build API"

    def test_list_active_tasks(self):
        """list_active_tasks should return active tasks."""
        from core.models import Task, TaskStatus
        state = SharedState()
        t1 = Task(title="Active 1", status=TaskStatus.IN_PROGRESS, assigned_to="CEO")
        t2 = Task(title="Done", status=TaskStatus.COMPLETED, assigned_to="CTO")
        t3 = Task(title="Pending", status=TaskStatus.PENDING, assigned_to="CFO")
        state.add_task(t1)
        state.add_task(t2)
        state.add_task(t3)
        executor = ToolExecutor(shared_state=state)

        import json
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("list_active_tasks", {}, "CEO")
        )
        data = json.loads(result)
        # Default filter = active (pending + in_progress)
        assert len(data["tasks"]) == 2

    def test_get_task_result(self):
        """get_task_result should return task details."""
        from core.models import Task, TaskStatus
        state = SharedState()
        t = Task(title="Finished work", status=TaskStatus.COMPLETED, result="All done!")
        state.add_task(t)
        executor = ToolExecutor(shared_state=state)

        import json
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("get_task_result", {"task_id": t.id}, "CTO")
        )
        data = json.loads(result)
        assert data["result"] == "All done!"
        assert data["status"] == "completed"

    def test_collaboration_tools_in_all_roles(self):
        """All roles should have access to collaboration tools."""
        for role in ["ceo", "cfo", "cto", "sales", "marketing", "support", "operations", "developer", "hr"]:
            tools = get_tools_for_role(role)
            tool_names = [t["name"] for t in tools]
            assert "get_agent_status" in tool_names, f"Role {role} missing get_agent_status"
            assert "list_active_tasks" in tool_names, f"Role {role} missing list_active_tasks"
            assert "get_task_result" in tool_names, f"Role {role} missing get_task_result"
