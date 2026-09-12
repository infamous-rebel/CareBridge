# CareBridge: Autonomous Care Coordination Agent — Functional Specification

**Version:** 1.0
**Target:** Agents for Humans Hackathon (deadline 15 Sept 2026, 06:00 GMT+6)
**Framework:** Strands Agents SDK (Python) + Qoder MCP + Qoder Cloud Agents
**Track:** Everyday Agents

---

## 1. PROBLEM STATEMENT

- 10,000 Americans turn 65 every day.
- 90% of older adults want to age in place, but family coordination is a massive burden.
- Nearly 1 in 4 Americans is now a family caregiver — a 45% increase since 2015.
- Caregivers spend an average of 27 hours per week on care coordination.
- Medication adherence among elderly patients with chronic disease is only 40.26%.
- Non-adherence costs health systems approximately €2B/year.
- Existing solutions are fragmented: medication apps, calendar apps, grocery apps, and messaging apps are separate silos. No single system owns the end-to-end coordination workflow.

**CareBridge is the coordination layer that owns the workflow end-to-end.**

The agent monitors medication adherence, coordinates pharmacy refills, schedules appointments, manages grocery and pharmacy deliveries, and provides proactive alerts to family members when patterns deviate from normal. The adult child is the primary user. The older adult is a passive beneficiary — no app required.

---

## 2. PRIMARY USERS

| Role | Description | Primary Interface |
|---|---|---|
| **Caregiver** (primary user) | Adult child coordinating care for aging parent | Web dashboard + proactive alerts |
| **Care Recipient** (passive beneficiary) | Older adult living independently | Voice check-in (optional), no app required |
| **Family Members** (secondary) | Siblings, relatives receiving updates | SMS/email notifications |

---

## 3. SYSTEM SCOPE — FIVE AGENTS

### 3.1 Supervisor Agent (Orchestrator)

**Responsibility:** Routes all tasks to specialized agents. Maintains longitudinal care context. Applies escalation logic. Maintains immutable audit trail. Never calls external APIs directly.

**File:** `src/agents/supervisor_agent.py`

**Implementation (Strands Agents SDK, agents-as-tools pattern):**

```python
from strands import Agent
from strands.models import BedrockModel
from src.agents.medication_agent import medication_agent
from src.agents.appointment_agent import appointment_agent
from src.agents.logistics_agent import logistics_agent
from src.agents.communication_agent import communication_agent

supervisor_agent = Agent(
    name="CareBridgeSupervisor",
    model=BedrockModel(model_id="anthropic.claude-sonnet-4"),
    system_prompt=SUPERVISOR_SYSTEM_PROMPT,
    tools=[
        medication_agent,
        appointment_agent,
        logistics_agent,
        communication_agent,
    ],
)
```

**Public methods:**
- `process_event(event: CareEvent) -> ResolutionResult` — main entry point
- `query_status(care_recipient_id: str, question: str) -> str` — caregiver Q&A
- `approve_pending_action(action_id: str, approved: bool) -> None`

**System prompt focus:** Orchestration only. Route by intent. Apply escalation logic. Never call external APIs directly. Always log to audit trail before executing.

---

### 3.2 Medication Agent

**Responsibility:** Monitor medication adherence and refill status. Trigger refills autonomously. Escalate adherence pattern deviations to family.

**File:** `src/agents/medication_agent.py`

**Tools (exact signatures):**

```python
def check_refill_status(medication_id: str) -> RefillStatus:
    """
    Returns:
        RefillStatus(
            medication_id: str,
            days_remaining: int,
            refill_eligible: bool,
            pharmacy_id: str,
        )
    """

def order_refill(medication_id: str, pharmacy_id: str) -> RefillOrder:
    """
    Returns:
        RefillOrder(
            order_id: str,
            medication_id: str,
            status: Literal["placed", "failed"],
            estimated_delivery: date,
            failure_reason: Optional[str],
        )
    """

def detect_adherence_pattern(medication_id: str, window_days: int = 7) -> AdherencePattern:
    """
    Returns:
        AdherencePattern(
            medication_id: str,
            missed_doses: int,
            late_doses: int,
            deviation_flag: bool,
            severity: Literal["none", "mild", "moderate", "severe"],
        )
    """
```

**Behavior rules:**
- If `days_remaining <= refill_threshold` (default 5): call `order_refill`
- If `order_refill` fails 3×: escalate to Communication Agent with `level="alert"`
- If `deviation_flag=True` and `severity >= "moderate"`: alert family immediately

---

### 3.3 Appointment Agent

**Responsibility:** Manage provider calendars, coordinate transportation, send preparation checklists.

**File:** `src/agents/appointment_agent.py`

**Tools (exact signatures):**

