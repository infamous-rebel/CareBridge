"""CareBridge Supervisor Agent — orchestration of specialized care agents.

The Supervisor is the single entry point for care events. It NEVER calls
external APIs directly: it routes work to the specialized agents
(Medication, Appointment, Logistics, Communication), makes escalation
decisions using the deterministic classify_action() rules from
src/models/escalation_logic.py, and writes an immutable audit-trail entry
BEFORE any action executes.

Routing model
-------------
Routing is LLM-driven. ``create_supervisor_agent()`` builds a real Strands
``Agent`` whose model comes from the provider-agnostic factory in
``src/runtime/model_factory.py`` (selected by ``LLM_PROVIDER``), with the four
specialist agents attached as tools — so the LLM reads the incoming event and
decides which specialist to invoke. ``process_event()`` contains no
``if event_type == ...`` dispatch: the decision is the model's.

Two things are deliberately NOT delegated to the LLM:

1. Escalation classification stays deterministic (AGENTS.md §3/§8 — "never let
   an LLM classify an action as autonomous vs. requiring approval"). The LLM's
   escalation opinion is captured as advisory context; ``classify_action()`` and
   the hard-coded emergency triggers remain authoritative.
2. The audit trail is written by this module before/after execution, never by
   the model.

FALLBACK PATH — used only when the LLM is unavailable (no API key, missing
provider SDK, or offline tests): ``_route_via_fallback()`` performs the same
routing from a declarative table so the system, the demo, and the test suite
keep working with no network. An LLM invocation that fails at runtime also
degrades to that table for the affected event, loudly (logged + audited),
never silently (AGENTS.md §9).
"""

import json
import logging
import threading
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID, uuid4

from src.models.schemas import (
    CareEvent,
    PendingAction,
    ResolutionResult,
)
from src.models.audit_log import (
    get_audit_events,
    init_audit_db,
    write_audit_event,
)
from src.models.escalation_logic import (
    EMERGENCY_TRIGGERS,
    classify_action,
)
from src.agents.medication_agent import (
    create_medication_agent,
    handle_medication_event,
)
from src.agents.appointment_agent import (
    create_appointment_agent,
    handle_appointment_event,
)
from src.agents.logistics_agent import (
    create_logistics_agent,
    handle_logistics_event,
)
from src.agents.communication_agent import (
    create_communication_agent,
    handle_communication_event,
)
from src.tools.communication_tools import synthesize_status
from src.mcp import get_mcp_server_configs
from src.runtime.model_factory import (
    get_configured_model_id,
    get_model,
    get_provider_name,
)

logger = logging.getLogger(__name__)

# All four MCP server configs, attached to the Supervisor's Strands Agent for
# orchestration-level visibility (SPEC.md §6 / architecture.md §5). Order
# matches the "Attached MCP servers" demo log line emitted in main.py.
_ALL_MCP_CONFIGS = get_mcp_server_configs()
SUPERVISOR_MCP_SERVERS: list[dict] = [
    _ALL_MCP_CONFIGS[name]
    for name in ("pharmacy", "messaging", "delivery", "calendar")
]

SUPERVISOR_SYSTEM_PROMPT = """You are the CareBridge Supervisor, an AI care coordination agent.

You ORCHESTRATE care for elderly individuals. You have four specialist agents
available as tools:

- CareBridgeMedication    — medication refills, adherence, pharmacy status
- CareBridgeAppointment   — calendar, scheduling, appointment prep
- CareBridgeLogistics     — pharmacy and grocery delivery
- CareBridgeCommunication — family alerts, notifications, status digests

For each incoming care event you MUST:
1. Read the event (its type, payload, and care recipient) carefully.
2. Decide which ONE specialist is responsible for that intent.
3. Invoke that specialist tool, passing the care event details it needs.
4. Write a rationale for your decision — one sentence, plain language, saying
   why that specialist owns this event.
5. Then consider whether the family needs to be notified, and report your
   recommendation.

You MUST NOT:
- Call a specialist that does not match the event intent. Never route a
  medication event to Logistics, or a delivery event to Appointment.
- Invoke more than one specialist for a single event unless the event genuinely
  spans two domains; if it does, state why in your rationale.
- Call external APIs directly, or invent tool results you did not receive.
- Make clinical decisions: never diagnose, prescribe, or alter treatment. You
  coordinate care; you do not practice medicine.
- Skip or fabricate a rationale.
- Include names, addresses, or phone numbers in your output — reference
  identifiers only (PII never appears in logs or the audit trail).

Escalation is NOT yours to decide. The system computes the authoritative
escalation level deterministically from classify_action() and hard-coded
emergency triggers (fall detection, ER visit, critical medication interaction).
Your recommendation is advisory context only and will never override that
determination.

Finish every response with a single JSON object on its own line, and nothing
after it:

{"routed_to": "<medication|appointment|logistics|communication>", "rationale": "<one sentence>", "actions_taken": ["<what the specialist actually did>"], "escalation_recommended": "<none|info|alert|emergency>"}
"""

# ---------------------------------------------------------------------------
# Internal routing tables
# ---------------------------------------------------------------------------

# Escalation level severity ranking: info < alert < emergency (AGENTS.md §8).
_LEVEL_RANK: dict[str, int] = {"info": 1, "alert": 2, "emergency": 3}

