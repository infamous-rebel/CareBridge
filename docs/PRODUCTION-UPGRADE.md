# CareBridge Production Upgrade Guide

Moving beyond mocked integrations to live production services.

---

## Table of Contents

- [Overview](#overview)
- [Twilio SMS](#twilio-sms)
- [Google Calendar OAuth](#google-calendar-oauth)
- [Persistent Storage (PostgreSQL)](#persistent-storage-postgresql)
- [Real Pharmacy API](#real-pharmacy-api)
- [Real Delivery API](#real-delivery-api)
- [HIPAA-Compliant Hosting](#hipaa-compliant-hosting)

---

## Overview

CareBridge ships with four in-process MCP servers that mock external services using JSON fixtures. This lets the full agent pipeline run without any external credentials. Each mock is a drop-in replacement target: the tool names, signatures, and return shapes are the stable contract.

| Server | Current State | Upgrade Target |
|---|---|---|
| Pharmacy | Mock (JSON fixtures, 10% timeout) | Surescript / Walgreens API |
| Messaging | Mock (logs to file) | Twilio SMS + SendGrid Email |
| Delivery | Mock (JSON fixtures, 15% failure) | Instacart / DoorDash API |
| Calendar | Mock (JSON fixtures) | Google Calendar OAuth |

---

## Twilio SMS

### Current State

`src/mcp/messaging_server.py` — `send_sms()` and `send_email()` append messages to `logs/messages.log` and return synthetic delivery receipts. Every call writes one audit event (actor="communication").

### Required Credentials

| Variable | Source | Cost |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | https://console.twilio.com | Free trial: ~60 credits |
| `TWILIO_AUTH_TOKEN` | https://console.twilio.com | |
| `TWILIO_FROM` | Purchase a Twilio phone number | $1/month + usage |
| `SENDGRID_API_KEY` | https://console.sendgrid.com | Free: 100 emails/day |

### Code Change Scope

**File:** `src/mcp/messaging_server.py`

Replace the mock `send_sms()` implementation with Twilio SDK calls:

```python
# Current (mock):
def _send_sms_mock(recipient_id, message, level):
    # Append to logs/messages.log
    return {"status": "delivered", "channel": "sms", ...}

# Target (real):
from twilio.rest import Client

def _send_sms_real(recipient_id, message, level):
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=message,
        from_=TWILIO_FROM,
        to=recipient_phone,  # Resolve from family_members fixture/DB
    )
    return {"status": "delivered", "sid": message.sid, "channel": "sms", ...}
```

Similarly, replace `send_email()` with SendGrid SDK calls.

**Dependencies:** Add `twilio>=8.0` and `sendgrid>=6.0` to `requirements.txt`.

**Config:** Read credentials from environment variables (already defined in `.env.example`).

### Estimated Effort

~2 hours. The mock and real implementations have the same input/output contract. The main work is resolving recipient phone numbers from the care recipient's family member list and handling Twilio error codes (invalid number, rate limit, etc.).

---

## Google Calendar OAuth

### Current State

`src/mcp/calendar_server.py` — `get_calendar()` reads from `fixtures/appointments.json`. `schedule_appointment()` returns a synthetic appointment. The spec (SPEC.md §6.4) designates Calendar as an external SSE MCP server backed by the Qoder Google Calendar Connector. The in-process mock is the documented fallback.

### Required Credentials

| Variable | Source | Notes |
|---|---|---|
| Google Cloud OAuth 2.0 Client ID | https://console.cloud.google.com | Web application type |
| `GOOGLE_CLIENT_ID` | From OAuth credential | |
| `GOOGLE_CLIENT_SECRET` | From OAuth credential | |
| `GOOGLE_CALENDAR_SCOPES` | `https://www.googleapis.com/auth/calendar.app.created` | No verification needed |

The `calendar.app.created` scope allows creating events without requiring Google's OAuth verification process (which is needed for read access to other users' calendars). This means you can go live immediately with ~100 trial users.

### Code Change Scope

**File:** `src/mcp/calendar_server.py`

Add an OAuth flow module:

1. **New file:** `src/api/routers/calendar_oauth.py` — handles the OAuth consent redirect, callback, and token storage.
2. **Modify:** `calendar_server.py` — replace mock `get_calendar()` with Google Calendar API calls using `google-api-python-client`.
3. **New dependency:** `google-api-python-client>=2.0`, `google-auth-httplib2>=0.1`, `google-auth-oauthlib>=1.0`.

```python
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def _get_calendar_real(care_recipient_id, horizon_days=30):
    creds = _load_user_credentials(care_recipient_id)  # From DB
    service = build('calendar', 'v3', credentials=creds)
    events = service.events().list(
        calendarId='primary',
        timeMin=now.isoformat() + 'Z',
        timeMax=(now + timedelta(days=horizon_days)).isoformat() + 'Z',
    ).execute()
    return [_map_event(e) for e in events.get('items', [])]
```

**Storage:** OAuth tokens must be persisted per user (add a `calendar_tokens` table or column to `auth.db`).

### Estimated Effort

~4 hours. OAuth flow setup, token storage, event mapping, error handling for expired tokens and revoked access.

---

## Persistent Storage (PostgreSQL)

### Current State

Two SQLite databases:
- `audit.db` — immutable audit trail (default path: `./audit.db`, configurable via `AUDIT_DB_PATH`)
- `auth.db` — user accounts, medications, appointments, settings

SQLite is fine for development and single-container deployments. It does not support concurrent writes from multiple containers or connection pooling.

### Required Credentials

| Variable | Source | Notes |
|---|---|---|
| `DATABASE_URL` | Railway PostgreSQL addon, Supabase, or Neon | `postgresql://user:pass@host:5432/carebridge` |

### Code Change Scope

**Files affected:**
- `src/models/audit_log.py` — swap `sqlite3.connect()` for `psycopg2` or `asyncpg` connection
- `src/api/user_store.py` — same swap for the users DB
- `requirements.txt` — add `psycopg2-binary>=2.9` or `asyncpg>=0.29`

**Migration path:**
1. Add `DATABASE_URL` env var.
2. When `DATABASE_URL` is set, use PostgreSQL; otherwise fall back to SQLite.
3. Create tables with PostgreSQL-compatible DDL (the current schema is already compatible — no SQLite-specific syntax beyond triggers).
4. Re-implement the audit immutability triggers in PostgreSQL syntax:
   ```sql
   CREATE RULE audit_no_update AS ON UPDATE TO audit_events
       DO INSTEAD NOTHING;
   CREATE RULE audit_no_delete AS ON DELETE TO audit_events
       DO INSTEAD NOTHING;
   ```

**Railway approach:** Add a PostgreSQL addon ($5/month for 1GB). Set `DATABASE_URL` automatically.

### Estimated Effort

~1 hour for the swap. The schema is already PostgreSQL-compatible. The main work is the connection management and trigger syntax change.

---

## Real Pharmacy API

### Current State

`src/mcp/pharmacy_server.py` — reads from `fixtures/medications.json`. `order_refill()` has a 10% simulated timeout to exercise retry logic. `check_refill_status()` returns deterministic refill data.

### Required Credentials

Real pharmacy integration requires a **contract** with a pharmacy API provider:

| Provider | API | Requirements |
|---|---|---|
| **Surescripts** | e-Prescribing / Formulary | BAA, pharmacy partnership agreement, NCPDP certification |
| **Walgreens** | Walgreens Developer API | Partnership agreement, pharmacy license |
| **Capsule** | Capsule API | Partnership agreement |
| **Amazon Pharmacy** | Not publicly available | N/A |

### Code Change Scope

**File:** `src/mcp/pharmacy_server.py`

Replace mock implementations with real API calls. The tool contract (signatures, return shapes) stays the same. The main changes:

1. Replace fixture reads with API calls.
2. Handle real error codes (insurance rejection, formulary mismatch, pharmacy closed).
3. Add authentication headers for the pharmacy API.
4. Implement real retry/backoff against the pharmacy's rate limits.

### Estimated Effort

Contract-dependent. Once a contract is in place: ~1-2 days for integration, testing, and compliance review.

---

## Real Delivery API

### Current State

`src/mcp/delivery_server.py` — reads from `fixtures/delivery_history.json`. `order_grocery()` and `order_pharmacy_delivery()` have a 15% simulated failure rate.

### Required Credentials

| Provider | API | Requirements |
|---|---|---|
| **Instacart** | Instacart Delivery API | Partnership agreement |
| **DoorDash** | DoorDash Drive API | Business account, API access request |
| **Uber Direct** | Uber Direct API | Business account |
| **Shipt** | Shipt API | Partnership agreement |

### Code Change Scope

**File:** `src/mcp/delivery_server.py`

Replace mock implementations with real delivery API calls. Key changes:

1. Replace fixture reads with API calls.
2. Handle real delivery states (assigned to shopper, picked up, out for delivery, delivered, failed).
3. Implement webhook handlers for delivery status updates (the delivery provider pushes updates to your endpoint).
4. Add address validation before placing orders.

### Estimated Effort

Contract-dependent. Once a contract is in place: ~1-2 days per provider.

---

## HIPAA-Compliant Hosting

### Current State

Backend runs on Railway (general-purpose PaaS). Railway is **not** HIPAA-compliant out of the box. For handling real patient data (PHI), you need HIPAA-compliant infrastructure.

### Requirements

| Requirement | Current | Target |
|---|---|---|
| BAA (Business Associate Agreement) | None | AWS (with BAA) or Google Cloud (with BAA) |
| Encryption at rest | SQLite file | PostgreSQL with encryption |
| Encryption in transit | HTTPS (Railway managed) | HTTPS (AWS ALB / Cloudflare) |
| Access logging | Application logs | CloudTrail + CloudWatch |
| Data residency | Railway region | AWS region (user-controlled) |
| Audit trail | SQLite triggers | PostgreSQL + S3 backup |

### Recommended Path: AWS Bedrock AgentCore

The spec (SPEC.md §11) targets Qoder Cloud Agents for deployment. For HIPAA compliance:

1. **Move the backend to AWS ECS or Lambda** behind an ALB with TLS.
2. **Use Amazon Bedrock** for LLM inference (Bedrock is HIPAA-eligible under the AWS BAA).
3. **Use RDS PostgreSQL** with encryption at rest and in transit.
4. **Use S3** for audit trail backups (versioned, encrypted bucket).
5. **Sign the AWS BAA** — this covers Bedrock, RDS, S3, ECS, and CloudTrail.

### Code Change Scope

Minimal. CareBridge is already provider-agnostic:
- LLM: Set `LLM_PROVIDER=bedrock` and provide AWS credentials.
- Storage: Set `DATABASE_URL` to an RDS PostgreSQL endpoint.
- The agent pipeline, audit trail, and MCP servers are infrastructure-agnostic.

The main work is:
1. Docker image → ECR.
2. ECS task definition with secrets manager for env vars.
3. ALB + Route 53 for the API endpoint.
4. VPC configuration for database access.
5. CloudTrail + CloudWatch for compliance logging.

### Estimated Effort

~1-2 weeks for a full HIPAA-compliant deployment on AWS. The code changes are minimal; the effort is in infrastructure setup, BAA execution, and compliance documentation.
