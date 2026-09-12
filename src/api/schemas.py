"""API request/response models (Pydantic v2).

These are transport-layer models for the REST API. They are intentionally
separate from ``src/models/schemas.py`` (the agent domain models), which are
reused here where applicable — e.g. :class:`~src.models.schemas.AuditEvent`,
:class:`~src.models.schemas.StatusSummary`,
:class:`~src.models.schemas.PendingAction`,
:class:`~src.models.schemas.Medication`,
:class:`~src.models.schemas.Appointment`, and
:class:`~src.models.schemas.DeliveryStatus`.

No PII beyond the login identity appears in these models' logged fields; logs
carry ``user_id`` only (guardrail J / AGENTS.md §10).
"""

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Lightweight email check — avoids the email-validator dependency while still
# enforcing format on every request (guardrail J).
EmailStr = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]

# Reused domain models (re-exported for router response_model convenience).
from src.models.schemas import (  # noqa: F401
    Appointment,
    AuditEvent,
    DeliveryStatus,
    Medication,
    PendingAction,
    StatusSummary,
)

Role = Literal["caregiver_primary", "caregiver_secondary", "viewer"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    """Credentials for ``POST /auth/login``."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    """Refresh token for ``POST /auth/refresh``."""

    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """Issued token pair."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class UserOut(BaseModel):
    """Public view of an authenticated user (``GET /auth/me``)."""

    user_id: str
    email: EmailStr
    role: Role
    full_name: Optional[str] = None
    care_recipient_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Alerts & approvals
# ---------------------------------------------------------------------------
class AlertAckRequest(BaseModel):
    """Body for ``POST /alerts/{alert_id}/ack``."""

    note: Optional[str] = Field(default=None, max_length=500)


class ApprovalDecision(BaseModel):
    """Optional body for approve/reject endpoints (reason recorded in audit)."""

    reason: Optional[str] = Field(default=None, max_length=500)


class ActionResponse(BaseModel):
    """Generic acknowledgement result carrying the audit correlation."""

    status: Literal["ok", "degraded"] = "ok"
    detail: Optional[str] = None
    action_id: Optional[str] = None
    correlation_id: Optional[str] = None
    acknowledged_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Query (caregiver Q&A -> Supervisor)
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    """Body for ``POST /query``."""

    care_recipient_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2000)


class QueryResponse(BaseModel):
    """Answer from the Supervisor for a caregiver question."""

    care_recipient_id: str
    question: str
    answer: str
    status: Literal["ok", "degraded"] = "ok"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
class PaginatedAudit(BaseModel):
    """A page of audit events plus pagination metadata."""

    items: list[AuditEvent]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int


# ---------------------------------------------------------------------------
# Health / readiness / version / errors / degradation
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """``GET /health`` — liveness."""

    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    """``GET /ready`` — dependency readiness.

    ``llm_provider`` / ``llm_available`` are informational: a deployment that
    runs without LLM credentials is still *ready* (the Supervisor degrades to
    its deterministic routing path and LLM-dependent routes return 503
    individually), so ``llm_available=False`` does not by itself degrade
    ``status`` or the HTTP code.
    """

    status: Literal["ok", "degraded"]
    checks: dict[str, bool]
    llm_provider: str
    llm_available: bool


class VersionResponse(BaseModel):
    """``GET /version`` — build metadata."""

    app_name: str
    version: str
    git_sha: str
    build_timestamp: str
    environment: str


class DegradedResponse(BaseModel):
    """Returned with HTTP 503 for LLM-dependent routes when the SDK is absent."""

    status: Literal["degraded"] = "degraded"
    reason: str


class ErrorResponse(BaseModel):
    """Global error envelope — never leaks stack traces (SPEC section E)."""

    error: str
    request_id: Optional[str] = None


# ---------------------------------------------------------------------------
# MCP introspection
# ---------------------------------------------------------------------------
class MCPServerInfo(BaseModel):
    """One registered in-process MCP server."""

    name: str
    type: str
    tools: list[str] = []


class MCPServersResponse(BaseModel):
    """``GET /mcp/servers`` — registry introspection."""

    count: int
    servers: list[MCPServerInfo]


