"""Workflow orchestration for staged ledger transactions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import uuid4

from sqlmodel import Session, select

from ..audit import apply_creation_metadata, get_current_actor
from ..models.models import (
    Account,
    AuditAction,
    AuditLog,
    JournalEntry,
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
        """Persist raw transaction payloads into the staging tables atomically."""

        staged_records: list[StagedTransaction] = []
        base_metadata = dict(metadata or {})

        try:
            for payload in transactions:
                txn_metadata = base_metadata.copy()
                meta_obj = payload.get("metadata")
                if isinstance(meta_obj, Mapping):
                    txn_metadata.update(meta_obj)
                elif meta_obj is not None:
                    raise ValueError("transaction metadata must be a mapping")

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
                posting_payloads = self._normalise_ingest_postings(payload.get("postings") or [])

                existing = self._find_by_source_reference(source, resolved_source_reference)
                if existing is not None:
                    self._assert_idempotent_payload(
                        existing,
                        txn_date=txn_date,
                        description=description,
                        metadata=txn_metadata,
                        postings=posting_payloads,
                    )
                    staged_records.append(existing)
                    continue

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

                for posting in posting_payloads:
                    self.s.add(
                        StagedPosting(
                            staged_transaction_id=staged_id,
                            account_id=cast(int | None, posting["account_id"]),
                            account_code=cast(str | None, posting["account_code"]),
                            account_name=cast(str | None, posting["account_name"]),
                            debit=cast(float, posting["debit"]),
                            credit=cast(float, posting["credit"]),
                            currency=cast(str | None, posting["currency"]),
                            context=cast(dict[str, object], posting["context"]),
                        )
                    )

                staged_records.append(staged)
                if chunk_size > 0 and len(staged_records) % chunk_size == 0:
                    self.s.flush()

            self.s.commit()
        except Exception:
            self.s.rollback()
            raise

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
        """Validate and optionally post staged transactions independently."""

        stmt = select(StagedTransaction)
        staged_id_col = cast(Any, StagedTransaction.id)
        if staged_ids:
            stmt = stmt.where(staged_id_col.in_(staged_ids))
        stmt = stmt.order_by(staged_id_col)

        staged_items = list(self.s.exec(stmt))
        results: list[WorkflowResult] = []

        for staged in staged_items:
            staged_id = self._require_int(staged.id, "staged transaction")
            previous_status = staged.status
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
                payload, organization_id = self._prepare_postings(postings)
                ledger = LedgerService(self.s, organization_id=organization_id)
                normalised = ledger.validate_transaction(staged.date, staged.description, payload)
            except ValueError as exc:
                error = str(exc)
                staged.status = WorkflowStatus.FAILED
                staged.validation_errors = [error]
                staged.ingest_diagnostics = {
                    "error": error,
                    "stage": "validation",
                    "postings": [posting.context for posting in postings],
                }
                staged.updated_at = datetime.now(UTC)
                self.s.add(staged)
                self._stage_workflow_audit(
                    staged,
                    previous_status=previous_status,
                    event="rejected",
                    organization_id=None,
                )
                self.s.commit()
                results.append(self._result_from_staged(staged))
                continue

            staged.validation_errors = None
            staged.ingest_diagnostics = {}
            staged.status = WorkflowStatus.VALIDATED
            staged.updated_at = datetime.now(UTC)
            self.s.add(staged)

            for posting, normalised_posting in zip(postings, normalised, strict=True):
                account_value = cast(int | str, normalised_posting["account_id"])
                posting.account_id = self._require_int(int(account_value), "normalised posting account")
                posting.debit = float(cast(Any, normalised_posting["debit"]))
                posting.credit = float(cast(Any, normalised_posting["credit"]))
                posting.currency = str(cast(Any, normalised_posting["currency"]))
                self.s.add(posting)

            if not auto_post:
                event = "revalidated" if previous_status == WorkflowStatus.FAILED else "validated"
                self._stage_workflow_audit(
                    staged,
                    previous_status=previous_status,
                    event=event,
                    organization_id=organization_id,
                )
                self.s.commit()
                results.append(self._result_from_staged(staged))
                continue

            transaction_id = staged.transaction_id
            if transaction_id:
                existing = self.s.get(Transaction, transaction_id)
                if existing is not None:
                    staged.status = WorkflowStatus.POSTED
                    staged.updated_at = datetime.now(UTC)
                    self.s.add(staged)
                    event = "retried" if previous_status == WorkflowStatus.FAILED else "posted"
                    self._stage_workflow_audit(
                        staged,
                        previous_status=previous_status,
                        event=event,
                        organization_id=organization_id,
                    )
                    self.s.commit()
                    results.append(self._result_from_staged(staged))
                    continue

            try:
                transaction = self._stage_transaction(
                    staged,
                    normalised,
                    organization_id=organization_id,
                )
                staged.transaction_id = transaction.id
                staged.status = WorkflowStatus.POSTED
                staged.updated_at = datetime.now(UTC)
                self.s.add(staged)
                event = "retried" if previous_status == WorkflowStatus.FAILED else "posted"
                self._stage_workflow_audit(
                    staged,
                    previous_status=previous_status,
                    event=event,
                    organization_id=organization_id,
                )
                self.s.commit()
            except Exception as exc:
                self.s.rollback()
                failed = self.s.get(StagedTransaction, staged_id)
                if failed is None:
                    raise
                error = f"Posting failed: {exc}"
                failed.status = WorkflowStatus.FAILED
                failed.validation_errors = [error]
                failed.ingest_diagnostics = {
                    "error": str(exc),
                    "stage": "posting",
                }
                failed.updated_at = datetime.now(UTC)
                self.s.add(failed)
                self._stage_workflow_audit(
                    failed,
                    previous_status=previous_status,
                    event="posting_failed",
                    organization_id=organization_id,
                )
                self.s.commit()
                results.append(self._result_from_staged(failed))
                continue

            results.append(self._result_from_staged(staged))

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
    def _normalise_ingest_postings(self, raw_postings: object) -> list[dict[str, object]]:
        if not isinstance(raw_postings, Iterable) or isinstance(raw_postings, (str, bytes)):
            raise ValueError("postings must be iterable")

        postings: list[dict[str, object]] = []
        for posting in raw_postings:
            if not isinstance(posting, Mapping):
                raise ValueError("posting must be a mapping")
            account_id_value = posting.get("account_id")
            account_id = (
                int(account_id_value)
                if isinstance(account_id_value, int) and not isinstance(account_id_value, bool)
                else None
            )
            metadata = posting.get("metadata")
            if metadata is not None and not isinstance(metadata, Mapping):
                raise ValueError("posting metadata must be a mapping")
            postings.append(
                {
                    "account_id": account_id,
                    "account_code": posting.get("account_code"),
                    "account_name": posting.get("account_name"),
                    "debit": float(posting.get("debit", 0.0) or 0.0),
                    "credit": float(posting.get("credit", 0.0) or 0.0),
                    "currency": posting.get("currency"),
                    "context": dict(cast(Mapping[str, object], metadata or {})),
                }
            )
        return postings

    def _find_by_source_reference(self, source: str, source_reference: str | None) -> StagedTransaction | None:
        if source_reference is None:
            return None
        stmt = (
            select(StagedTransaction)
            .where(StagedTransaction.source == source)
            .where(StagedTransaction.source_reference == source_reference)
            .order_by(StagedTransaction.id)  # type: ignore[arg-type]
        )
        return self.s.exec(stmt).first()

    def _assert_idempotent_payload(
        self,
        existing: StagedTransaction,
        *,
        txn_date: date,
        description: str,
        metadata: dict[str, object],
        postings: list[dict[str, object]],
    ) -> None:
        existing_id = self._require_int(existing.id, "staged transaction")
        existing_postings = self._load_postings(existing_id)
        existing_payload = [
            {
                "account_id": posting.account_id,
                "account_code": posting.account_code,
                "account_name": posting.account_name,
                "debit": float(posting.debit),
                "credit": float(posting.credit),
                "currency": posting.currency,
                "context": posting.context,
            }
            for posting in existing_postings
        ]
        if (
            existing.date != txn_date
            or existing.description != description
            or existing.source_metadata != metadata
            or existing_payload != postings
        ):
            reference = existing.source_reference or "<none>"
            raise ValueError(f"source reference '{reference}' already exists with different payload")

    def _load_postings(self, staged_id: int) -> list[StagedPosting]:
        stmt = (
            select(StagedPosting)
            .where(StagedPosting.staged_transaction_id == staged_id)
            .order_by(StagedPosting.id)  # type: ignore[arg-type]
        )
        return list(self.s.exec(stmt))

    def _prepare_postings(
        self, postings: Sequence[StagedPosting]
    ) -> tuple[list[dict[str, object]], int | None]:
        payload: list[dict[str, object]] = []
        currencies: set[str] = set()
        organization_ids: set[int | None] = set()

        for idx, posting in enumerate(postings, start=1):
            account = self._resolve_account(posting, idx)
            account_id = self._require_int(account.id, "posting account")
            posting.account_id = account_id
            organization_ids.add(account.organization_id)

            if posting.currency:
                currencies.add(posting.currency)

            payload.append(
                {
                    "account_id": account_id,
                    "debit": float(posting.debit),
                    "credit": float(posting.credit),
                    "currency": posting.currency,
                }
            )

        if len(organization_ids) > 1:
            raise ValueError("All postings in a staged transaction must belong to a single organization")
        if len(currencies) > 1:
            raise ValueError("Currency mismatch across postings")

        organization_id = next(iter(organization_ids), None)
        return payload, organization_id

    def _resolve_account(self, posting: StagedPosting, index: int) -> Account:
        if posting.account_id is not None:
            account = self.s.get(Account, posting.account_id)
            if account is None:
                raise ValueError(f"account {posting.account_id} not found")
            return account

        identifier = posting.account_code or posting.account_name
        if not identifier:
            raise ValueError(f"Posting {index}: account reference (id or code/name) is required")

        stmt = select(Account)
        if posting.account_code:
            stmt = stmt.where(Account.code == posting.account_code)
        else:
            stmt = stmt.where(Account.name == posting.account_name)
        accounts = list(self.s.exec(stmt))
        if not accounts:
            raise ValueError(f"account {identifier} not found")
        if len(accounts) > 1:
            raise ValueError(f"account reference '{identifier}' is ambiguous across organizations")
        return accounts[0]

    def _stage_transaction(
        self,
        staged: StagedTransaction,
        normalised: Sequence[dict[str, object]],
        *,
        organization_id: int | None,
    ) -> Transaction:
        transaction = Transaction(
            date=staged.date,
            description=staged.description.strip(),
            organization_id=organization_id,
            external_ref=staged.source_reference,
        )
        apply_creation_metadata(transaction)
        self.s.add(transaction)
        self.s.flush()
        transaction_id = self._require_int(transaction.id, "transaction")

        for posting in normalised:
            self.s.add(
                JournalEntry(
                    transaction_id=transaction_id,
                    account_id=int(cast(Any, posting["account_id"])),
                    debit=float(cast(Any, posting["debit"])),
                    credit=float(cast(Any, posting["credit"])),
                    currency=str(cast(Any, posting["currency"])),
                )
            )

        self._stage_audit(
            AuditAction.CREATE,
            "Transaction",
            transaction_id,
            after={
                "date": transaction.date.isoformat(),
                "description": transaction.description,
                "source": staged.source,
                "source_reference": staged.source_reference,
                "organization_id": organization_id,
                "postings": [
                    {
                        "account_id": posting["account_id"],
                        "debit": float(cast(Any, posting["debit"])),
                        "credit": float(cast(Any, posting["credit"])),
                        "currency": posting["currency"],
                    }
                    for posting in normalised
                ],
            },
            metadata={"staged_transaction_id": staged.id},
        )
        return transaction

    def _stage_workflow_audit(
        self,
        staged: StagedTransaction,
        *,
        previous_status: WorkflowStatus,
        event: str,
        organization_id: int | None,
    ) -> None:
        self._stage_audit(
            AuditAction.UPDATE,
            "StagedTransaction",
            staged.id,
            before={"status": previous_status.value},
            after={
                "status": staged.status.value,
                "transaction_id": staged.transaction_id,
                "validation_errors": staged.validation_errors,
            },
            metadata={
                "event": event,
                "source": staged.source,
                "source_reference": staged.source_reference,
                "organization_id": organization_id,
            },
        )

    def _stage_audit(
        self,
        action: AuditAction,
        entity_name: str,
        entity_id: int | None,
        *,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        actor = get_current_actor()
        before_state = before or None
        after_state = after or None
        before_map = before or {}
        after_map = after or {}
        payload_diff = {
            key: {"before": before_map.get(key), "after": after_map.get(key)}
            for key in sorted(set(before_map) | set(after_map))
            if before_map.get(key) != after_map.get(key)
        }
        self.s.add(
            AuditLog(
                ts=datetime.now(UTC),
                action=action,
                entity_name=entity_name,
                entity_id=str(entity_id) if entity_id is not None else None,
                before_state=before_state,
                after_state=after_state,
                payload_diff=payload_diff or None,
                request_id=actor.request_id if actor else str(uuid4()),
                actor_user_id=actor.user_id if actor else None,
                actor_org_id=actor.organization_id if actor else None,
                actor_label=actor.user_label if actor else None,
                source=actor.source if actor else None,
                context=metadata,
            )
        )

    @staticmethod
    def _result_from_staged(staged: StagedTransaction) -> WorkflowResult:
        if staged.id is None:
            raise ValueError("staged transaction missing identifier")
        return WorkflowResult(
            staged_transaction_id=staged.id,
            status=staged.status,
            transaction_id=staged.transaction_id,
            validation_errors=staged.validation_errors,
        )
