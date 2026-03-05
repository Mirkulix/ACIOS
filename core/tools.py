"""AICOS Tool System: Defines executable tools for AI agents.

Each tool has:
  - An Anthropic API schema (for the LLM to decide when to call it)
  - A handler function (actually executes the action)

Tools bridge agents to real actions: creating tasks, querying CRM,
sending emails, storing knowledge, and more.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger("aicos.tools")

# Task explosion safeguards
MAX_DELEGATIONS_PER_TASK = 3  # max delegate_task calls per agent per task execution
MAX_DELEGATION_DEPTH = 3       # max chain depth: A delegates to B delegates to C


# ---------------------------------------------------------------------------
# Tool schemas (Anthropic tool_use format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "delegate_task": {
        "name": "delegate_task",
        "description": "Create a new task and assign it to another agent. Use this when work should be delegated to a specialist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title for the task"},
                "description": {"type": "string", "description": "Detailed description of what needs to be done"},
                "assign_to": {"type": "string", "description": "Agent role to assign to: ceo, cfo, cto, sales, marketing, support, operations, developer, hr"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "Task priority"},
            },
            "required": ["title", "description", "assign_to"],
        },
    },
    "send_message": {
        "name": "send_message",
        "description": "Send a message to another agent for collaboration or information sharing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to_agent": {"type": "string", "description": "Name of the receiving agent"},
                "content": {"type": "string", "description": "Message content"},
            },
            "required": ["to_agent", "content"],
        },
    },
    "store_knowledge": {
        "name": "store_knowledge",
        "description": "Save an important fact or decision to company memory for future reference.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short key name (e.g. 'q1_revenue_target')"},
                "value": {"type": "string", "description": "The information to store"},
                "scope": {"type": "string", "description": "Scope: 'company' for shared, or agent name for private", "default": "company"},
            },
            "required": ["key", "value"],
        },
    },
    "retrieve_knowledge": {
        "name": "retrieve_knowledge",
        "description": "Search company memory for stored facts and decisions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query to find relevant knowledge"},
            },
            "required": ["query"],
        },
    },
    "crm_add_contact": {
        "name": "crm_add_contact",
        "description": "Add a new contact to the CRM system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Contact full name"},
                "email": {"type": "string", "description": "Contact email address"},
                "company": {"type": "string", "description": "Company name"},
                "notes": {"type": "string", "description": "Additional notes"},
            },
            "required": ["name"],
        },
    },
    "crm_search_contacts": {
        "name": "crm_search_contacts",
        "description": "Search for contacts in the CRM by name, email, or company.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
            },
            "required": ["query"],
        },
    },
    "crm_add_deal": {
        "name": "crm_add_deal",
        "description": "Create a new deal in the CRM pipeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "integer", "description": "ID of the contact for this deal"},
                "title": {"type": "string", "description": "Deal title"},
                "value": {"type": "number", "description": "Deal value in EUR"},
                "stage": {"type": "string", "enum": ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]},
            },
            "required": ["contact_id", "title"],
        },
    },
    "crm_get_pipeline": {
        "name": "crm_get_pipeline",
        "description": "Get the full sales pipeline with all deals grouped by stage.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "crm_update_deal_stage": {
        "name": "crm_update_deal_stage",
        "description": "Move a deal to a different pipeline stage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "integer", "description": "Deal ID"},
                "stage": {"type": "string", "enum": ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]},
            },
            "required": ["deal_id", "stage"],
        },
    },
    "send_email": {
        "name": "send_email",
        "description": "Send an email to a recipient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body text"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    "track_kpi": {
        "name": "track_kpi",
        "description": "Record a KPI measurement for tracking business metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "KPI name (e.g. 'monthly_revenue', 'customer_satisfaction')"},
                "value": {"type": "number", "description": "Current value"},
                "target": {"type": "number", "description": "Target value"},
            },
            "required": ["name", "value"],
        },
    },
    "run_workflow": {
        "name": "run_workflow",
        "description": "Trigger a multi-step workflow (e.g. client_onboarding, project_delivery).",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_name": {"type": "string", "description": "Name of the workflow to run"},
                "context": {"type": "object", "description": "Optional context data to pass to the workflow"},
            },
            "required": ["workflow_name"],
        },
    },
    # ----- Collaboration tools (available to ALL agents) -----
    "get_agent_status": {
        "name": "get_agent_status",
        "description": "See the current status of all agents in the company (who is busy, idle, what they're working on). Use this before delegating to check workload.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "list_active_tasks": {
        "name": "list_active_tasks",
        "description": "List all active tasks (pending and in-progress) to understand current company workload and avoid duplicates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {"type": "string", "enum": ["pending", "in_progress", "completed", "all"], "description": "Filter by status (default: all active)"},
            },
        },
    },
    "get_task_result": {
        "name": "get_task_result",
        "description": "Get the result of a completed task by its ID. Use this to build on work done by other agents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task ID to look up"},
            },
            "required": ["task_id"],
        },
    },
}

# Collaboration tools every agent gets
_COLLAB_TOOLS = ["get_agent_status", "list_active_tasks", "get_task_result"]

# Map which tools each role has access to (beyond the universal tools)
ROLE_TOOL_MAP: dict[str, list[str]] = {
    "ceo": ["delegate_task", "send_message", "store_knowledge", "retrieve_knowledge", "track_kpi", "run_workflow"] + _COLLAB_TOOLS,
    "cfo": ["delegate_task", "send_message", "store_knowledge", "retrieve_knowledge", "track_kpi", "send_email"] + _COLLAB_TOOLS,
    "cto": ["delegate_task", "send_message", "store_knowledge", "retrieve_knowledge", "track_kpi", "run_workflow"] + _COLLAB_TOOLS,
    "sales": ["send_message", "store_knowledge", "retrieve_knowledge", "crm_add_contact", "crm_search_contacts", "crm_add_deal", "crm_get_pipeline", "crm_update_deal_stage", "track_kpi", "send_email"] + _COLLAB_TOOLS,
    "marketing": ["send_message", "store_knowledge", "retrieve_knowledge", "track_kpi", "send_email", "crm_search_contacts"] + _COLLAB_TOOLS,
    "support": ["send_message", "store_knowledge", "retrieve_knowledge", "crm_search_contacts", "track_kpi", "send_email", "delegate_task"] + _COLLAB_TOOLS,
    "operations": ["delegate_task", "send_message", "store_knowledge", "retrieve_knowledge", "track_kpi", "run_workflow"] + _COLLAB_TOOLS,
    "developer": ["send_message", "store_knowledge", "retrieve_knowledge", "track_kpi", "delegate_task"] + _COLLAB_TOOLS,
    "hr": ["send_message", "store_knowledge", "retrieve_knowledge", "track_kpi", "send_email", "crm_add_contact"] + _COLLAB_TOOLS,
}


def get_tools_for_role(role: str) -> list[dict[str, Any]]:
    """Return the Anthropic tool schemas available to a specific agent role."""
    tool_names = ROLE_TOOL_MAP.get(role.lower(), ["send_message", "store_knowledge", "retrieve_knowledge"])
    return [TOOL_SCHEMAS[name] for name in tool_names if name in TOOL_SCHEMAS]


# ---------------------------------------------------------------------------
# Tool Executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Executes tool calls dispatched from the Orchestrator's LLM loop.

    Bridges tool invocations to SharedState, IntegrationManager, Memory, etc.
    """

    def __init__(
        self,
        shared_state: Any = None,
        memory: Any = None,
        comm_bus: Any = None,
        integration_manager: Any = None,
    ) -> None:
        self._state = shared_state
        self._memory = memory
        self._bus = comm_bus
        self._integrations = integration_manager

        # Track delegation counts per agent to prevent task explosion
        # Key: agent_name, Value: number of delegate_task calls in current execution
        self._delegation_counts: defaultdict[str, int] = defaultdict(int)

    async def execute(self, tool_name: str, tool_input: dict[str, Any], agent_name: str = "") -> str:
        """Execute a tool and return the result as a string."""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            result = await handler(tool_input, agent_name)
            return json.dumps(result, default=str, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def reset_delegation_count(self, agent_name: str) -> None:
        """Reset the delegation counter for an agent (called when task execution starts)."""
        self._delegation_counts[agent_name] = 0

    async def _tool_delegate_task(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        from core.models import Task, TaskPriority, TaskStatus

        # --- Safeguard 1: Per-agent delegation limit per task execution ---
        self._delegation_counts[agent_name] += 1
        if self._delegation_counts[agent_name] > MAX_DELEGATIONS_PER_TASK:
            return {
                "error": f"Delegation limit reached ({MAX_DELEGATIONS_PER_TASK} per task). "
                "Complete your current work instead of delegating further.",
            }

        # --- Safeguard 2: Global task queue backpressure ---
        if self._state:
            pending = len(self._state.list_tasks(TaskStatus.PENDING))
            in_progress = len(self._state.list_tasks(TaskStatus.IN_PROGRESS))
            if pending + in_progress >= 50:
                return {
                    "error": f"Task queue is full ({pending} pending + {in_progress} in-progress). "
                    "Wait for existing tasks to complete before creating new ones.",
                }

        # --- Safeguard 3: Prevent self-delegation loops ---
        role_to_name = {}
        if self._state:
            for a in self._state.get_agents():
                role_to_name[a.get("role", "")] = a.get("name", "")

        assign_to = params.get("assign_to", "")
        resolved_name = role_to_name.get(assign_to.lower(), assign_to.upper())

        if resolved_name == agent_name:
            return {
                "error": "Cannot delegate a task to yourself. Either complete it directly or assign to a different agent.",
            }

        task = Task(
            title=params["title"],
            description=params.get("description", ""),
            assigned_to=resolved_name,
            created_by=agent_name,
            priority=TaskPriority(params.get("priority", "medium")),
        )
        if self._state:
            self._state.add_task(task)
            await self._state._notify("task_created", {"task_id": task.id})
        return {"status": "created", "task_id": task.id, "assigned_to": resolved_name}

    async def _tool_send_message(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._bus:
            await self._bus.send(agent_name, params["to_agent"], params["content"])
        return {"status": "sent", "to": params["to_agent"]}

    async def _tool_store_knowledge(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        scope = params.get("scope", "company")
        if self._memory:
            self._memory.store(params["key"], params["value"], scope=scope)
        return {"status": "stored", "key": params["key"], "scope": scope}

    async def _tool_retrieve_knowledge(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._memory:
            results = self._memory.search(params["query"])
            return {"results": results[:10]}
        return {"results": []}

    async def _tool_crm_add_contact(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._integrations:
            try:
                return await self._integrations.execute("crm", "add_contact", params)
            except Exception as exc:
                return {"error": f"CRM not available: {exc}"}
        return {"error": "CRM integration not configured"}

    async def _tool_crm_search_contacts(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._integrations:
            try:
                return await self._integrations.execute("crm", "search_contacts", params)
            except Exception as exc:
                return {"error": f"CRM not available: {exc}"}
        return {"error": "CRM integration not configured"}

    async def _tool_crm_add_deal(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._integrations:
            try:
                return await self._integrations.execute("crm", "add_deal", params)
            except Exception as exc:
                return {"error": f"CRM not available: {exc}"}
        return {"error": "CRM integration not configured"}

    async def _tool_crm_get_pipeline(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._integrations:
            try:
                return await self._integrations.execute("crm", "get_pipeline", {})
            except Exception as exc:
                return {"error": f"CRM not available: {exc}"}
        return {"error": "CRM integration not configured"}

    async def _tool_crm_update_deal_stage(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._integrations:
            try:
                return await self._integrations.execute("crm", "update_deal_stage", params)
            except Exception as exc:
                return {"error": f"CRM not available: {exc}"}
        return {"error": "CRM integration not configured"}

    async def _tool_send_email(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if self._integrations:
            try:
                return await self._integrations.execute("email", "send_email", params)
            except Exception as exc:
                return {"error": f"Email not available: {exc}"}
        return {"error": "Email integration not configured"}

    async def _tool_track_kpi(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        from core.models import KPI, AgentRole
        if self._state:
            # Try to resolve agent role
            role = None
            for a in self._state.get_agents():
                if a.get("name", "") == agent_name:
                    try:
                        role = AgentRole(a.get("role", ""))
                    except ValueError:
                        pass
                    break
            kpi = KPI(
                name=params["name"],
                value=params["value"],
                target=params.get("target", 0.0),
                agent_role=role,
            )
            self._state.add_kpi(kpi)
        return {"status": "tracked", "name": params["name"], "value": params["value"]}

    async def _tool_run_workflow(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        # This will be connected to the WorkflowEngine
        return {"status": "queued", "workflow": params["workflow_name"], "note": "Workflow execution triggered"}

    # ------------------------------------------------------------------
    # Collaboration tools (available to ALL agents)
    # ------------------------------------------------------------------

    async def _tool_get_agent_status(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        """Return the current status of all agents."""
        if not self._state:
            return {"agents": []}
        agents = []
        for a in self._state.get_agents():
            agents.append({
                "name": a.get("name", ""),
                "role": a.get("role", ""),
                "status": a.get("status", "unknown"),
                "current_task": a.get("current_task"),
                "active_tasks": a.get("active_tasks", 0),
                "tasks_completed": a.get("tasks_completed", 0),
            })
        return {"agents": agents}

    async def _tool_list_active_tasks(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        """List tasks filtered by status."""
        if not self._state:
            return {"tasks": []}
        from core.models import TaskStatus
        status_filter = params.get("status_filter", "all")
        tasks = []
        for t in self._state.tasks.values():
            if status_filter == "all":
                include = t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
            elif status_filter == "completed":
                include = t.status == TaskStatus.COMPLETED
            else:
                include = t.status.value == status_filter
            if include:
                tasks.append({
                    "id": t.id,
                    "title": t.title,
                    "assigned_to": t.assigned_to,
                    "created_by": t.created_by,
                    "status": t.status.value,
                    "priority": t.priority.value,
                })
        return {"tasks": tasks[:30]}  # Cap at 30 to avoid huge responses

    async def _tool_get_task_result(self, params: dict[str, Any], agent_name: str) -> dict[str, Any]:
        """Get the result of a specific task."""
        if not self._state:
            return {"error": "State not available"}
        task = self._state.get_task(params["task_id"])
        if task is None:
            return {"error": f"Task {params['task_id']} not found"}
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status.value,
            "assigned_to": task.assigned_to,
            "result": task.result or "(no result yet)",
        }
