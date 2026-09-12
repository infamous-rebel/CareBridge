"""Health, readiness, and version endpoints (public — no JWT required).

- ``GET /health``  — liveness: ``{"status": "ok"}``.
- ``GET /ready``   — readiness: SQLite audit DB reachable + MCP registry loaded,
  plus the resolved LLM provider and whether it can build a model adapter.
- ``GET /version`` — app version, git SHA, build timestamp, environment.
"""

import logging

from fastapi import APIRouter, Response

from src.api.config import get_settings
from src.api.rate_limit import limiter
from src.api.schemas import HealthResponse, ReadyResponse, VersionResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def _audit_db_reachable() -> bool:
    """Return True if the audit trail can be queried."""
    try:
        from src.models.audit_log import get_audit_events

        get_audit_events()
        return True
    except Exception as exc:  # pragma: no cover - only on a broken DB
        logger.warning("Audit DB not reachable: %s", type(exc).__name__)
        return False


def _mcp_registry_loaded() -> bool:
    """Return True if the in-process MCP registry exposes servers."""
    try:
        from src.mcp import get_mcp_server_configs

        return len(get_mcp_server_configs()) > 0
    except Exception as exc:  # pragma: no cover - only on a broken registry
        logger.warning("MCP registry not loaded: %s", type(exc).__name__)
        return False


def _llm_provider_name() -> str:
    """Return the configured LLM provider, or ``"none"`` if it cannot resolve.

    A probe must never raise (AGENTS.md §9), so an unexpected failure degrades to
    a reported value rather than a 500.
    """
    try:
        from src.runtime.model_factory import get_provider_name

        return get_provider_name()
    except Exception as exc:  # pragma: no cover - only on a broken runtime
        logger.warning("LLM provider unresolved: %s", type(exc).__name__)
        return "none"


def _llm_available() -> bool:
    """Return True if the configured provider can build a model adapter.

    Construction is offline — no inference request is issued — so this does not
    add network latency or cost to the readiness probe.
    """
    try:
        from src.runtime.model_factory import is_llm_available

        return is_llm_available()
    except Exception as exc:  # pragma: no cover - only on a broken runtime
        logger.warning("LLM availability unresolved: %s", type(exc).__name__)
        return False


@router.get("/health", response_model=HealthResponse)
@limiter.exempt
async def health() -> HealthResponse:
    """Liveness probe.

    Returns:
        ``HealthResponse`` with ``status="ok"``.
    """
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
@limiter.exempt
async def ready(response: Response) -> ReadyResponse:
    """Readiness probe — verifies core dependencies.

    Checks that the immutable audit DB is queryable and the MCP registry is
    loaded. Returns HTTP 503 with ``status="degraded"`` if any check fails.

    Also reports which LLM provider the deployment resolved to and whether it
    can build a model adapter (spec F). Building an adapter is an offline
    operation — no inference request is issued — so this is safe on a probe
    path. ``llm_available`` is deliberately excluded from the readiness
    verdict: a deployment without LLM credentials is still ready, because the
    Supervisor degrades to deterministic routing and LLM-dependent routes
    return 503 individually rather than the whole service going unready.

    Args:
        response: Injected response, used to set the status code on degradation.

    Returns:
        ``ReadyResponse`` with per-check booleans, overall status, and the
        resolved LLM provider.
    """
    checks = {
        "audit_db": _audit_db_reachable(),
        "mcp_registry": _mcp_registry_loaded(),
    }
    all_ok = all(checks.values())
    if not all_ok:
        response.status_code = 503

    provider = _llm_provider_name()
    return ReadyResponse(
        status="ok" if all_ok else "degraded",
        checks=checks,
        llm_provider=provider,
        llm_available=_llm_available(),
    )


@router.get("/version", response_model=VersionResponse)
@limiter.exempt
async def version() -> VersionResponse:
    """Build metadata.

    Returns:
        ``VersionResponse`` with app name, version, git SHA, build timestamp,
        and environment.
    """
    settings = get_settings()
    return VersionResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        git_sha=settings.build_git_sha,
        build_timestamp=settings.build_timestamp,
        environment=settings.environment,
    )
