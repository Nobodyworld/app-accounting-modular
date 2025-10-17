from __future__ import annotations
"""Database models used across Modular Accounting services."""

from typing import Optional
from enum import Enum
from datetime import date, datetime

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel

__all__ = [
    "Account",
    "AccountType",
    "Budget",
    "BudgetLine",
    "Country",
    "Event",
    "ForecastOutput",
    "ForecastPlan",
    "Instrument",
    "JournalEntry",
    "Organization",
    "Price",
    "Rate",
    "TaxRule",
    "Transaction",
]


class AccountType(str, Enum):
    """Supported account categories."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class Organization(SQLModel, table=True):
    """Legal entity or business unit tracked in the system."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Account(SQLModel, table=True):
    """Chart of accounts entry."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    code: Optional[str] = None
    type: AccountType
    currency: str = "USD"
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id")


class Transaction(SQLModel, table=True):
    """General ledger transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    description: str
    external_ref: Optional[str] = None


class JournalEntry(SQLModel, table=True):
    """Individual journal posting tied to a transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "USD"


class Budget(SQLModel, table=True):
    """Operating budget for an organization."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id")
    name: str
    start_date: date
    end_date: date
    currency: str = "USD"


class BudgetLine(SQLModel, table=True):
    """Budgeted amount for an account and period."""

    id: Optional[int] = Field(default=None, primary_key=True)
    budget_id: int = Field(foreign_key="budget.id")
    account_id: int = Field(foreign_key="account.id")
    period_start: date
    amount: float


class ForecastPlan(SQLModel, table=True):
    """Configuration describing how forecasts are generated."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id")
    budget_id: Optional[int] = Field(default=None, foreign_key="budget.id")
    name: str
    horizon: int
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ForecastOutput(SQLModel, table=True):
    """Stored forecast artefact for quick retrieval."""

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="forecastplan.id")
    report_type: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: dict | None = Field(default=None, sa_column=Column(JSON))
    context: dict | None = Field(default=None, sa_column=Column(JSON))
    csv_data: Optional[str] = Field(default=None, sa_column=Column(Text))


class Instrument(SQLModel, table=True):
    """Financial instrument reference data."""

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str
    name: Optional[str] = None
    type: str = "equity"  # equity/etf/commodity/currency


class Price(SQLModel, table=True):
    """Daily close price for an instrument."""

    id: Optional[int] = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    date: date
    close: float
    provider: str


class Rate(SQLModel, table=True):
    """Foreign exchange rate observation."""

    id: Optional[int] = Field(default=None, primary_key=True)
    base: str
    quote: str
    date: date
    value: float
    provider: str


class Country(SQLModel, table=True):
    """Geopolitical country reference."""

    id: Optional[int] = Field(default=None, primary_key=True)
    iso2: str
    name: str


class TaxRule(SQLModel, table=True):
    """Machine-readable tax rule."""

    id: Optional[int] = Field(default=None, primary_key=True)
    jurisdiction: str  # e.g., US-FED, EU-IE
    scope: str  # e.g., vat, corporate_income, payroll
    expression: str  # JSONLogic or simple expr string
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source: Optional[str] = None


class Event(SQLModel, table=True):
    """External event for market intelligence."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime
    source: str
    title: str
    score: Optional[float] = None  # relevance/intensity
