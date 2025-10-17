"""Ledger-related API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..models.models import Account, Transaction
from ..schemas import AccountCreate, TransactionCreate, TrialBalanceResponse
from ..services.ledger_service import LedgerService

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.post("/account", response_model=Account)
def create_account(payload: AccountCreate, s: Session = Depends(get_session)) -> Account:
    """Create a new ledger account."""

    ls = LedgerService(s)
    return ls.create_account(**payload.model_dump())


@router.post("/post", response_model=Transaction)
def post_transaction(
    payload: TransactionCreate, s: Session = Depends(get_session)
) -> Transaction:
    """Persist a balanced journal transaction."""

    ls = LedgerService(s)
    return ls.post_transaction(
        payload.date,
        payload.description,
        list(payload.ledger_payload()),
    )


@router.get("/trial-balance", response_model=TrialBalanceResponse)
def trial_balance(s: Session = Depends(get_session)) -> TrialBalanceResponse:
    """Return the current trial balance across all accounts."""

    ls = LedgerService(s)
    return TrialBalanceResponse.from_service(ls.trial_balance())
