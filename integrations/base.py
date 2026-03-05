"""AICOS Integrations: Base class for all external service integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseIntegration(ABC):
    """Abstract base class that every AICOS integration must implement.

    Sub-classes provide ``connect``, ``disconnect``, and ``execute`` methods.
    The integration manager uses ``get_status`` to report health.
    """

    name: str = "base"
    enabled: bool = False
    config: dict[str, Any]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.enabled = self.config.get("enabled", False)
        self._connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Establish a connection to the external service."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully tear down the connection."""

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run an *action* with the given *params* and return the result dict.

        Raises ``ValueError`` if the action is not supported.
        """

    def get_status(self) -> dict[str, Any]:
        """Return a JSON-serialisable status snapshot."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "connected": self._connected,
        }