# Which specialized agent owns each action type. Used by
# approve_pending_action() to route approved actions to the correct agent.
_APPROVAL_AGENT_ROUTES: dict[str, str] = {
    # Medication Agent actions
    "check_refill_status": "medication",
    "order_refill": "medication",
    "detect_adherence_pattern": "medication",
    "change_medication_schedule": "medication",
    # Appointment Agent actions
    "get_calendar": "appointment",
    "schedule_appointment": "appointment",
    "cancel_appointment": "appointment",
    "send_prep_checklist": "appointment",
    "add_service_provider": "appointment",
    # Logistics Agent actions
    "check_delivery_status": "logistics",
    "order_grocery": "logistics",
    "order_pharmacy_delivery": "logistics",
    # Communication Agent actions
    "send_alert": "communication",
    "synthesize_status": "communication",
    "send_daily_digest": "communication",
}

# CareEvent event_type used to re-dispatch an approved action to the agent
# that owns it. Day 1 schema constraint: CareEvent.event_type is a Literal of
# exactly these four values, so the Communication Agent receives its work
# carried on an "adherence_deviation" event with an explicit level/message
# payload (it reads level and message from payload, not event_type).
_AGENT_EVENT_TYPES: dict[str, str] = {
    "medication": "refill_low",
    "appointment": "appointment_upcoming",
    "logistics": "delivery_failed",
    "communication": "adherence_deviation",
}

# Specialist area -> its async event handler. Used by approve_pending_action()
# to execute a human-approved action deterministically: approval execution is a
# safety path and is never delegated to an LLM (AGENTS.md §3).
_AGENT_HANDLERS: dict[str, Callable[[CareEvent], Awaitable[dict]]] = {
    "medication": handle_medication_event,
    "appointment": handle_appointment_event,
    "logistics": handle_logistics_event,
    "communication": handle_communication_event,
}

# FALLBACK PATH — used only when the LLM is unavailable (no API key, missing
# provider SDK, offline tests), or when an LLM invocation fails at runtime.
#
# This is a declarative table, deliberately NOT a chain of
# ``if event_type == ...`` branches. ``process_event()`` performs no conditional
# routing of its own: whenever a model is configured, the LLM is the router and
# this table is never consulted.
_FALLBACK_ROUTES: dict[str, tuple[str, Callable[[CareEvent], Awaitable[dict]]]] = {
    "refill_low": ("medication", handle_medication_event),
    "adherence_deviation": ("medication", handle_medication_event),
    "appointment_upcoming": ("appointment", handle_appointment_event),
    "delivery_failed": ("logistics", handle_logistics_event),
}

# Strands tool name (each specialist Agent's ``name``) -> specialist area. Lets
# the Supervisor report which specialist the LLM actually invoked.
_SPECIALIST_TOOL_AREAS: dict[str, str] = {
    "CareBridgeMedication": "medication",
    "CareBridgeAppointment": "appointment",
    "CareBridgeLogistics": "logistics",
    "CareBridgeCommunication": "communication",
}

# Specialist factories, attached as tools in this order (agents-as-tools).
_SPECIALIST_FACTORIES: tuple[Callable[[], Optional[Any]], ...] = (
    create_medication_agent,
    create_appointment_agent,
    create_logistics_agent,
    create_communication_agent,
)

# Process-local flags (Day 1: single-process orchestration).
_audit_db_initialized: bool = False
_resolved_action_ids: set[str] = set()

# Routing mode ("llm" | "fallback") is resolved once per process and announced on
# first use, so a demo recording visibly proves which path handled the events.
_ROUTING_MODE_LLM = "llm"
_ROUTING_MODE_FALLBACK = "fallback"
_routing_mode: Optional[str] = None
_routing_mode_announced: bool = False
_routing_mode_lock = threading.Lock()

# Cached Supervisor Agent, used for startup introspection and /ready.
_supervisor_agent: Optional[Any] = None
_supervisor_agent_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_audit_db() -> None:
    """Initialize the audit database once per process (idempotent).

    Guarantees the audit_events table and immutability triggers exist before
    the Supervisor writes its first "before action" entry.
    """
    global _audit_db_initialized
    if not _audit_db_initialized:
        init_audit_db()
        _audit_db_initialized = True


def _raise_level(
    current: Optional[str], candidate: Optional[str]
) -> Optional[str]:
    """Return the more severe of two escalation levels.

    Args:
        current: Current escalation level ("info" | "alert" | "emergency" | None).
        candidate: Candidate escalation level ("info" | "alert" | "emergency" | None).

    Returns:
        The higher-severity level, or None if both are None.
    """
    if current is None:
        return candidate
    if candidate is None:
        return current
    if _LEVEL_RANK.get(candidate, 0) > _LEVEL_RANK.get(current, 0):
        return candidate
    return current


def _refill_low_actions(agent_result: dict) -> list[str]:
    """Actions executed while handling a ``refill_low`` event.

    The Medication Agent reports a refill_order only when an order was actually
    attempted (placed or softly failed).

    Args:
        agent_result: Structured result dict from the specialized agent.

    Returns:
        ``["order_refill"]`` when an order was attempted, otherwise
        ``["check_refill_status"]``.
    """
    if agent_result.get("refill_order") is not None:
        return ["order_refill"]
    return ["check_refill_status"]


