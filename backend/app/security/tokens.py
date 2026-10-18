"""Security: bearer-token management and per-launch session bootstrapping."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _OTC:
    """One-time launch code record."""
    code: str
    expires_at: float
    used: bool = False


class TokenStore:
    """
    Holds the per-launch bearer token and manages one-time codes.

    The bearer token is generated once at startup and never leaves the server
    except via the /api/session endpoint (which exchanges a one-time code for it).
    """

    def __init__(self, bearer_token: str, code_ttl_seconds: float = 60.0) -> None:
        self._token: str = bearer_token
        self._code_ttl: float = code_ttl_seconds
        self._codes: dict[str, _OTC] = {}
        self._lock = Lock()

    # ── One-time code ─────────────────────────────────────────────────────────

    def issue_launch_code(self) -> str:
        """Generate and store a new one-time launch code."""
        code = secrets.token_urlsafe(32)
        expires = time.monotonic() + self._code_ttl
        with self._lock:
            self._codes[code] = _OTC(code=code, expires_at=expires)
        return code

    def exchange_code(self, code: str) -> str | None:
        """
        Exchange a one-time code for the bearer token.

        Returns the bearer token on success, or None if the code is invalid,
        expired, or already used.
        """
        now = time.monotonic()
        with self._lock:
            otc = self._codes.get(code)
            if otc is None or otc.used or otc.expires_at < now:
                return None
            otc.used = True
        return self._token

    # ── Bearer token validation ────────────────────────────────────────────────

    def validate_token(self, token: str) -> bool:
        """Compare in constant time to resist timing attacks."""
        return hmac.compare_digest(
            self._token.encode(),
            token.encode(),
        )


def _get_token_store() -> "TokenStore":
    """Return the global TokenStore (created in main.py at startup)."""
    from backend.app.main import token_store  # imported lazily to avoid circular deps
    return token_store
