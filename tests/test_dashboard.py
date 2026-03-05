"""Tests for the Dashboard REST API."""

import pytest
from httpx import AsyncClient, ASGITransport
from core.state import SharedState
from core.models import Task, TaskPriority
from dashboard.app import create_app


@pytest.fixture
def state():
    s = SharedState()
    s.company_name = "Test Company"
    s.set_agent("CEO", {"name": "CEO", "role": "ceo", "status": "idle", "enabled": True})
    return s


@pytest.fixture
def app(state):
    return create_app(shared_state=state)


@pytest.mark.asyncio
async def test_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_status_live(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status")
        data = resp.json()
        assert data["live"] is True
        assert data["company"] == "Test Company"


@pytest.mark.asyncio
async def test_agents_list(app, state):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents")
        agents = resp.json()
        assert len(agents) == 1
        assert agents[0]["name"] == "CEO"


@pytest.mark.asyncio
async def test_create_task(app, state):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tasks", json={
            "title": "Test task",
            "description": "A test",
            "priority": "high",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test task"
        assert data["priority"] == "high"
        assert len(state.tasks) == 1


@pytest.mark.asyncio
async def test_list_tasks(app, state):
    state.add_task(Task(title="T1"))
    state.add_task(Task(title="T2"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/tasks")
        tasks = resp.json()
        assert len(tasks) == 2


@pytest.mark.asyncio
async def test_workflows_list(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/workflows")
        assert resp.status_code == 200
        workflows = resp.json()
        assert isinstance(workflows, list)
        assert len(workflows) > 0  # We have workflow definitions