def _static_actions(*action_types: str) -> Callable[[dict], list[str]]:
    """Build a resolver that always reports the same executed actions.

    Args:
        *action_types: Action names to report for the event type.

    Returns:
        Resolver taking the agent result and returning the action names.
    """
    def _resolver(agent_result: dict) -> list[str]:
        return list(action_types)

    return _resolver


# event_type -> resolver listing the classified actions that actually executed.
_EVENT_ACTION_RESOLVERS: dict[str, Callable[[dict], list[str]]] = {
    "refill_low": _refill_low_actions,
    "adherence_deviation": _static_actions("check_refill_status"),
    "appointment_upcoming": _static_actions("get_calendar"),
    "delivery_failed": _static_actions("check_delivery_status"),
}


def _executed_actions(event: CareEvent, agent_result: dict) -> list[str]:
    """Deterministically list the classified actions executed for an event.

    Maps the event type and the specialized agent's structured result to the
    action names defined in the escalation tables. Only actions that actually
    executed are listed (e.g., "order_refill" only when the Medication Agent
    attempted an order).

    Args:
        event: The care event being processed.
        agent_result: The structured result dict returned by the specialized agent.

    Returns:
        List of action-type names for classify_action() evaluation.
    """
    resolver = _EVENT_ACTION_RESOLVERS.get(event.event_type)
    return resolver(agent_result) if resolver is not None else []


def _evaluate_escalation(
    event: CareEvent, agent_result: dict
) -> tuple[bool, Optional[str]]:
    """Deterministic escalation decision — never LLM-decided.

    Combines three deterministic sources (all from
    src/models/escalation_logic.py and the structured agent results):

    1. Hard-coded emergency triggers (fall detection, ER visit, critical
       medication interaction) — AGENTS.md §8.
    2. classify_action() on the actions that actually executed while handling
       the event (ALERT-category actions always notify the family).
    3. The specialized agent's own escalation flags (e.g., essential delivery
       failure, moderate/severe adherence deviation).

    Args:
        event: The care event being processed.
        agent_result: The structured result dict returned by the specialized agent.

    Returns:
        Tuple of (escalation_required, escalation_level) where the level is
        one of "info" | "alert" | "emergency", or None when no escalation
        is required.
    """
    escalation_required: bool = False
    escalation_level: Optional[str] = None

    # Source 1: hard-coded emergency triggers (AGENTS.md §8 — never LLM-decided).
    trigger = event.payload.get("trigger")
    if trigger in EMERGENCY_TRIGGERS:
        escalation_required = True
        escalation_level = _raise_level(escalation_level, "emergency")

    # Source 2: deterministic classification of the actions that executed.
    for action_type in _executed_actions(event, agent_result):
        classification = classify_action(action_type)
        if classification == "alert":
            escalation_required = True
            escalation_level = _raise_level(escalation_level, "alert")
        elif classification == "approve":
            # Safety net: an APPROVE-category action executed without human
            # authorization — surface it for immediate human review.
            logger.warning(
                "APPROVE-category action executed without authorization: %s",
                action_type,
            )
            escalation_required = True
            escalation_level = _raise_level(escalation_level, "alert")

    # Source 3: the specialized agent's structured escalation flags.
    if agent_result.get("escalation_required"):
        escalation_required = True
        escalation_level = _raise_level(
            escalation_level, agent_result.get("escalation_level")
        )

    return escalation_required, escalation_level


def _build_alert_message(
    event: CareEvent, agent_result: dict, level: str
) -> str:
    """Build the family alert message from the event and actions taken.

    References IDs only — never raw PII (AGENTS.md §10).

    Args:
        event: The care event that triggered the escalation.
        agent_result: The structured result dict from the specialized agent.
        level: The escalation level ("info" | "alert" | "emergency").

    Returns:
        Human-readable alert message for the Communication Agent.
    """
    key_actions = "; ".join(agent_result.get("actions_taken", [])[:3])
    return (
        f"CareBridge {level} for care recipient {event.care_recipient_id} "
        f"({event.event_type}): {key_actions}"
    )


_ROUTING_PROMPT_TEMPLATE = """A care event has arrived. Decide which ONE specialist agent owns it and request that tool now.

Event (JSON):
{event_json}

Rules for this turn:
- Request exactly one specialist tool: the one whose domain matches the event intent.
- Then report your decision as the JSON object described in your instructions.
- Reason only from the event above; never invent medication, appointment, or delivery data.
"""


def _build_routing_prompt(event: CareEvent) -> str:
    """Build the routing instruction sent to the LLM for one care event.

    Carries identifiers and event data only — never PII (AGENTS.md §10).

    Args:
        event: The care event to route.

    Returns:
        The user-turn prompt text.
    """
    return _ROUTING_PROMPT_TEMPLATE.format(
        event_json=event.model_dump_json(indent=2)
    )


