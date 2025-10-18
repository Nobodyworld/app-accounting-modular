"""Budget and forecast orchestration services."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from typing import Iterable

import csv

from sqlmodel import Session, select

from ..models.models import (
    Account,
    AccountType,
    Budget,
    BudgetLine,
    ForecastOutput,
    ForecastPlan,
    JournalEntry,
    Organization,
    Transaction,
)
from .forecast_service import ForecastResult, ForecastService


@dataclass(slots=True)
class BudgetVarianceLine:
    account_id: int
    account_code: str | None
    account_name: str
    period_start: date
    budget_amount: float
    actual_amount: float
    variance: float
    burn_rate: float | None
    forecast: list[tuple[str, float]] | None


@dataclass(slots=True)
class BudgetReport:
    lines: list[BudgetVarianceLine]
    total_budget: float
    total_actual: float
    total_variance: float
    burn_rate: float | None
    metadata: dict[str, object]
    csv_export: str


@dataclass(slots=True)
class CashflowReport:
    historical: list[tuple[str, float]]
    forecast: ForecastResult | None
    current_cash: float
    average_monthly_flow: float | None
    metadata: dict[str, object]
    csv_export: str


class BudgetService:
    """Service responsible for budget variance and cashflow forecasting."""

    BUDGET_PLAN_NAME = "Budget vs Actual"
    CASHFLOW_PLAN_NAME = "Cashflow Forecast"

    def __init__(self, session: Session, forecast_service: ForecastService | None = None):
        self.session = session
        self.forecaster = forecast_service or ForecastService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def budget_vs_actual(
        self, budget_id: int, *, horizon: int | None = None, refresh: bool = False
    ) -> BudgetReport:
        """Return a budget vs actual report, optionally refreshing persisted data."""

        plan = self._ensure_budget_plan(budget_id, horizon)
        if not refresh:
            cached = self._load_latest_output(plan.id, "budget_vs_actual")
            if cached is not None:
                return cached

        report = self._build_budget_report(plan)
        self._persist_output(plan, "budget_vs_actual", report)
        return report

    def cashflow_forecast(
        self, organization_id: int, *, horizon: int | None = None, refresh: bool = False
    ) -> CashflowReport:
        """Return a cashflow forecast for an organisation."""

        plan = self._ensure_cashflow_plan(organization_id, horizon)
        if not refresh:
            cached = self._load_latest_cashflow(plan.id)
            if cached is not None:
                return cached

        report = self._build_cashflow_report(plan)
        self._persist_output(plan, "cashflow_forecast", report)
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_budget_plan(self, budget_id: int, horizon: int | None) -> ForecastPlan:
        budget = self.session.get(Budget, budget_id)
        if budget is None:
            raise ValueError(f"Budget {budget_id} not found")

        plan_stmt = select(ForecastPlan).where(
            ForecastPlan.budget_id == budget_id,
            ForecastPlan.name == self.BUDGET_PLAN_NAME,
        )
        plan = self.session.exec(plan_stmt).one_or_none()
        if plan is None:
            plan = ForecastPlan(
                organization_id=budget.organization_id,
                budget_id=budget.id,
                name=self.BUDGET_PLAN_NAME,
                horizon=horizon or 90,
            )
            self.session.add(plan)
            self.session.commit()
            self.session.refresh(plan)
            # TODO - Lock plan creation to avoid duplicate rows under concurrent calls.
        else:
            updated_horizon = horizon or plan.horizon
            if plan.horizon != updated_horizon:
                plan.horizon = updated_horizon
                plan.updated_at = datetime.utcnow()
                self.session.add(plan)
                self.session.commit()
                self.session.refresh(plan)
        return plan

    def _ensure_cashflow_plan(self, organization_id: int, horizon: int | None) -> ForecastPlan:
        org = self.session.get(Organization, organization_id)
        if org is None:
            raise ValueError(f"Organization {organization_id} not found")

        plan_stmt = select(ForecastPlan).where(
            ForecastPlan.organization_id == organization_id,
            ForecastPlan.budget_id.is_(None),
            ForecastPlan.name == self.CASHFLOW_PLAN_NAME,
        )
        plan = self.session.exec(plan_stmt).one_or_none()
        if plan is None:
            plan = ForecastPlan(
                organization_id=organization_id,
                budget_id=None,
                name=self.CASHFLOW_PLAN_NAME,
                horizon=horizon or 90,
            )
            self.session.add(plan)
            self.session.commit()
            self.session.refresh(plan)
            # TODO - Capture creator metadata when provisioning default cashflow plan.
        else:
            updated_horizon = horizon or plan.horizon
            if plan.horizon != updated_horizon:
                plan.horizon = updated_horizon
                plan.updated_at = datetime.utcnow()
                self.session.add(plan)
                self.session.commit()
                self.session.refresh(plan)
        return plan

    def _build_budget_report(self, plan: ForecastPlan) -> BudgetReport:
        budget = self.session.get(Budget, plan.budget_id)
        if budget is None:
            raise ValueError(f"Budget {plan.budget_id} not found")

        lines_stmt = (
            select(BudgetLine, Account)
            .join(Account, BudgetLine.account_id == Account.id)
            .where(BudgetLine.budget_id == budget.id)
            .order_by(BudgetLine.period_start, Account.name)
        )

        lines: list[BudgetVarianceLine] = []
        account_ids: set[int] = set()
        period_keys: set[date] = set()

        budget_lines: list[tuple[BudgetLine, Account]] = list(self.session.exec(lines_stmt).all())
        for line, account in budget_lines:
            account_ids.add(account.id)
            period_keys.add(self._period_key(line.period_start))

        if not budget_lines:
            raise ValueError("Budget contains no lines to analyse")

        actuals = self._collect_actuals(account_ids, period_keys)
        forecast_series = self._forecast_by_account(actuals, plan.horizon)
        # TODO - Surface accounts missing actuals in report metadata for diagnostics.

        total_budget = Decimal("0")
        total_actual = Decimal("0")

        for line, account in budget_lines:
            period = self._period_key(line.period_start)
            actual_amount = actuals.get((account.id, period), Decimal("0"))
            budget_amount = Decimal(str(line.amount))
            variance = actual_amount - budget_amount
            burn_rate = None
            if budget_amount != 0:
                burn_rate = float(actual_amount / budget_amount)

            lines.append(
                BudgetVarianceLine(
                    account_id=account.id,
                    account_code=account.code,
                    account_name=account.name,
                    period_start=period,
                    budget_amount=float(budget_amount),
                    actual_amount=float(actual_amount),
                    variance=float(variance),
                    burn_rate=burn_rate,
                    forecast=[(point[0], point[1]) for point in forecast_series.get(account.id, [])],
                )
            )

            total_budget += budget_amount
            total_actual += actual_amount

        total_variance = total_actual - total_budget
        burn_rate_total = None
        if total_budget != 0:
            burn_rate_total = float(total_actual / total_budget)

        csv_export = self._render_budget_csv(lines)

        metadata = {
            "generated_at": datetime.utcnow().isoformat(),
            "horizon": plan.horizon,
            "plan_id": plan.id,
            "budget_id": plan.budget_id,
            "organization_id": plan.organization_id,
        }
        # TODO - Include reporting currency and fx assumptions in metadata payload.

        return BudgetReport(
            lines=lines,
            total_budget=float(total_budget),
            total_actual=float(total_actual),
            total_variance=float(total_variance),
            burn_rate=burn_rate_total,
            metadata=metadata,
            csv_export=csv_export,
        )

    def _build_cashflow_report(self, plan: ForecastPlan) -> CashflowReport:
        asset_accounts = self.session.exec(
            select(Account.id)
            .where(Account.organization_id == plan.organization_id)
            .where(Account.type == AccountType.ASSET)
        ).all()

        if not asset_accounts:
            raise ValueError("Organization has no asset accounts to build cashflow report")

        account_ids = {
            row[0] if isinstance(row, tuple) else row for row in asset_accounts
        }

        stmt = (
            select(Transaction.date, JournalEntry.debit, JournalEntry.credit)
            .join(JournalEntry, JournalEntry.transaction_id == Transaction.id)
            .where(JournalEntry.account_id.in_(account_ids))
            .order_by(Transaction.date)
        )
        results = self.session.exec(stmt).all()

        monthly: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        for txn_date, debit, credit in results:
            if txn_date is None:
                continue
            period = self._period_key(txn_date)
            monthly[period] += Decimal(str(debit)) - Decimal(str(credit))

        historical = sorted((period, float(amount)) for period, amount in monthly.items())

        forecast_result: ForecastResult | None = None
        if historical:
            series = [(period.isoformat(), amount) for period, amount in historical]
            try:
                forecast_result = self.forecaster.forecast_series(series, plan.horizon)
            except ValueError:
                # TODO - Capture forecasting errors for monitoring and automatic fallbacks.
                forecast_result = None

        current_cash = float(sum(amount for _, amount in historical)) if historical else 0.0
        avg_flow = None
        if historical:
            avg_flow = float(sum(amount for _, amount in historical) / len(historical))

        csv_export = self._render_cashflow_csv(historical, forecast_result)

        metadata = {
            "generated_at": datetime.utcnow().isoformat(),
            "horizon": plan.horizon,
            "plan_id": plan.id,
            "organization_id": plan.organization_id,
            "budget_id": plan.budget_id,
        }
        # TODO - Expose plan revision identifiers to aid reconciliation between exports.

        return CashflowReport(
            historical=[(period.isoformat(), amount) for period, amount in historical],
            forecast=forecast_result,
            current_cash=current_cash,
            average_monthly_flow=avg_flow,
            metadata=metadata,
            csv_export=csv_export,
        )

    def _collect_actuals(
        self, account_ids: Iterable[int], periods: Iterable[date]
    ) -> dict[tuple[int, date], Decimal]:
        period_set = {self._period_key(p) for p in periods}
        if not period_set:
            return {}

        min_period = min(period_set)
        max_period = max(period_set)

        stmt = (
            select(JournalEntry.account_id, Transaction.date, JournalEntry.debit, JournalEntry.credit)
            .join(Transaction, Transaction.id == JournalEntry.transaction_id)
            .where(JournalEntry.account_id.in_(set(account_ids)))
            .where(Transaction.date >= min_period)
            .where(Transaction.date <= self._period_month_end(max_period))
        )

        rows = self.session.exec(stmt).all()
        actuals: dict[tuple[int, date], Decimal] = defaultdict(lambda: Decimal("0"))
        for account_id, txn_date, debit, credit in rows:
            if txn_date is None:
                continue
            period = self._period_key(txn_date)
            key = (account_id, period)
            actuals[key] += Decimal(str(debit)) - Decimal(str(credit))
        # TODO - Apply currency conversion when aggregating multi-currency ledgers.
        # TODO - Stream large actual datasets instead of loading all rows into memory.

        return actuals

    def _forecast_by_account(
        self, actuals: dict[tuple[int, date], Decimal], horizon: int
    ) -> dict[int, list[tuple[str, float]]]:
        series_by_account: dict[int, list[tuple[str, float]]] = defaultdict(list)
        for (account_id, period), amount in actuals.items():
            series_by_account[account_id].append((period.isoformat(), float(amount)))

        forecasts: dict[int, list[tuple[str, float]]] = {}
        for account_id, series in series_by_account.items():
            if not series:
                continue
            series.sort(key=lambda item: item[0])
            try:
                result = self.forecaster.forecast_series(series, horizon)
            except ValueError:
                continue
            forecasts[account_id] = result.points
        return forecasts

    def _load_latest_output(
        self, plan_id: int, report_type: str
    ) -> BudgetReport | None:
        stmt = (
            select(ForecastOutput)
            .where(ForecastOutput.plan_id == plan_id)
            .where(ForecastOutput.report_type == report_type)
            .order_by(ForecastOutput.generated_at.desc())
        )
        output = self.session.exec(stmt).first()
        if output is None or not output.summary:
            return None

        lines = [
            BudgetVarianceLine(
                account_id=item["account_id"],
                account_code=item.get("account_code"),
                account_name=item["account_name"],
                period_start=date.fromisoformat(item["period_start"]),
                budget_amount=float(item["budget_amount"]),
                actual_amount=float(item["actual_amount"]),
                variance=float(item["variance"]),
                burn_rate=item.get("burn_rate"),
                forecast=[(point[0], float(point[1])) for point in item.get("forecast", [])],
            )
            for item in output.summary.get("lines", [])
        ]

        metadata = output.context or {}

        return BudgetReport(
            lines=lines,
            total_budget=float(output.summary.get("total_budget", 0.0)),
            total_actual=float(output.summary.get("total_actual", 0.0)),
            total_variance=float(output.summary.get("total_variance", 0.0)),
            burn_rate=output.summary.get("burn_rate"),
            metadata=metadata,
            csv_export=output.csv_data or "",
        )

    def _load_latest_cashflow(self, plan_id: int) -> CashflowReport | None:
        stmt = (
            select(ForecastOutput)
            .where(ForecastOutput.plan_id == plan_id)
            .where(ForecastOutput.report_type == "cashflow_forecast")
            .order_by(ForecastOutput.generated_at.desc())
        )
        output = self.session.exec(stmt).first()
        if output is None or not output.summary:
            return None

        forecast_points = output.summary.get("forecast", [])
        forecast_result = None
        if forecast_points:
            forecast_result = ForecastResult(
                horizon=output.summary.get("horizon", 0),
                points=[(point[0], float(point[1])) for point in forecast_points],
                model_order=tuple(output.summary.get("model_order", (0, 0, 0))),
            )

        metadata = output.context or {}

        return CashflowReport(
            historical=[(item[0], float(item[1])) for item in output.summary.get("historical", [])],
            forecast=forecast_result,
            current_cash=float(output.summary.get("current_cash", 0.0)),
            average_monthly_flow=output.summary.get("average_monthly_flow"),
            metadata=metadata,
            csv_export=output.csv_data or "",
        )

    def _persist_output(
        self, plan: ForecastPlan, report_type: str, payload: BudgetReport | CashflowReport
    ) -> None:
        if isinstance(payload, BudgetReport):
            summary = {
                "lines": [
                    {
                        "account_id": line.account_id,
                        "account_code": line.account_code,
                        "account_name": line.account_name,
                        "period_start": line.period_start.isoformat(),
                        "budget_amount": line.budget_amount,
                        "actual_amount": line.actual_amount,
                        "variance": line.variance,
                        "burn_rate": line.burn_rate,
                        "forecast": line.forecast or [],
                    }
                    for line in payload.lines
                ],
                "total_budget": payload.total_budget,
                "total_actual": payload.total_actual,
                "total_variance": payload.total_variance,
                "burn_rate": payload.burn_rate,
            }
            context = payload.metadata
            csv_data = payload.csv_export
        else:
            summary = {
                "historical": payload.historical,
                "forecast": payload.forecast.points if payload.forecast else [],
                "horizon": payload.forecast.horizon if payload.forecast else 0,
                "model_order": payload.forecast.model_order if payload.forecast else (0, 0, 0),
                "current_cash": payload.current_cash,
                "average_monthly_flow": payload.average_monthly_flow,
            }
            context = payload.metadata
            csv_data = payload.csv_export

        output = ForecastOutput(
            plan_id=plan.id,
            report_type=report_type,
            summary=summary,
            context=context,
            csv_data=csv_data,
        )
        self.session.add(output)
        self.session.commit()

    @staticmethod
    def _period_key(value: date) -> date:
        return value.replace(day=1)

    @staticmethod
    def _period_month_end(value: date) -> date:
        if value.month == 12:
            return date(value.year, 12, 31)
        next_month = date(value.year, value.month + 1, 1)
        return next_month - timedelta(days=1)

    @staticmethod
    def _render_budget_csv(lines: Iterable[BudgetVarianceLine]) -> str:
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "account_id",
                "account_code",
                "account_name",
                "period_start",
                "budget_amount",
                "actual_amount",
                "variance",
                "burn_rate",
            ],
        )
        writer.writeheader()
        for line in lines:
            writer.writerow(
                {
                    "account_id": line.account_id,
                    "account_code": line.account_code or "",
                    "account_name": line.account_name,
                    "period_start": line.period_start.isoformat(),
                    "budget_amount": f"{line.budget_amount:.2f}",
                    "actual_amount": f"{line.actual_amount:.2f}",
                    "variance": f"{line.variance:.2f}",
                    "burn_rate": f"{line.burn_rate:.4f}" if line.burn_rate is not None else "",
                }
            )
        return buffer.getvalue()

    @staticmethod
    def _render_cashflow_csv(
        historical: Iterable[tuple[date, float]], forecast: ForecastResult | None
    ) -> str:
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["period", "amount", "type"])
        for period, amount in historical:
            writer.writerow([period.isoformat() if hasattr(period, "isoformat") else period, f"{amount:.2f}", "historical"])
        if forecast:
            for period, amount in forecast.points:
                writer.writerow([period, f"{amount:.2f}", "forecast"])
        return buffer.getvalue()

