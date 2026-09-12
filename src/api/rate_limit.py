"""Rate limiting via slowapi.

Two tiers (SPEC section E):
- **Global** default limit applied to every route via ``SlowAPIMiddleware``
  (default ``300/minute``).
- **Auth** endpoints carry a stricter explicit limit (default ``60/minute``)
  applied with ``@limiter.limit(auth_limit)`` in ``routers/auth.py``.

The auth limit is read through a callable so it reflects the current
``Settings`` at request time — tests tighten ``AUTH_RATE_LIMIT`` and clear the
settings cache to exercise the 429 path without rebuilding the limiter.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.config import get_settings


def _build_limiter() -> Limiter:
    """Construct the shared limiter with the global default limit."""
    settings = get_settings()
    return Limiter(
        key_func=get_remote_address,
        default_limits=[settings.global_rate_limit],
        storage_uri="memory://",
    )


# Shared, module-level limiter. Wired into the app in ``main.create_app``
# (``app.state.limiter``) and consumed by ``SlowAPIMiddleware`` + decorators.
limiter = _build_limiter()


def auth_limit() -> str:
    """Callable limit value for auth endpoints — resolved per request.

    Returns:
        The configured auth rate limit string (e.g. ``"60/minute"``).
    """
    return get_settings().auth_rate_limit