def _extract_json_object(text: str) -> Optional[dict]:
    """Parse the routing envelope out of raw model output.

    Scans every brace-balanced candidate and prefers the last one that looks
    like the envelope, tolerating markdown fences and trailing prose that models
    emit despite instructions.

    Args:
        text: Raw model output text.

    Returns:
        The parsed envelope dict, or None when no JSON object is present.
    """
    if not text:
        return None

    candidates: list[dict] = []
    index = text.find("{")
    while index != -1:
        depth = 0
        for position in range(index, len(text)):
            character = text[position]
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[index:position + 1])
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        candidates.append(parsed)
                    index = position
                    break
        index = text.find("{", index + 1)

    if not candidates:
        return None
    for parsed in reversed(candidates):
        if "routed_to" in parsed or "rationale" in parsed:
            return parsed
    return candidates[-1]


async def _decide_route_via_llm(agent: Any, event: CareEvent) -> tuple[str, dict]:
    """Ask the LLM which specialist owns the event — a decision-only turn.

    Streams one inference turn with the four specialist agents' tool specs
    attached and reads back the model's choice. Tools are deliberately NOT
    executed by this turn:

    - AGENTS.md §2 requires specialized agents to return structured models, not
      free-form LLM text, so execution stays with the deterministic handler for
      the specialist the model selected.
    - Executing the specialist here would duplicate side effects (a second
      refill order, a second family alert) for one care event.
    - Escalation must stay deterministic (AGENTS.md §3/§8); the model's
      escalation opinion is captured as advisory context only.

    The routing decision itself is entirely the model's: nothing in this module
    maps an event type to a specialist on the LLM path.

    Args:
        agent: Supervisor Strands Agent built by :func:`create_supervisor_agent`.
        event: The care event to route.

    Returns:
        Tuple of (specialist area name, advisory dict carrying the model's
        rationale, escalation recommendation, and how it was selected).

    Raises:
        RuntimeError: If the model selected no known specialist, so the caller
            can degrade to the deterministic fallback for this event.
    """
    tool_specs = list(agent.tool_registry.get_all_tool_specs())
    messages: list[dict] = [
        {"role": "user", "content": [{"text": _build_routing_prompt(event)}]}
    ]

    invoked: list[str] = []
    text_parts: list[str] = []

    async for chunk in agent.model.stream(
        messages, tool_specs=tool_specs, system_prompt=SUPERVISOR_SYSTEM_PROMPT
    ):
        tool_use = (chunk.get("contentBlockStart") or {}).get("toolUse") or {}
        name = tool_use.get("name")
        if name:
            invoked.append(str(name))
        delta = (chunk.get("contentBlockDelta") or {}).get("delta") or {}
        if isinstance(delta.get("text"), str):
            text_parts.append(delta["text"])

    envelope = _extract_json_object("".join(text_parts)) or {}
    declared = str(envelope.get("routed_to") or "").strip().lower()

    # A requested tool call is the strongest signal of the model's decision; the
    # declared JSON envelope is the secondary signal for models that answer in
    # prose instead of calling a tool.
    area = next(
        (
            _SPECIALIST_TOOL_AREAS[name]
            for name in invoked
            if name in _SPECIALIST_TOOL_AREAS
        ),
        None,
    )
    selected_via = "tool_use"
    if area is None and declared in _AGENT_HANDLERS:
        area = declared
        selected_via = "declared_json"

    if area is None:
        raise RuntimeError(
            f"LLM selected no known specialist for event {event.event_id} "
            f"(tools requested: {invoked or 'none'}; declared: {declared or 'none'})"
        )

    if len(invoked) > 1:
        logger.warning(
            "LLM requested %d tools for event %s (%s); honouring the first "
            "specialist (%s)",
            len(invoked), event.event_id, ", ".join(invoked), area,
        )

    rationale = str(envelope.get("rationale") or "").strip()
    logger.info(
        "LLM routing decision for event %s: %s specialist (via %s) — rationale: %s",
        event.event_id, area, selected_via, rationale or "<not provided>",
    )

    return area, {
        "llm_rationale": rationale,
        "llm_escalation_recommended": str(
            envelope.get("escalation_recommended") or "none"
        ).strip().lower(),
        "llm_selected_via": selected_via,
    }


async def _route_via_llm(agent: Any, event: CareEvent) -> tuple[str, dict]:
    """Route a care event using the LLM's routing decision.

    Args:
        agent: Supervisor Strands Agent built by :func:`create_supervisor_agent`.
        event: The care event to route.

    Returns:
        Tuple of (specialist area name, that specialist's structured result dict
        enriched with the model's advisory rationale).

    Raises:
        RuntimeError: If the LLM produced no usable routing decision.
        Exception: Errors from the specialist handler propagate so the caller can
            audit the failure (AGENTS.md §9 — never silently fail).
    """
    area, advisory = await _decide_route_via_llm(agent, event)

    handler = _AGENT_HANDLERS[area]
    agent_result: dict = dict(await handler(event))
    agent_result.update(advisory)

    # Observability only. A divergence between the model's choice and the
    # deterministic expectation is worth surfacing to an operator, but it never
    # overrides the LLM's decision.
    expected = _FALLBACK_ROUTES.get(event.event_type)
    if expected is not None and expected[0] != area:
        logger.warning(
            "LLM routed event %s (%s) to the %s specialist; the deterministic "
            "expectation was %s",
            event.event_id, event.event_type, area, expected[0],
        )
    return area, agent_result


