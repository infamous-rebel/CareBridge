"""Authentication endpoints.

- ``POST /auth/login``   — exchange credentials for an access+refresh token pair.
- ``POST /auth/refresh`` — exchange a valid refresh token for a new access token.
- ``GET  /auth/me``      — the current authenticated user.
- ``POST /auth/firebase/exchange`` — exchange a Firebase ID token for CareBridge
  JWTs + a Firebase custom token (hybrid identity).
- ``GET  /auth/firebase/config``   — public: whether Firebase is enabled.
- ``POST /auth/firebase/verify``   — verify a Firebase ID token without issuing tokens.

``/auth/login`` and ``/auth/refresh`` are public (no bearer access token) but
carry the stricter auth rate limit (default 60/min). ``/auth/refresh`` is
authenticated by the *refresh* token in its body rather than the access token —
that is the whole point of a refresh flow (the access token may be expired).
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api import user_store
from src.api.dependencies import get_current_user
from src.api.firebase_auth import (
    create_firebase_custom_token,
    verify_firebase_id_token,
)
from src.api.rate_limit import auth_limit, limiter
from src.api.schemas import (
    FirebaseConfigResponse,
    FirebaseExchangeRequest,
    FirebaseTokenResponse,
    FirebaseUserProfile,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from src.api.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from src.api.config import firebase_is_configured, get_settings
from jose import JWTError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(auth_limit)
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Authenticate a user and issue a token pair.

    Args:
        request: Injected for rate limiting.
        body: Email + password.

    Returns:
        ``TokenResponse`` with access + refresh tokens.

    Raises:
        HTTPException: 401 if the email is unknown or the password is wrong.
    """
    user = user_store.get_user_by_email(body.email)
    # Verify against a dummy hash when the user is unknown is unnecessary here;
    # bcrypt verification already runs in constant time for a real hash. We
    # simply reject unknown emails without disclosing which field was wrong.
    if user is None or not verify_password(body.password, user["password_hash"]):
        logger.info("Failed login attempt for user_id=%s", user["user_id"] if user else "-")
        raise _INVALID_CREDS

    logger.info("Successful login for user_id=%s", user["user_id"])
    return TokenResponse(
        access_token=create_access_token(user["user_id"], user["role"]),
        refresh_token=create_refresh_token(user["user_id"], user["role"]),
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(auth_limit)
async def refresh(request: Request, body: RefreshRequest) -> TokenResponse:
    """Issue a fresh access token from a valid refresh token.

    Args:
        request: Injected for rate limiting.
        body: The refresh token.

    Returns:
        ``TokenResponse`` with a new access token and a rotated refresh token.

    Raises:
        HTTPException: 401 if the refresh token is invalid, expired, or the user
            no longer exists.
    """
    try:
        payload = decode_token(body.refresh_token, TOKEN_TYPE_REFRESH)
    except JWTError as exc:
        logger.info("Rejected refresh token: %s", type(exc).__name__)
        raise _INVALID_CREDS from exc

    user = user_store.get_user_by_id(payload.get("sub", ""))
    if user is None:
        raise _INVALID_CREDS

    return TokenResponse(
        access_token=create_access_token(user["user_id"], user["role"]),
        refresh_token=create_refresh_token(user["user_id"], user["role"]),
        token_type="bearer",
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)) -> UserOut:
    """Return the current authenticated user.

    Args:
        user: Injected authenticated user dict.

    Returns:
        ``UserOut`` public view of the user.
    """
    return UserOut(
        user_id=user["user_id"],
        email=user["email"],
        role=user["role"],
        full_name=user.get("full_name"),
        care_recipient_id=user.get("care_recipient_id"),
    )


# ---------------------------------------------------------------------------
# Firebase Authentication endpoints (hybrid identity)
# ---------------------------------------------------------------------------

@router.get("/firebase/config", response_model=FirebaseConfigResponse)
async def firebase_config() -> FirebaseConfigResponse:
    """Public endpoint: whether Firebase Auth is enabled and the project ID.

    The frontend calls this on load to decide whether to render the Google
    sign-in button.  No authentication required.

    Returns:
        ``FirebaseConfigResponse`` with ``enabled`` and ``project_id``.
    """
    return FirebaseConfigResponse(
        enabled=firebase_is_configured(),
        project_id=get_settings().firebase_project_id,
    )


