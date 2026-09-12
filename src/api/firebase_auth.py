"""Firebase Authentication integration for CareBridge.

Hybrid identity model: Firebase handles identity (Google sign-in, email/password),
while the FastAPI backend issues business-claim JWTs and owns authorization.

This module:
1. Lazy-initializes ``firebase_admin`` (once, thread-safe).
2. Verifies Firebase ID tokens from the client SDK.
3. Creates Firebase custom tokens with business claims (role, care_recipient_id).

All Firebase operations degrade gracefully: if the service account file is
missing or malformed, a WARNING is logged and endpoints return 503.
"""

import logging
import os
import threading
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status

from src.api.config import get_settings

logger = logging.getLogger(__name__)

_app_lock = threading.Lock()
_initialized: bool = False
_init_failed: bool = False


@dataclass(frozen=True)
class FirebaseUser:
    """Decoded Firebase ID token payload."""

    uid: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    email_verified: bool = False


def init_firebase() -> bool:
    """Initialize the Firebase Admin SDK (once, thread-safe).

    Returns:
        True if the SDK is ready, False if initialization failed or Firebase
        is not enabled.

    Raises:
        None — failures are logged and return False (graceful degradation).
    """
    global _initialized, _init_failed

    if _initialized:
        return True
    if _init_failed:
        return False

    settings = get_settings()
    if not settings.firebase_auth_enabled:
        logger.debug("FIREBASE_AUTH_ENABLED is False; skipping Firebase init")
        return False

    with _app_lock:
        # Double-check after acquiring the lock.
        if _initialized:
            return True
        if _init_failed:
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials

            # If already initialized (e.g. by another code path), just mark ready.
            try:
                firebase_admin.get_app()
                _initialized = True
                logger.info("Firebase Admin SDK already initialized")
                return True
            except ValueError:
                pass  # Not yet initialized; proceed.

            # Priority 1: FIREBASE_CREDENTIALS_JSON env var (cloud deployment)
            if settings.firebase_credentials_json:
                import json
                try:
                    cred_dict = json.loads(settings.firebase_credentials_json)
                    cred = credentials.Certificate(cred_dict)
                    logger.info("Firebase Admin initialized from FIREBASE_CREDENTIALS_JSON env var")
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning(
                        "FIREBASE_CREDENTIALS_JSON is present but invalid: %s. "
                        "Firebase endpoints will return 503.",
                        exc,
                    )
                    _init_failed = True
                    return False
            else:
                # Priority 2: FIREBASE_SERVICE_ACCOUNT_PATH file
                sa_path = settings.firebase_service_account_path
                if not os.path.exists(sa_path):
                    logger.warning(
                        "Firebase service account not found at '%s'. "
                        "Firebase endpoints will return 503 until the file is placed.",
                        sa_path,
                    )
                    _init_failed = True
                    return False

                cred = credentials.Certificate(sa_path)
            app_config = {}
            if settings.firebase_project_id:
                app_config["projectId"] = settings.firebase_project_id

            firebase_admin.initialize_app(cred, app_config)
            _initialized = True
            logger.info(
                "Firebase Admin SDK initialized (project=%s)",
                settings.firebase_project_id or "<from-service-account>",
            )
            return True

        except Exception as exc:
            logger.warning(
                "Firebase initialization failed: %s: %s. "
                "Firebase endpoints will return 503.",
                type(exc).__name__,
                exc,
            )
            _init_failed = True
            return False


def verify_firebase_id_token(id_token: str) -> FirebaseUser:
    """Verify a Firebase ID token and return the decoded user profile.

    Args:
        id_token: The raw Firebase ID token string from the client SDK.

    Returns:
        A :class:`FirebaseUser` with uid, email, name, picture, email_verified.

    Raises:
        HTTPException: 401 if the token is invalid or the email is not verified.
        HTTPException: 503 if Firebase is not configured.
    """
    if not init_firebase():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is not configured",
        )

    try:
        from firebase_admin import auth as firebase_auth

        decoded = firebase_auth.verify_id_token(id_token)

        if not decoded.get("email_verified"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email not verified. Please verify your email address.",
            )

        return FirebaseUser(
            uid=decoded["uid"],
            email=decoded.get("email", ""),
            name=decoded.get("name"),
            picture=decoded.get("picture"),
            email_verified=decoded.get("email_verified", False),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.info("Firebase ID token verification failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token",
        ) from exc


def create_firebase_custom_token(uid: str, claims: dict) -> str:
    """Create a Firebase custom token embedding business claims.

    Args:
        uid: The Firebase UID to mint the token for.
        claims: Business claims (role, care_recipient_id) to embed.

    Returns:
        The custom token as a UTF-8 string.

    Raises:
        HTTPException: 503 if Firebase is not configured, 500 on creation failure.
    """
    if not init_firebase():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is not configured",
        )

    try:
        from firebase_admin import auth as firebase_auth

        token = firebase_auth.create_custom_token(uid, developer_claims=claims)
        # firebase_admin returns bytes; decode to str for JSON transport.
        if isinstance(token, bytes):
            return token.decode("utf-8")
        return str(token)

    except Exception as exc:
        logger.error("Failed to create Firebase custom token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create Firebase custom token",
        ) from exc