async def _route_via_fallback(event: CareEvent) -> tuple[str, dict]:
    """FALLBACK PATH — used only when LLM is unavailable.

    Routes from the declarative :data:`_FALLBACK_ROUTES` table when no provider
    model is configured (missing API key, absent SDK, offline tests) or when an
    LLM invocation failed for the event. Never consulted while an LLM is
    configured and healthy.

    Args:
        event: The care event to route.

    Returns:
        Tuple of (specialist area name, structured result dict from the handler).

    Raises:
        ValueError: If the event type has no route (defensive — the CareEvent
            schema constrains event_type to the four routed types).
    """
    route = _FALLBACK_ROUTES.get(event.event_type)
    if route is None:
        raise ValueError(f"No route for event type: {event.event_type}")
    area, handler = route
    return area, await handler(event)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def process_event(event: CareEvent) -> ResolutionResult:
    """Process an incoming care event by routing it to the responsible specialist.

    The routing decision is made by the configured LLM (see
    :func:`_route_via_llm`); this function contains no event-type dispatch. When
    no LLM is available it degrades to the declarative table in
    :func:`_route_via_fallback`, and when an LLM invocation fails it degrades for
    that event only — loudly, in the result and the audit trail.

    Escalation is always computed deterministically (AGENTS.md §3/§8), never by
    the model.

    Audit-first pattern: a "pending" supervisor event is written BEFORE any
    routing executes, and a follow-up event records the final outcome
    (success | escalated | failure). When escalation is required, the event
    is routed onward to the Communication Agent for family notification.

    Args:
        event: The care event to process.

    Returns:
        ResolutionResult with actions taken and escalation status.
    """
    _ensure_audit_db()
    correlation_id = str(uuid4())

    # Audit BEFORE processing (AGENTS.md §7 — immutable, append-only).
    before_id = write_audit_event(
        actor="supervisor",
        action_type="process_event",
        care_recipient_id=event.care_recipient_id,
        rationale=f"Routing '{event.event_type}' event to specialized agent",
        outcome="pending",
        correlation_id=correlation_id,
    )
    audit_event_ids: list[UUID] = [UUID(before_id)]

    logger.info(
        "Supervisor processing event %s (type=%s, recipient=%s)",
        event.event_id, event.event_type, event.care_recipient_id,
    )

    # --- Step 1: route to the specialized agent -----------------------------
    # The routing DECISION is the LLM's whenever a provider model is configured.
    # There is no event-type dispatch here: the model reads the event and picks
    # the specialist. The table-driven fallback is used only when no LLM is
    # available, or when an LLM invocation fails for this event (AGENTS.md §9 —
    # degrade loudly, never silently drop a care event).
    routing_mode = get_routing_mode()
    agent_name: Optional[str] = None
    agent_result: Optional[dict] = None
    degradation: Optional[str] = None

    if routing_mode == _ROUTING_MODE_LLM:
        try:
            supervisor = get_supervisor_agent()
            if supervisor is None:
                raise RuntimeError("Supervisor Agent could not be constructed")
            agent_name, agent_result = await _route_via_llm(supervisor, event)
        except Exception as e:
            logger.error(
                "LLM routing failed for event %s: %s — degrading to "
                "deterministic routing for this event",
                event.event_id, e,
            )
            degradation = f"error: LLM routing failed — {e}"

    if agent_name is None:
        # FALLBACK PATH — used only when LLM is unavailable
        try:
            agent_name, agent_result = await _route_via_fallback(event)
        except Exception as e:
            logger.error("Routing failed for event %s: %s", event.event_id, e)
            failure_id = write_audit_event(
                actor="supervisor",
                action_type="process_event",
                care_recipient_id=event.care_recipient_id,
                rationale=f"Routing failed for '{event.event_type}' event: {e}",
                outcome="failure",
                correlation_id=correlation_id,
            )
            audit_event_ids.append(UUID(failure_id))
            return ResolutionResult(
                event_id=event.event_id,
                resolved=False,
                actions_taken=[f"error: routing failed — {e}"],
                escalation_required=False,
                escalation_level=None,
                audit_event_ids=audit_event_ids,
            )

    agent_actions: list[str] = list((agent_result or {}).get("actions_taken", []))

    # --- Step 2: deterministic escalation decision ---------------------------
    # Never delegated to the LLM (AGENTS.md §3/§8): classify_action() and the
    # hard-coded emergency triggers are authoritative.
    escalation_required, escalation_level = _evaluate_escalation(
        event, agent_result or {}
    )

    # Surface — but never act on — a divergence between the model's advisory
    # recommendation and the deterministic determination.
    advisory_level = str(
        (agent_result or {}).get("llm_escalation_recommended") or ""
    ).strip().lower()
    resolved_level = escalation_level if escalation_required else "none"
    if advisory_level and advisory_level != resolved_level:
        logger.warning(
            "LLM recommended escalation '%s' for event %s, but the deterministic "
            "classifier resolved '%s' — the classifier is authoritative",
            advisory_level, event.event_id, resolved_level,
        )

    # --- Step 3: route to Communication Agent when escalation is needed ------
    comm_actions: list[str] = []
    if escalation_required:
        level = escalation_level or "info"
        message = _build_alert_message(event, agent_result, level)
        comm_event = CareEvent(
            event_type=event.event_type,
            care_recipient_id=event.care_recipient_id,
            payload={"level": level, "message": message},
        )
        try:
            comm_result = await handle_communication_event(comm_event)
            comm_actions = list(comm_result.get("actions_taken", []))
        except Exception as e:
            # AGENTS.md §9 fallback: never silently fail — queue the alert
            # failure visibly in the result and audit trail.
            logger.error(
                "Family alert dispatch failed for event %s: %s", event.event_id, e
            )
            comm_actions = [f"error: family alert dispatch failed — {e}"]

    routing_line = f"Supervisor routed '{event.event_type}' to {agent_name} agent"
    actions_taken: list[str] = (
        [routing_line]
        + ([degradation] if degradation is not None else [])
        + agent_actions
        + comm_actions
    )

    # --- Step 4: follow-up audit event with the final outcome ----------------
    # The routing decision's rationale is recorded here so every LLM decision is
    # explainable from the immutable audit trail alone (AGENTS.md §7).
    llm_rationale = str((agent_result or {}).get("llm_rationale") or "").strip()
    rationale_parts: list[str] = [
        f"Processed '{event.event_type}' event via {agent_name} agent",
        f"routing={'LLM' if routing_mode == _ROUTING_MODE_LLM else 'FALLBACK'}",
    ]
    if llm_rationale:
        rationale_parts.append(f"decision rationale: {llm_rationale}")
    rationale_parts.append(f"{len(actions_taken)} actions")
    rationale_parts.append(
        f"escalation={'none' if not escalation_required else escalation_level}"
    )
    if degradation is not None:
        rationale_parts.append(
            f"degraded to deterministic routing: {degradation}"
        )

    final_outcome = "escalated" if escalation_required else "success"
    after_id = write_audit_event(
        actor="supervisor",
        action_type="process_event",
        care_recipient_id=event.care_recipient_id,
        rationale="; ".join(rationale_parts),
        outcome=final_outcome,
        correlation_id=correlation_id,
    )
    audit_event_ids.append(UUID(after_id))

    return ResolutionResult(
        event_id=event.event_id,
        resolved=True,
        actions_taken=actions_taken,
        escalation_required=escalation_required,
        escalation_level=escalation_level,
        audit_event_ids=audit_event_ids,
    )