@router.post(
    "/firebase/exchange",
    response_model=FirebaseTokenResponse,
)
@limiter.limit(auth_limit)
async def firebase_exchange(
    request: Request, body: FirebaseExchangeRequest
) -> FirebaseTokenResponse:
    """Exchange a Firebase ID token for CareBridge JWTs + a custom token.

    Flow:
    1. Verify the Firebase ID token.
    2. Find the user by firebase_uid, else by email, else create new.
    3. If existing but no firebase_uid: link it.
    4. Issue CareBridge JWTs (access + refresh) and a Firebase custom token
       carrying business claims (role, care_recipient_id).
    5. Write an audit event.

    Args:
        request: Injected for rate limiting.
        body: The Firebase ID token.

    Returns:
        ``FirebaseTokenResponse`` with custom_token, user, access_token,
        refresh_token, token_type.

    Raises:
        HTTPException: 401 if the token is invalid or email not verified.
        HTTPException: 503 if Firebase is not configured.
    """
    if not firebase_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is not configured",
        )

    fb_user = verify_firebase_id_token(body.id_token)

    # Find or create the CareBridge user.
    user = user_store.get_user_by_firebase_uid(fb_user.uid)
    if user is None:
        # Try matching by email (existing password-less account or demo user).
        user = user_store.get_user_by_email(fb_user.email)
        if user is None:
            # New user: create from Firebase profile.
            user = user_store.create_user_from_firebase(
                uid=fb_user.uid,
                email=fb_user.email,
                full_name=fb_user.name,
            )
            logger.info(
                "Created new user %s from Firebase (uid=%s)",
                user.get("user_id"), fb_user.uid,
            )
        else:
            # Existing user: link the Firebase UID.
            user_store.link_firebase_uid(user["user_id"], fb_user.uid)
            user = user_store.get_user_by_id(user["user_id"])
            logger.info(
                "Linked firebase_uid=%s to existing user %s",
                fb_user.uid, user.get("user_id"),
            )

    # Ensure the user has a care_recipient (required for CRUD routers).
    if not user.get("care_recipient_id"):
        cr_id = user_store.create_care_recipient_for_user(
            user["user_id"], fb_user.name,
        )
        user = user_store.get_user_by_id(user["user_id"])
        logger.info(
            "Created care_recipient %s for user %s",
            cr_id, user.get("user_id"),
        )

    # Issue CareBridge JWTs.
    access_token = create_access_token(user["user_id"], user["role"])
    refresh_token = create_refresh_token(user["user_id"], user["role"])

    # Issue Firebase custom token with business claims.
    custom_token = create_firebase_custom_token(
        fb_user.uid,
        {"role": user["role"], "care_recipient_id": user.get("care_recipient_id", "")},
    )

    # Audit trail — onboarding event when a care_recipient was just created.
    try:
        from src.models.audit_log import write_audit_event

        write_audit_event(
            actor="human",
            action_type="onboard_new_user",
            care_recipient_id=user.get("care_recipient_id") or "unassigned",
            rationale=f"Firebase onboarding for uid={fb_user.uid}",
            outcome="success",
            correlation_id=str(uuid4()),
        )
        write_audit_event(
            actor="human",
            action_type="login_firebase",
            care_recipient_id=user.get("care_recipient_id") or "unassigned",
            rationale=f"Firebase login for uid={fb_user.uid}",
            outcome="success",
            correlation_id=str(uuid4()),
        )
    except Exception as exc:
        logger.warning("Audit write failed for firebase login: %s", exc)

    return FirebaseTokenResponse(
        custom_token=custom_token,
        user=UserOut(
            user_id=user["user_id"],
            email=user["email"],
            role=user["role"],
            full_name=user.get("full_name"),
            care_recipient_id=user.get("care_recipient_id"),
        ),
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post(
    "/firebase/verify",
    response_model=FirebaseUserProfile,
)
@limiter.limit(auth_limit)
async def firebase_verify(
    request: Request, body: FirebaseExchangeRequest
) -> FirebaseUserProfile:
    """Verify a Firebase ID token without issuing CareBridge tokens.

    Used by the frontend to validate a session on page load (silent re-auth).

    Args:
        request: Injected for rate limiting.
        body: The Firebase ID token.

    Returns:
        ``FirebaseUserProfile`` with uid, email, name, picture.

    Raises:
        HTTPException: 401 if the token is invalid or email not verified.
        HTTPException: 503 if Firebase is not configured.
    """
    if not firebase_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is not configured",
        )

    fb_user = verify_firebase_id_token(body.id_token)
    return FirebaseUserProfile(
        uid=fb_user.uid,
        email=fb_user.email,
        name=fb_user.name,
        picture=fb_user.picture,
    )
