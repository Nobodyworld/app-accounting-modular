"""Workflow orchestration for staged ledger transactions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlmodel import Session, select

from ..models.models import (
    StagedPosting,
    StagedTransaction,
    Transaction,
    WorkflowStatus,
)
from .ledger_service import LedgerService


@dataclass(slots=True, frozen=True)
class WorkflowResult:
    """Outcome for a staged transaction after processing."""

    staged_transaction_id: int
    status: WorkflowStatus
    transaction_id: int | None
    validation_errors: list[str] | None


class WorkflowService:
    """Service responsible for staging, validating, and posting transactions."""

    def __init__(self, session: Session):
        self.s = session
        self.ledger = LedgerService(session)

    @staticmethod
    def _require_int(value: int | None, context: str) -> int:
        if value is None:
            raise ValueError(f"{context} missing identifier")
        return int(value)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def ingest_transactions(
        self,
        transactions: Iterable[Mapping[str, object]],
        *,
        source: str,
        source_reference: str | None = None,
        metadata: Mapping[str, object] | None = None,
        chunk_size: int = 500,
    ) -> list[StagedTransaction]:
        """Persist raw transaction payloads into the staging tables."""

        staged_records: list[StagedTransaction] = []
        base_metadata = dict(metadata or {})

        for payload in transactions:
            txn_metadata = base_metadata.copy()
            meta_obj = payload.get("metadata")
            if isinstance(meta_obj, Mapping):
                txn_metadata.update(meta_obj)

            raw_date = payload.get("date")
            txn_date: date
            if isinstance(raw_date, date):
                txn_date = raw_date
            elif isinstance(raw_date, str):
                txn_date = date.fromisoformat(raw_date)
            else:
                raise ValueError("transaction date is required")

            raw_description = payload.get("description")
            description = str(raw_description or "")
            payload_source_reference = payload.get("source_reference")
            resolved_source_reference: str | None = (
                payload_source_reference if isinstance(payload_source_reference, str) else source_reference
            )
            staged = StagedTransaction(
                date=txn_date,
                description=description,
                source=source,
                source_reference=resolved_source_reference,
                source_metadata=txn_metadata,
            )
            self.s.add(staged)
            self.s.flush()
            staged_id = self._require_int(staged.id, "staged transaction")

            postings = payload.get("postings") or []
            if not isinstance(postings, Iterable):
                raise ValueError("postings must be iterable")
            for posting in postings:
                if not isinstance(posting, Mapping):
                    raise ValueError("posting must be a mapping")
                account_id_value = posting.get("account_id")
                account_id = int(account_id_value) if isinstance(account_id_value, int) else None
                debit_value = posting.get("debit", 0.0)
                credit_value = posting.get("credit", 0.0)
                staged_posting = StagedPosting(
                    staged_transaction_id=staged_id,
                    account_id=account_id,
                    account_code=posting.get("account_code"),
                    account_name=posting.get("account_name"),
                    debit=float(debit_value or 0.0),
                    credit=float(credit_value or 0.0),
                    currency=posting.get("currency"),
                    context=dict(posting.get("metadata") or {}),
                )
                self.s.add(staged_posting)

            staged_records.append(staged)
            if chunk_size > 0 and len(staged_records) % chunk_size == 0:
                self.s.commit()

        self.s.commit()
        # TODO - Introduce chunked commits for very large ingestion batches.
        return staged_records

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def process_transactions(
        self,
        staged_ids: Sequence[int] | None = None,
        *,
        auto_post: bool = True,
    ) -> list[WorkflowResult]:
        """Validate and optionally post staged transactions."""

        stmt = select(StagedTransaction)
        staged_id_col = cast(Any, StagedTransaction.id)
        if staged_ids:
            stmt = stmt.where(staged_id_col.in_(staged_ids))
        stmt = stmt.order_by(staged_id_col)

        staged_items = list(self.s.exec(stmt))
        results: list[WorkflowResult] = []

        for staged in staged_items:
            staged_id = self._require_int(staged.id, "staged transaction")
            if staged.status == WorkflowStatus.POSTED and staged.transaction_id and auto_post:
                results.append(
                    WorkflowResult(
                        staged_transaction_id=staged_id,
                        status=WorkflowStatus.POSTED,
                        transaction_id=staged.transaction_id,
                        validation_errors=None,
                    )
                )
                continue

            postings = self._load_postings(staged_id)

            try:
                payload = self._prepare_postings(postings)
                normalised = self.ledger.validate_transaction(staged.date, staged.description, payload)
            except ValueError as exc:
                staged.status = WorkflowStatus.FAILED
                staged.validation_errors = [str(exc)]
                staged.ingest_diagnostics = {
                    "error": str(exc),
                    "postings": [posting.context for posting in postings],
                }
                staged.updated_at = datetime.now(UTC)
                self.s.add(staged)
                results.append(
                    WorkflowResult(
                        staged_transaction_id=staged_id,
                        status=WorkflowStatus.FAILED,
                        transaction_id=staged.transaction_id,
                        validation_errors=staged.validation_errors,
                    )
                )
                continue

            staged.validation_errors = None
            staged.ingest_diagnostics = {}
            staged.status = WorkflowStatus.VALIDATED
            staged.updated_at = datetime.now(UTC)
            self.s.add(staged)

            for posting, normalised_posting in zip(postings, normalised, strict=True):
                account_value = cast(int | str, normalised_posting["account_id"])
                posting.account_id = self._require_int(int(account_value), "normalised posting account")
                debit_value = cast(Any, normalised_posting["debit"])
                credit_value = cast(Any, normalised_posting["credit"])
                currency_value = cast(Any, normalised_posting["currency"])
                posting.debit = float(debit_value)
                posting.credit = float(credit_value)
                posting.currency = str(currency_value)
                self.s.add(posting)
            # TODO - Persist validation diagnostics for review in audit trails.

            if not auto_post:
                results.append(
                    WorkflowResult(
                        staged_transaction_id=staged_id,
                        status=staged.status,
                        transaction_id=staged.transaction_id,
                        validation_errors=None,
                    )
                )
                continue

            transaction_id = staged.transaction_id
            if transaction_id:
                existing = self.s.get(Transaction, transaction_id)
                if existing is not None:
                    staged.status = WorkflowStatus.POSTED
                    staged.updated_at = datetime.now(UTC)
                    self.s.add(staged)
                    results.append(
                        WorkflowResult(
                            staged_transaction_id=staged_id,
                            status=WorkflowStatus.POSTED,
                            transaction_id=transaction_id,
                            validation_errors=None,
                        )
                    )
                    continue

            transaction = self.ledger.post_transaction(staged.date, staged.description, normalised)
            staged.transaction_id = transaction.id
            staged.status = WorkflowStatus.POSTED
            staged.updated_at = datetime.now(UTC)
            self.s.add(staged)

            results.append(
                WorkflowResult(
                    staged_transaction_id=staged_id,
                    status=WorkflowStatus.POSTED,
                    transaction_id=transaction.id,
                    validation_errors=None,
                )
            )

        self.s.commit()
        return results

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_transaction(self, staged_id: int) -> tuple[StagedTransaction, list[StagedPosting]] | None:
        """Return a staged transaction and its postings."""

        staged = self.s.get(StagedTransaction, staged_id)
        if staged is None:
            return None
        postings = self._load_postings(staged_id)
        return staged, postings

    def list_transactions(
        self, limit: int = 100, offset: int = 0
    ) -> list[tuple[StagedTransaction, list[StagedPosting]]]:
        """Return staged transactions ordered by creation time."""

        stmt = (
            select(StagedTransaction)
            .order_by(StagedTransaction.id)  # type: ignore[arg-type]
            .offset(offset)
            .limit(limit)
        )
        items = []
        for staged in self.s.exec(stmt):
            staged_id = self._require_int(staged.id, "staged transaction")
            items.append((staged, self._load_postings(staged_id)))
        return items

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _load_postings(self, staged_id: int) -> list[StagedPosting]:
        stmt = (
            select(StagedPosting).where(StagedPosting.staged_transaction_id == staged_id).order_by(StagedPosting.id)  # type: ignore[arg-type]
        )
        return list(self.s.exec(stmt))

    def _prepare_postings(self, postings: Sequence[StagedPosting]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        currencies: set[str] = set()
        for idx, posting in enumerate(postings, start=1):
            account_id = posting.account_id
            if account_id is None:
                identifier = posting.account_code or posting.account_name
                if not identifier:
                    raise ValueError(f"Posting {idx}: account reference (id or code/name) is required")
                try:
                    account = self.ledger.require_account(identifier)
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc
                account_id = account.id
                posting.account_id = account_id

            if posting.currency:
                currencies.add(posting.currency)

            payload.append(
                {
                    "account_id": self._require_int(account_id, "posting account"),
                    "debit": float(posting.debit),
                    "credit": float(posting.credit),
                    "currency": posting.currency,
                }
            )
        if len(currencies) > 1:
            raise ValueError("Currency mismatch across postings")
        return payload