_QUERY_SYSTEM_PROMPT = (
    "You are the CareBridge Supervisor. Answer the caregiver's question using "
    "ONLY the events provided. Be concise (2-4 sentences), warm, and factual. "
    "Never diagnose or prescribe. Never invent events that are not in the list."
)


async def query_status(care_recipient_id: str, question: str) -> str:
    """Query the current care status for a recipient.

    Fetches recent audit events via ``synthesize_status()``, then asks the
    configured LLM to synthesise a natural-language answer to the caregiver's
    question.  Falls back to the deterministic summary when the LLM is
    unavailable or fails, so the endpoint never breaks (AGENTS.md §9 — degrade
    loudly, never silently).

    Exactly one audit event records the query.

    Args:
        care_recipient_id: The care recipient to query about.
        question: Natural language question about care status.

    Returns:
        Natural-language answer from the LLM, or the deterministic summary
        as a fallback.
    """
    _ensure_audit_db()

    logger.info(
        "Status query for recipient %s: %s", care_recipient_id, question
    )

    summary = synthesize_status(care_recipient_id)

    write_audit_event(
        actor="supervisor",
        action_type="synthesize_status",
        care_recipient_id=care_recipient_id,
        rationale=f"Answered caregiver status query: {question}",
        outcome="success",
        correlation_id=str(uuid4()),
    )

    # --- LLM synthesis -------------------------------------------------------
    # Build a prompt from the deterministic data so the LLM can answer the
    # caregiver's question in natural language.  Falls back to the raw summary
    # when no model is configured or the call fails.
    events_as_text = "\n".join(
        f"- {evt.action_type} ({evt.outcome}) at {evt.timestamp}: {evt.rationale}"
        for evt in summary.recent_events
    ) or "No recent events."

    state_summary = summary.summary_text
    if summary.pending_actions:
        state_summary += (
            f" {len(summary.pending_actions)} pending action(s) awaiting resolution."
        )

    user_prompt = (
        f"Question: {question}\n\n"
        f"Recent events:\n{events_as_text}\n\n"
        f"Current state: {state_summary}"
    )

    messages = [{"role": "user", "content": [{"text": user_prompt}]}]

    try:
        model = get_model()
        response = model(messages, system_prompt=_QUERY_SYSTEM_PROMPT)
        # Strands model responses expose .output.text; handle both shapes.
        answer: str
        if isinstance(response, str):
            answer = response
        else:
            answer = str(getattr(response, "output", response))
            if hasattr(response, "output") and hasattr(response.output, "text"):
                answer = response.output.text
        answer = answer.strip()
        if answer:
            logger.info(
                "query_status: LLM synthesis succeeded (provider=%s)",
                get_provider_name(),
            )
            return answer
    except RuntimeError:
        # No LLM configured — fall through to deterministic summary.
        logger.info("query_status: LLM not available, using deterministic fallback")
    except Exception as exc:
        # LLM call failed at runtime — degrade loudly (AGENTS.md §9).
        logger.warning(
            "query_status: LLM synthesis failed (%s), using deterministic fallback",
            exc,
        )

    return summary.summary_text


