from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..db import get_session
from ..schemas import (
    AccountCreate,
    AccountRead,
    TransactionCreate,
    TransactionRead,
    TrialBalanceResponse,
    TrialBalanceRowSchema,
)
from ..services.ledger_service import LedgerService

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.post("/account", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, session: Session = Depends(get_session)) -> AccountRead:
    service = LedgerService(session)
    try:
        account = service.create_account(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AccountRead.model_validate(account)


@router.post("/post", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def post_transaction(payload: TransactionCreate, session: Session = Depends(get_session)) -> TransactionRead:
    service = LedgerService(session)
    try:
        transaction = service.post_transaction(
            date=payload.date,
            description=payload.description,
            postings=[posting.model_dump() for posting in payload.postings],
            external_ref=payload.external_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TransactionRead.model_validate(transaction)


@router.get("/trial-balance", response_model=TrialBalanceResponse)
def trial_balance(session: Session = Depends(get_session)) -> TrialBalanceResponse:
    service = LedgerService(session)
    summary = service.trial_balance()
    rows = [
        TrialBalanceRowSchema(
            account_id=row.account_id,
            account_code=row.account_code,
            account_name=row.account_name,
            account_type=row.account_type,
            currency=row.currency,
            debit=row.debit,
            credit=row.credit,
            balance=row.balance,
        )
        for row in summary["rows"]
    ]
    return TrialBalanceResponse(rows=rows, total_debit=summary["total_debit"], total_credit=summary["total_credit"])
