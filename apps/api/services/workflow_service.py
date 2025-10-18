"""Workflow orchestration for staged ledger transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

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
    ) -> list[StagedTransaction]:
        """Persist raw transaction payloads into the staging tables."""

        staged_records: list[StagedTransaction] = []
        base_metadata = dict(metadata or {})

        for payload in transactions:
            txn_metadata = base_metadata.copy()
            txn_metadata.update(payload.get("metadata") or {})
            staged = StagedTransaction(
                date=payload["date"],
                description=str(payload["description"]),
                source=source,
                source_reference=payload.get("source_reference") or source_reference,
                source_metadata=txn_metadata,
            )
            self.s.add(staged)
            self.s.flush()

            postings = payload.get("postings") or []
            for posting in postings:
                staged_posting = StagedPosting(
                    staged_transaction_id=staged.id,
                    account_id=posting.get("account_id"),
                    account_code=posting.get("account_code"),
                    account_name=posting.get("account_name"),
                    debit=float(posting.get("debit", 0.0) or 0.0),
                    credit=float(posting.get("credit", 0.0) or 0.0),
                    currency=posting.get("currency"),
                    context=dict(posting.get("metadata") or {}),
                )
                self.s.add(staged_posting)

            staged_records.append(staged)

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
        if staged_ids:
            stmt = stmt.where(StagedTransaction.id.in_(staged_ids))
        stmt = stmt.order_by(StagedTransaction.id)

        staged_items = list(self.s.exec(stmt))
        results: list[WorkflowResult] = []

        for staged in staged_items:
            if staged.status == WorkflowStatus.POSTED and staged.transaction_id and auto_post:
                results.append(
                    WorkflowResult(
                        staged_transaction_id=staged.id,
                        status=WorkflowStatus.POSTED,
                        transaction_id=staged.transaction_id,
                        validation_errors=None,
                    )
                )
                continue

            postings = self._load_postings(staged.id)

            try:
                payload = self._prepare_postings(postings)
                normalised = self.ledger.validate_transaction(
                    staged.date, staged.description, payload
                )
            except ValueError as exc:
                staged.status = WorkflowStatus.FAILED
                staged.validation_errors = [str(exc)]
                staged.updated_at = datetime.now(timezone.utc)
                self.s.add(staged)
                results.append(
                    WorkflowResult(
                        staged_transaction_id=staged.id,
                        status=WorkflowStatus.FAILED,
                        transaction_id=staged.transaction_id,
                        validation_errors=staged.validation_errors,
                    )
                )
                continue

            staged.validation_errors = None
            staged.status = WorkflowStatus.VALIDATED
            staged.updated_at = datetime.now(timezone.utc)
            self.s.add(staged)

            for posting, normalised_posting in zip(postings, normalised, strict=True):
                posting.account_id = normalised_posting["account_id"]
                posting.debit = normalised_posting["debit"]
                posting.credit = normalised_posting["credit"]
                posting.currency = normalised_posting["currency"]
                self.s.add(posting)
            # TODO - Persist validation diagnostics for review in audit trails.

            if not auto_post:
                results.append(
                    WorkflowResult(
                        staged_transaction_id=staged.id,
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
                    staged.updated_at = datetime.now(timezone.utc)
                    self.s.add(staged)
                    results.append(
                        WorkflowResult(
                            staged_transaction_id=staged.id,
                            status=WorkflowStatus.POSTED,
                            transaction_id=transaction_id,
                            validation_errors=None,
                        )
                    )
                    continue

            transaction = self.ledger.post_transaction(
                staged.date, staged.description, normalised
            )
            staged.transaction_id = transaction.id
            staged.status = WorkflowStatus.POSTED
            staged.updated_at = datetime.now(timezone.utc)
            self.s.add(staged)

            results.append(
                WorkflowResult(
                    staged_transaction_id=staged.id,
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
    def get_transaction(
        self, staged_id: int
    ) -> tuple[StagedTransaction, list[StagedPosting]] | None:
        """Return a staged transaction and its postings."""

        staged = self.s.get(StagedTransaction, staged_id)
        if staged is None:
            return None
        postings = self._load_postings(staged_id)
        return staged, postings

    def list_transactions(
        self, limit: int = 100
    ) -> list[tuple[StagedTransaction, list[StagedPosting]]]:
        """Return staged transactions ordered by creation time."""

        stmt = select(StagedTransaction).order_by(StagedTransaction.id).limit(limit)
        items = []
        for staged in self.s.exec(stmt):
            items.append((staged, self._load_postings(staged.id)))
        return items

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _load_postings(self, staged_id: int) -> list[StagedPosting]:
        stmt = (
            select(StagedPosting)
            .where(StagedPosting.staged_transaction_id == staged_id)
            .order_by(StagedPosting.id)
        )
        return list(self.s.exec(stmt))

    def _prepare_postings(
        self, postings: Sequence[StagedPosting]
    ) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for idx, posting in enumerate(postings, start=1):
            account_id = posting.account_id
            if account_id is None:
                identifier = posting.account_code or posting.account_name
                if not identifier:
                    raise ValueError(
                        f"Posting {idx}: account reference (id or code/name) is required"
                    )
                try:
                    account = self.ledger.require_account(identifier)
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc
                account_id = account.id
                posting.account_id = account_id

            payload.append(
                {
                    "account_id": account_id,
                    "debit": posting.debit,
                    "credit": posting.credit,
                    "currency": posting.currency,
                }
            )
        # TODO - Validate currency consistency across postings before posting.
        return payload
