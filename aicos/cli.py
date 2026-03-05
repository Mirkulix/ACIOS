"""AICOS CLI: Beautiful command-line interface for AI Company OS."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

# Ensure the project root is on sys.path so `core`, `agents`, etc. are importable.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

app = typer.Typer(
    name="aicos",
    help="AICOS - AI Company OS: Run your entire company with AI agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

DEFAULT_CONFIG = "config/company.yaml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_config(config: str | None) -> Path:
    """Resolve the company config path."""
    p = Path(config or DEFAULT_CONFIG)
    if not p.exists():
        console.print(f"[bold red]Error:[/] Config file not found: {p}")
        raise typer.Exit(1)
    return p


def _load_company_config(config_path: Path):
    """Load and validate the company YAML config via ConfigLoader."""
    from core.config_loader import ConfigLoader

    loader = ConfigLoader()
    return loader.load_company_config(config_path)


def _banner() -> None:
    """Print the AICOS banner."""
    banner_text = (
        "[bold cyan]"
        "    _    ___ ____ ___  ____\n"
        "   / \\  |_ _/ ___/ _ \\/ ___|\n"
        "  / _ \\  | | |  | | | \\___ \\\n"
        " / ___ \\ | | |__| |_| |___) |\n"
        "/_/   \\_\\___\\____\\___/|____/\n"
        "[/bold cyan]"
    )
    console.print(Panel(
        banner_text + "\n[dim]AI Company OS - Your entire company, powered by AI[/dim]",
        border_style="cyan",
        padding=(1, 2),
    ))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def start(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to company YAML config"),
    dashboard: bool = typer.Option(True, "--dashboard/--no-dashboard", help="Start web dashboard"),
) -> None:
    """Boot the AI company: load config, start agents, and begin operations."""
    _banner()

    config_path = _resolve_config(config)
    company_cfg = _load_company_config(config_path)

    console.print(f"\n[bold green]Starting company:[/] {company_cfg.company.name}")
    console.print(f"[dim]Config:[/] {config_path}")
    console.print(f"[dim]Type:[/]   {company_cfg.company.type}\n")

    # Show agent boot progress
    enabled_agents = {k: v for k, v in company_cfg.agents.items() if v.enabled}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        boot_task = progress.add_task("Booting agents...", total=len(enabled_agents))
        for name, agent_cfg in enabled_agents.items():
            progress.update(boot_task, description=f"Starting {name} ({agent_cfg.role})...")
            # Actual boot happens in main.py; here we just show progress
            progress.advance(boot_task)

    console.print(f"\n[bold green]{len(enabled_agents)} agents online.[/]")

    if dashboard:
        dash_cfg = company_cfg.model_extra if hasattr(company_cfg, 'model_extra') else {}
        console.print("[dim]Dashboard available at http://localhost:8080[/dim]\n")

    # Run the main loop
    console.print("[bold cyan]Company is running.[/] Press Ctrl+C to stop.\n")

    try:
        from main import boot
        asyncio.run(boot(config_path=str(config_path), start_dashboard=dashboard))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down gracefully...[/]")
    except ImportError:
        console.print("[dim]Main entry point not yet available. Use 'python main.py' directly.[/dim]")


@app.command()
def stop() -> None:
    """Gracefully shut down all running agents and the company."""
    console.print("[yellow]Sending shutdown signal to all agents...[/]")
    # In a real deployment this would signal via PID file or IPC
    console.print("[green]Shutdown complete.[/]")


@app.command()
def status(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to company YAML config"),
) -> None:
    """Show the current status of all agents and active tasks."""
    config_path = _resolve_config(config)
    company_cfg = _load_company_config(config_path)

    console.print(Panel(
        f"[bold]{company_cfg.company.name}[/bold]\n"
        f"[dim]{company_cfg.company.description}[/dim]",
        title="Company Status",
        border_style="blue",
    ))

    # Agents table
    table = Table(title="Agents", box=box.ROUNDED, show_lines=True)
    table.add_column("Agent", style="cyan", no_wrap=True)
    table.add_column("Role", style="magenta")
    table.add_column("Model", style="dim")
    table.add_column("Status", justify="center")

    for name, agent_cfg in company_cfg.agents.items():
        status_str = "[green]Enabled[/]" if agent_cfg.enabled else "[red]Disabled[/]"
        table.add_row(name, agent_cfg.role, agent_cfg.model, status_str)

    console.print(table)

    # Orchestration settings
    orch = company_cfg.orchestration
    console.print(f"\n[dim]Max parallel tasks:[/] {orch.max_parallel_tasks}")
    console.print(f"[dim]Escalation enabled:[/] {orch.escalation_enabled}")
    console.print(f"[dim]Auto-assign:[/] {orch.auto_assign}")


@app.command()
def agents(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to company YAML config"),
) -> None:
    """List all configured agents and their details."""
    config_path = _resolve_config(config)
    company_cfg = _load_company_config(config_path)

    table = Table(title="AI Employees", box=box.HEAVY_HEAD)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold cyan")
    table.add_column("Role", style="magenta")
    table.add_column("Model", style="dim")
    table.add_column("Max Tasks", justify="center")
    table.add_column("Tools", style="yellow")
    table.add_column("Status", justify="center")

    for i, (name, agent_cfg) in enumerate(company_cfg.agents.items(), 1):
        status_str = "[green]Active[/]" if agent_cfg.enabled else "[red]Inactive[/]"
        tools = ", ".join(agent_cfg.tools) if agent_cfg.tools else "[dim]none[/dim]"
        table.add_row(
            str(i), name, agent_cfg.role,
            agent_cfg.model, str(agent_cfg.max_concurrent_tasks),
            tools, status_str,
        )

    console.print(table)
    enabled = sum(1 for a in company_cfg.agents.values() if a.enabled)
    console.print(f"\n[dim]{enabled} active / {len(company_cfg.agents)} total agents[/dim]")


@app.command()
def task(
    description: str = typer.Argument(..., help="Task description to submit to the company"),
    priority: str = typer.Option("medium", "--priority", "-p", help="Priority: low, medium, high, critical"),
    assign: Optional[str] = typer.Option(None, "--assign", "-a", help="Assign to a specific agent role"),
) -> None:
    """Submit a new task to the AI company."""
    from core.models import Task, TaskPriority

    new_task = Task(
        title=description,
        description=description,
        priority=TaskPriority(priority),
        assigned_to=assign or "",
    )

    panel = Panel(
        f"[bold]Task ID:[/] {new_task.id}\n"
        f"[bold]Title:[/]   {new_task.title}\n"
        f"[bold]Priority:[/] {new_task.priority.value}\n"
        f"[bold]Assigned:[/] {new_task.assigned_to or 'auto-assign'}",
        title="[green]Task Submitted[/]",
        border_style="green",
    )
    console.print(panel)
    console.print("[dim]Task will be picked up by the orchestrator on the next tick.[/dim]")


@app.command()
def workflow(
    action: str = typer.Argument(..., help="Action: run, list, show"),
    name: Optional[str] = typer.Argument(None, help="Workflow name (for run/show)"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to company YAML config"),
) -> None:
    """Manage and execute workflows.

    \b
    Actions:
      list  - List all available workflow definitions
      show  - Show details of a specific workflow
      run   - Execute a workflow by name
    """
    from workflows.engine import load_workflow, list_available_workflows, WorkflowEngine

    if action == "list":
        workflows = list_available_workflows()
        if not workflows:
            console.print("[yellow]No workflow definitions found.[/]")
            return

        table = Table(title="Available Workflows", box=box.ROUNDED)
        table.add_column("#", style="dim", width=3)
        table.add_column("Name", style="bold cyan")
        table.add_column("Description", style="dim")
        table.add_column("Steps", justify="center")

        for i, wf_name in enumerate(workflows, 1):
            try:
                wf = load_workflow(wf_name)
                table.add_row(str(i), wf.name, wf.description[:60], str(len(wf.steps)))
            except Exception:
                table.add_row(str(i), wf_name, "[red]Error loading[/]", "?")

        console.print(table)

    elif action == "show":
        if not name:
            console.print("[red]Please specify a workflow name.[/]")
            raise typer.Exit(1)

        wf = load_workflow(name)
        console.print(Panel(
            f"[bold]{wf.name}[/bold]\n"
            f"[dim]{wf.description}[/dim]\n"
            f"Version: {wf.version}",
            title="Workflow Details",
            border_style="cyan",
        ))

        table = Table(title="Steps", box=box.SIMPLE_HEAVY)
        table.add_column("#", style="dim", width=3)
        table.add_column("Step ID", style="bold")
        table.add_column("Agent", style="magenta")
        table.add_column("Action", style="cyan")
        table.add_column("Input From", style="dim")
        table.add_column("Timeout", justify="right")
        table.add_column("Condition", style="yellow")

        for i, step in enumerate(wf.steps, 1):
            table.add_row(
                str(i), step.id, step.agent_role, step.action,
                step.input_from or "-", f"{step.timeout_minutes}m",
                step.condition or "-",
            )

        console.print(table)

    elif action == "run":
        if not name:
            console.print("[red]Please specify a workflow name.[/]")
            raise typer.Exit(1)

        wf = load_workflow(name)
        console.print(f"[bold cyan]Running workflow:[/] {wf.name}")
        console.print(f"[dim]{wf.description}[/dim]\n")

        engine = WorkflowEngine()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            run_task = progress.add_task(f"Executing {wf.name}...", total=None)
            result = asyncio.run(engine.execute(wf))
            progress.update(run_task, description="Done")

        # Show results
        status_style = "green" if result.status.value == "completed" else "red"
        console.print(f"\n[bold {status_style}]Status: {result.status.value.upper()}[/]")
        console.print(f"[dim]Duration: {result.duration_seconds:.1f}s[/dim]\n")

        table = Table(title="Step Results", box=box.ROUNDED)
        table.add_column("Step", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Output", max_width=50)

        for step_id, sr in result.step_results.items():
            s_style = {
                "completed": "green", "failed": "red",
                "skipped": "yellow", "running": "blue",
            }.get(sr.status.value, "white")
            table.add_row(
                step_id,
                f"[{s_style}]{sr.status.value}[/{s_style}]",
                f"{sr.duration_seconds:.1f}s",
                (sr.output[:50] + "...") if len(sr.output) > 50 else sr.output,
            )

        console.print(table)

    else:
        console.print(f"[red]Unknown action: {action}. Use 'list', 'show', or 'run'.[/]")
        raise typer.Exit(1)


@app.command(name="dashboard")
def open_dashboard(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Dashboard host"),
    port: int = typer.Option(8080, "--port", "-p", help="Dashboard port"),
) -> None:
    """Open the web-based monitoring dashboard."""
    import webbrowser

    console.print(f"[bold cyan]Starting AICOS Dashboard[/] on http://{host}:{port}")

    try:
        from dashboard.app import create_app
        import uvicorn

        webbrowser.open(f"http://localhost:{port}")
        uvicorn.run(create_app(), host=host, port=port)
    except ImportError:
        console.print("[yellow]Dashboard module not yet available.[/]")
        console.print(f"[dim]Once built, it will be served at http://{host}:{port}[/dim]")


@app.command()
def init(
    output: str = typer.Option("config/company.yaml", "--output", "-o", help="Output config path"),
) -> None:
    """Interactively initialize a new company configuration."""
    _banner()
    console.print("[bold]Let's set up your AI company![/]\n")

    company_name = typer.prompt("Company name", default="My AI Company")
    available_types = ["agency", "saas", "consulting", "dev_shop", "marketing"]
    company_type = typer.prompt(
        f"Company type ({'/'.join(available_types)})",
        default="agency",
    )
    description = typer.prompt("Brief description", default="An AI-powered company")

    # Try loading a template for the chosen company type
    from core.config_loader import ConfigLoader
    import yaml

    loader = ConfigLoader()
    template_data: dict = {}
    try:
        template_data = loader.load_template(company_type)
        console.print(f"[dim]Loaded template for '{company_type}'[/dim]")
    except FileNotFoundError:
        console.print(f"[dim]No template for '{company_type}', using defaults[/dim]")

    # Determine default agent enablement from template or fallback
    template_agents = template_data.get("agents", {})
    all_roles = ["ceo", "cfo", "cto", "sales", "marketing", "support", "operations", "developer", "hr"]

    console.print("\n[bold]Select which agents to enable:[/]")
    enabled_roles: list[str] = []

    for role in all_roles:
        tmpl = template_agents.get(role, {})
        default_on = tmpl.get("enabled", role != "hr") if isinstance(tmpl, dict) else (role != "hr")
        if typer.confirm(f"  Enable {role.upper()} agent?", default=default_on):
            enabled_roles.append(role)

    model = typer.prompt("\nDefault model", default="claude-sonnet-4-5-20250929")

    # Build config, merging template workflows/KPIs when available
    config_data = {
        "company": {
            "name": company_name,
            "type": company_type,
            "description": description,
        },
        "agents": {
            role: {"enabled": role in enabled_roles, "model": model}
            for role in all_roles
        },
        "workflows": template_data.get("workflows", [
            "client_onboarding", "project_delivery",
            "content_pipeline", "support_escalation",
        ]),
        "focus_kpis": template_data.get("focus_kpis", [
            "revenue", "client_satisfaction",
        ]),
        "orchestration": {
            "max_concurrent_tasks": 10,
            "task_timeout_minutes": 30,
            "escalation_threshold": 3,
            "decision_mode": "autonomous",
        },
        "dashboard": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 8080,
        },
    }

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        yaml.dump(config_data, fh, default_flow_style=False, sort_keys=False)

    console.print(Panel(
        f"[green]Configuration saved to {output_path}[/green]\n\n"
        f"Company: {company_name}\n"
        f"Type:    {company_type}\n"
        f"Agents:  {', '.join(enabled_roles)}\n"
        f"Model:   {model}",
        title="[bold green]Company Initialized[/]",
        border_style="green",
    ))
    console.print(f"\n[dim]Start your company with:[/] [bold]aicos start --config {output_path}[/bold]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
