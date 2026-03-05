"""AICOS Main Entry Point: Boots the AI company in a single unified process.

One command — `python main.py` — starts everything:
  1. SharedState singleton
  2. Orchestrator (with all agents)
  3. Web Dashboard (FastAPI + Uvicorn)

No file sync, no two-process coordination. Everything shares memory.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

console = Console()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger("aicos")


# ---------------------------------------------------------------------------
# Boot sequence
# ---------------------------------------------------------------------------

class CompanyRuntime:
    """Manages the lifecycle of an AICOS company instance."""

    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._orchestrator = None

    async def start(self, start_dashboard: bool = True) -> None:
        """Boot all components in a single process."""
        from core.orchestrator import Orchestrator
        from core.persistence import Persistence
        from core.state import SharedState

        # 1. Create the shared state singleton
        shared_state = SharedState()

        # 2. Initialize SQLite persistence and restore saved tasks
        self._persistence = Persistence()
        self._persistence.connect()
        saved_tasks = self._persistence.load_tasks()
        for task in saved_tasks:
            shared_state.add_task(task)
        if saved_tasks:
            logger.info("Restored %d tasks from database", len(saved_tasks))

        saved_kpis = self._persistence.load_kpis()
        for kpi in saved_kpis:
            shared_state.add_kpi(kpi)
        if saved_kpis:
            logger.info("Restored %d KPIs from database", len(saved_kpis))

        # Register persistence observer (auto-saves on changes)
        shared_state.add_observer(self._persistence.on_state_change)

        # 3. Initialize and boot the Orchestrator (shares the same state)
        orchestrator = Orchestrator(shared_state=shared_state)
        orchestrator.load_config(self.config_path)
        booted = orchestrator.boot_company()
        self._orchestrator = orchestrator

        # 4. Start IntegrationManager (CRM, Email) and inject into Orchestrator
        await self._start_integrations(orchestrator)

        logger.info("Booted %d agents: %s", len(booted), ", ".join(booted))

        # 5. Start the Orchestrator main loop
        orch_task = asyncio.create_task(orchestrator.run(), name="orchestrator")
        self._tasks.append(orch_task)

        # 6. Start the Dashboard (same process, same SharedState)
        if start_dashboard:
            await self._start_dashboard(shared_state, orchestrator)

        # 7. Print status
        self._print_status(booted, start_dashboard)

        # Wait for shutdown signal
        await self._shutdown_event.wait()
        await self.shutdown()

    async def _start_integrations(self, orchestrator) -> None:
        """Start CRM, Email, and other integrations."""
        try:
            from integrations.manager import IntegrationManager
            self._integration_manager = IntegrationManager(config={
                "crm": {"enabled": True, "db_path": "data/crm.db"},
                "email": {"enabled": False},  # Enable when SMTP configured
            })
            await self._integration_manager.start()
            orchestrator.set_integration_manager(self._integration_manager)
            logger.info("Integrations started (CRM: active)")
        except Exception as exc:
            logger.warning("Could not start integrations: %s", exc)

    async def _start_dashboard(self, shared_state, orchestrator=None) -> None:
        """Start the web dashboard as an async task in the same process."""
        try:
            import uvicorn
            from dashboard.app import create_app

            dash_app = create_app(shared_state=shared_state, orchestrator=orchestrator)

            host = os.getenv("AICOS_DASHBOARD_HOST", "0.0.0.0")
            port = int(os.getenv("AICOS_DASHBOARD_PORT", "8080"))

            config = uvicorn.Config(
                dash_app,
                host=host,
                port=port,
                log_level="warning",
            )
            server = uvicorn.Server(config)
            task = asyncio.create_task(server.serve(), name="dashboard")
            self._tasks.append(task)
            logger.info("Dashboard started on http://%s:%s", host, port)
        except ImportError as exc:
            logger.warning("Dashboard dependencies missing: %s", exc)
        except Exception as exc:
            logger.warning("Could not start dashboard: %s", exc)

    async def shutdown(self) -> None:
        """Gracefully shut down all components."""
        logger.info("Initiating graceful shutdown...")

        if self._orchestrator is not None:
            self._orchestrator.shutdown()

        # Close integrations
        if hasattr(self, "_integration_manager") and self._integration_manager:
            await self._integration_manager.stop()

        # Close persistence
        if hasattr(self, "_persistence") and self._persistence:
            self._persistence.close()

        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("Shutdown complete.")

    def request_shutdown(self) -> None:
        """Signal the runtime to shut down."""
        self._shutdown_event.set()

    def _print_status(self, booted_agents: list[str], dashboard: bool) -> None:
        cfg = self._orchestrator.config
        enabled = sum(1 for a in cfg.agents.values() if a.enabled) if cfg else 0
        lines = [
            f"[bold]{cfg.company.name if cfg else 'AICOS'}[/bold]",
            f"[dim]Type: {cfg.company.type if cfg else 'unknown'}[/dim]",
            f"",
            f"Agents online: [green]{len(booted_agents)}[/green] / {enabled} enabled",
            f"Orchestrator:  [green]active[/green]",
            f"Dashboard:     [green]{'active' if dashboard else 'disabled'}[/green]",
            f"Architecture:  [cyan]Unified Single-Process[/cyan]",
        ]
        console.print(Panel(
            "\n".join(lines),
            title="[bold cyan]AICOS Company Running[/bold cyan]",
            border_style="cyan",
        ))


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

async def boot(config_path: str = "config/company.yaml", start_dashboard: bool = True) -> None:
    """Main async entry point."""
    load_dotenv()

    config_path = os.getenv("AICOS_COMPANY_CONFIG", config_path)
    runtime = CompanyRuntime(config_path)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, runtime.request_shutdown)

    await runtime.start(start_dashboard=start_dashboard)


def main() -> None:
    """Synchronous entry point: ``python main.py``."""
    parser = argparse.ArgumentParser(description="AICOS - AI Company OS")
    parser.add_argument(
        "--config", "-c",
        default="config/company.yaml",
        help="Path to company YAML config (default: config/company.yaml)",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Do not start the web dashboard",
    )
    args = parser.parse_args()

    console.print(Panel(
        "[bold cyan]AICOS - AI Company OS[/bold cyan]\n"
        "[dim]Starting your AI-powered company...[/dim]",
        border_style="cyan",
    ))

    try:
        asyncio.run(boot(config_path=args.config, start_dashboard=not args.no_dashboard))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Goodbye.[/yellow]")


if __name__ == "__main__":
    main()
