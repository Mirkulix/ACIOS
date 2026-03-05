"""AICOS Integrations: External service connectors."""

from integrations.base import BaseIntegration
from integrations.crm import CRMIntegration
from integrations.email_integration import EmailIntegration
from integrations.manager import IntegrationManager

__all__ = [
    "BaseIntegration",
    "CRMIntegration",
    "EmailIntegration",
    "IntegrationManager",
]
