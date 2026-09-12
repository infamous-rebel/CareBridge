# CareBridge API Reference

Full reference for every endpoint in the CareBridge REST API.

**Base URL (production):** `https://carebridge-production-4bd1.up.railway.app`
**Base URL (local):** `http://localhost:8000`
**Swagger UI:** `/docs`
**OpenAPI spec:** `/openapi.json`

---

## Authentication

Most endpoints require a **Bearer token** in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Tokens are obtained via `POST /auth/login` or `POST /auth/firebase/exchange`.

**Roles:**
- `caregiver_primary` — full access (read + write + approve/reject)
- `caregiver_secondary` — full access (read + write + approve/reject)
- `viewer` — read-only (cannot approve/reject actions)

---

## Table of Contents

- [Health](#health)
- [Auth](#auth)
- [Status](#status)
- [Query](#query)
- [Alerts](#alerts)
- [Approvals](#approvals)
- [Audit](#audit)
- [Medications (Fixture)](#medications-fixture)
- [Medications CRUD](#medications-crud)
- [Appointments (Fixture)](#appointments-fixture)
- [Appointments CRUD](#appointments-crud)
- [Deliveries](#deliveries)
- [Settings](#settings)
- [MCP Introspection](#mcp-introspection)

---

## Health

### `GET /health`

Liveness probe. Always returns 200 when the server is running.

**Auth:** No

**Response:**
```json
{
  "status": "ok"
}
```

**Example:**
```bash
curl https://carebridge-production-4bd1.up.railway.app/health
```

---

### `GET /ready`

Readiness probe. Checks audit DB reachability and MCP registry. Reports LLM provider status. Returns 503 with `status="degraded"` if any core check fails.

**Auth:** No

**Response (200):**
```json
{
  "status": "ok",
  "checks": {
    "audit_db": true,
    "mcp_registry": true
  },
  "llm_provider": "gemini",
  "llm_available": true
}
```

**Response (503):**
```json
{
  "status": "degraded",
  "checks": {
    "audit_db": false,
    "mcp_registry": true
  },
  "llm_provider": "none",
  "llm_available": false
}
```

**Example:**
```bash
curl https://carebridge-production-4bd1.up.railway.app/ready
```

---

### `GET /version`

Build metadata.

**Auth:** No

**Response:**
```json
{
  "app_name": "CareBridge",
  "version": "1.0.0",
  "git_sha": "abc1234",
  "build_timestamp": "2026-09-12T00:00:00Z",
  "environment": "production"
}
```

**Example:**
```bash
curl https://carebridge-production-4bd1.up.railway.app/version
```

---

## Auth

### `POST /auth/login`

Exchange email + password for an access + refresh token pair.

**Auth:** No (rate limited: 60/min)

**Request Body:**
```json
{
  "email": "demo@carebridge.local",
  "password": "CareBridgeDemo!2026"
}
```

**Response (200):**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:** 401 (invalid credentials), 429 (rate limit exceeded)

**Example:**
```bash
curl -X POST https://carebridge-production-4bd1.up.railway.app/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@carebridge.local","password":"CareBridgeDemo!2026"}'
```

---

### `POST /auth/refresh`

Exchange a valid refresh token for a new access + refresh token pair.

**Auth:** No (rate limited: 60/min). The refresh token is in the request body, not the Authorization header.

**Request Body:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Response (200):**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:** 401 (invalid/expired refresh token)

**Example:**
```bash
curl -X POST https://carebridge-production-4bd1.up.railway.app/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"eyJ..."}'
```

---

### `GET /auth/me`

Return the current authenticated user.

**Auth:** Yes (any role)

**Response:**
```json
{
  "user_id": "uuid",
  "email": "demo@carebridge.local",
  "role": "caregiver_primary",
  "full_name": "Demo Caregiver",
  "care_recipient_id": "cr-001"
}
```

**Example:**
```bash
curl https://carebridge-production-4bd1.up.railway.app/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

### `GET /auth/firebase/config`

Public endpoint: whether Firebase Auth is enabled and the project ID. The frontend calls this on load to decide whether to render the Google sign-in button.

**Auth:** No

**Response:**
```json
{
  "enabled": true,
  "project_id": "carebridge-675df"
}
```

---

### `POST /auth/firebase/exchange`

Exchange a Firebase ID token for CareBridge JWTs + a Firebase custom token.

**Auth:** No (rate limited: 60/min). The Firebase ID token is in the request body.

**Request Body:**
```json
{
  "id_token": "firebase-id-token..."
}
```

**Response (200):**
```json
{
  "custom_token": "firebase-custom-token...",
  "user": {
    "user_id": "uuid",
    "email": "user@gmail.com",
    "role": "caregiver_primary",
    "full_name": "Jane Doe",
    "care_recipient_id": "cr-uuid"
  },
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:** 401 (invalid Firebase token), 503 (Firebase not configured)

---

### `POST /auth/firebase/verify`

Verify a Firebase ID token without issuing CareBridge tokens. Used for silent re-auth on page load.

**Auth:** No (rate limited: 60/min)

**Request Body:**
```json
{
  "id_token": "firebase-id-token..."
}
```

**Response (200):**
```json
{
  "uid": "firebase-uid",
  "email": "user@gmail.com",
  "name": "Jane Doe",
  "picture": "https://..."
}
```

**Errors:** 401 (invalid token), 503 (Firebase not configured)

---

## Status

### `GET /status/{care_recipient_id}`

Synthesized care status summary for a care recipient. Deterministic (no LLM required).

**Auth:** Yes (any role)

**Response:**
```json
{
  "summary_text": "3 medications active. Last refill ordered 2 days ago...",
  "recent_events": [...],
  "pending_actions": [...]
}
```

**Example:**
```bash
curl https://carebridge-production-4bd1.up.railway.app/status/cr-001 \
  -H "Authorization: Bearer <access_token>"
```

---

## Query

### `POST /query`

Natural-language caregiver Q&A. Routes the question to the Supervisor Agent for LLM synthesis. Returns 503 when the Supervisor is unavailable.

**Auth:** Yes (any role)

**Request Body:**
```json
{
  "care_recipient_id": "cr-001",
  "question": "How is Mom doing today?"
}
```

**Response (200):**
```json
{
  "care_recipient_id": "cr-001",
  "question": "How is Mom doing today?",
  "answer": "Mom's refill has been placed and is expected tomorrow...",
  "status": "ok"
}
```

**Response (503):**
```json
{
  "status": "degraded",
  "reason": "Supervisor agent runtime unavailable"
}
```

**Example:**
```bash
curl -X POST https://carebridge-production-4bd1.up.railway.app/query \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"care_recipient_id":"cr-001","question":"How is Mom doing today?"}'
```

---

## Alerts

### `GET /alerts`

Recent family-facing alert events from the audit trail. Filtered to `send_alert`, `send_sms`, `send_email` action types.

**Auth:** Yes (any role)

**Query Parameters:**
- `care_recipient_id` (optional) — filter by recipient

**Response:**
```json
[
  {
    "event_id": "uuid",
    "timestamp": "2026-09-12T10:00:00Z",
    "actor": "communication",
    "action_type": "send_alert",
    "care_recipient_id": "cr-001",
    "rationale": "...",
    "outcome": "success",
    "correlation_id": "uuid"
  }
]
```

**Example:**
```bash
curl https://carebridge-production-4bd1.up.railway.app/alerts \
  -H "Authorization: Bearer <access_token>"
```

---

### `POST /alerts/{alert_id}/ack`

Acknowledge an alert. Records a human audit event.

**Auth:** Yes (caregiver_primary, caregiver_secondary)

**Request Body (optional):**
```json
{
  "note": "Spoke with Mom, she's doing fine"
}
```

**Response:**
```json
{
  "status": "ok",
  "detail": "Alert acknowledged",
  "action_id": "uuid",
  "correlation_id": "uuid",
  "acknowledged_at": "2026-09-12T10:30:00Z"
}
```

**Errors:** 404 (alert not found)

---

## Approvals

### `GET /approvals`

Pending-approval queue. Returns audit events with `outcome="pending"`.

**Auth:** Yes (any role — viewers can read, not act)

**Query Parameters:**
- `care_recipient_id` (optional) — filter by recipient

**Response:**
```json
[
  {
    "action_id": "uuid",
    "action_type": "order_refill",
    "care_recipient_id": "cr-001",
    "rationale": "...",
    "requested_at": "2026-09-12T10:00:00Z",
    "status": "pending"
  }
]
```

---

### `POST /approvals/{action_id}/approve`

Approve a pending action. The Supervisor executes it via the responsible specialist agent.

**Auth:** Yes (caregiver_primary, caregiver_secondary)

**Request Body (optional):**
```json
{
  "reason": "Approved — Mom needs her medication"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "detail": "Action approved",
  "action_id": "uuid"
}
```

**Response (503):** Supervisor unavailable.
**Errors:** 404 (action not found or already resolved)

---

### `POST /approvals/{action_id}/reject`

Reject a pending action. Records the rejection in the audit trail.

**Auth:** Yes (caregiver_primary, caregiver_secondary)

**Request Body (optional):**
```json
{
  "reason": "Not needed — doctor already changed the prescription"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "detail": "Action rejected",
  "action_id": "uuid"
}
```

**Response (503):** Supervisor unavailable.
**Errors:** 404 (action not found or already resolved)

---

## Audit

### `GET /audit`

Paginated, filterable read access to the immutable audit trail.

**Auth:** Yes (any role)

**Query Parameters:**
- `page` (default: 1) — 1-based page number
- `page_size` (default: 50, max: 200) — items per page
- `care_recipient_id` (optional) — filter by recipient
- `correlation_id` (optional) — filter by correlation ID
- `actor` (optional) — filter by actor (`supervisor`, `medication`, `appointment`, `logistics`, `communication`, `human`)
- `action_type` (optional) — filter by action type
- `outcome` (optional) — filter by outcome (`success`, `failure`, `pending`, `escalated`)

**Response:**
```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 50,
  "pages": 1
}
```

**Example:**
```bash
curl "https://carebridge-production-4bd1.up.railway.app/audit?actor=supervisor&outcome=success&page=1&page_size=20" \
  -H "Authorization: Bearer <access_token>"
```

---

## Medications (Fixture)

### `GET /medications/{care_recipient_id}`

List medications from fixture data for a care recipient. Read-only.

**Auth:** Yes (any role)

**Response:**
```json
[
  {
    "medication_id": "med-001",
    "name": "Lisinopril",
    "dosage": "10mg",
    "frequency": "once daily",
    "refill_threshold": 5,
    "pharmacy_id": "pharm-001",
    "care_recipient_id": "cr-001"
  }
]
```

---

## Medications CRUD

### `GET /care-recipients/me/medications`

List all active medications for the current user's care recipient (DB-backed).

**Auth:** Yes

**Response:** Array of `MedicationOut` objects.

---

### `POST /care-recipients/me/medications`

Create a new medication. Writes audit event BEFORE the DB commit.

**Auth:** Yes

**Request Body:**
```json
{
  "name": "Amlodipine",
  "dosage": "5mg",
  "frequency": "once daily",
  "refill_threshold": 5,
  "pharmacy_id": "pharm-001",
  "notes": "For blood pressure"
}
```

**Response (201):** Created medication object.

---

### `GET /care-recipients/me/medications/{medication_id}`

Fetch a single medication by ID.

**Auth:** Yes

**Errors:** 404 (not found or belongs to different care recipient)

---

### `PUT /care-recipients/me/medications/{medication_id}`

Update an existing medication (partial update supported).

**Auth:** Yes

**Request Body (partial):**
```json
{
  "dosage": "10mg",
  "notes": "Increased dosage"
}
```

**Response:** Updated medication object.
**Errors:** 404 (not found)

---

### `DELETE /care-recipients/me/medications/{medication_id}`

Soft-delete a medication (sets `active=false`).

**Auth:** Yes

**Response:** Soft-deleted medication object.
**Errors:** 404 (not found)

---

## Appointments (Fixture)

### `GET /appointments/{care_recipient_id}`

List upcoming appointments from fixture data. Read-only.

**Auth:** Yes (any role)

**Query Parameters:**
- `horizon_days` (default: 30, range: 1–365)

**Response:**
```json
[
  {
    "appointment_id": "apt-001",
    "provider_name": "Dr. Smith",
    "specialty": "Cardiology",
    "datetime": "2026-09-15T10:00:00Z",
    "location": "City Medical Center",
    "prep_required": ["Fast for 12 hours"],
    "transportation_needed": true,
    "care_recipient_id": "cr-001"
  }
]
```

---

## Appointments CRUD

### `GET /care-recipients/me/appointments`

List all appointments for the current user's care recipient (DB-backed).

**Auth:** Yes

---

### `POST /care-recipients/me/appointments`

Create a new appointment.

**Auth:** Yes

**Request Body:**
```json
{
  "provider_name": "Dr. Johnson",
  "specialty": "Neurology",
  "appointment_at": "2026-10-01T14:00:00Z",
  "location": "Neurology Associates",
  "prep_required": ["Bring MRI results"],
  "transportation_needed": true,
  "notes": "Follow-up for headaches"
}
```

**Response (201):** Created appointment object.

---

### `GET /care-recipients/me/appointments/{appointment_id}`

Fetch a single appointment.

**Auth:** Yes

**Errors:** 404 (not found)

---

### `PUT /care-recipients/me/appointments/{appointment_id}`

Update an existing appointment (partial update).

**Auth:** Yes

**Errors:** 404 (not found)

---

### `POST /care-recipients/me/appointments/{appointment_id}/cancel`

Cancel an appointment (sets `status="cancelled"`).

**Auth:** Yes

**Response:** Cancelled appointment object.
**Errors:** 404 (not found)

---

## Deliveries

### `GET /deliveries/{care_recipient_id}`

List delivery records from fixture data for a care recipient. Read-only.

**Auth:** Yes (any role)

**Response:**
```json
[
  {
    "delivery_id": "del-001",
    "delivery_type": "pharmacy",
    "status": "delivered",
    "expected_at": "2026-09-12T14:00:00Z",
    "care_recipient_id": "cr-001"
  }
]
```

---

## Settings

### `GET /settings/me`

Get (or auto-create default) settings for the current user.

**Auth:** Yes

**Response:**
```json
{
  "user_id": "uuid",
  "notification_prefs": {"sms": true, "email": true},
  "escalation_order": ["member-1", "member-2"],
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "07:00",
  "timezone": "America/New_York",
  "language": "en",
  "updated_at": "2026-09-12T10:00:00Z"
}
```

---

### `PUT /settings/me`

Partially update the current user's settings.

**Auth:** Yes

**Request Body (partial):**
```json
{
  "timezone": "America/Chicago",
  "language": "en",
  "quiet_hours_start": "23:00"
}
```

**Response:** Updated settings object.
**Errors:** 422 (invalid timezone)

---

## MCP Introspection

### `GET /mcp/servers`

List the registered in-process MCP servers and their tool names.

**Auth:** Yes (any role)

**Response:**
```json
{
  "count": 4,
  "servers": [
    {
      "name": "calendar",
      "type": "sdk",
      "tools": ["get_calendar", "schedule_appointment"]
    },
    {
      "name": "delivery",
      "type": "sdk",
      "tools": ["check_delivery_status", "order_grocery", "order_pharmacy_delivery"]
    },
    {
      "name": "messaging",
      "type": "sdk",
      "tools": ["send_sms", "send_email"]
    },
    {
      "name": "pharmacy",
      "type": "sdk",
      "tools": ["check_refill_status", "order_refill", "get_medication_schedule"]
    }
  ]
}
```

---

## Error Responses

All errors follow a consistent shape:

```json
{
  "detail": "Human-readable error message",
  "request_id": "uuid"
}
```

| Status | Meaning |
|---|---|
| 400 | Bad request (validation error) |
| 401 | Unauthorized (missing or invalid token) |
| 403 | Forbidden (insufficient role) |
| 404 | Not found |
| 422 | Unprocessable entity (validation error) |
| 429 | Rate limit exceeded |
| 503 | Service degraded (Supervisor or Firebase unavailable) |
