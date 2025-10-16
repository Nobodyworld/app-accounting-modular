from fastapi import APIRouter, Depends
from ..db import get_session
from sqlmodel import Session
from ..services.plugin_loader import available_plugins

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/providers")
def providers():
    return {"available": available_plugins()}
