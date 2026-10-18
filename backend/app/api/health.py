"""API: /api/health — boolean-only health check (token-protected)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.security.auth import require_token

router = APIRouter()


class _HealthResponse(BaseModel):
    ok: bool
    fts5: bool


@router.get("/health", response_model=_HealthResponse)
async def health(_token: str = Depends(require_token)) -> _HealthResponse:
    """
    Return boolean health flags only.

    Never expose environment values, local paths, prompts, logs or DB contents.
    Token-protected per the spec (every /api/* route requires a valid bearer token).
    """
    import sqlite3

    fts5_ok = True
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE _h USING fts5(x)")
        con.close()
    except sqlite3.OperationalError:
        fts5_ok = False

    return _HealthResponse(ok=True, fts5=fts5_ok)
