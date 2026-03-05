"""AICOS Email Integration: Send emails via SMTP with template support."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in email templates
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, str]] = {
    "welcome": {
        "subject": "Welcome to {company_name}!",
        "body": (
            "Hi {name},\n\n"
            "Welcome aboard! We're thrilled to have you as part of {company_name}.\n\n"
            "If you have any questions, don't hesitate to reach out.\n\n"
            "Best regards,\n"
            "{company_name} Team"
        ),
    },
    "invoice": {
        "subject": "Invoice #{invoice_number} from {company_name}",
        "body": (
            "Hi {name},\n\n"
            "Please find below the details for Invoice #{invoice_number}:\n\n"
            "Amount: {amount}\n"
            "Due Date: {due_date}\n\n"
            "Thank you for your business.\n\n"
            "Best regards,\n"
            "{company_name} Team"
        ),
    },
    "notification": {
        "subject": "[{company_name}] {notification_title}",
        "body": (
            "Hi {name},\n\n"
            "{notification_body}\n\n"
            "Best regards,\n"
            "{company_name} Team"
        ),
    },
}


class EmailIntegration(BaseIntegration):
    """SMTP-based email integration for AICOS agents.

    Config keys::

        smtp_host: str          (default "smtp.gmail.com")
        smtp_port: int          (default 587)
        smtp_user: str          (required)
        smtp_password: str      (required)
        use_tls: bool           (default True)
        from_address: str       (falls back to smtp_user)
        company_name: str       (used in templates)
    """

    name = "email"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._host: str = self.config.get("smtp_host", "smtp.gmail.com")
        self._port: int = int(self.config.get("smtp_port", 587))
        self._user: str = self.config.get("smtp_user", "")
        self._password: str = self.config.get("smtp_password", "")
        self._use_tls: bool = self.config.get("use_tls", True)
        self._from: str = self.config.get("from_address", self._user)
        self._company: str = self.config.get("company_name", "AICOS Company")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Validate SMTP credentials by opening and immediately closing a connection."""
        if not self._user or not self._password:
            logger.warning("Email integration: SMTP credentials not configured.")
            self._connected = False
            return
        try:
            await asyncio.to_thread(self._test_connection)
            self._connected = True
            logger.info("Email integration connected (%s:%d)", self._host, self._port)
        except Exception as exc:
            self._connected = False
            logger.error("Email integration connection failed: %s", exc)

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("Email integration disconnected.")

    # ------------------------------------------------------------------
    # Execute dispatcher
    # ------------------------------------------------------------------

    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        actions = {
            "send_email": self._action_send_email,
            "send_template": self._action_send_template,
            "list_templates": self._action_list_templates,
        }
        handler = actions.get(action)
        if handler is None:
            raise ValueError(f"Unknown email action: {action!r}. Available: {list(actions)}")
        return await handler(params)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _action_send_email(self, params: dict[str, Any]) -> dict[str, Any]:
        to = params["to"]
        subject = params["subject"]
        body = params["body"]
        html = params.get("html")
        await self.send_email(to, subject, body, html=html)
        return {"status": "sent", "to": to, "subject": subject}

    async def _action_send_template(self, params: dict[str, Any]) -> dict[str, Any]:
        template_name = params["template"]
        to = params["to"]
        variables = params.get("variables", {})
        variables.setdefault("company_name", self._company)

        tpl = TEMPLATES.get(template_name)
        if tpl is None:
            raise ValueError(f"Unknown template: {template_name!r}. Available: {list(TEMPLATES)}")

        subject = tpl["subject"].format_map(variables)
        body = tpl["body"].format_map(variables)
        await self.send_email(to, subject, body)
        return {"status": "sent", "to": to, "template": template_name, "subject": subject}

    async def _action_list_templates(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"templates": list(TEMPLATES.keys())}

    # ------------------------------------------------------------------
    # Core send
    # ------------------------------------------------------------------

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
    ) -> None:
        """Send a single email. Runs the blocking SMTP calls in a thread."""
        msg = MIMEMultipart("alternative")
        msg["From"] = self._from
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))

        await asyncio.to_thread(self._smtp_send, to, msg)
        logger.info("Email sent to %s: %s", to, subject)

    # ------------------------------------------------------------------
    # Internals (blocking, run via to_thread)
    # ------------------------------------------------------------------

    def _smtp_send(self, to: str, msg: MIMEMultipart) -> None:
        ctx = ssl.create_default_context() if self._use_tls else None
        with smtplib.SMTP(self._host, self._port) as server:
            if self._use_tls and ctx is not None:
                server.starttls(context=ctx)
            if self._user and self._password:
                server.login(self._user, self._password)
            server.sendmail(self._from, to, msg.as_string())

    def _test_connection(self) -> None:
        ctx = ssl.create_default_context() if self._use_tls else None
        with smtplib.SMTP(self._host, self._port, timeout=10) as server:
            if self._use_tls and ctx is not None:
                server.starttls(context=ctx)
            if self._user and self._password:
                server.login(self._user, self._password)