```python
def get_calendar(care_recipient_id: str, horizon_days: int = 30) -> list[Appointment]:
    """
    Returns list of Appointment(
        appointment_id: str,
        provider_name: str,
        specialty: str,
        datetime: datetime,
        location: str,
        prep_required: list[str],
        transportation_needed: bool,
    )
    """

def schedule_appointment(
    provider_id: str,
    care_recipient_id: str,
    preferred_datetime: datetime,
) -> Appointment:
    """Creates appointment; returns Appointment on success, raises on failure."""

def send_prep_checklist(appointment_id: str) -> ChecklistResult:
    """Sends prep checklist via Communication Agent. Returns delivery status."""
```

**Behavior rules:**
- If appointment is within 7 days AND `transportation_needed=True`: coordinate transport via Logistics Agent
- If appointment is within 48 hours: send prep checklist

---

### 3.4 Logistics Agent

**Responsibility:** Coordinate grocery and pharmacy deliveries. Monitor delivery confirmation.

**File:** `src/agents/logistics_agent.py`

**Tools (exact signatures):**

```python
def check_delivery_status(delivery_id: str) -> DeliveryStatus:
    """
    Returns DeliveryStatus(
        delivery_id: str,
        status: Literal["pending", "in_transit", "delivered", "failed"],
        expected_at: datetime,
        failure_reason: Optional[str],
    )
    """

def order_grocery(
    care_recipient_id: str,
    items: list[str],
    delivery_address: str,
) -> DeliveryOrder:
    """Places grocery order; returns DeliveryOrder with order_id and ETA."""

def order_pharmacy_delivery(
    medication_id: str,
    pharmacy_id: str,
    delivery_address: str,
) -> DeliveryOrder:
    """Places pharmacy delivery; returns DeliveryOrder with order_id and ETA."""
```

**Behavior rules:**
- If `status="failed"` for essential items (medication, food): escalate to family as `level="alert"`
- If `status="failed"` for non-essential: retry once, then log warning

---

### 3.5 Communication Agent

**Responsibility:** Generate proactive family updates. Handle two-way queries. Respect per-member notification preferences.

**File:** `src/agents/communication_agent.py`

**Tools (exact signatures):**

```python
def send_alert(
    recipient_id: str,
    message: str,
    level: Literal["info", "alert", "emergency"],
) -> AlertResult:
    """
    Sends SMS or email based on recipient preferences.
    Returns AlertResult(delivery_status, channel_used, sent_at).
    """

def synthesize_status(care_recipient_id: str) -> StatusSummary:
    """
    Reads audit trail + current state; generates natural-language summary.
    Returns StatusSummary(
        summary_text: str,
        recent_events: list[AuditEvent],
        pending_actions: list[PendingAction],
    )
    """

def get_family_preferences(family_id: str) -> FamilyPreferences:
    """
    Returns FamilyPreferences(
        family_id: str,
        members: list[FamilyMember],
        escalation_order: list[str],
    )
    """
```

**Behavior rules:**
- `level="emergency"` → SMS + email + phone call to ALL family members in escalation_order
- `level="alert"` → SMS to primary caregiver, email to others
- `level="info"` → batch into daily digest unless urgent

---

## 4. DATA MODELS

**File:** `src/models/schemas.py` — all models use Pydantic v2.

```python
from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Literal, Optional
from uuid import UUID

class Medication(BaseModel):
    medication_id: str
    name: str
    dosage: str
    frequency: str
    refill_threshold: int = 5
    pharmacy_id: str
    care_recipient_id: str

class Appointment(BaseModel):
    appointment_id: str
    provider_name: str
    specialty: str
    datetime: datetime
    location: str
    prep_required: list[str] = []
    transportation_needed: bool = False
    care_recipient_id: str

class FamilyMember(BaseModel):
    family_id: str
    name: str
    relationship: str
    phone: Optional[str]
    email: Optional[str]
    notification_preference: Literal["sms", "email", "both"] = "both"
    escalation_priority: int = 1

class AuditEvent(BaseModel):
    event_id: UUID
    timestamp: datetime
    actor: Literal["supervisor", "medication", "appointment", "logistics", "communication", "human"]
    action_type: str
    care_recipient_id: str
    rationale: str
    outcome: Literal["success", "failure", "pending", "escalated"]
    correlation_id: UUID
    authorization_ref: Optional[str]

class CareEvent(BaseModel):
    event_id: UUID
    event_type: Literal["refill_low", "appointment_upcoming", "delivery_failed", "adherence_deviation"]
    care_recipient_id: str
    payload: dict
    received_at: datetime

class ResolutionResult(BaseModel):
    event_id: UUID
    resolved: bool
    actions_taken: list[str]
    escalation_required: bool
    escalation_level: Optional[Literal["info", "alert", "emergency"]]
    audit_event_ids: list[UUID]
```

---

## 5. ESCALATION LOGIC

**File:** `src/models/escalation_logic.py` — deterministic, NOT LLM-driven.

```python
AUTONOMOUS_ACTIONS = {
    "check_refill_status",
    "check_delivery_status",
    "get_calendar",
    "synthesize_status",
    "send_daily_digest",
}

REQUIRES_ALERT = {
    "order_refill",
    "order_grocery",
    "schedule_appointment",
}

REQUIRES_APPROVAL = {
    "cancel_appointment",
    "change_medication_schedule",
    "add_service_provider",
    "modify_health_record",
}

def classify_action(action_type: str, context: dict) -> Literal["auto", "alert", "approve"]:
    """Deterministic classification. Do NOT call LLM here."""
```

