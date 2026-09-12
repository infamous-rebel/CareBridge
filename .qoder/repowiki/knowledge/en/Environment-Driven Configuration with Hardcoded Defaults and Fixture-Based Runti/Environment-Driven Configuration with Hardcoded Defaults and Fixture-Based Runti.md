---
kind: configuration_system
name: Environment-Driven Configuration with Hardcoded Defaults and Fixture-Based Runtime State
category: configuration_system
scope:
    - '**'
source_files:
    - .env.example
    - main.py
    - src/models/audit_log.py
    - src/agents/supervisor_agent.py
    - src/tools/retry.py
    - pyproject.toml
---

## Overview

CareBridge does not use a centralized configuration framework (no `pydantic-settings`, `dynaconf`, `python-dotenv` loader, or config files). Instead, it relies on a minimal, environment-variable-driven approach combined with hardcoded defaults and JSON fixtures for runtime data.

## Environment Variables

The repository ships `.env.example` documenting every expected environment variable. These are grouped by subsystem:

- **LLM / Amazon Bedrock**: `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `BEDROCK_MODEL_ID`
- **Pharmacy MCP server**: `PHARMACY_MCP_URL`, `PHARMACY_API_KEY`
- **Calendar MCP server**: `CALENDAR_MCP_URL`, `CALENDAR_API_KEY`
- **Delivery MCP server**: `DELIVERY_MCP_URL`, `DELIVERY_API_KEY`
- **Messaging (SMS/email/phone)**: `MESSAGING_MCP_URL`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `SENDGRID_API_KEY`
- **Storage**: `DATABASE_URL` (PostgreSQL/Supabase; SQLite is used in development)
- **Auth**: `JWT_SECRET_KEY`

The comment in `.env.example` explicitly states the rule: *"Copy to .env and fill in real values. NEVER commit .env — it holds secrets."*

However, none of the application code currently reads these variables via `os.environ` or `dotenv`. The Strands agent creation in `src/agents/supervisor_agent.py` hardcodes the model ID (`anthropic.claude-sonnet-4-20250514`) rather than reading `BEDROCK_MODEL_ID`, and the audit log uses a hardcoded SQLite path (`audit.db`). This means the documented env vars are intended but not yet wired into the runtime — they serve as a contract for deployment and future integration.

## Hardcoded Defaults

Configuration values that are read at runtime are embedded directly in source:

| Value | Location | Purpose |
|---|---|---|
| `DB_PATH = "audit.db"` | `src/models/audit_log.py` | SQLite audit database file location |
| `logs/carebridge.log` | `main.py` | File-based logging destination |
| `logs/messages.log` | implied by logs dir | Message logging |
| `fixtures/` directory | `main.py` | Required fixture files (`medications.json`, `appointments.json`, `delivery_history.json`, `family_members.json`) |
| Model ID `anthropic.claude-sonnet-4-20250514` | `src/agents/supervisor_agent.py` | Bedrock LLM model selection |

## Fixture-Based Runtime Data

Runtime state (medications, appointments, delivery history, family members) is loaded from JSON fixtures under `fixtures/` at startup via `load_fixtures()` in `main.py`. Missing required fixtures raise `FileNotFoundError`, enforcing that demo/test runs have all data present before execution.

## Logging Configuration

Logging is configured inline in `main.py` using Python's stdlib `logging.basicConfig`: INFO level, structured format with timestamp/name/level/message, dual handlers (stdout + `logs/carebridge.log`). No log-level overrides or external logging config files are used.

## Feature Flags / Graceful Degradation

The system uses an import-time feature flag pattern: `create_supervisor_agent()` tries to import `strands` and connect to Bedrock; if either fails, it returns `None` and the caller falls back to deterministic direct routing. This is the only runtime configuration toggle observed.

## Constraints and Conventions Observed

- Secrets belong in `.env` and must never be committed (documented in `.env.example`).
- Audit events are immutable: SQLite triggers block UPDATE/DELETE on `audit_events`; this is enforced at the database layer, not via configuration.
- External tool calls go through the shared `with_retry()` helper in `src/tools/retry.py` (3 attempts, exponential backoff 1s/2s/4s); custom retry loops are prohibited per the module docstring.
- Fixtures are mandatory: missing files cause startup failure.
- There is no configuration validation layer — values are assumed correct when consumed.

## Key Files

- `.env.example` — canonical list of expected environment variables and their purpose
- `main.py` — bootstraps logging, loads fixtures, initializes audit DB, creates supervisor agent
- `src/models/audit_log.py` — defines the default SQLite audit database path and immutability schema
- `src/agents/supervisor_agent.py` — contains the hardcoded Bedrock model ID and graceful-degradation agent creation
- `src/tools/retry.py` — enforces a single retry strategy across all external API calls
- `pyproject.toml` — only pytest options; no project-wide config metadata
- `requirements.txt` — dependency declarations (no config-related packages beyond stdlib)