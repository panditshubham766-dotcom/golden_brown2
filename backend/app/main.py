"""
LexiGuard FastAPI application factory.

Startup sequence:
1. Generate per-launch bearer token.
2. Verify SQLite has FTS5.
3. Emit startup notice for reduced parser isolation on Windows/macOS.
4. Print the launch URL containing the one-time code fragment.
"""
from __future__ import annotations

import platform
import sys
import sqlite3
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.app.config import get_settings
from backend.app.security.tokens import TokenStore
from backend.app.security.headers import SecurityHeadersMiddleware, NoStoreCacheMiddleware

logger = logging.getLogger("lexiguard")

# ── Module-level singleton (imported by auth.py and security/tokens.py) ───────
token_store: TokenStore  # assigned in create_app()


def _check_fts5() -> None:
    """Fail fast if the bundled SQLite was built without FTS5."""
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE _fts5_check USING fts5(x)")
    except sqlite3.OperationalError as exc:
        logger.critical(
            "SQLite FTS5 is not available: %s. "
            "LexiGuard requires a SQLite build with FTS5 support. "
            "Install a Python built against a FTS5-enabled SQLite.",
            exc,
        )
        sys.exit(1)
    finally:
        con.close()


def _emit_parser_isolation_notice() -> None:
    """Warn on platforms where full parser sandbox limits are unavailable."""
    os_name = platform.system()
    if os_name == "Windows":
        logger.warning(
            "[SECURITY] Parser isolation: REDUCED. "
            "Windows does not have a `resource` module; "
            "only wall-clock timeout, output cap and page/size caps are enforced. "
            "No Job Object memory limit is currently implemented. "
            "See docs/SECURITY.md for details."
        )
    elif os_name == "Darwin":
        logger.warning(
            "[SECURITY] Parser isolation: REDUCED. "
            "macOS: RLIMIT_AS is not reliably enforced; "
            "an RSS watchdog is used instead. "
            "See docs/SECURITY.md for details."
        )


def create_app() -> FastAPI:
    global token_store

    settings = get_settings()

    # Ensure data directory exists.
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    # Warn if data dir looks like it could be inside a cloud-sync folder.
    data_str = str(settings.data_dir).lower()
    cloud_indicators = ("dropbox", "onedrive", "google drive", "icloud", "nextcloud")
    if any(ind in data_str for ind in cloud_indicators):
        logger.warning(
            "[PRIVACY] data_dir appears to be inside a cloud-sync folder (%s). "
            "Move it outside to prevent document leakage.",
            settings.data_dir,
        )

    # Generate per-launch token.
    token_store = TokenStore(
        bearer_token=settings.launch_token,
        code_ttl_seconds=float(settings.launch_code_ttl_seconds),
    )

    _check_fts5()
    _emit_parser_isolation_notice()

    app = FastAPI(
        title="LexiGuard",
        version="0.1.0.dev0",
        docs_url=None,   # disable Swagger UI in production
        redoc_url=None,
        openapi_url=None,
    )

    # ── Middleware ─────────────────────────────────────────────────────────────
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(NoStoreCacheMiddleware)

    # No wildcard CORS; only same-origin calls are expected.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://127.0.0.1:{settings.port}"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── API routes ─────────────────────────────────────────────────────────────
    from backend.app.api.health import router as health_router
    from backend.app.api.session import router as session_router
    from backend.app.api.documents import router as documents_router

    app.include_router(session_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(documents_router, prefix="/api")

    # ── Frontend static files (Phase 4+) ───────────────────────────────────────
    frontend_dist = Path("frontend/dist")
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    # ── Startup event: print launch URL ───────────────────────────────────────
    @app.on_event("startup")
    async def _on_startup() -> None:
        code = token_store.issue_launch_code()
        url = f"http://{settings.host}:{settings.port}/#k={code}"
        print(f"\n{'='*60}", flush=True)
        print(f"  LexiGuard is running.", flush=True)
        print(f"  Open this URL in your browser (valid for {settings.launch_code_ttl_seconds}s):", flush=True)
        print(f"  {url}", flush=True)
        print(f"{'='*60}\n", flush=True)
        logger.info("LexiGuard startup complete. Launch URL printed to stdout.")

    return app


app = create_app()
