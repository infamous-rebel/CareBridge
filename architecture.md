# CareBridge System Architecture

**Last updated:** 2026-09-11
**Version:** 1.0
**Framework:** Strands Agents SDK (Python) + Qoder MCP + Qoder Cloud Agents
**Companion documents:** `SPEC.md` (functional spec), `AGENTS.md` (agent boundary rules)

---

## 1. HIGH-LEVEL ARCHITECTURE

```mermaid
flowchart TB
    subgraph Users["Users"]
        CG[Caregiver<br/>Web Dashboard]
        FM[Family Members<br/>SMS / Email]
        CR[Care Recipient<br/>Voice check-in optional]
    end

    subgraph CareBridge["CareBridge System"]
        SUP[Supervisor Agent<br/>Orchestrator]

        subgraph Specialists["Specialized Agents (as tools)"]
            MED[Medication Agent]
            APT[Appointment Agent]
            LOG[Logistics Agent]
            COM[Communication Agent]
        end

        AUDIT[(Audit Trail<br/>SQLite immutable)]
        ESC[Escalation Logic<br/>Deterministic Python]
        POL[Policy Engine<br/>Action Classifier]
    end

    subgraph MCP["MCP Integration Layer"]
        PHAR[Pharmacy MCP<br/>in-process SDK]
        MSG[Messaging MCP<br/>in-process SDK]
        DEL[Delivery MCP<br/>in-process SDK]
        CAL[Calendar MCP<br/>SSE external]
    end

    subgraph External["External World"]
        GCal[Google Calendar]
        Twilio[Twilio / SendGrid<br/>or mock logger]
        MockRx[Pharmacy Mock API<br/>JSON fixtures]
        MockDel[Delivery Mock API<br/>JSON fixtures]
    end

    CG -->|query / approve| SUP
    FM -.->|receive alerts| MSG
    CR -.->|optional check-in| COM

    SUP --> MED
    SUP --> APT
    SUP --> LOG
    SUP --> COM

    MED --> PHAR
    APT --> CAL
    LOG --> DEL
    COM --> MSG

    PHAR --> MockRx
    DEL --> MockDel
    CAL --> GCal
    MSG --> Twilio

    SUP --> AUDIT
    SUP --> ESC
    ESC --> POL
    MED --> AUDIT
    APT --> AUDIT
    LOG --> AUDIT
    COM --> AUDIT
```

---

## 2. AGENT-AS-TOOLS PATTERN

CareBridge uses the Strands Agents SDK's native **agents-as-tools** pattern. The Supervisor Agent holds instances of the four specialized agents in its `tools=[]` list. When the Supervisor's LLM decides to delegate, Strands automatically wraps the target agent as a callable tool — no custom routing code required.

### 2.1 Happy Path Sequence — Low Refill Detected

```mermaid
sequenceDiagram
    autonumber
    participant Trigger as Scheduler / Event
    participant SUP as Supervisor Agent
    participant AUD as Audit Trail
    participant MED as Medication Agent
    participant COM as Communication Agent
    participant CG as Caregiver

    Trigger->>SUP: CareEvent(refill_low, medication_id)
    SUP->>AUD: log(before_action, rationale)
    SUP->>MED: check_refill_status(medication_id)
    MED-->>SUP: RefillStatus(days_remaining=3, refill_eligible=true)
    SUP->>SUP: classify_action("order_refill") → "alert"
    SUP->>AUD: log(classified=alert)
    SUP->>MED: order_refill(medication_id, pharmacy_id)
    MED-->>SUP: RefillOrder(order_id, status=placed, eta)
    SUP->>COM: send_alert(caregiver_id, msg, level="info")
    COM-->>SUP: AlertResult(delivered, channel=sms)
    SUP->>AUD: log(outcome=success)
    SUP-->>Trigger: ResolutionResult(resolved=true)
    COM-->>CG: SMS: "Mom's refill has been placed, ETA tomorrow"
```

### 2.2 Why This Pattern

- No custom routing code — Strands handles dispatch via the LLM
- Each specialized agent has its own LLM call and tool scope
- Supervisor context stays small (only sees agent outputs, not internal tool calls)
- Enables parallel execution when multiple agents are needed for one event
- Enables independent testing of each specialized agent

---

## 3. DATA FLOWS

### 3.1 Happy Path — Low Refill → Refill Ordered → Family Notified

```mermaid
flowchart LR
    S[Scheduler<br/>daily 08:00] --> SUP[Supervisor]
    SUP --> MED[Medication Agent]
    MED --> CHK{check_refill_status}
    CHK -->|days <= 5| ORD[order_refill]
    CHK -->|days > 5| WAIT[Wait]
    ORD --> AUD[(audit_log)]
    ORD --> COM[Communication Agent]
    COM --> SMS[SMS to caregiver]
    AUD --> DASH[Dashboard update]
```

