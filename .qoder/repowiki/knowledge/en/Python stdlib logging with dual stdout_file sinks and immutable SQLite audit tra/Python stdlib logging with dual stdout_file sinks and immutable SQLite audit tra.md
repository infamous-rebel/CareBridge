---
kind: logging_system
name: Python stdlib logging with dual stdout/file sinks and immutable SQLite audit trail
category: logging_system
scope:
    - '**'
source_files:
    - main.py
    - src/models/audit_log.py
    - src/agents/supervisor_agent.py
    - src/agents/medication_agent.py
    - src/agents/appointment_agent.py
    - src/agents/logistics_agent.py
    - src/agents/communication_agent.py
    - src/tools/appointment_tools.py
    - src/tools/communication_tools.py
    - src/tools/logistics_tools.py
    - src/tools/medication_tools.py
    - src/models/escalation_logic.py
---

## What system/approach is used

CareBridge uses Python's built-in `logging` module exclusively — no third-party logging framework (e.g., structlog, loguru, or Sentry) is imported anywhere in the codebase. Logging is configured once at process startup in `main.py` via `logging.basicConfig`, which installs a root logger with two handlers:
- A `StreamHandler` writing to `sys.stdout`
- A `FileHandler` appending to `logs/carebridge.log`
The default level is `INFO`; no per-module override is applied, so all modules inherit this level.

The application also maintains a separate **immutable audit trail** implemented as an append-only SQLite database (`audit.db`) defined in `src/models/audit_log.py`. This is distinct from the text-based log stream: every agent action writes one row to the `audit_events` table, enforced by `BEFORE UPDATE` and `BEFORE DELETE` triggers that abort on modification or deletion.

## Key files and packages

- `main.py` — single point of logging configuration; creates the `logs/` directory if missing, configures `basicConfig`, and drives demo-scenario logging (startup, fixture load, scenario steps, completion).
- `src/models/audit_log.py` — defines the audit schema, immutability triggers, `write_audit_event`, and `get_audit_events`; logs its own successes and errors via a module-level `logger = logging.getLogger(__name__)`.
- `src/agents/*.py` (`appointment_agent.py`, `communication_agent.py`, `logistics_agent.py`, `medication_agent.py`, `supervisor_agent.py`) — each imports `logging`, creates a module-scoped `logger = logging.getLogger(__name__)`, and emits `info`/`warning`/`error` messages tied to agent actions.
- `src/tools/*.py` (`appointment_tools.py`, `communication_tools.py`, `logistics_agent.py`, `medication_tools.py`, `retry.py`) — same pattern: module-level logger used for tool execution traces.
- `src/models/escalation_logic.py` — uses the module logger for escalation decisions.
- `logs/` — runtime output directory containing `carebridge.log` and `messages.log` (the latter appears empty in the tree but exists).

## Architecture and conventions

1. **Single initialization**: All logging configuration happens in `main.py` before any other module is imported. The `logs/` directory is created with `Path("logs").mkdir(exist_ok=True)` right before `basicConfig` so the file handler never fails on first run.
2. **Module-scoped loggers**: Every source file declares `logger = logging.getLogger(__name__)` immediately after importing `logging`. No global logger instance is shared across modules; each module gets a named logger whose name reflects its dotted path (e.g. `src.agents.medication_agent`).
3. **Log levels observed**:
   - `INFO` is the dominant level, used for lifecycle events (startup, fixture loading, scenario steps, resolution summaries, audit event confirmations).
   - `WARNING` is used for non-fatal anomalies (e.g. appointment time conflicts, medication stock warnings).
   - `ERROR` is used for failures (tool execution exceptions, audit write failures).
   - `DEBUG` is not used anywhere in the codebase.
4. **Message format**: The configured format string `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"` produces lines like `2025-... - src.agents.medication_agent - INFO - ...`. Messages are constructed with `%s`/`%d` style formatting rather than f-strings, except inside `audit_log.write_audit_event` where f-strings are used for the audit confirmation/error messages.
5. **Structured fields live in the audit DB, not in log lines**: The audit trail stores typed fields (`event_id`, `timestamp`, `actor`, `action_type`, `care_recipient_id`, `rationale`, `outcome`, `correlation_id`, `authorization_ref`) in SQLite. Log messages remain free-form text strings; there is no JSON/log-structured payload emitted to the log stream.
6. **Audit vs. log separation**: `audit_log.write_audit_event` both persists a row to SQLite and emits an `INFO` log line confirming the write. Errors during audit persistence are logged via `logger.error` and re-raised. The audit DB is initialized by calling `init_audit_db()` before any agent runs.
7. **No rotation or size limits**: The `FileHandler` is created with default arguments, meaning `logs/carebridge.log` grows without bound until the process ends.
8. **No per-module level overrides**: No module calls `setLevel` or attaches additional handlers; all behavior is inherited from the root logger configured in `main.py`.

## Conventions and constraints

- **Every agent action must produce exactly one audit event** — documented in the module docstring of `audit_log.py`: "Every agent action produces exactly one audit event. The 'before action' event (outcome='pending') MUST be written BEFORE executing the action." This is enforced by the call site convention in agents/tools that wrap each tool invocation with a pending→success/failure/escalated pair of `write_audit_event` calls.
- **Audit events are immutable** — enforced at the database layer by SQLite triggers `prevent_audit_update` and `prevent_audit_delete` that raise `ABORT` on UPDATE/DELETE attempts. This is a hard constraint, not just a convention.
- **Correlation tracking** — every audit event carries a `correlation_id` (a UUID v4 generated per care event), allowing all actions for a single care event to be queried together via `get_audit_events(care_recipient_id=..., correlation_id=...)`.
- **Actor field is constrained to a known set** — the docstring for `write_audit_event` specifies `actor` must be one of `supervisor`, `medication`, `appointment`, `logistics`, `communication`, `human`.
- **Outcome field is constrained** — the docstring specifies outcome must be one of `success`, `failure`, `pending`, `escalated`.
- **Timestamps are UTC ISO-8601** — produced via `datetime.now(timezone.utc).isoformat()`.
- **All loggers derive from the root logger configured in `main.py`**; no module reconfigures handlers or formatters.