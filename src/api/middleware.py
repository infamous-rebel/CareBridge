"""Middleware and observability wiring (SPEC section E).

Provides:
- Context vars + a ``LogRecordFactory`` that stamp ``request_id`` and ``user_id``
  onto *every* log record (so all handlers — including pytest's caplog — see
  them, avoiding the child-logger filter-propagation gotcha).
- ``RequestIDMiddleware``: assigns/propagates a per-request UUID, injects it into
  logs and the ``X-Request-ID`` response header, and enforces the 1 MB body cap.
- ``setup_logging``: structured JSON logging to stdout (python-json-logger),
  idempotent, additive (never clobbers existing handlers such as caplog's).
- Exception handlers: HTTP, validation, rate-limit, and a catch-all that never
  leaks stack traces — all return ``{"error": ..., "request_id": ...}``.

PII policy (guardrail J / AGENTS.md §10): logs carry ``request_id`` and
``user_id`` only — never emails, phones, or addresses.
"""

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.api.config import Settings, get_settings

logger = logging.getLogger(__name__)

# --- Request context -------------------------------------------------------
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")

_LOGGING_CONFIGURED = False
_ORIG_RECORD_FACTORY: Callable[..., logging.LogRecord] = logging.getLogRecordFactory()


def bind_user(user_id: str) -> None:
    """Bind ``user_id`` to the current request context (called post-auth)."""
    user_id_var.set(user_id or "-")


def current_request_id() -> str:
    """Return the request id bound to the current context."""
    return request_id_var.get()


class _ContextRecordFactory:
    """LogRecordFactory that stamps request_id/user_id onto every record."""

    def __init__(self, previous: Callable[..., logging.LogRecord]) -> None:
        self._previous = previous

    def __call__(self, *args, **kwargs) -> logging.LogRecord:
        record = self._previous(*args, **kwargs)
        # Do not overwrite if a caller already set these explicitly.
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        if not hasattr(record, "user_id"):
            record.user_id = user_id_var.get()
        return record


def setup_logging(settings: Settings | None = None) -> None:
    """Configure structured logging (idempotent, additive).

    Args:
        settings: Optional settings; defaults to ``get_settings()``.
    """
    global _LOGGING_CONFIGURED
    settings = settings or get_settings()

    # Install the record factory once so every record carries request context.
    if not isinstance(logging.getLogRecordFactory(), _ContextRecordFactory):
        logging.setLogRecordFactory(_ContextRecordFactory(_ORIG_RECORD_FACTORY))

    root = logging.getLogger()
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    root.setLevel(level)

    if _LOGGING_CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if settings.json_logging:
        from pythonjsonlogger.json import JsonFormatter

        formatter: logging.Formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"levelname": "level", "asctime": "timestamp"},
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "[req=%(request_id)s user=%(user_id)s] %(message)s"
        )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    _LOGGING_CONFIGURED = True


def _request_id_from(request: Request) -> str:
    """Best-effort request id for exception handlers (state -> ctx -> header)."""
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    ctx = request_id_var.get()
    if ctx and ctx != "-":
        return ctx
    return request.headers.get("X-Request-ID", "-")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a request id, enforce the body-size cap, and tag the response."""

    def __init__(self, app, max_request_bytes: int) -> None:
        super().__init__(app)
        self._max_request_bytes = max_request_bytes

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming if incoming else str(uuid.uuid4())
        request_id_var.set(request_id)
        user_id_var.set("-")
        request.state.request_id = request_id

        # Reject oversized bodies early (guardrail: 1 MB default).
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > self._max_request_bytes:
                return _error_response(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "Request body too large",
                    request_id,
                )

        started = time.perf_counter()
        status_code: object = "-"
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Auth binds user_id on the shared scope state; pick it up so even
            # this access-log line is attributable (contextvars set in the
            # downstream task do not propagate back up).
            bound_user = getattr(request.state, "user_id", None)
            if bound_user:
                user_id_var.set(bound_user)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.url.path,
                status_code,
                elapsed_ms,
            )


def _error_response(status_code: int, message: str, request_id: str) -> JSONResponse:
    """Build the standard error envelope with the request id header."""
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


# --- Exception handlers ----------------------------------------------------
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Render ``HTTPException`` as the standard error envelope (no stack trace)."""
    request_id = _request_id_from(request)
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    headers = dict(getattr(exc, "headers", {}) or {})
    headers.setdefault("X-Request-ID", request_id)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": detail, "request_id": request_id},
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render request-validation failures as a 422 error envelope."""
    request_id = _request_id_from(request)
    # Field-level messages aid clients; no stack trace, no input echo of secrets.
    errors = [
        {"loc": list(map(str, err.get("loc", []))), "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Request validation failed",
            "request_id": request_id,
            "details": errors,
        },
        headers={"X-Request-ID": request_id},
    )


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Render slowapi 429s as the standard error envelope with Retry-After."""
    request_id = _request_id_from(request)
    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "Rate limit exceeded", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )
    retry_after = getattr(getattr(exc, "detail", None), "retry_after", None)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return response


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all: log the traceback server-side, return an opaque 500."""
    request_id = _request_id_from(request)
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )
