"""Domain primitives for portable accounting workflows."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(slots=True)
class Money:
    """Amount represented in a given currency.

    Parameters
    ----------
    amount:
        Decimal value of the monetary amount.
    currency:
        ISO 4217 currency code.
    """

    amount: Decimal
    currency: str


@dataclass(slots=True)
class FXRate:
    """Foreign exchange rate between two currencies.

    Parameters
    ----------
    base_currency:
        ISO 4217 code for the base currency.
    quote_currency:
        ISO 4217 code for the quote currency.
    rate:
        Conversion factor from the base to the quote currency.
    as_of:
        Timestamp when the rate was observed.
    """

    base_currency: str
    quote_currency: str
    rate: Decimal
    as_of: datetime


@dataclass(slots=True)
class CommodityQuote:
    """Snapshot price for a commodity instrument.

    Parameters
    ----------
    symbol:
        Identifier of the commodity instrument (e.g., ``XAU``).
    price:
        Price expressed as a :class:`Money` instance.
    as_of:
        Timestamp describing when the quote was captured.
    """

    symbol: str
    price: Money
    as_of: datetime


@dataclass(slots=True)
class TaxRule:
    """Jurisdiction-specific tax rule description.

    Parameters
    ----------
    jurisdiction:
        Tax jurisdiction code or slug.
    rate:
        Percentage rate expressed as a Decimal fraction (e.g., ``Decimal("0.2")``).
    description:
        Human-readable description of the tax rule.
    effective_from:
        Date when the rule becomes effective.
    effective_to:
        Optional end date when the rule expires.
    """

    jurisdiction: str
    rate: Decimal
    description: str
    effective_from: date
    effective_to: date | None = None


@dataclass(slots=True)
class LedgerEntry:
    """Individual ledger posting within a transaction.

    Parameters
    ----------
    account_code:
        Identifier for the ledger account.
    amount:
        Positive monetary magnitude applied to the account.
    direction:
        Either ``"debit"`` or ``"credit"``.
    """

    account_code: str
    amount: Money
    direction: str

    def __post_init__(self) -> None:
        direction = self.direction.strip().lower()
        if direction not in {"debit", "credit"}:
            raise ValueError("Ledger entry direction must be 'debit' or 'credit'")
        if self.amount.amount <= Decimal("0"):
            raise ValueError("Ledger entry amount must be positive")
        currency = self.amount.currency.strip().upper()
        if not currency:
            raise ValueError("Ledger entry currency is required")
        self.direction = direction
        self.amount.currency = currency


@dataclass(slots=True)
class Transaction:
    """Accounting transaction composed of balanced ledger entries.

    Parameters
    ----------
    transaction_id:
        Unique identifier for the transaction.
    occurred_on:
        Date when the transaction occurred.
    description:
        Free-form narrative describing the transaction.
    entries:
        Iterable of :class:`LedgerEntry` values making up the posting.
    """

    transaction_id: str
    occurred_on: date
    description: str
    entries: list[LedgerEntry] = field(default_factory=list)

    def is_balanced(self) -> bool:
        """Determine whether each currency in the transaction balances.

        Returns
        -------
        bool
            ``True`` only when at least two valid entries exist and every
            currency has equal debit and credit magnitudes.
        """

        if len(self.entries) < 2:
            return False

        totals: dict[str, Decimal] = {}
        for entry in self.entries:
            direction = entry.direction.strip().lower()
            currency = entry.amount.currency.strip().upper()
            amount = entry.amount.amount
            if direction not in {"debit", "credit"} or not currency or amount <= Decimal("0"):
                return False
            signed_amount = amount if direction == "debit" else -amount
            totals[currency] = totals.get(currency, Decimal("0")) + signed_amount

        return bool(totals) and all(total == Decimal("0") for total in totals.values())

    def add_entry(self, entry: LedgerEntry) -> None:
        """Append an entry to the transaction.

        Parameters
        ----------
        entry:
            Ledger posting to append.
        """

        self.entries.append(entry)

    def accounts(self) -> Iterable[str]:
        """Iterate over the accounts referenced in the transaction.

        Yields
        ------
        str
            Account codes included in the transaction.
        """

        for entry in self.entries:
            yield entry.account_code
