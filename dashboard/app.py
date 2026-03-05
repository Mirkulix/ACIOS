"""AICOS Dashboard: FastAPI backend serving the web UI and REST/WebSocket APIs.

Features:
  - Unified mode (SharedState in-memory) or standalone (file-based fallback)
  - Basic authentication via AICOS_DASHBOARD_USER / AICOS_DASHBOARD_PASS env vars
  - Workflow trigger API
  - WebSocket push on state changes
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.models import (
    KPI,
    Message,
    Task,
    TaskPriority,
    TaskStatus,
)


class TaskCreateModel(BaseModel):
    title: str
    description: str = ""
    assigned_to: str = ""
    priority: str = "medium"
    dependencies: list[str] = []


class WorkflowRunModel(BaseModel):
    workflow_name: str
    context: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

DASHBOARD_DIR = Path(__file__).resolve().parent
STATIC_DIR = DASHBOARD_DIR / "static"
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
CONFIG_PATH = PROJECT_ROOT / "config" / "company.yaml"
STATE_FILE = PROJECT_ROOT / "data" / "state" / "runtime.json"
TASK_INBOX = PROJECT_ROOT / "data" / "state" / "task_inbox.json"
LOGS_DIR = PROJECT_ROOT / "data" / "logs"

ROLE_COLORS: dict[str, str] = {
    "ceo": "#e74c3c", "cfo": "#2ecc71", "cto": "#3498db",
    "sales": "#f39c12", "marketing": "#9b59b6", "support": "#1abc9c",
    "operations": "#e67e22", "developer": "#2980b9", "hr": "#95a5a6",
}


# ---------------------------------------------------------------------------
# Authentication Middleware
# ---------------------------------------------------------------------------

class AuthMiddleware(BaseHTTPMiddleware):
    """HTTP Basic Auth middleware. Skipped if AICOS_DASHBOARD_PASS is not set."""

    def __init__(self, app, username: str, password: str) -> None:
        super().__init__(app)
        self._username = username
        self._password = password

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip auth for WebSocket and health endpoints
        if request.url.path in ("/ws", "/api/health"):
            return await call_next(request)

        # Check Authorization header
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode("utf-8")
                user, passwd = decoded.split(":", 1)
                if secrets.compare_digest(user, self._username) and secrets.compare_digest(passwd, self._password):
                    return await call_next(request)
            except Exception:
                pass

        # Return 401 with WWW-Authenticate header
        return Response(
            content="Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="AICOS Dashboard"'},
        )


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def create_app(shared_state: Any | None = None, orchestrator: Any | None = None) -> FastAPI:
    """Create and return the FastAPI application.

    Args:
        shared_state: A ``SharedState`` instance for in-memory mode.
        orchestrator: An ``Orchestrator`` instance for workflow execution.
    """
    application = FastAPI(title="AICOS Dashboard", version="3.0.0")

    # Add auth middleware if credentials are configured
    dash_user = os.getenv("AICOS_DASHBOARD_USER", "")
    dash_pass = os.getenv("AICOS_DASHBOARD_PASS", "")
    if dash_user and dash_pass:
        application.add_middleware(AuthMiddleware, username=dash_user, password=dash_pass)

    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    tpl = Jinja2Templates(directory=str(TEMPLATES_DIR))

    application.state.shared = shared_state
    application.state.orchestrator = orchestrator
    application.state.ws_clients: list[WebSocket] = []
    application.state.fallback_config: dict[str, Any] = {}
    application.state.fallback_agents: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    @application.on_event("startup")
    async def startup() -> None:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                application.state.fallback_config = yaml.safe_load(fh) or {}
        _seed_fallback_agents(application)

        if shared_state is not None:
            shared_state.add_observer(_ws_push_observer(application))

    def _ws_push_observer(app: FastAPI):
        async def observer(event: str, payload: dict[str, Any]) -> None:
            data = json.dumps({"type": event, **payload}, default=str)
            disconnected: list[WebSocket] = []
            for ws in app.state.ws_clients:
                try:
                    await ws.send_text(data)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                app.state.ws_clients.remove(ws)
        return observer

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    @application.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        if shared_state is not None:
            company_name = shared_state.company_name
        else:
            live = _read_file_state()
            company_name = live.get("company", "NEXUS AI") if live else application.state.fallback_config.get("company", {}).get("name", "AICOS")
        return tpl.TemplateResponse("index.html", {"request": request, "company_name": company_name})

    # ------------------------------------------------------------------
    # REST API
    # ------------------------------------------------------------------

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/agents")
    async def list_agents() -> list[dict[str, Any]]:
        if shared_state is not None:
            agents = shared_state.get_agents()
            for a in agents:
                a.setdefault("color", ROLE_COLORS.get(a.get("role", ""), "#888"))
            return agents
        live = _read_file_state()
        if live and live.get("agents"):
            for a in live["agents"]:
                a["color"] = ROLE_COLORS.get(a.get("role", ""), "#888")
            return live["agents"]
        return list(application.state.fallback_agents.values())

    @application.get("/api/tasks")
    async def list_tasks() -> list[dict[str, Any]]:
        if shared_state is not None:
            from core.state import _task_to_dict
            return [_task_to_dict(t) for t in shared_state.tasks.values()]
        live = _read_file_state()
        if live and "tasks" in live:
            return live["tasks"]
        return []

    @application.post("/api/tasks")
    async def create_task(body: TaskCreateModel) -> dict[str, Any]:
        task = Task(
            title=body.title,
            description=body.description,
            assigned_to=body.assigned_to,
            priority=TaskPriority(body.priority),
            created_by="DASHBOARD",
            dependencies=body.dependencies,
        )
        if shared_state is not None:
            shared_state.add_task(task)
            await shared_state._notify("task_created", {"task_id": task.id})
        else:
            _write_task_to_inbox(body)
        from core.state import _task_to_dict
        return _task_to_dict(task)

    @application.get("/api/messages")
    async def list_messages() -> list[dict[str, Any]]:
        if shared_state is not None:
            from core.state import _message_to_dict
            return [_message_to_dict(m) for m in shared_state.get_messages()]
        live = _read_file_state()
        if live and live.get("messages"):
            return live["messages"]
        return []

    @application.get("/api/kpis")
    async def list_kpis() -> list[dict[str, Any]]:
        if shared_state is not None:
            from core.state import _kpi_to_dict
            return [_kpi_to_dict(k) for k in shared_state.get_kpis()]
        live = _read_file_state()
        if live and live.get("kpis"):
            return live["kpis"]
        return []

    @application.get("/api/config")
    async def get_config() -> dict[str, Any]:
        return application.state.fallback_config

    @application.get("/api/status")
    async def get_status() -> dict[str, Any]:
        if shared_state is not None:
            return {
                "live": True,
                "company": shared_state.company_name,
                "updated_at": datetime.utcnow().isoformat(),
                "agent_count": len(shared_state.agents),
                "task_count": len(shared_state.tasks),
                "message_count": len(shared_state.messages),
            }
        live = _read_file_state()
        is_live = _is_file_live(live)
        return {
            "live": is_live,
            "company": live.get("company", "unknown") if live else "unknown",
            "updated_at": live.get("updated_at") if live else None,
            "agent_count": len(live["agents"]) if live and live.get("agents") else len(application.state.fallback_agents),
            "task_count": len(live["tasks"]) if live and "tasks" in live else 0,
            "message_count": len(live["messages"]) if live and live.get("messages") else 0,
        }

    # ------------------------------------------------------------------
    # Workflow API
    # ------------------------------------------------------------------

    @application.get("/api/workflows")
    async def list_workflows() -> list[str]:
        from workflows.engine import list_available_workflows
        return list_available_workflows()

    @application.post("/api/workflows/run")
    async def run_workflow(body: WorkflowRunModel) -> dict[str, Any]:
        orch = application.state.orchestrator
        if orch is None:
            raise HTTPException(status_code=503, detail="Orchestrator not available")
        result = await orch.execute_workflow(body.workflow_name, body.context)
        return result

    # ------------------------------------------------------------------
    # Reports API
    # ------------------------------------------------------------------

    @application.get("/api/reports")
    async def list_reports() -> list[dict[str, Any]]:
        if not LOGS_DIR.exists():
            return []
        reports: list[dict[str, Any]] = []
        for fp in sorted(LOGS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if fp.is_file() and fp.name != "conversation_snapshot.json":
                stat = fp.stat()
                reports.append({
                    "filename": fp.name,
                    "size": stat.st_size,
                    "modified": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                    "extension": fp.suffix,
                })
        return reports

    @application.get("/api/reports/{filename}")
    async def get_report(filename: str) -> dict[str, Any]:
        safe_name = Path(filename).name
        fp = LOGS_DIR / safe_name
        if not fp.exists() or not fp.is_file():
            raise HTTPException(status_code=404, detail="Report not found")
        content = fp.read_text(encoding="utf-8", errors="replace")
        return {"filename": safe_name, "content": content, "size": fp.stat().st_size,
                "modified": datetime.utcfromtimestamp(fp.stat().st_mtime).isoformat()}

    @application.get("/api/activity-feed")
    async def get_activity_feed() -> list[dict[str, Any]]:
        if shared_state is not None:
            return shared_state.get_activity_feed(200)
        return []

    @application.get("/api/activity")
    async def get_activity() -> list[dict[str, Any]]:
        if not LOGS_DIR.exists():
            return []
        entries: list[dict[str, Any]] = []
        for fp in sorted(LOGS_DIR.glob("comms_*.jsonl"), reverse=True):
            for line in fp.read_text(encoding="utf-8").strip().splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries[:200]

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    @application.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        application.state.ws_clients.append(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    if payload.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            if websocket in application.state.ws_clients:
                application.state.ws_clients.remove(websocket)

    return application


# ---------------------------------------------------------------------------
# Legacy file-based state reader
# ---------------------------------------------------------------------------

_file_cache: dict[str, Any] = {}
_file_cache_ts: float = 0.0


def _read_file_state() -> dict[str, Any] | None:
    global _file_cache, _file_cache_ts
    import time
    now = time.time()
    if _file_cache and (now - _file_cache_ts) < 1.0:
        return _file_cache
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            _file_cache = data
            _file_cache_ts = now
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return _file_cache if _file_cache else None


def _is_file_live(live: dict[str, Any] | None) -> bool:
    if not live:
        return False
    updated = live.get("updated_at", "")
    try:
        ts = datetime.fromisoformat(updated)
        return (datetime.utcnow() - ts).total_seconds() < 30
    except (ValueError, TypeError):
        return False


def _write_task_to_inbox(body: Any) -> None:
    try:
        TASK_INBOX.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict[str, Any]] = []
        if TASK_INBOX.exists():
            raw = TASK_INBOX.read_text(encoding="utf-8").strip()
            if raw:
                existing = json.loads(raw)
                if not isinstance(existing, list):
                    existing = []
        existing.append({
            "title": body.title, "description": body.description,
            "assigned_to": body.assigned_to, "priority": body.priority,
            "created_by": "DASHBOARD",
        })
        TASK_INBOX.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _seed_fallback_agents(application: FastAPI) -> None:
    agents_cfg = application.state.fallback_config.get("agents", {})
    for role_key, cfg in agents_cfg.items():
        enabled = cfg if isinstance(cfg, bool) else cfg.get("enabled", True)
        model = cfg.get("model", "claude-sonnet-4-5-20250929") if isinstance(cfg, dict) else "claude-sonnet-4-5-20250929"
        name = role_key.upper()
        application.state.fallback_agents[name] = {
            "name": name, "role": role_key, "model": model,
            "enabled": enabled, "status": "idle" if enabled else "disabled",
            "current_task": None, "tasks_completed": 0,
            "color": ROLE_COLORS.get(role_key, "#888888"),
        }


# Standalone entry: `uvicorn dashboard.app:app`
app = create_app(shared_state=None)
