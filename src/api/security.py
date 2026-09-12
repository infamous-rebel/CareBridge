"""Authentication primitives: password hashing, JWT, and RBAC roles.

Password hashing uses ``bcrypt`` directly. The spec suggested ``passlib[bcrypt]``,
but passlib 1.7.4 is incompatible with bcrypt>=4.1 on this interpreter (it probes
``bcrypt.__about__`` and then mis-enforces the 72-byte limit, raising on valid
input). Calling ``bcrypt`` directly satisfies guardrail J — cost factor >= 12 and
constant-time comparison (``bcrypt.checkpw``) — without the broken shim.

JWTs are HS256 via ``python-jose``. Access tokens are short-lived (15 min),
refresh tokens long-lived (7 days). Every token carries ``sub`` (user_id),
``role``, ``type`` (access|refresh), ``iat``, ``exp``, and a unique ``jti``.
"""

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from src.api.config import get_settings

logger = logging.getLogger(__name__)

# --- RBAC roles (SPEC / architecture.md §8) --------------------------------
ROLE_CAREGIVER_PRIMARY = "caregiver_primary"
ROLE_CAREGIVER_SECONDARY = "caregiver_secondary"
ROLE_VIEWER = "viewer"

VALID_ROLES: frozenset[str] = frozenset(
    {ROLE_CAREGIVER_PRIMARY, ROLE_CAREGIVER_SECONDARY, ROLE_VIEWER}
)

# Token type claims.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# bcrypt's hard input limit. Longer secrets are pre-hashed (see _prepare).
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    """Encode a password for bcrypt, pre-hashing inputs over the 72-byte limit.

    bcrypt silently truncates at 72 bytes; pre-hashing with SHA-256 (then
    base64, yielding 44 bytes) preserves the full entropy of long passphrases
    and keeps hash/verify symmetric.

    Args:
        password: The plaintext password.

    Returns:
        UTF-8 bytes safe to pass to bcrypt.
    """
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raw = base64.b64encode(hashlib.sha256(raw).digest())
    return raw


def hash_password(password: str, rounds: Optional[int] = None) -> str:
    """Hash a password with bcrypt.

    Args:
        password: Plaintext password.
        rounds: bcrypt cost factor. Defaults to ``settings.bcrypt_rounds``
            (>= 12 outside demo mode — guardrail J).

    Returns:
        The bcrypt hash string.
    """
    settings = get_settings()
    cost = rounds if rounds is not None else settings.bcrypt_rounds
    salt = bcrypt.gensalt(rounds=cost)
    return bcrypt.hashpw(_prepare(password), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verify a password against a bcrypt hash.

    Args:
        password: Plaintext password attempt.
        password_hash: Stored bcrypt hash.

    Returns:
        True if the password matches; False otherwise (never raises on a
        malformed hash — a bad hash simply fails to match).
    """
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        logger.warning("Password verification failed on malformed hash: %s", exc)
        return False


def _create_token(
    subject: str, role: str, token_type: str, expires_delta: timedelta
) -> str:
    """Build a signed JWT with standard claims.

    Args:
        subject: The ``sub`` claim (user_id).
        role: RBAC role claim.
        token_type: ``access`` or ``refresh``.
        expires_delta: Lifetime of the token.

    Returns:
        The encoded JWT string.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, role: str) -> str:
    """Create a short-lived access token (default 15 minutes)."""
    settings = get_settings()
    return _create_token(
        subject,
        role,
        TOKEN_TYPE_ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str, role: str) -> str:
    """Create a long-lived refresh token (default 7 days)."""
    settings = get_settings()
    return _create_token(
        subject,
        role,
        TOKEN_TYPE_REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT, enforcing its token type.

    Args:
        token: The encoded JWT.
        expected_type: ``access`` or ``refresh`` — the required ``type`` claim.

    Returns:
        The decoded payload dict.

    Raises:
        JWTError: If the signature is invalid, the token is expired, or the
            ``type`` claim does not match ``expected_type``.
    """
    settings = get_settings()
    payload = jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise JWTError(
            f"Expected a {expected_type} token, got {payload.get('type')!r}"
        )
    return payload


def is_valid_role(role: str) -> bool:
    """Return True if ``role`` is one of the recognized RBAC roles."""
    return role in VALID_ROLES
