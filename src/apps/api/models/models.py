"""SQLModel-powered persistence models for the public API."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class AccountType(str, Enum):
    """Enumerates supported account classifications."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class Account(SQLModel, table=True):
    """Chart-of-accounts entry supporting optional display codes."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    code: str | None = None
    type: AccountType
    currency: str = "USD"


class Transaction(SQLModel, table=True):
    """Financial transaction describing journal entry context."""

    id: int | None = Field(default=None, primary_key=True)
    date: date
    description: str
    external_ref: str | None = None


class JournalEntry(SQLModel, table=True):
    """Double-entry bookkeeping line item for a transaction."""

    id: int | None = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "USD"


class Instrument(SQLModel, table=True):
    """Tradable instrument metadata for price lookups."""

    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    name: str | None = None
    type: str = "equity"  # equity/etf/commodity/currency


class Price(SQLModel, table=True):
    """Historical price observation for an instrument."""

    id: int | None = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    date: date
    close: float
    provider: str


class Rate(SQLModel, table=True):
    """Foreign exchange rate observation."""

    id: int | None = Field(default=None, primary_key=True)
    base: str
    quote: str
    date: date
    value: float
    provider: str


class Country(SQLModel, table=True):
    """Country metadata including ISO codes."""

    id: int | None = Field(default=None, primary_key=True)
    iso2: str
    name: str


class TaxRule(SQLModel, table=True):
    """Configured tax rule definition stored for orchestration."""

    id: int | None = Field(default=None, primary_key=True)
    jurisdiction: str  # e.g., US-FED, EU-IE
    scope: str  # e.g., vat, corporate_income, payroll
    expression: str  # JSONLogic or simple expr string
    valid_from: date | None = None
    valid_to: date | None = None
    source: str | None = None


class Event(SQLModel, table=True):
    """Forecast-relevant event used for metadata enrichment."""

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime
    source: str
    title: str
    score: float | None = None  # relevance/intensity
