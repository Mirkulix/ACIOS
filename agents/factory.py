"""AICOS Agent Factory: Creates and wires up AI agent instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.models import AgentConfig, AgentRole, CompanyConfig

if TYPE_CHECKING:
    from agents.base import BaseAgent
    from core.communication import CommunicationBus
    from core.memory import MemoryManager

logger = logging.getLogger("aicos.factory")


# ---------------------------------------------------------------------------
# Role -> Agent class mapping
# ---------------------------------------------------------------------------

def _get_agent_class(role: AgentRole) -> type:
    """Lazily import and return the agent class for a given role.

    Lazy imports avoid circular dependencies and allow individual role
    modules to be loaded only when needed.
    """
    match role:
        case AgentRole.CEO:
            from agents.roles.ceo_agent import CEOAgent
            return CEOAgent
        case AgentRole.CFO:
            from agents.roles.cfo_agent import CFOAgent
            return CFOAgent
        case AgentRole.CTO:
            from agents.roles.cto_agent import CTOAgent
            return CTOAgent
        case AgentRole.SALES:
            from agents.roles.sales_agent import SalesAgent
            return SalesAgent
        case AgentRole.MARKETING:
            from agents.roles.marketing_agent import MarketingAgent
            return MarketingAgent
        case AgentRole.SUPPORT:
            from agents.roles.support_agent import SupportAgent
            return SupportAgent
        case AgentRole.OPERATIONS:
            from agents.roles.operations_agent import OperationsAgent
            return OperationsAgent
        case AgentRole.DEVELOPER:
            from agents.roles.developer_agent import DeveloperAgent
            return DeveloperAgent
        case AgentRole.HR:
            from agents.roles.hr_agent import HRAgent
            return HRAgent
        case _:
            raise ValueError(f"Unknown agent role: {role}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class AgentFactory:
    """Creates agent instances and injects shared dependencies.

    Usage::

        factory = AgentFactory(comm_bus=bus, memory_manager=mm, anthropic_client=client)
        ceo = factory.create_agent(AgentRole.CEO, agent_config)
        all_agents = factory.create_all_agents(company_config)
    """

    def __init__(
        self,
        comm_bus: CommunicationBus | None = None,
        memory_manager: MemoryManager | None = None,
        anthropic_client: Any = None,
    ) -> None:
        self._comm_bus = comm_bus
        self._memory_manager = memory_manager
        self._anthropic_client = anthropic_client

    def create_agent(self, role: AgentRole, config: AgentConfig) -> BaseAgent:
        """Create a single agent instance for the given role.

        Args:
            role:   The AgentRole enum value.
            config: Agent-specific configuration (model, tools, etc.).

        Returns:
            A fully initialized BaseAgent subclass instance.
        """
        agent_cls = _get_agent_class(role)

        agent = agent_cls(
            config=config,
            comm_bus=self._comm_bus,
            memory_manager=self._memory_manager,
            anthropic_client=self._anthropic_client,
        )

        # Register with the communication bus
        if self._comm_bus is not None:
            self._comm_bus.register_agent(config.name)

        logger.info("Created agent: %s (role=%s, model=%s)", config.name, role.value, config.model)
        return agent

    def create_all_agents(self, company_config: CompanyConfig) -> dict[str, BaseAgent]:
        """Create all enabled agents defined in the company configuration.

        Args:
            company_config: The full company configuration.

        Returns:
            Dict mapping agent name to agent instance.
        """
        agents: dict[str, BaseAgent] = {}

        for agent_name, agent_cfg in company_config.agents.items():
            if not agent_cfg.enabled:
                logger.info("Skipping disabled agent: %s", agent_name)
                continue

            try:
                role = AgentRole(agent_cfg.role) if isinstance(agent_cfg.role, str) else agent_cfg.role
            except ValueError:
                logger.warning("Unknown role '%s' for agent '%s', skipping", agent_cfg.role, agent_name)
                continue

            # Ensure the config has a name set
            if not agent_cfg.name:
                agent_cfg.name = agent_name

            agent = self.create_agent(role, agent_cfg)
            agents[agent_name] = agent

        logger.info("Created %d agents out of %d configured", len(agents), len(company_config.agents))
        return agents
