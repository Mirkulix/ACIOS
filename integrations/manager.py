"""AICOS Integration Manager: loads, manages, and dispatches all integrations."""

from __future__ import annotations

import logging
from typing import Any

from integrations.base import BaseIntegration
from integrations.crm import CRMIntegration
from integrations.email_integration import EmailIntegration

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry of built-in integrations
# ---------------------------------------------------------------------------

_BUILTIN_INTEGRATIONS: dict[str, type[BaseIntegration]] = {
    "email": EmailIntegration,
    "crm": CRMIntegration,
}


class IntegrationManager:
    """Central manager that loads, initialises, and provides access to all
    AICOS integrations.

    Usage::

        manager = IntegrationManager(config={"email": {...}, "crm": {...}})
        await manager.start()

        crm = manager.get_integration("crm")
        result = await crm.execute("add_contact", {"name": "Alice"})

        await manager.stop()
    """

    def __init__(self, config: dict[str, dict[str, Any]] | None = None) -> None:
        self._config = config or {}
        self._integrations: dict[str, BaseIntegration] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Instantiate and connect every configured integration."""
        for name, cls in _BUILTIN_INTEGRATIONS.items():
            cfg = self._config.get(name, {})
            integration = cls(config=cfg)
            self._integrations[name] = integration

            if integration.enabled:
                try:
                    await integration.connect()
                    logger.info("Integration '%s' started.", name)
                except Exception as exc:
                    logger.error("Integration '%s' failed to start: %s", name, exc)
            else:
                logger.info("Integration '%s' is disabled, skipping connect.", name)

    async def stop(self) -> None:
        """Disconnect every running integration."""
        for name, integration in self._integrations.items():
            try:
                await integration.disconnect()
                logger.info("Integration '%s' stopped.", name)
            except Exception as exc:
                logger.error("Integration '%s' failed to stop: %s", name, exc)

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get_integration(self, name: str) -> BaseIntegration:
        """Return the integration instance by name.

        Raises ``KeyError`` if not found.
        """
        integration = self._integrations.get(name)
        if integration is None:
            raise KeyError(f"Integration not found: {name!r}. Available: {list(self._integrations)}")
        return integration

    def list_integrations(self) -> list[dict[str, Any]]:
        """Return status dicts for every registered integration."""
        return [integ.get_status() for integ in self._integrations.values()]

    # ------------------------------------------------------------------
    # Runtime enable / disable
    # ------------------------------------------------------------------

    async def enable_integration(self, name: str) -> dict[str, Any]:
        """Enable and connect an integration at runtime."""
        integration = self.get_integration(name)
        if integration.enabled and integration._connected:
            return {"status": "already_enabled", "name": name}

        integration.enabled = True
        try:
            await integration.connect()
            logger.info("Integration '%s' enabled at runtime.", name)
            return {"status": "enabled", "name": name}
        except Exception as exc:
            logger.error("Failed to enable integration '%s': %s", name, exc)
            return {"status": "error", "name": name, "error": str(exc)}

    async def disable_integration(self, name: str) -> dict[str, Any]:
        """Disable and disconnect an integration at runtime."""
        integration = self.get_integration(name)
        if not integration.enabled:
            return {"status": "already_disabled", "name": name}

        integration.enabled = False
        try:
            await integration.disconnect()
            logger.info("Integration '%s' disabled at runtime.", name)
            return {"status": "disabled", "name": name}
        except Exception as exc:
            logger.error("Failed to disable integration '%s': %s", name, exc)
            return {"status": "error", "name": name, "error": str(exc)}

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def execute(self, integration_name: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Shorthand to execute an action on a named integration."""
        integration = self.get_integration(integration_name)
        if not integration.enabled:
            raise RuntimeError(f"Integration '{integration_name}' is disabled.")
        return await integration.execute(action, params)