# ---------------------------------------------------------------------------
# Firebase Authentication (hybrid identity)
# ---------------------------------------------------------------------------
class FirebaseExchangeRequest(BaseModel):
    """Body for ``POST /auth/firebase/exchange`` and ``/auth/firebase/verify``."""

    id_token: str = Field(min_length=1, max_length=4096)


class FirebaseUserProfile(BaseModel):
    """Public Firebase user profile returned by ``/auth/firebase/verify``."""

    uid: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class FirebaseTokenResponse(BaseModel):
    """Response from ``POST /auth/firebase/exchange``.

    Carries both a Firebase custom token (for client-side Firebase SDK) and
    the standard CareBridge JWT pair (for API calls).
    """

    custom_token: str
    user: UserOut
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class FirebaseConfigResponse(BaseModel):
    """``GET /auth/firebase/config`` — public signal for the frontend."""

    enabled: bool
    project_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Medications CRUD
# ---------------------------------------------------------------------------
class MedicationCreate(BaseModel):
    """Body for ``POST /care-recipients/me/medications``."""

    name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    refill_threshold: int = Field(default=5, ge=1, le=30)
    pharmacy_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class MedicationUpdate(BaseModel):
    """Body for ``PUT /care-recipients/me/medications/{id}``."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    dosage: Optional[str] = Field(default=None, min_length=1, max_length=100)
    frequency: Optional[str] = Field(default=None, min_length=1, max_length=100)
    refill_threshold: Optional[int] = Field(default=None, ge=1, le=30)
    pharmacy_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class MedicationOut(BaseModel):
    """Public view of a medication row."""

    id: str
    care_recipient_id: str
    name: str
    dosage: str
    frequency: str
    refill_threshold: int
    pharmacy_id: Optional[str] = None
    notes: Optional[str] = None
    active: bool
    created_at: str
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Appointments CRUD
# ---------------------------------------------------------------------------
class AppointmentCreate(BaseModel):
    """Body for ``POST /care-recipients/me/appointments``."""

    provider_name: str = Field(min_length=1, max_length=200)
    specialty: Optional[str] = None
    appointment_at: str = Field(min_length=1)
    location: Optional[str] = None
    prep_required: list[str] = Field(default_factory=list, max_length=10)
    transportation_needed: bool = False
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("appointment_at")
    @classmethod
    def _validate_appointment_at(cls, v: str) -> str:
        """Ensure the appointment time is in the future."""
        from datetime import datetime, timezone

        try:
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt <= datetime.now(timezone.utc):
                raise ValueError("appointment_at must be in the future")
        except ValueError as exc:
            if "must be in the future" in str(exc):
                raise
            raise ValueError("appointment_at must be a valid ISO 8601 datetime") from exc
        return v


class AppointmentUpdate(BaseModel):
    """Body for ``PUT /care-recipients/me/appointments/{id}``."""

    provider_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    specialty: Optional[str] = None
    appointment_at: Optional[str] = None
    location: Optional[str] = None
    prep_required: Optional[list[str]] = Field(default=None, max_length=10)
    transportation_needed: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = None


class AppointmentOut(BaseModel):
    """Public view of an appointment row."""

    id: str
    care_recipient_id: str
    provider_name: str
    specialty: Optional[str] = None
    appointment_at: str
    location: Optional[str] = None
    prep_required: list[str] = []
    transportation_needed: bool
    notes: Optional[str] = None
    status: str
    created_at: str
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# User Settings CRUD
# ---------------------------------------------------------------------------
class NotificationPrefs(BaseModel):
    """Nested notification preferences."""

    email: bool = True
    sms: bool = True
    push: bool = True


class SettingsUpdate(BaseModel):
    """Body for ``PUT /settings/me`` (all fields optional / partial)."""

    notification_prefs: Optional[NotificationPrefs] = None
    escalation_order: Optional[list[str]] = Field(default=None, max_length=5)
    quiet_hours_start: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: Optional[str] = None
    language: Optional[str] = Field(default=None, max_length=5)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        """Validate against IANA timezone database."""
        if v is None:
            return v
        try:
            from zoneinfo import available_timezones

            if v not in available_timezones():
                raise ValueError(f"Unknown timezone: {v}")
        except ImportError:
            pass  # zoneinfo unavailable; accept any string
        return v


class SettingsOut(BaseModel):
    """Public view of user settings."""

    user_id: str
    notification_prefs: dict
    escalation_order: list[str]
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    timezone: str
    language: str
    updated_at: str