### 3.2 Exception Path — Order Failure

```mermaid
flowchart LR
    ORD[order_refill] --> FAIL{3x retry<br/>exhausted?}
    FAIL -->|no| RETRY[Retry with<br/>exponential backoff]
    RETRY --> ORD
    FAIL -->|yes| ESC[Escalate]
    ESC --> AUD[(audit_log<br/>outcome=escalated)]
    ESC --> COM[Communication Agent]
    COM --> ALERT[SMS + Email<br/>level=alert]
    ALERT --> DASH[Pending Approval<br/>Dashboard]
    DASH --> CG[Caregiver decides]
    CG --> RESUME[Manual resolution<br/>logged to audit]
```

### 3.3 Escalation Path — Adherence Deviation

```mermaid
flowchart TB
    MED[Medication Agent] --> DET[detect_adherence_pattern]
    DET --> SEV{severity?}
    SEV -->|none / mild| LOG[Log only]
    SEV -->|moderate| ALERT[send_alert<br/>level=alert]
    SEV -->|severe| EMERG[send_alert<br/>level=emergency]
    EMERG --> ALL[All family members<br/>SMS + Email + Call]
    ALERT --> PRIM[Primary caregiver<br/>SMS]
```

---

## 4. AGENT INTERACTION MODEL

```mermaid
graph TB
    subgraph Supervisor["Supervisor Agent (State Owner)"]
        CTX[Care Context<br/>medications, appointments,<br/>family, preferences]
        ROUTER[Task Router]
        CLASS[Action Classifier]
    end

    subgraph Tools["Agent Instances (in tools=[])"]
        MED[Medication Agent]
        APT[Appointment Agent]
        LOG[Logistics Agent]
        COM[Communication Agent]
    end

    CTX --> ROUTER
    ROUTER -->|refill_low| MED
    ROUTER -->|appt_upcoming| APT
    ROUTER -->|delivery_event| LOG
    ROUTER -->|notify_family| COM

    MED --> CLASS
    APT --> CLASS
    LOG --> CLASS
    COM --> CLASS

    CLASS -->|auto| EXEC[Execute]
    CLASS -->|alert| ALERT[Notify + Execute]
    CLASS -->|approve| PEND[Queue for approval]
```

**Interaction rules (enforced by `AGENTS.md`):**

- Specialized agents NEVER call each other directly.
- All cross-agent coordination passes through the Supervisor.
- Supervisor never calls external APIs directly — only via agents.
- Every agent action is classified by the Policy Engine BEFORE execution.
- Every action is written to the audit trail BEFORE execution.

---

## 5. MCP INTEGRATION ARCHITECTURE

```mermaid
flowchart LR
    SUP[Supervisor Agent] -->|mcp_servers config| MCP{MCP Registry}

    MCP --> P[Pharmacy MCP<br/>in-process SDK]
    MCP --> M[Messaging MCP<br/>in-process SDK]
    MCP --> D[Delivery MCP<br/>in-process SDK]
    MCP --> C[Calendar MCP<br/>SSE external]

    P --> PAPI[Mock Pharmacy API<br/>JSON fixtures]
    M --> MAPI[Twilio / SendGrid<br/>or mock logger]
    D --> DAPI[Mock Delivery API<br/>JSON fixtures]
    C --> GAPI[Google Calendar API<br/>via Qoder Connector]
```

**Transport rationale:**

| Server | Transport | Why |
|---|---|---|
| Pharmacy | In-process SDK | Custom tools, zero subprocess overhead |
| Messaging | In-process SDK | Custom tools, direct host state access |
| Delivery | In-process SDK | Custom tools, zero subprocess overhead |
| Calendar | SSE external | Qoder Connector already provides it |

**In-process MCP benefits:**

- No subprocess lifecycle management
- Direct access to shared Python state (e.g., audit log connection)
- Faster startup (no MCP handshake)
- Simpler debugging (single process)

**Qoder MCP configuration (`mcp_config.json`):**

```json
{
  "mcpServers": {
    "pharmacy":  { "type": "sdk" },
    "messaging": { "type": "sdk" },
    "delivery":  { "type": "sdk" },
    "calendar":  {
      "type": "sse",
      "url": "https://mcp.carebridge.dev/calendar",
      "headers": { "Authorization": "Bearer ${CALENDAR_TOKEN}" }
    }
  }
}
```

---

## 6. DATA MODEL (Entity Relationships)

