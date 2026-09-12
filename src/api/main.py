"""CareBridge FastAPI application factory and ASGI entrypoint.

Run with:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000

``create_app`` assembles middleware (request-id + size cap, CORS, rate limiting),
exception handlers, and all routers. The lifespan hook configures structured
logging, ensures the immutable audit DB exists, and seeds the demo user when
``DEMO_MODE=true`` and the users table is empty.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api import user_store
from src.api.config import Settings, get_settings
from src.api.middleware import (
    RequestIDMiddleware,
    http_exception_handler,
    rate_limit_exceeded_handler,
    setup_logging,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.api.rate_limit import limiter
from src.api.routers import ALL_ROUTERS

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle.

    Args:
        app: The FastAPI application.

    Yields:
        Control back to the ASGI server for the lifetime of the app.
    """
    settings: Settings = get_settings()
    setup_logging(settings)

    # Ensure the immutable audit trail exists. Uses the audit module's own
    # DB_PATH (which the test suite patches to a temp file) — never modified here.
    from src.models import audit_log

    try:
        audit_log.init_audit_db(audit_log.DB_PATH)
    except Exception as exc:  # pragma: no cover - only on a broken DB path
        logger.error("Audit DB init failed: %s", type(exc).__name__)

    # Users DB + demo bootstrap (SPEC section C).
    user_store.init_user_db()
    user_store.seed_demo_user(settings)

    # Seed realistic demo audit events (idempotent, DEMO_MODE only).
    from src.api.demo_seed import seed_demo_audit_events

    seed_demo_audit_events()

    logger.info(
        "CareBridge API started (env=%s demo_mode=%s version=%s)",
        settings.environment,
        settings.demo_mode,
        settings.app_version,
    )
    try:
        yield
    finally:
        logger.info("CareBridge API shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        A fully-wired ``FastAPI`` instance.
    """
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    # slowapi reads the limiter off app.state.
    app.state.limiter = limiter

    # --- Exception handlers (never leak stack traces; SPEC section E) --------
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # --- Middleware (last added == outermost) -------------------------------
    # Order (outermost -> innermost): RequestID -> CORS -> SlowAPI -> routes.
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(
        RequestIDMiddleware, max_request_bytes=settings.max_request_bytes
    )

    # --- Routers -------------------------------------------------------------
    for router in ALL_ROUTERS:
        app.include_router(router)

    return app


# Module-level ASGI app for `uvicorn src.api.main:app`.
app = create_app()
