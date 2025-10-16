from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..db import get_session
from ..services.ledger_service import LedgerService

router = APIRouter(prefix="/ledger", tags=["ledger"])

@router.post("/account")
def create_account(payload: dict, s: Session = Depends(get_session)):
    ls = LedgerService(s)
    return ls.create_account(**payload)

@router.post("/post")
def post_transaction(payload: dict, s: Session = Depends(get_session)):
    ls = LedgerService(s)
    return ls.post_transaction(payload["date"], payload["description"], payload["postings"])

@router.get("/trial-balance")
def trial_balance(s: Session = Depends(get_session)):
    ls = LedgerService(s)
    return ls.trial_balance()
