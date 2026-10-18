"""Security: Host and Origin header validation."""
from __future__ import annotations

from fastapi import HTTPException, Request, status


def check_host(request: Request, allowed_host: str, allowed_port: int) -> None:
    """
    Reject requests whose Host header does not match the configured binding.

    Reduces DNS-rebinding risk: an attacker page served from a public domain
    cannot reach the API even if the browser follows a rebinding trick, because
    the Host header will not match.
    """
    host_header = request.headers.get("host", "")
    allowed = {
        f"127.0.0.1:{allowed_port}",
        f"localhost:{allowed_port}",
        allowed_host if ":" in allowed_host else f"{allowed_host}:{allowed_port}",
    }
    if host_header not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Host header.",
        )


def check_origin(request: Request, allowed_origin: str) -> None:
    """
    For state-changing requests, validate the Origin header.

    If Origin is present it must exactly match the allowed origin.
    If it is absent the request passes (non-browser clients, curl, tests).
    """
    origin = request.headers.get("origin")
    if origin is not None and origin != allowed_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed.",
        )