async def approve_pending_action(action_id: str, approved: bool) -> None:
    """Approve or reject a pending action.

    Records the human decision in the audit trail (actor="human"). Approved
    actions are executed by routing to the specialized agent that owns the
    action type; rejected actions are logged and never executed.

    Args:
        action_id: The pending action identifier (audit event_id of a
            "pending" audit entry).
        approved: Whether to approve the action.

    Raises:
        ValueError: If action_id not found, not in "pending" state, or
            already resolved.
    """
    _ensure_audit_db()

    if action_id in _resolved_action_ids:
        raise ValueError(f"Pending action already resolved: {action_id}")

    # Locate the pending action in the audit trail.
    pending_event: Optional[dict] = None
    for evt in get_audit_events():
        if evt["event_id"] == action_id:
            pending_event = evt
            break

    if pending_event is None or pending_event["outcome"] != "pending":
        raise ValueError(f"Pending action not found: {action_id}")

    action = PendingAction(
        action_id=pending_event["event_id"],
        action_type=pending_event["action_type"],
        care_recipient_id=pending_event["care_recipient_id"],
        rationale=pending_event["rationale"],
        requested_at=pending_event["timestamp"],
        status="pending",
        authorization_ref=pending_event.get("authorization_ref"),
    )

    _resolved_action_ids.add(action_id)
    correlation_id = str(uuid4())
    decision = "approve_action" if approved else "reject_action"

    # --- Rejection: the decision is complete in itself -----------------------
    if not approved:
        write_audit_event(
            actor="human",
            action_type=decision,
            care_recipient_id=action.care_recipient_id,
            rationale=(
                f"Human rejected pending action '{action.action_type}' "
                f"({action_id})"
            ),
            outcome="success",
            correlation_id=correlation_id,
            authorization_ref=action_id,
        )
        logger.info("Pending action %s rejected by human", action_id)
        return

    # --- Approval: audit the decision BEFORE executing (audit-first) ---------
    write_audit_event(
        actor="human",
        action_type=decision,
        care_recipient_id=action.care_recipient_id,
        rationale=(
            f"Human approved pending action '{action.action_type}' "
            f"({action_id})"
        ),
        outcome="pending",
        correlation_id=correlation_id,
        authorization_ref=action_id,
    )

    agent_name: Optional[str] = _APPROVAL_AGENT_ROUTES.get(action.action_type)
    if agent_name is None:
        # No automated execution path — escalate for manual handling,
        # never silently fail (AGENTS.md §9).
        write_audit_event(
            actor="supervisor",
            action_type=decision,
            care_recipient_id=action.care_recipient_id,
            rationale=(
                f"No automated route for action '{action.action_type}' — "
                f"escalated for manual execution"
            ),
            outcome="escalated",
            correlation_id=correlation_id,
            authorization_ref=action_id,
        )
        logger.warning(
            "No automated route for approved action '%s'", action.action_type
        )
        return

    event_type = _AGENT_EVENT_TYPES[agent_name]
    payload: dict = {
        "authorization_ref": action_id,
        "approved_action": action.action_type,
        "original_rationale": action.rationale,
    }
    if agent_name == "communication":
        payload["level"] = "info"
        payload["message"] = (
            f"Approved action executed: {action.action_type} (ref {action_id})"
        )

    redelivered = CareEvent(
        event_type=event_type,
        care_recipient_id=action.care_recipient_id,
        payload=payload,
    )

    try:
        # Deterministic re-dispatch: executing a human-approved action is a
        # safety path and is never routed by an LLM (AGENTS.md §3).
        handler = _AGENT_HANDLERS[agent_name]
        result = await handler(redelivered)

        executed_actions: list[str] = list(result.get("actions_taken", []))
        execution_failed = any(
            entry.startswith("error") for entry in executed_actions
        )
        write_audit_event(
            actor="supervisor",
            action_type=decision,
            care_recipient_id=action.care_recipient_id,
            rationale=(
                f"Executed approved action '{action.action_type}' via "
                f"{agent_name} agent: {'; '.join(executed_actions[:3])}"
            ),
            outcome="failure" if execution_failed else "success",
            correlation_id=correlation_id,
            authorization_ref=action_id,
        )
        logger.info(
            "Approved action %s executed via %s agent", action_id, agent_name
        )
    except Exception as e:
        logger.error(
            "Failed to execute approved action %s: %s", action_id, e
        )
        write_audit_event(
            actor="supervisor",
            action_type=decision,
            care_recipient_id=action.care_recipient_id,
            rationale=(
                f"Execution of approved action '{action.action_type}' "
                f"failed: {e}"
            ),
            outcome="failure",
            correlation_id=correlation_id,
            authorization_ref=action_id,
        )
        raise


# ---------------------------------------------------------------------------
# Strands agents-as-tools wiring (LLM-driven, with graceful degradation)
# ---------------------------------------------------------------------------

