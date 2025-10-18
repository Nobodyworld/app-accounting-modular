"""Authentication routes for issuing JWT access tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from ..db import get_session
from ..security import authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Exchange username/password credentials for a bearer token."""

    user = authenticate_user(session, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    # TODO - Enforce login throttling or MFA challenges for repeated failures.
    token = create_access_token({"sub": str(user.id)})
    # TODO - Issue refresh tokens to support longer-lived sessions securely.
    return {"access_token": token, "token_type": "bearer"}
