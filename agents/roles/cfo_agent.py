"""AICOS CFO Agent: Chief Financial Officer - financial steward and strategic advisor."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agents.base import BaseAgent, TaskResult
from core.models import (
    AgentConfig,
    AgentRole,
    Message,
    Task,
    TaskStatus,
)

logger = logging.getLogger("aicos.agents.cfo")

CFO_SYSTEM_PROMPT = """\
You are the Chief Financial Officer of this AI-powered company. Your name is {name}.

You are a meticulous, numbers-driven executive who ensures the company's financial \
health and long-term viability. You combine analytical rigor with business acumen to \
advise leadership on every decision that touches money.

Core responsibilities:
- Track all revenue streams, expenses, and cash flow in real time.
- Create and manage budgets for each department and project.
- Generate financial reports: P&L statements, balance sheets, and cash flow projections.
- Process invoices, manage accounts receivable and payable.
- Perform cost-benefit analysis on proposed initiatives before they're greenlit.
- Flag financial risks and recommend hedging or cost-cutting measures.

Financial philosophy:
- Every dollar should earn more than it costs. You ruthlessly evaluate ROI.
- You maintain a healthy cash reserve for unexpected opportunities or downturns.
- Transparency is non-negotiable — you present numbers honestly even when they're uncomfortable.
- You plan for three horizons: this month, this quarter, this year.

Communication style:
- You lead with data — every recommendation comes with supporting numbers.
- You simplify complex financial concepts so non-finance team members understand them.
- You flag concerns early rather than waiting for a crisis.
- Reports are structured, scannable, and always include a clear bottom line.

You work closely with the CEO on strategic financial decisions, with Sales on revenue \
forecasting, and with Operations on cost management. You hold every agent accountable \
for staying within budget.
"""

DEFAULT_CFO_TOOLS = [
    "create_invoice",
    "generate_financial_report",
    "analyze_costs",
    "manage_budget",
    "track_revenue",
    "forecast_cashflow",
    "approve_expense",
]

DEFAULT_CFO_KPIS = {
    "revenue": 0.0,
    "expenses": 0.0,
    "profit_margin": 0.0,
    "outstanding_invoices": 0.0,
}


class CFOAgent(BaseAgent):
    """Chief Financial Officer agent — financial tracking, budgets, and fiscal strategy."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = CFO_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_CFO_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_CFO_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "invoice":
                return await self._handle_invoice(task)
            elif task_type == "report":
                return await self._handle_financial_report(task)
            elif task_type == "budget":
                return await self._handle_budget(task)
            elif task_type == "analysis":
                return await self._handle_cost_analysis(task)
            else:
                return await self._handle_general_finance(task)

        except Exception as exc:
            logger.exception("CFO %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("invoice", "billing", "payment", "receivable")):
            return "invoice"
        if any(kw in combined for kw in ("report", "statement", "p&l", "balance sheet", "financial report")):
            return "report"
        if any(kw in combined for kw in ("budget", "allocation", "spending limit")):
            return "budget"
        if any(kw in combined for kw in ("cost", "analysis", "roi", "expense", "forecast")):
            return "analysis"
        return "general"

    async def _handle_invoice(self, task: Task) -> TaskResult:
        prompt = (
            f"As CFO, handle this invoicing task:\n\n"
            f"Task: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Invoice details (client, amount, line items, payment terms).\n"
            f"2. Any adjustments or discounts to apply.\n"
            f"3. Follow-up actions for accounts receivable.\n"
            f"4. Impact on cash flow projections."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("outstanding_invoices", self.kpis.get("outstanding_invoices", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_financial_report(self, task: Task) -> TaskResult:
        prompt = (
            f"As CFO, generate a financial report:\n\n"
            f"Request: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Include:\n"
            f"1. Executive summary with key metrics.\n"
            f"2. Revenue breakdown by source.\n"
            f"3. Expense breakdown by category.\n"
            f"4. Profit/loss calculation.\n"
            f"5. Cash flow status.\n"
            f"6. Comparison to budget targets.\n"
            f"7. Trends and forward projections.\n"
            f"8. Recommendations for financial optimization."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_budget(self, task: Task) -> TaskResult:
        prompt = (
            f"As CFO, manage this budget request:\n\n"
            f"Task: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Proposed budget allocation with line items.\n"
            f"2. Justification for each major expense category.\n"
            f"3. Comparison with previous period spending.\n"
            f"4. Contingency reserves.\n"
            f"5. Approval conditions and spending controls."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_cost_analysis(self, task: Task) -> TaskResult:
        prompt = (
            f"As CFO, perform a cost analysis:\n\n"
            f"Subject: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Total cost breakdown (fixed, variable, one-time).\n"
            f"2. Expected return or savings.\n"
            f"3. ROI calculation with timeline.\n"
            f"4. Risk-adjusted projections (best/worst/likely case).\n"
            f"5. Recommendation: proceed, modify, or pass."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_finance(self, task: Task) -> TaskResult:
        prompt = (
            f"As CFO, address this financial matter:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Provide a thorough financial analysis and clear recommendations."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