def create_supervisor_agent() -> Optional[Any]:
    """Build the Supervisor as a real Strands Agent driven by the configured LLM.

    The four specialist agents are attached as tools (agents-as-tools), so the
    model — not this module — decides which specialist handles an incoming care
    event. The model comes from the provider-agnostic factory, so switching
    ``LLM_PROVIDER`` changes the Supervisor's brain with no code change.

    Returns:
        The configured Strands Agent, or None when no LLM can be built (missing
        API key, absent provider SDK, strands-agents not installed, or no
        specialist could be constructed). None keeps the degraded deterministic
        path available for offline tests.
    """
    try:
        model = get_model()
    except RuntimeError as e:
        logger.error("Supervisor cannot build LLM: %s", e)
        return None

    try:
        from strands import Agent
    except ImportError as e:
        logger.error(
            "Supervisor cannot route via LLM: strands-agents is not installed "
            "(%s). Install with: pip install 'strands-agents>=1.55'",
            e,
        )
        return None

    specialists = [factory() for factory in _SPECIALIST_FACTORIES]
    # A specialist that failed to build must not disable orchestration entirely;
    # the LLM routes among the specialists that are available.
    built = [specialist for specialist in specialists if specialist is not None]
    if len(built) != len(specialists):
        logger.warning(
            "Built %d of %d specialist agents; the Supervisor will route among "
            "those available",
            len(built), len(specialists),
        )
    if not built:
        # An agent with no tools could not route anything, and claiming LLM
        # routing while silently doing nothing would be worse than degrading.
        logger.error(
            "No specialist agents could be built; Supervisor will use "
            "deterministic fallback routing"
        )
        return None

    try:
        agent = Agent(
            name="CareBridgeSupervisor",
            description=(
                "Routes incoming care events to the Medication, Appointment, "
                "Logistics, or Communication specialist, then coordinates "
                "deterministic escalation and audit logging."
            ),
            model=model,
            system_prompt=SUPERVISOR_SYSTEM_PROMPT,
            tools=built,
        )
    except Exception as e:
        logger.error("Failed to construct the Supervisor Agent: %s", e)
        return None

    logger.info(
        "Strands Supervisor Agent created (provider=%s, model=%s, specialists=%s)",
        get_provider_name(),
        get_configured_model_id(),
        ", ".join(str(getattr(specialist, "name", "?")) for specialist in built),
    )
    return agent


def _llm_routing_available() -> bool:
    """Return True when both a provider model and the Strands SDK are available.

    Returns:
        True when :func:`get_model` succeeds and ``strands`` is importable.
    """
    try:
        get_model()
    except RuntimeError as exc:
        logger.info("LLM routing unavailable: %s", exc)
        return False
    try:
        from strands import Agent  # noqa: F401  (import check only)
    except ImportError as exc:
        logger.info(
            "LLM routing unavailable: strands-agents is not installed (%s)", exc
        )
        return False
    return True


def get_routing_mode() -> str:
    """Resolve — and announce once — whether routing uses the LLM or the fallback.

    The announcement is the demo-visible proof of which path handled the events
    (spec D.4): exactly one of the two lines below is logged per process.

    Returns:
        ``"llm"`` when a provider model is configured, otherwise ``"fallback"``.
    """
    global _routing_mode, _routing_mode_announced

    with _routing_mode_lock:
        if _routing_mode is None:
            _routing_mode = (
                _ROUTING_MODE_LLM
                if _llm_routing_available()
                else _ROUTING_MODE_FALLBACK
            )
        if not _routing_mode_announced:
            _routing_mode_announced = True
            if _routing_mode == _ROUTING_MODE_LLM:
                logger.info(
                    "Supervisor routing via LLM: %s / %s",
                    get_provider_name(), get_configured_model_id(),
                )
            else:
                logger.info("Supervisor routing via FALLBACK (no LLM configured)")
        return _routing_mode


def get_supervisor_agent() -> Optional[Any]:
    """Return the cached Supervisor Agent, building it on first use.

    Safe to reuse across events: routing performs a decision-only inference turn
    (:func:`_decide_route_via_llm`) that supplies its own messages and never
    mutates the agent's conversation history.

    Returns:
        The Strands Agent, or None when no LLM is available.
    """
    global _supervisor_agent

    if _supervisor_agent is None:
        with _supervisor_agent_lock:
            if _supervisor_agent is None:
                _supervisor_agent = create_supervisor_agent()
    return _supervisor_agent


def get_supervisor_tool_names(agent: Optional[Any] = None) -> list[str]:
    """Return the specialist tool names registered on a Supervisor Agent.

    Strands 1.55 exposes registered tools through ``tool_names`` — there is no
    ``Agent.tools`` attribute — so this is the introspection point used by tests
    and by ``GET /ready``.

    Args:
        agent: Agent to inspect. Defaults to the cached Supervisor.

    Returns:
        Registered tool names, or an empty list when no agent is available.
    """
    target = agent if agent is not None else get_supervisor_agent()
    if target is None:
        return []
    return list(getattr(target, "tool_names", None) or [])


def reset_supervisor_state() -> None:
    """Clear the cached routing mode and Supervisor Agent.

    Both are resolved once per process, so this is required after changing LLM
    configuration in-process (tests switching ``LLM_PROVIDER`` or API keys).

    Returns:
        None.
    """
    global _routing_mode, _routing_mode_announced, _supervisor_agent

    with _routing_mode_lock:
        _routing_mode = None
        _routing_mode_announced = False
    with _supervisor_agent_lock:
        _supervisor_agent = None
