"""API: /api/session — one-time launch-code exchange."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter()


class _ExchangeRequest(BaseModel):
    code: str


class _ExchangeResponse(BaseModel):
    token: str


@router.post("/session", response_model=_ExchangeResponse)
async def exchange_launch_code(body: _ExchangeRequest) -> _ExchangeResponse:
    """
    Exchange a one-time launch code (from the URL fragment) for the session token.

    The code is single-use and expires after `launch_code_ttl_seconds`.
    The token is held in JavaScript memory only — never in localStorage or cookies.

    T-SEC-BOOT-01: this endpoint must reject a used or expired code.
    """
    from backend.app.main import token_store

    token = token_store.exchange_code(body.code.strip())
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired or already-used launch code.",
        )
    return _ExchangeResponse(token=token)