```mermaid
erDiagram
    CARE_RECIPIENT ||--o{ MEDICATION : has
    CARE_RECIPIENT ||--o{ APPOINTMENT : has
    CARE_RECIPIENT ||--o{ FAMILY_MEMBER : has
    CARE_RECIPIENT ||--o{ AUDIT_EVENT : generates
    MEDICATION ||--o{ REFILL_ORDER : produces
    APPOINTMENT ||--o{ PREP_CHECKLIST : requires
    FAMILY_MEMBER ||--o{ ALERT : receives

    CARE_RECIPIENT {
        string id PK
        string name
        int age
        list conditions
        string address
    }

    MEDICATION {
        string id PK
        string name
        string dosage
        string frequency
        int refill_threshold
        string pharmacy_id
    }

    APPOINTMENT {
        string id PK
        string provider_name
        datetime datetime
        string location
        bool transportation_needed
    }

    FAMILY_MEMBER {
        string id PK
        string name
        string relationship
        string phone
        string email
        int escalation_priority
    }

    AUDIT_EVENT {
        uuid event_id PK
        datetime timestamp
        string actor
        string action_type
        string rationale
        string outcome
        uuid correlation_id
    }

    ALERT {
        string id PK
        string level
        string channel
        datetime sent_at
    }
```

---

## 7. DEPLOYMENT ARCHITECTURE

```mermaid
flowchart TB
    subgraph Dev["Development (Local)"]
        LCL["python main.py"]
        SQL[(SQLite<br/>audit.db)]
        ENV[.env<br/>API keys]
    end

    subgraph Prod["Production (Qoder Cloud Agents)"]
        CA[Cloud Agent<br/>Forward Mode]
        RUNTIME[Managed Runtime<br/>Firecracker isolation]
        ID[Identity Isolation<br/>per family]
        IM[IM Channel<br/>SMS / Email delivery]
        PG[(PostgreSQL<br/>audit + state)]
    end

    subgraph Monitoring["Observability"]
        LOGS[Cloud Logs]
        METRICS[Metrics]
        EVAL[AgentCore Evaluations]
    end

    Dev -.->|deploy| Prod
    CA --> RUNTIME
    RUNTIME --> PG
    RUNTIME --> ID
    RUNTIME --> IM
    RUNTIME --> LOGS
    RUNTIME --> METRICS
    RUNTIME --> EVAL
```

**Deployment path:**

1. **Local dev:** `python main.py` → SQLite audit trail → mock MCP servers
2. **Staging:** Cloud Agents with test family → PostgreSQL → real MCP connectors
3. **Production:** Cloud Agents with identity isolation → real pharmacy / calendar / messaging

**For the hackathon:** Local dev + Cloud Agents deploy (even without real external APIs).

---

## 8. SECURITY & AUTHORIZATION MODEL

```mermaid
flowchart LR
    ACT[Agent proposes action] --> SCHEMA[Pydantic schema validation]
    SCHEMA --> POL[Policy Engine<br/>classify_action]
    POL -->|auto| EXEC[Execute]
    POL -->|alert| NOTIFY[Notify + Execute]
    POL -->|approve| QUEUE[Queue for human approval]
    QUEUE --> CG[Caregiver approves / rejects]
    CG -->|approved| EXEC
    CG -->|rejected| AUDIT[(audit_log<br/>outcome=rejected)]
    EXEC --> VERIFY[Verify outcome]
    VERIFY --> AUDIT2[(audit_log<br/>outcome=success / failure)]
```

**Authorization layers:**

1. **Schema validation** — every agent action must conform to a Pydantic model
2. **Policy classification** — deterministic Python (NOT LLM)
3. **Human approval gate** — for destructive or clinical actions
4. **Audit-before-action** — write to audit log BEFORE executing
5. **Outcome verification** — confirm the action actually succeeded
6. **Immutable audit** — SQLite triggers prevent UPDATE / DELETE

---

## 9. FAILURE RECOVERY

```mermaid
stateDiagram-v2
    [*] --> Attempt1
    Attempt1 --> Success: 90% (mock)
    Attempt1 --> Retry1: fail
    Retry1 --> Success: backoff 1s
    Retry1 --> Retry2: fail
    Retry2 --> Success: backoff 2s
    Retry2 --> Retry3: fail
    Retry3 --> Success: backoff 4s
    Retry3 --> Escalate: 3x exhausted
    Escalate --> Audit[Log outcome=escalated]
    Audit --> Notify[Notify family]
    Notify --> Manual[Manual resolution]
    Manual --> [*]
    Success --> Audit2[Log outcome=success]
    Audit2 --> [*]
```

**Failure rules:**

- Retry 3× with exponential backoff (1s, 2s, 4s)
- After 3 failures: escalate with `level="alert"` to primary caregiver
- Never silently fail — every failure logged + communicated
- Every integration has a documented fallback plan

---

## 10. DIRECTORY STRUCTURE

