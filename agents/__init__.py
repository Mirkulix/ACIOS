"""AICOS Agents: Base agent and specialized AI employee roles."""

from agents.base import BaseAgent, TaskResult
from agents.roles.ceo_agent import CEOAgent
from agents.roles.cfo_agent import CFOAgent
from agents.roles.cto_agent import CTOAgent
from agents.roles.sales_agent import SalesAgent
from agents.roles.marketing_agent import MarketingAgent
from agents.roles.support_agent import SupportAgent
from agents.roles.operations_agent import OperationsAgent
from agents.roles.developer_agent import DeveloperAgent
from agents.roles.hr_agent import HRAgent
from core.models import AgentRole

# Mapping from AgentRole enum to the concrete agent class.
ROLE_AGENT_MAP: dict[AgentRole, type[BaseAgent]] = {
    AgentRole.CEO: CEOAgent,
    AgentRole.CFO: CFOAgent,
    AgentRole.CTO: CTOAgent,
    AgentRole.SALES: SalesAgent,
    AgentRole.MARKETING: MarketingAgent,
    AgentRole.SUPPORT: SupportAgent,
    AgentRole.OPERATIONS: OperationsAgent,
    AgentRole.DEVELOPER: DeveloperAgent,
    AgentRole.HR: HRAgent,
}

__all__ = [
    "BaseAgent",
    "TaskResult",
    "CEOAgent",
    "CFOAgent",
    "CTOAgent",
    "SalesAgent",
    "MarketingAgent",
    "SupportAgent",
    "OperationsAgent",
    "DeveloperAgent",
    "HRAgent",
    "ROLE_AGENT_MAP",
]
