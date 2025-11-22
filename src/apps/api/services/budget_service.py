"""Budget and forecast orchestration services.

The service layer composes ledger data, forecast plans, and diagnostics into
coherent artefacts exposed over the API. Helper dataclasses capture the shape
of responses while keeping the persistence layer isolated from presentation
formatting concerns.
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO

from sqlalchemy.exc import IntegrityError
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
    Rate,
    Transaction,
)
from ..utils.metadata import merge_forecast_diagnostics
from .forecast_service import ForecastResult, ForecastService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BudgetVarianceLine:
    """Denormalised view of a single budget line with observed performance."""

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
    """Structured representation of a budget variance report."""

    lines: list[BudgetVarianceLine]
    total_budget: float
    total_actual: float
    total_variance: float
    burn_rate: float | None
    metadata: dict[str, object]
    csv_export: str


@dataclass(slots=True)
class CashflowReport:
    """Historical and forecast cashflow data packaged for API responses."""

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
    def budget_vs_actual(self, budget_id: int, *, horizon: int | None = None, refresh: bool = False) -> BudgetReport:
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
            plan = self._provision_plan(
                plan_stmt,
                ForecastPlan(
                    organization_id=budget.organization_id,
                    budget_id=budget.id,
                    name=self.BUDGET_PLAN_NAME,
                    horizon=horizon or 90,
                ),
            )
        else:
            plan = self._update_plan_horizon(plan, horizon)
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
            plan = self._provision_plan(
                plan_stmt,
                ForecastPlan(
                    organization_id=organization_id,
                    budget_id=None,
                    name=self.CASHFLOW_PLAN_NAME,
                    horizon=horizon or 90,
                ),
            )
        else:
            plan = self._update_plan_horizon(plan, horizon)
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
        accounts_by_id = {account.id: account for _, account in budget_lines}

        if not budget_lines:
            raise ValueError("Budget contains no lines to analyse")

        actuals = self._collect_actuals(accounts_by_id, period_keys, budget.currency)
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

        accounts_with_actuals = {account_id for account_id, _ in actuals.keys()}
        missing_accounts = [
            {
                "account_id": account.id,
                "account_name": account.name,
                "account_code": account.code,
            }
            for account_id, account in accounts_by_id.items()
            if account_id not in accounts_with_actuals
        ]

        metadata: dict[str, object] = {
            "generated_at": datetime.now(UTC),
            "horizon": plan.horizon,
            "plan_id": plan.id,
            "plan_revision": self._as_utc(plan.updated_at),
            "budget_id": plan.budget_id,
            "organization_id": plan.organization_id,
            "reporting_currency": budget.currency,
        }
        if missing_accounts:
            metadata["accounts_without_actuals"] = missing_accounts

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
            select(Account.id, Account.currency)
            .where(Account.organization_id == plan.organization_id)
            .where(Account.type == AccountType.ASSET)
        ).all()

        if not asset_accounts:
            raise ValueError("Organization has no asset accounts to build cashflow report")

        account_ids = {row[0] if isinstance(row, tuple) else row.id for row in asset_accounts}
        currencies = {row[1] if isinstance(row, tuple) else row.currency for row in asset_accounts}

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
        forecast_error: str | None = None
        if historical:
            series = [(period.isoformat(), amount) for period, amount in historical]
            try:
                forecast_result = self.forecaster.forecast_series(series, plan.horizon)
            except ValueError as exc:
                forecast_result = None
                forecast_error = str(exc)
                logger.warning(
                    "Cashflow forecasting failed",  # pragma: no cover - structured logging hook
                    extra={
                        "plan_id": plan.id,
                        "organization_id": plan.organization_id,
                        "error": forecast_error,
                    },
                )

        current_cash = float(sum(amount for _, amount in historical)) if historical else 0.0
        avg_flow = None
        if historical:
            avg_flow = float(sum(amount for _, amount in historical) / len(historical))

        csv_export = self._render_cashflow_csv(historical, forecast_result)

        metadata = {
            "generated_at": datetime.now(UTC),
            "horizon": plan.horizon,
            "plan_id": plan.id,
            "plan_revision": self._as_utc(plan.updated_at),
            "organization_id": plan.organization_id,
            "budget_id": plan.budget_id,
            "reporting_currency": currencies.pop() if len(currencies) == 1 else None,
        }
        forecast_status = "unavailable"
        if forecast_result:
            forecast_status = "success"
            if forecast_result.diagnostics:
                merge_forecast_diagnostics(metadata, forecast_result.diagnostics)
            if forecast_result.timezone:
                metadata["forecast_timezone"] = forecast_result.timezone
        elif forecast_error:
            forecast_status = "error"
            merge_forecast_diagnostics(metadata, {"status": "error", "detail": forecast_error})
        metadata["forecast_status"] = forecast_status

        return CashflowReport(
            historical=[(period.isoformat(), amount) for period, amount in historical],
            forecast=forecast_result,
            current_cash=current_cash,
            average_monthly_flow=avg_flow,
            metadata=metadata,
            csv_export=csv_export,
        )

    def _provision_plan(self, stmt, candidate: ForecastPlan) -> ForecastPlan:
        """Persist a new forecast plan guarding against concurrent creation."""

        self.session.add(candidate)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.exec(stmt).one()
            return existing
        self.session.refresh(candidate)
        return candidate

    def _update_plan_horizon(self, plan: ForecastPlan, horizon: int | None) -> ForecastPlan:
        updated_horizon = horizon or plan.horizon
        if plan.horizon != updated_horizon:
            plan.horizon = updated_horizon
            plan.updated_at = datetime.now(UTC)
            self.session.add(plan)
            self.session.commit()
            self.session.refresh(plan)
        return plan

    def _convert_currency(self, amount: Decimal, from_ccy: str, to_ccy: str, as_of: date) -> Decimal | None:
        if from_ccy == to_ccy:
            return amount
        rate_stmt = (
            select(Rate.value)
            .where(Rate.base == from_ccy)
            .where(Rate.quote == to_ccy)
            .where(Rate.date <= as_of)
            .order_by(Rate.date.desc())
        )
        rate = self.session.exec(rate_stmt).first()
        if rate is None:
            logger.warning(
                "Missing FX rate for conversion",
                extra={"base": from_ccy, "quote": to_ccy, "as_of": as_of.isoformat()},
            )
            return None
        return amount * Decimal(str(rate))

    def _collect_actuals(
        self,
        accounts_by_id: dict[int, Account],
        periods: Iterable[date],
        budget_currency: str,
    ) -> dict[tuple[int, date], Decimal]:
        period_set = {self._period_key(p) for p in periods}
        if not period_set:
            return {}

        min_period = min(period_set)
        max_period = max(period_set)

        stmt = (
            select(JournalEntry.account_id, Transaction.date, JournalEntry.debit, JournalEntry.credit)
            .join(Transaction, Transaction.id == JournalEntry.transaction_id)
            .where(JournalEntry.account_id.in_(set(accounts_by_id.keys())))
            .where(Transaction.date >= min_period)
            .where(Transaction.date <= self._period_month_end(max_period))
        )

        actuals: dict[tuple[int, date], Decimal] = defaultdict(lambda: Decimal("0"))
        result = self.session.exec(stmt)
        for account_id, txn_date, debit, credit in result.yield_per(1000):
            if txn_date is None:
                continue
            period = self._period_key(txn_date)
            key = (account_id, period)
            raw_amount = Decimal(str(debit)) - Decimal(str(credit))
            account_currency = accounts_by_id.get(account_id).currency if accounts_by_id.get(account_id) else budget_currency
            converted = self._convert_currency(raw_amount, account_currency, budget_currency, txn_date)
            if converted is None:
                continue
            actuals[key] += converted

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

    def _load_latest_output(self, plan_id: int, report_type: str) -> BudgetReport | None:
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
                diagnostics=output.summary.get("diagnostics"),
                timezone=output.summary.get("timezone"),
                model=output.summary.get("model", "arima"),
            )

        metadata = output.context or {}
        if output.summary.get("status") and "forecast_status" not in metadata:
            metadata = {**metadata, "forecast_status": output.summary.get("status")}

        return CashflowReport(
            historical=[(item[0], float(item[1])) for item in output.summary.get("historical", [])],
            forecast=forecast_result,
            current_cash=float(output.summary.get("current_cash", 0.0)),
            average_monthly_flow=output.summary.get("average_monthly_flow"),
            metadata=metadata,
            csv_export=output.csv_data or "",
        )

    def _persist_output(self, plan: ForecastPlan, report_type: str, payload: BudgetReport | CashflowReport) -> None:
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
            context = self._serialise_metadata(payload.metadata)
            csv_data = payload.csv_export
        else:
            summary = {
                "historical": payload.historical,
                "forecast": payload.forecast.points if payload.forecast else [],
                "horizon": payload.forecast.horizon if payload.forecast else 0,
                "model_order": payload.forecast.model_order if payload.forecast else (0, 0, 0),
                "model": payload.forecast.model if payload.forecast else "arima",
                "diagnostics": payload.forecast.diagnostics if payload.forecast else None,
                "timezone": payload.forecast.timezone if payload.forecast else None,
                "status": payload.metadata.get("forecast_status"),
                "current_cash": payload.current_cash,
                "average_monthly_flow": payload.average_monthly_flow,
            }
            context = self._serialise_metadata(payload.metadata)
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
    def _render_cashflow_csv(historical: Iterable[tuple[date, float]], forecast: ForecastResult | None) -> str:
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["period", "amount", "type"])
        for period, amount in historical:
            label = period.isoformat() if hasattr(period, "isoformat") else period
            writer.writerow([label, f"{amount:.2f}", "historical"])
        if forecast:
            for period, amount in forecast.points:
                writer.writerow([period, f"{amount:.2f}", "forecast"])
        return buffer.getvalue()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _serialise_metadata(metadata: dict[str, object]) -> dict[str, object]:
        def convert(value: object) -> object:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, list):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            return value

        return {key: convert(value) for key, value in metadata.items()}