**Escalation triggers:**

| Trigger | Level | Action |
|---|---|---|
| Medication missed >2 consecutive days | alert | SMS + email to primary caregiver |
| Appointment no-show without cancellation | alert | SMS + email to primary caregiver |
| Delivery failure (essential items) | alert | SMS to primary caregiver immediately |
| Adherence deviation severity >= moderate | alert | SMS + email |
| Fall detection signal | emergency | All channels, all family members |
| Emergency room notification | emergency | All channels, all family members |
| Critical medication interaction | emergency | All channels, all family members |

---

## 6. MCP SERVER CONTRACTS

All MCP servers use Qoder's in-process SDK pattern (`create_sdk_mcp_server`) except calendar.

### 6.1 Pharmacy MCP (in-process)

**File:** `src/mcp/pharmacy_server.py`
**Tools:** `check_refill_status`, `order_refill`, `get_medication_schedule`
**Mock data:** 3 medications — Lisinopril 10mg, Metformin 500mg, Atorvastatin 20mg
**Failure simulation:** 10% random timeout on `order_refill`

### 6.2 Messaging MCP (in-process)

**File:** `src/mcp/messaging_server.py`
**Tools:** `send_sms`, `send_email`
**Mock behavior:** Logs to `logs/messages.log`, returns synthetic delivery_status

### 6.3 Delivery MCP (in-process)

**File:** `src/mcp/delivery_server.py`
**Tools:** `check_delivery_status`, `order_grocery`, `order_pharmacy_delivery`
**Mock behavior:** 15% failure rate to exercise escalation path

### 6.4 Calendar MCP (external SSE)

**Config:** Connects to Google Calendar via Qoder Connector
**Tools:** `get_calendar`, `schedule_appointment`
**Fallback:** If connector unavailable, use in-process mock

---

## 7. AUDIT TRAIL

**File:** `src/models/audit_log.py` — IMMUTABLE. Do not modify.

**Table schema (SQLite):**

```sql
CREATE TABLE audit_events (
    event_id        TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    actor           TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    care_recipient_id TEXT NOT NULL,
    rationale       TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    correlation_id  TEXT NOT NULL,
    authorization_ref TEXT,
    FOREIGN KEY (care_recipient_id) REFERENCES care_recipients(id)
);

CREATE INDEX idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX idx_audit_correlation ON audit_events(correlation_id);
CREATE INDEX idx_audit_recipient ON audit_events(care_recipient_id);

CREATE TRIGGER prevent_audit_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are immutable');
END;

CREATE TRIGGER prevent_audit_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are immutable');
END;
```

**Rule:** Every agent action MUST write to the audit trail BEFORE executing. If the write fails, the action MUST NOT execute.

---

## 8. ACCEPTANCE CRITERIA

- [ ] All 5 agents instantiate and register with Supervisor (agents-as-tools pattern)
- [ ] Supervisor routes "refill_low" event to Medication Agent and receives RefillOrder
- [ ] Medication Agent autonomously orders refill when `days_remaining <= 5`
- [ ] Communication Agent sends family alert when adherence deviation detected
- [ ] Audit trail captures every action with rationale and outcome (immutable)
- [ ] Escalation logic correctly classifies auto / alert / approve
- [ ] Caregiver dashboard displays live care status + pending approvals
- [ ] Caregiver can query "How is Mom doing today?" and receive synthesized answer
- [ ] Approval flow: pending action → caregiver approves → agent executes
- [ ] All MCP servers registered and reachable from Supervisor
- [ ] All external API calls logged to audit trail
- [ ] Unit tests pass for every tool function
- [ ] Integration test: end-to-end missed-refill flow works
- [ ] `python main.py` starts the system without error

---

## 9. NON-FUNCTIONAL REQUIREMENTS

| Requirement | Target |
|---|---|
| **Latency** | Single agent task < 5 seconds (mocked) |
| **Concurrency** | Support 10 concurrent care recipients |
| **Retry policy** | 3× with exponential backoff (1s, 2s, 4s) |
| **Audit retention** | Immutable, indefinite |
| **Error visibility** | All failures logged + escalated |
| **Security** | JWT auth for caregiver UI; API keys in env vars only |
| **Failure mode** | Never silently fail — always log + communicate |

---

## 10. OUT OF SCOPE

- Clinical decision-making (agent NEVER diagnoses, prescribes, or alters treatment)
- Real pharmacy API integration (mocked in this build)
- Real SMS/WhatsApp delivery (mocked in this build)
- HIPAA certification (architecture is HIPAA-ready, not certified)
- Mobile app (web dashboard only)

---

## 11. DELIVERABLES

- Public GitHub repo (MIT license)
- README with architecture diagram
- 5-minute demo video
- Qoder Cloud Agents deployment (if time permits)
- AWS Builder Center blog post (0.6 bonus points)