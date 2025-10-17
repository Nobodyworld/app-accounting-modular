from __future__ import annotations
"""Database models used across Modular Accounting services."""

from typing import Any, Optional
from enum import Enum
from datetime import date, datetime

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

__all__ = [
    "Account",
    "AccountType",
    "Country",
    "Event",
    "StagedPosting",
    "StagedTransaction",
    "WorkflowStatus",
    "Instrument",
    "JournalEntry",
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


class Account(SQLModel, table=True):
    """Chart of accounts entry."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    code: Optional[str] = None
    type: AccountType
    currency: str = "USD"


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


class WorkflowStatus(str, Enum):
    """Processing state for staged transactions."""

    INGESTED = "INGESTED"
    VALIDATED = "VALIDATED"
    POSTED = "POSTED"
    FAILED = "FAILED"


class StagedTransaction(SQLModel, table=True):
    """Workflow-controlled transaction awaiting validation/posting."""

    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    description: str
    status: WorkflowStatus = Field(default=WorkflowStatus.INGESTED)
    source: str = Field(default="unknown")
    source_reference: Optional[str] = None
    source_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    validation_errors: Optional[list[str]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    transaction_id: Optional[int] = Field(default=None, foreign_key="transaction.id")
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class StagedPosting(SQLModel, table=True):
    """Individual staging record for a transaction posting."""

    id: Optional[int] = Field(default=None, primary_key=True)
    staged_transaction_id: int = Field(foreign_key="stagedtransaction.id")
    account_id: Optional[int] = None
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    debit: float = 0.0
    credit: float = 0.0
    currency: Optional[str] = None
    context: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )

