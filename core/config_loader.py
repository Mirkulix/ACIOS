"""AICOS Config Loader: YAML-based company configuration."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from core.models import AgentConfig, AgentRole, CompanyConfig, CompanyInfo, OrchestrationSettings

console = Console()

TEMPLATES_DIR = Path("config/templates")

# Default system prompts per role (concise — agents extend them at runtime).
_DEFAULT_PROMPTS: dict[AgentRole, str] = {
    AgentRole.CEO: (
        "You are the CEO of this AI company. You make strategic decisions, "
        "handle escalations, and ensure all departments are aligned. "
        "Delegate work to the right agents and resolve conflicts."
    ),
    AgentRole.CFO: (
        "You are the CFO. You manage budgets, forecasts, invoicing, and "
        "financial KPIs. Provide clear financial guidance to the CEO."
    ),
    AgentRole.CTO: (
        "You are the CTO. You own the technical architecture, code quality, "
        "and technology strategy. Review technical decisions and guide developers."
    ),
    AgentRole.SALES: (
        "You are the Sales lead. You qualify leads, prepare proposals, "
        "negotiate deals, and hand off closed clients to operations."
    ),
    AgentRole.MARKETING: (
        "You are the Marketing lead. You create content, manage campaigns, "
        "track engagement metrics, and generate inbound leads for sales."
    ),
    AgentRole.SUPPORT: (
        "You are the Support lead. You handle customer issues, maintain "
        "the knowledge base, and escalate unresolved problems to the CTO or CEO."
    ),
    AgentRole.OPERATIONS: (
        "You are the Operations manager. You coordinate workflows, "
        "ensure deadlines are met, and optimise internal processes."
    ),
    AgentRole.DEVELOPER: (
        "You are a Software Developer. You write, review, and ship code. "
        "Follow CTO guidance and report blockers to operations."
    ),
    AgentRole.HR: (
        "You are the HR lead. You manage hiring pipelines, onboarding, "
        "team culture, and internal communications."
    ),
}


class ConfigLoader:
    """Load, validate, and merge YAML-based company configurations."""

    def __init__(self, templates_dir: Path | str = TEMPLATES_DIR) -> None:
        self._templates_dir = Path(templates_dir)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_company_config(self, path: str | Path) -> CompanyConfig:
        """Parse a company YAML file into a validated CompanyConfig."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Company config not found: {path}")

        raw = self._read_yaml(path)
        return self._parse_raw_config(raw)

    def load_template(self, template_name: str) -> dict[str, Any]:
        """Load a template YAML by name (without extension)."""
        path = self._templates_dir / f"{template_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")
        return self._read_yaml(path)

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    def merge_configs(self, base: CompanyConfig, override: CompanyConfig) -> CompanyConfig:
        """Deep-merge *override* on top of *base*, returning a new config."""
        base_dict = base.model_dump()
        override_dict = override.model_dump(exclude_defaults=True)
        merged = _deep_merge(base_dict, override_dict)
        return CompanyConfig.model_validate(merged)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_config(config: CompanyConfig) -> bool:
        """Return True if *config* is structurally sound.

        Checks:
        - At least one agent is enabled.
        - A CEO agent exists if escalation is enabled.
        - Every agent has a valid role.
        """
        enabled = [a for a in config.agents.values() if a.enabled]
        if not enabled:
            console.log("[red]Config validation failed:[/] no agents enabled")
            return False

        if config.orchestration.escalation_enabled:
            ceo_present = any(a.role == AgentRole.CEO for a in enabled)
            if not ceo_present:
                console.log("[red]Config validation failed:[/] escalation requires an enabled CEO agent")
                return False

        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a YAML mapping at top level in {path}")
        return data

    def _parse_raw_config(self, raw: dict[str, Any]) -> CompanyConfig:
        """Convert loose YAML structure into a strict CompanyConfig."""
        company_info = CompanyInfo(**(raw.get("company") or {}))

        agents: dict[str, AgentConfig] = {}
        for role_str, agent_data in (raw.get("agents") or {}).items():
            role = AgentRole(role_str)
            if isinstance(agent_data, dict):
                enabled = agent_data.get("enabled", True)
                model = agent_data.get("model", "claude-sonnet-4-5-20250929")
                tools = agent_data.get("tools", [])
                prompt = agent_data.get("system_prompt", _DEFAULT_PROMPTS.get(role, ""))
                name = agent_data.get("name", role_str.upper())
            else:
                enabled = bool(agent_data) if agent_data is not None else True
                model = "claude-sonnet-4-5-20250929"
                tools = []
                prompt = _DEFAULT_PROMPTS.get(role, "")
                name = role_str.upper()

            agents[role_str] = AgentConfig(
                name=name,
                role=role,
                model=model,
                system_prompt=prompt,
                tools=tools,
                enabled=enabled,
            )

        orchestration = OrchestrationSettings(**(raw.get("orchestration") or {}))
        workflows = raw.get("workflows") or []
        focus_kpis = raw.get("focus_kpis") or []

        return CompanyConfig(
            company=company_info,
            agents=agents,
            workflows=workflows,
            focus_kpis=focus_kpis,
            orchestration=orchestration,
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
