from __future__ import annotations
from typing import Optional, Literal
from datetime import date, datetime
from sqlmodel import SQLModel, Field, Relationship

AccountType = Literal["ASSET","LIABILITY","EQUITY","REVENUE","EXPENSE"]

class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    code: Optional[str] = None
    type: AccountType
    currency: str = "USD"

class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    description: str
    external_ref: Optional[str] = None

class JournalEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "USD"

class Instrument(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str
    name: Optional[str] = None
    type: str = "equity"  # equity/etf/commodity/currency

class Price(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    date: date
    close: float
    provider: str

class Rate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    base: str
    quote: str
    date: date
    value: float
    provider: str

class Country(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    iso2: str
    name: str

class TaxRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    jurisdiction: str  # e.g., US-FED, EU-IE
    scope: str         # e.g., vat, corporate_income, payroll
    expression: str    # JSONLogic or simple expr string
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source: Optional[str] = None

class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime
    source: str
    title: str
    score: Optional[float] = None  # relevance/intensity