```
carebridge/
├── AGENTS.md                     # architecture rules (Qoder reads on every session)
├── SPEC.md                       # functional spec
├── architecture.md               # this document
├── README.md                     # setup + demo instructions
├── main.py                       # entry point
├── requirements.txt
├── .env.example
├── .gitignore
├── mcp_config.json               # MCP server registry
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── supervisor_agent.py
│   │   ├── medication_agent.py
│   │   ├── appointment_agent.py
│   │   ├── logistics_agent.py
│   │   └── communication_agent.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── medication_tools.py
│   │   ├── appointment_tools.py
│   │   ├── logistics_tools.py
│   │   └── communication_tools.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py            # Pydantic models
│   │   ├── audit_log.py          # IMMUTABLE audit trail
│   │   └── escalation_logic.py   # deterministic classifier
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── pharmacy_server.py
│   │   ├── messaging_server.py
│   │   ├── delivery_server.py
│   │   └── calendar_server.py
│   └── ui/
│       ├── package.json
│       ├── app/
│       │   ├── page.tsx          # caregiver dashboard
│       │   ├── alerts/page.tsx
│       │   ├── approvals/page.tsx
│       │   └── audit/page.tsx
│       └── components/
│           ├── CareStatusCard.tsx
│           ├── AlertFeed.tsx
│           ├── ApprovalQueue.tsx
│           └── AuditTrail.tsx
├── tests/
│   ├── __init__.py
│   ├── test_medication_agent.py
│   ├── test_appointment_agent.py
│   ├── test_logistics_agent.py
│   ├── test_communication_agent.py
│   ├── test_supervisor.py
│   └── integration/
│       ├── test_refill_flow.py
│       ├── test_escalation_flow.py
│       └── test_approval_flow.py
├── fixtures/
│   ├── medications.json
│   ├── appointments.json
│   ├── family_members.json
│   └── delivery_history.json
└── logs/
    ├── messages.log
    └── audit.db
```

---

## 11. TECHNOLOGY STACK

| Layer | Technology | Rationale |
|---|---|---|
| Agent framework | Strands Agents SDK (Python) | Native agents-as-tools pattern |
| Model | Claude Sonnet via Amazon Bedrock | Best reasoning for care coordination |
| MCP | Qoder MCP SDK (in-process + SSE) | Zero subprocess overhead for custom tools |
| Storage (dev) | SQLite | Zero-config, fast setup |
| Storage (prod) | PostgreSQL (Supabase) | Production-grade, HIPAA-ready |
| Frontend | React / Next.js 15 | Fast dashboard, server components |
| Deployment | Qoder Cloud Agents (Forward Mode) | Fastest path to live demo |
| Testing | pytest + pytest-asyncio | Standard Python testing |

---

## 12. DEPLOYMENT CHECKLIST

- [ ] `python main.py` runs locally without errors
- [ ] Audit trail database created and writable
- [ ] All 4 MCP servers registered in `mcp_config.json`
- [ ] Caregiver dashboard loads at `http://localhost:3000`
- [ ] End-to-end refill flow works (detect → order → alert → approve)
- [ ] Cloud Agents deployment succeeds
- [ ] Environment variables set (`.env` not committed to repo)
- [ ] README complete with setup steps
- [ ] Demo video recorded and uploaded
- [ ] AWS Builder Center blog post published

---

## 13. ARCHITECTURAL DECISIONS (ADRs)

### ADR-001: Agents-as-Tools over Multi-Agent Chat

**Decision:** Use Strands Agents SDK's agents-as-tools pattern instead of a free-form multi-agent chat.

**Reason:** Deterministic routing, smaller context windows per agent, independent testing, and clear ownership boundaries. A free-form multi-agent chat has unpredictable routing and higher hallucination risk — unacceptable for care coordination.

### ADR-002: In-Process MCP for Custom Tools

**Decision:** Pharmacy, Messaging, and Delivery MCP servers run in-process. Only Calendar runs externally via SSE.

**Reason:** In-process MCP eliminates subprocess lifecycle management, enables direct access to shared Python state (audit log), and simplifies debugging. Only Calendar needs external transport because Qoder's Connector already provides it.

### ADR-003: Deterministic Escalation Logic

**Decision:** Escalation classification is Python code, NOT an LLM call.

**Reason:** Escalation decisions are safety-critical. Deterministic logic is auditable, testable, and cannot be manipulated by prompt injection. The LLM proposes actions; the Policy Engine classifies them.

### ADR-004: Audit-Before-Action

**Decision:** Every agent action writes to the audit trail BEFORE executing.

**Reason:** If the audit write fails, the action must not execute. This ensures no action can occur without a record. Combined with SQLite triggers preventing UPDATE/DELETE, this provides a tamper-evident log.

### ADR-005: Caregiver as Primary User

**Decision:** The adult child is the primary user of the product. The older adult is a passive beneficiary.

**Reason:** Older adults resist technology that threatens autonomy. Caregivers are the ones making decisions and absorbing coordination burden. Designing for the caregiver (with the older adult as a passive beneficiary) removes the adoption barrier entirely for the older adult.