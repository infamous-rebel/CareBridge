# Testing Strategy

<cite>
**Referenced Files in This Document**
- [pyproject.toml](file://pyproject.toml)
- [requirements.txt](file://requirements.txt)
- [conftest.py](file://conftest.py)
- [tests/integration/test_refill_flow.py](file://tests/integration/test_refill_flow.py)
- [tests/integration/test_escalation_flow.py](file://tests/integration/test_escalation_flow.py)
- [tests/integration/test_approval_flow.py](file://tests/integration/test_approval_flow.py)
- [tests/test_medication_agent.py](file://tests/test_medication_agent.py)
- [tests/test_appointment_agent.py](file://tests/test_appointment_agent.py)
- [tests/test_communication_agent.py](file://tests/test_communication_agent.py)
- [tests/test_logistics_agent.py](file://tests/test_logistics_agent.py)
- [tests/test_supervisor.py](file://tests/test_supervisor.py)
- [fixtures/medications.json](file://fixtures/medications.json)
- [fixtures/appointments.json](file://fixtures/appointments.json)
</cite>

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Dependency Analysis
7. Performance Considerations
8. Troubleshooting Guide
9. Conclusion

## Introduction
This document describes the multi-layered testing strategy for CareBridge, ensuring system reliability and correctness across unit tests, integration flows, and quality assurance practices. It explains how pytest is configured for async support, how fixtures and mocks are used to simulate external services, and how end-to-end scenarios (refill, escalation, approval) validate agent behavior, escalation logic, and audit trail integrity. Guidance is also provided for writing effective tests for new features and considerations for performance and load testing concurrent care recipient scenarios.

## Project Structure
CareBridge organizes tests by scope:
- Unit tests per agent and tool under tests/
- Integration tests covering end-to-end workflows under tests/integration/
- JSON fixtures under fixtures/ providing realistic data for tools and agents
- Shared test configuration via conftest.py and pytest settings in pyproject.toml

```mermaid
graph TB
subgraph "Tests"
U["Unit Tests<br/>tests/*.py"]
I["Integration Tests<br/>tests/integration/*.py"]
end
subgraph "Fixtures"
F1["medications.json"]
F2["appointments.json"]
end
subgraph "Config"
C1["pyproject.toml<br/>pytest asyncio_mode=auto"]
C2["conftest.py<br/>temp_audit_db fixture"]
end
U --> C2
I --> C2
U --> F1
U --> F2
I --> F1
I --> F2
```

**Diagram sources**
- [pyproject.toml:1-4](file://pyproject.toml#L1-L4)
- [conftest.py:1-60](file://conftest.py#L1-L60)
- [fixtures/medications.json:1-33](file://fixtures/medications.json#L1-L33)
- [fixtures/appointments.json:1-33](file://fixtures/appointments.json#L1-L33)

**Section sources**
- [pyproject.toml:1-4](file://pyproject.toml#L1-L4)
- [requirements.txt:1-8](file://requirements.txt#L1-L8)
- [conftest.py:1-60](file://conftest.py#L1-L60)

## Core Components
- Async test execution: pytest is configured with asyncio_mode auto so async tests run without explicit markers.
- Isolation: A shared temp_audit_db fixture rewrites default DB paths and resets supervisor state per test, ensuring isolation and deterministic outcomes.
- Fixtures: JSON fixtures provide deterministic medication and appointment data for tools and agents.
- Mocking: External APIs are simulated or patched at the module level to control behavior and failure modes.

Key patterns observed:
- Tool-level assertions on return values and error handling.
- Agent-level assertions on event routing, actions taken, and escalation flags.
- End-to-end verification of audit trail entries, correlation IDs, and outcomes.

**Section sources**
- [pyproject.toml:1-4](file://pyproject.toml#L1-L4)
- [conftest.py:7-60](file://conftest.py#L7-L60)
- [fixtures/medications.json:1-33](file://fixtures/medications.json#L1-L33)
- [fixtures/appointments.json:1-33](file://fixtures/appointments.json#L1-L33)

## Architecture Overview
The testing architecture mirrors the runtime architecture: events flow through a supervisor that routes to specialized agents (medication, appointment, logistics, communication). Tests assert both functional outcomes and audit trail integrity.

```mermaid
sequenceDiagram
participant T as "Test"
participant S as "Supervisor Agent"
participant M as "Medication Agent"
participant L as "Logistics Agent"
participant C as "Communication Agent"
participant A as "Audit Log"
T->>S : process_event(CareEvent)
alt refill_low
S->>M : handle_medication_event()
M-->>S : ResolutionResult (actions, escalation?)
else delivery_failed
S->>L : handle_logistics_event()
L-->>S : ResolutionResult (escalation?)
end
alt escalation_required
S->>C : send_alert / escalate
C-->>S : AlertResult
end
S->>A : write_audit_event(pending/follow-up)
S-->>T : ResolutionResult + audit_event_ids
```

**Diagram sources**
- [tests/integration/test_refill_flow.py:14-48](file://tests/integration/test_refill_flow.py#L14-L48)
- [tests/integration/test_escalation_flow.py:16-54](file://tests/integration/test_escalation_flow.py#L16-L54)
- [tests/test_supervisor.py:67-115](file://tests/test_supervisor.py#L67-L115)

## Detailed Component Analysis

### Refill Flow Integration
End-to-end validation of refill_low events:
- Event routed to medication agent; refill ordered when days_remaining <= threshold.
- Audit trail includes pending and follow-up entries linked by correlation_id.
- Escalation occurs for alert-category actions like order_refill.

```mermaid
flowchart TD
Start(["Start: refill_low event"]) --> Route["Route to Medication Agent"]
Route --> CheckRefill{"Days remaining <= threshold?"}
CheckRefill -- Yes --> Order["Place refill order"]
CheckRefill -- No --> Skip["No refill needed"]
Order --> AuditPending["Write audit 'pending'"]
Skip --> AuditPending
AuditPending --> Outcome["Write outcome/follow-up"]
Outcome --> End(["End: verify audit and actions"])
```

**Diagram sources**
- [tests/integration/test_refill_flow.py:14-48](file://tests/integration/test_refill_flow.py#L14-L48)
- [tests/integration/test_refill_flow.py:49-63](file://tests/integration/test_refill_flow.py#L49-L63)
- [tests/integration/test_refill_flow.py:64-82](file://tests/integration/test_refill_flow.py#L64-L82)

**Section sources**
- [tests/integration/test_refill_flow.py:14-82](file://tests/integration/test_refill_flow.py#L14-L82)

### Escalation Flow Integration
Validates that failures and critical events trigger escalation:
- Retry exhaustion from pharmacy API leads to escalation and family alerts.
- Essential delivery failures escalate immediately.
- Adherence deviations with moderate severity escalate.

```mermaid
sequenceDiagram
participant T as "Test"
participant S as "Supervisor Agent"
participant M as "Medication Agent"
participant R as "Retry Layer"
participant C as "Communication Agent"
participant A as "Audit Log"
T->>S : process_event(refill_low)
S->>M : order_refill()
M->>R : with_retry()
R-->>M : RetryExhausted
M-->>S : escalation_required=True
S->>C : send_alert(level=alert)
C-->>S : AlertResult
S->>A : write_audit_event(escalated)
S-->>T : Result with escalation and actions
```

**Diagram sources**
- [tests/integration/test_escalation_flow.py:16-54](file://tests/integration/test_escalation_flow.py#L16-L54)
- [tests/integration/test_escalation_flow.py:56-82](file://tests/integration/test_escalation_flow.py#L56-L82)
- [tests/integration/test_escalation_flow.py:83-97](file://tests/integration/test_escalation_flow.py#L83-L97)

**Section sources**
- [tests/integration/test_escalation_flow.py:16-97](file://tests/integration/test_escalation_flow.py#L16-L97)

### Approval Flow Integration
Validates human-in-the-loop approvals:
- Pending actions created in audit log can be approved or rejected.
- Approvals execute actions and record authorization references.
- Rejections log rejection rationale without execution.

```mermaid
sequenceDiagram
participant T as "Test"
participant S as "Supervisor Agent"
participant A as "Audit Log"
T->>A : write_audit_event(outcome=pending)
T->>S : approve_pending_action(action_id, approved=True/False)
alt approved
S->>A : write_audit_event(approve_action, authorization_ref)
S->>A : write_audit_event(execution result)
else rejected
S->>A : write_audit_event(reject_action, authorization_ref)
end
S-->>T : Verified audit trail
```

**Diagram sources**
- [tests/integration/test_approval_flow.py:15-57](file://tests/integration/test_approval_flow.py#L15-L57)
- [tests/integration/test_approval_flow.py:58-96](file://tests/integration/test_approval_flow.py#L58-L96)
- [tests/integration/test_approval_flow.py:97-130](file://tests/integration/test_approval_flow.py#L97-L130)

**Section sources**
- [tests/integration/test_approval_flow.py:15-130](file://tests/integration/test_approval_flow.py#L15-L130)

### Unit Testing Patterns: Agents and Tools
- Medication agent and tools:
  - Assert refill eligibility and adherence pattern detection against fixture data.
  - Simulate API failures and verify retry exhaustion triggers escalation.
- Appointment agent and tools:
  - Validate calendar retrieval, scheduling, and checklist sending.
  - Handle invalid recipients and API failures gracefully.
- Communication agent and tools:
  - Verify alert levels (info/alert/emergency) and channel selection.
  - Synthesize status summaries and family preferences.
- Logistics agent and tools:
  - Check delivery statuses and order placements.
  - Escalate on essential delivery failures and missing identifiers.

```mermaid
classDiagram
class TestCheckRefillStatus
class TestOrderRefill
class TestDetectAdherencePattern
class TestHandleMedicationEvent
class TestGetCalendar
class TestScheduleAppointment
class TestSendPrepChecklist
class TestHandleAppointmentEvent
class TestSendAlert
class TestSynthesizeStatus
class TestGetFamilyPreferences
class TestHandleCommunicationEvent
class TestCheckDeliveryStatus
class TestOrderGrocery
class TestOrderPharmacyDelivery
class TestHandleLogisticsEvent
```

**Diagram sources**
- [tests/test_medication_agent.py:19-177](file://tests/test_medication_agent.py#L19-L177)
- [tests/test_appointment_agent.py:18-127](file://tests/test_appointment_agent.py#L18-L127)
- [tests/test_communication_agent.py:23-141](file://tests/test_communication_agent.py#L23-L141)
- [tests/test_logistics_agent.py:18-148](file://tests/test_logistics_agent.py#L18-L148)

**Section sources**
- [tests/test_medication_agent.py:19-177](file://tests/test_medication_agent.py#L19-L177)
- [tests/test_appointment_agent.py:18-127](file://tests/test_appointment_agent.py#L18-L127)
- [tests/test_communication_agent.py:23-141](file://tests/test_communication_agent.py#L23-L141)
- [tests/test_logistics_agent.py:18-148](file://tests/test_logistics_agent.py#L18-L148)

### Supervisor Agent and Escalation Logic
- Routing: Events route to appropriate agents based on type.
- Escalation classification: Deterministic action classification ensures safety defaults.
- Query status: Aggregates synthesized status for care recipients.
- Approval workflow: Enforces idempotency and validates resolution states.

```mermaid
flowchart TD
Classify["Classify action"] --> Auto{"Auto?"}
Auto -- Yes --> Execute["Execute autonomously"]
Auto -- No --> RequireApproval{"Requires approval?"}
RequireApproval -- Yes --> Pending["Create pending action"]
RequireApproval -- No --> Alert["Escalate to alert"]
Pending --> HumanReview["Human review"]
HumanReview --> Approved{"Approved?"}
Approved -- Yes --> Execute
Approved -- No --> Reject["Reject and log"]
```

**Diagram sources**
- [tests/test_supervisor.py:19-57](file://tests/test_supervisor.py#L19-L57)
- [tests/test_supervisor.py:67-115](file://tests/test_supervisor.py#L67-L115)
- [tests/test_supervisor.py:137-197](file://tests/test_supervisor.py#L137-L197)

**Section sources**
- [tests/test_supervisor.py:19-197](file://tests/test_supervisor.py#L19-L197)

### Audit Trail Integrity
- Every process_event writes multiple audit events (pending and follow-up).
- Immutability enforced via database triggers; attempts to update/delete raise integrity errors.
- Correlation IDs link related events across flows.

```mermaid
flowchart TD
Start(["process_event"]) --> WritePending["Write 'pending' audit event"]
WritePending --> Process["Process via agent(s)"]
Process --> WriteOutcome["Write outcome/follow-up"]
WriteOutcome --> Verify["Verify correlation_id and counts"]
Verify --> End(["End"])
```

**Diagram sources**
- [tests/integration/test_refill_flow.py:64-82](file://tests/integration/test_refill_flow.py#L64-L82)
- [tests/test_supervisor.py:207-276](file://tests/test_supervisor.py#L207-L276)

**Section sources**
- [tests/integration/test_refill_flow.py:64-82](file://tests/integration/test_refill_flow.py#L64-L82)
- [tests/test_supervisor.py:207-276](file://tests/test_supervisor.py#L207-L276)

## Dependency Analysis
External dependencies relevant to testing:
- pytest and pytest-asyncio enable async test execution.
- Strands agents framework provides agent abstractions.
- Pydantic models ensure schema validation in tests.
- Boto3 and python-dotenv may be used for environment/config but are not directly invoked in the analyzed tests.

```mermaid
graph LR
P["pytest"] --> PA["pytest-asyncio"]
P --> T["Unit & Integration Tests"]
SA["strands-agents"] --> A["Agents"]
PD["pydantic"] --> S["Schemas"]
T --> A
T --> S
```

**Diagram sources**
- [requirements.txt:1-8](file://requirements.txt#L1-L8)

**Section sources**
- [requirements.txt:1-8](file://requirements.txt#L1-L8)

## Performance Considerations
- Use isolated temp databases per test to avoid contention and ensure deterministic results.
- Prefer targeted mocking of external APIs to minimize flakiness and speed up tests.
- For concurrency and load testing:
  - Run parallel test suites using pytest-xdist to simulate concurrent care recipients.
  - Introduce controlled backpressure by patching slow external calls and asserting timeouts/retries.
  - Measure end-to-end latency for approval flows under load to identify bottlenecks in audit logging and agent routing.
  - Validate that escalation pathways remain responsive under high event throughput.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Audit DB path conflicts: Ensure the temp_audit_db fixture runs; it rewrites function defaults and patches module-level constants to use a temporary database.
- State leakage between tests: The fixture clears resolved-action caches and resets supervisor flags to maintain independence.
- External API flakiness: Patch specific modules where APIs are called; simulate failures to exercise retry and escalation paths.
- Invalid identifiers: Tests assert ValueError for unknown medications, appointments, deliveries, and families; ensure fixtures contain expected IDs.

**Section sources**
- [conftest.py:7-60](file://conftest.py#L7-L60)
- [tests/test_medication_agent.py:36-40](file://tests/test_medication_agent.py#L36-L40)
- [tests/test_appointment_agent.py:28-32](file://tests/test_appointment_agent.py#L28-L32)
- [tests/test_logistics_agent.py:34-38](file://tests/test_logistics_agent.py#L34-L38)
- [tests/test_communication_agent.py:86-90](file://tests/test_communication_agent.py#L86-L90)

## Conclusion
CareBridge’s testing strategy combines robust unit tests, comprehensive integration flows, and strict audit trail verification to ensure reliability and correctness. Async support, isolated fixtures, and targeted mocking enable fast, deterministic tests that cover normal operations, error conditions, and escalation scenarios. Following these patterns will help maintain high-quality coverage as new features are added, while performance and load testing practices ensure scalability under concurrent care recipient workloads.