"""Deterministic escalation classification for CareBridge.

Safety-critical: an LLM must NEVER classify an action as autonomous vs.
requiring approval. All routing decisions flow through the pure, hardcoded
sets below (sourced from SPEC.md and AGENTS.md).
"""

from typing import Literal
import logging

logger = logging.getLogger(__name__)

AUTONOMOUS_ACTIONS: set[str] = {
    "check_refill_status",
    "check_delivery_status",
    "get_calendar",
    "synthesize_status",
    "send_daily_digest",
}

REQUIRES_ALERT: set[str] = {
    "order_refill",
    "order_grocery",
    "schedule_appointment",
    "order_pharmacy_delivery",
}

REQUIRES_APPROVAL: set[str] = {
    "cancel_appointment",
    "change_medication_schedule",
    "add_service_provider",
    "modify_health_record",
}

EMERGENCY_TRIGGERS: set[str] = {
    "fall_detection",
    "emergency_room_visit",
    "critical_medication_interaction",
}


def classify_action(action_type: str, context: dict | None = None) -> Literal["auto", "alert", "approve"]:
    """Deterministic classification of action type for escalation.

    Pure Python logic — no LLM calls. Uses hardcoded sets from SPEC.md and AGENTS.md.

    Args:
        action_type: The tool/action name to classify.
        context: Optional context dict (for future extension; currently unused for base classification).

    Returns:
        "auto" for autonomous actions, "alert" for actions requiring alert, "approve" for actions requiring approval.
        Unknown actions default to "approve" for safety (most restrictive category).
    """
    if context is None:
        context = {}

    # Check for emergency triggers in context
    if context.get("trigger") in EMERGENCY_TRIGGERS:
        return "alert"  # Emergency triggers escalate at minimum to alert level

    if action_type in AUTONOMOUS_ACTIONS:
        return "auto"
    elif action_type in REQUIRES_ALERT:
        return "alert"
    elif action_type in REQUIRES_APPROVAL:
        return "approve"
    else:
        logger.warning(f"Unknown action type: {action_type}. Defaulting to 'approve' for safety.")
        return "approve"
