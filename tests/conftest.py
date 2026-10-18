"""
pytest socket guard (Guide §11.4, Phase 1 requirement):
All non-setup tests must not make non-loopback network connections.

This conftest installs a global socket.connect patch that fails any
attempt to connect to a non-loopback address in test sessions.
"""
from __future__ import annotations

import socket
import pytest

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex

_LOOPBACK_PREFIXES = ("127.", "::1", "localhost")


def _is_loopback(addr: object) -> bool:
    if isinstance(addr, (tuple, list)) and len(addr) >= 1:
        host = str(addr[0])
        return any(host.startswith(p) or host == p for p in _LOOPBACK_PREFIXES)
    if isinstance(addr, str):
        return any(addr.startswith(p) for p in _LOOPBACK_PREFIXES)
    return False


def _guarded_connect(self: socket.socket, address: object) -> None:
    if not _is_loopback(address):
        raise ConnectionRefusedError(
            f"[SOCKET GUARD] Non-loopback connection attempt blocked in tests: {address!r}. "
            "LexiGuard tests must not make external network connections."
        )
    return _original_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: object) -> int:
    if not _is_loopback(address):
        raise ConnectionRefusedError(
            f"[SOCKET GUARD] Non-loopback connection attempt blocked in tests: {address!r}."
        )
    return _original_connect_ex(self, address)


@pytest.fixture(autouse=True, scope="session")
def socket_guard() -> None:
    """Block non-loopback connections for the entire test session."""
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
    yield
    socket.socket.connect = _original_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _original_connect_ex  # type: ignore[method-assign]
