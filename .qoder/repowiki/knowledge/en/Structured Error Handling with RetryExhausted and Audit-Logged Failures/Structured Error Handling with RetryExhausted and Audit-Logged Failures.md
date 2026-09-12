---
kind: error_handling
name: Structured Error Handling with RetryExhausted and Audit-Logged Failures
category: error_handling
scope:
    - '**'
source_files:
    - src/tools/retry.py
    - src/agents/communication_agent.py
    - src/agents/logistics_agent.py
    - src/agents/appointment_agent.py
    - src/models/schemas.py
    - main.py
---

## Overview

CareBridge uses a Python-native, structured error-handling approach centered on a single custom exception (`RetryExhausted`) raised by a shared retry utility, combined with pervasive `logging` calls and an immutable SQLite audit trail for every failure path. There is no centralized error class hierarchy, no HTTP-style error codes, and no middleware — errors are handled locally in each agent where the failure occurs.

## Core Components

### Custom Exception: `RetryExhausted`
Defined in `src/tools/retry.py`, this is the only application-specific exception type used to signal unrecoverable failures after retries:

```python
class RetryExhausted(Exception):
    def __init__(self, message: str, last_exception: Exception):
        super().__init__(message)
        self.last_exception = last_exception
```

It wraps the final underlying exception via a `last_exception` attribute so callers can inspect the root cause.

### Shared Retry Utility: `with_retry()`
Also in `src/tools/retry.py`, this async/sync-compatible helper implements exponential backoff (1s, 2s, 4s) with a default of 3 attempts. It logs warnings on intermediate failures and logs an error when all attempts are exhausted before raising `RetryExhausted`. The module docstring prescribes that **all agents must use `with_retry()`** and must not implement custom retry loops.

### Agent-Level Error Handling Patterns

- **Communication Agent** (`src/agents/communication_agent.py`): Wraps `send_family_alert` calls in `try/except RetryExhausted`, logs the failure at `ERROR` level, appends a human-readable "FAILED after retries" action string, and still marks escalation as required with the appropriate level (`emergency` or `alert`).
- **Logistics Agent** (`src/agents/logistics_agent.py`): Uses `with_retry(check_delivery_status, max_attempts=2)` for non-essential delivery failures; if the status remains `failed`, it raises `RetryExhausted` manually with a `RuntimeError` as the wrapped cause. Essential delivery failures bypass retry and escalate immediately. Missing deliveries raise `ValueError` from tools, caught and logged as `ERROR`.
- **Appointment & Medication Agents**: Catch `ValueError` from tool calls (e.g., invalid date parsing), log at `ERROR` level, and return structured results indicating failure.

### Structured Return Values Instead of Exceptions
Agents do not always propagate exceptions upward. Many failure paths return a dict containing fields like `escalated`, `escalation_level`, `retry_attempted`, and `actions_taken`, allowing the Supervisor to decide whether to escalate without unwrapping exceptions. This pattern is visible in `process_delivery_failure` and `handle_logistics_event`.

### Audit Trail Integration
Every notable error or failure path writes an immutable audit event via `write_audit_event(...)` with an `outcome` field set to `"failure"` or `"escalated"`. Examples include:
- Delivery not found → `action_type="check_delivery_status"`, `outcome="failure"`
- Non-essential delivery retry exhausted → `action_type="retry_delivery_failure"`, `outcome="failure"`
- Essential delivery failure → `action_type="escalate_delivery_failure"`, `outcome="escalated"`

This makes the audit log the authoritative record of all error outcomes, independent of logging output.

### Startup-Time Validation Errors
`main.py::load_fixtures()` validates that required fixture files exist and contain valid JSON, raising `FileNotFoundError` and `json.JSONDecodeError` respectively. These are documented in the function's docstring and propagate to the caller, causing the demo to fail fast at startup rather than silently proceeding.

### Logging Strategy
All modules define a module-level `logger = logging.getLogger(__name__)`. Errors are logged at `ERROR` level, warnings at `WARNING`, and informational messages at `INFO`. The root logger is configured in `main.py` to write both to stdout and to `logs/carebridge.log`. No structured log format (JSON) is used; messages are plain text with `%` formatting.

## Conventions Observed

1. **Use `with_retry()` for external/tool calls** — explicitly mandated by the module docstring in `src/tools/retry.py`; custom retry loops are discouraged.
2. **Catch `RetryExhausted` at agent boundaries** — communication and logistics agents catch this specific exception rather than catching bare `Exception`.
3. **Prefer structured return dicts over raising exceptions for recoverable failures** — agents return `escalated`, `escalation_level`, and `actions_taken` so the supervisor can route decisions uniformly.
4. **Always write an audit event on failure** — every error path in the logistics agent calls `write_audit_event` with `outcome="failure"` or `"escalated"`.
5. **Validate inputs early and raise standard Python exceptions** — `ValueError` for invalid data (e.g., missing delivery ID, bad dates), `FileNotFoundError` for missing fixtures.
6. **No panics / no `sys.exit()` inside agents** — agents return structured results; process termination is left to the top-level entry point.
7. **No global error middleware** — error handling is co-located with the code that can handle it.

## Key Files

- `src/tools/retry.py` — defines `RetryExhausted` and `with_retry()`
- `src/agents/communication_agent.py` — catches `RetryExhausted`, logs errors, sets escalation
- `src/agents/logistics_agent.py` — handles delivery failures, raises `RetryExhausted` manually, audits outcomes
- `src/agents/appointment_agent.py` — catches `ValueError` from tool calls
- `src/models/schemas.py` — Pydantic models with `Literal`-typed fields constrain allowed values (e.g., `outcome: Literal["success", "failure", "pending", "escalated"]`)
- `main.py` — startup validation, fixture loading, logging configuration
- `src/models/audit_log.py` — immutable audit sink written to on every failure path