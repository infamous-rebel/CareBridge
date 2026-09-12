"""FastAPI dependency providers.

Supplies the request-scoped dependencies used across routers:

- ``get_current_user`` — decode the bearer access token and load the user.
- ``require_roles``    — RBAC guard built on ``get_current_user``.
- ``get_supervisor``   — the Supervisor Agent module (or None if unavailable),
  enabling graceful degradation for LLM-dependent routes (SPEC section F).

SQLite connections are opened per-call inside ``user_store`` and ``audit_log``,
so there is no long-lived DB session to inject; the audit trail's patched
defaults (see root ``conftest.py``) are respected because routers call the audit
functions without an explicit ``db_path``.
"""

import logging
from importlib import import_module
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from starlette.concurrency import run_in_threadpool

from src.api import user_store
from src.api.middleware import bind_user
from src.api.security import TOKEN_TYPE_ACCESS, decode_token

logger = logging.getLogger(__name__)

# auto_error=False so we emit our own 401 through the standard error envelope
# rather than Starlette's default 403 for a missing scheme.
bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Resolve the authenticated user from the ``Authorization: Bearer`` header.

    Async so that ``bind_user`` sets the ``user_id`` context var in the request
    task (a sync dependency would run in a threadpool and lose the context). The
    blocking SQLite lookup is offloaded to a thread to keep the event loop free.

    Args:
        request: The current request (used to stash ``user_id`` on shared state
            so the request-id middleware's access log can attribute it too).
        credentials: Injected bearer credentials (may be None).

    Returns:
        The stored user dict (``user_id``, ``email``, ``role``, ...).

    Raises:
        HTTPException: 401 if the token is missing, invalid, expired, or the
            user no longer exists.
    """
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_EXC

    try:
        payload = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    except JWTError as exc:
        logger.info("Rejected access token: %s", type(exc).__name__)
        raise _CREDENTIALS_EXC from exc

    user_id = payload.get("sub")
    if not user_id:
        raise _CREDENTIALS_EXC

    user = await run_in_threadpool(user_store.get_user_by_id, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    # Stamp user_id into the request context (and shared scope state) so every
    # downstream log line is attributable without ever logging PII (guardrail J).
    bind_user(user_id)
    request.state.user_id = user_id
    return user


def require_roles(*roles: str) -> Callable[..., dict]:
    """Build a dependency enforcing that the current user has one of ``roles``.

    Args:
        *roles: Permitted RBAC roles.

    Returns:
        A FastAPI dependency that yields the current user or raises 403.
    """
    allowed = set(roles)

    def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed:
            logger.info(
                "Forbidden: user %s role not in %s", user.get("user_id"), sorted(allowed)
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action",
            )
        return user

    return _checker


def get_supervisor() -> Optional[Any]:
    """Return the Supervisor Agent module, or None if it cannot be imported.

    Used by LLM-dependent routes (e.g. ``/query``) to degrade gracefully with
    HTTP 503 when the agent stack is unavailable (SPEC section F). The module
    imports cleanly even without ``strands`` installed because its agent
    construction paths fall back to deterministic handlers.
    """
    try:
        return import_module("src.agents.supervisor_agent")
    except Exception as exc:  # pragma: no cover - import is expected to succeed
        logger.warning("Supervisor unavailable: %s", exc)
        return None


def llm_runtime_available() -> bool:
    """Report whether a real LLM-backed agent runtime can be constructed.

    True if either ``strands`` or ``qoder_agent_sdk`` is importable. Used for
    observability (``/ready`` detail) and to decide degradation messaging; the
    deterministic Supervisor handlers work regardless.
    """
    for module_name in ("strands", "strands_agents", "qoder_agent_sdk"):
        try:
            import_module(module_name)
            return True
        except Exception:
            continue
    return False
