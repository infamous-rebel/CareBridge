"""CareBridge: AI-powered care coordination system.

Entry point that initializes the system, loads fixtures, and runs the demo scenario.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

from src.models.audit_log import get_audit_events, init_audit_db
from src.models.schemas import CareEvent, ResolutionResult
from src.agents.supervisor_agent import (
    get_supervisor_agent,
    process_event,
    query_status,
    SUPERVISOR_MCP_SERVERS,
)
from src.runtime.model_factory import get_configured_model_id, get_provider_name

# Ensure the logs directory exists before the file handler is created.
Path("logs").mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/carebridge.log"),
    ],
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures"
REQUIRED_FIXTURES = (
    "medications.json",
    "appointments.json",
    "delivery_history.json",
    "family_members.json",
)

_LINE_WIDTH = 72


def load_fixtures() -> dict[str, list[dict]]:
    """Load and verify all fixture files required by the demo scenario.

    Returns:
        Dict mapping fixture filename to its list of records.

    Raises:
        FileNotFoundError: If a required fixture file is missing.
        json.JSONDecodeError: If a fixture file contains invalid JSON.
    """
    fixtures: dict[str, list[dict]] = {}
    for name in REQUIRED_FIXTURES:
        path = FIXTURES_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"Missing required fixture: {path}")
        with open(path) as f:
            fixtures[name] = json.load(f)
        logger.info("Loaded fixture %s (%d records)", name, len(fixtures[name]))
    return fixtures


def print_result(result: ResolutionResult) -> None:
    """Log a ResolutionResult summary block for the demo.

    Args:
        result: The ResolutionResult to display.
    """
    escalation = result.escalation_level if result.escalation_required else "none"
    logger.info("Resolved: %s | Escalation: %s", result.resolved, escalation)
    for action in result.actions_taken:
        logger.info("  - %s", action)


def print_audit_summary() -> None:
    """Log a chronological summary of all audit events recorded this run."""
    events = get_audit_events()
    logger.info("=" * _LINE_WIDTH)
    logger.info("Audit trail — %d event(s) recorded (newest first)", len(events))
    logger.info("=" * _LINE_WIDTH)
    for evt in events:
        logger.info(
            "  %s  %-13s %-28s %s",
            evt['timestamp'][:19], evt['actor'],
            evt['action_type'], evt['outcome'],
        )


async def run_demo_scenario() -> None:
    """Run the Day 1 demo scenario end-to-end.

    Processes three care events (refill running low, appointment upcoming,
    pharmacy delivery failed) and answers a caregiver status query, printing
    the resolution of each step.
    """
    care_recipient_id = "cr-001"

    logger.info("=" * _LINE_WIDTH)
    logger.info("CareBridge Demo — AI-powered care coordination")
    logger.info("=" * _LINE_WIDTH)

    # --- Scenario 1: medication refill running low --------------------------
    logger.info("[1] Medication refill low — med-001 (Lisinopril, 3 days remaining)")
    refill_event = CareEvent(
        event_type="refill_low",
        care_recipient_id=care_recipient_id,
        payload={"medication_id": "med-001", "days_remaining": 3},
    )
    refill_result = await process_event(refill_event)
    print_result(refill_result)

    # --- Scenario 2: appointment upcoming within 48 hours -------------------
    logger.info("[2] Appointment upcoming — apt-001 (Cardiology, within 48h)")
    appointment_event = CareEvent(
        event_type="appointment_upcoming",
        care_recipient_id=care_recipient_id,
        payload={"appointment_id": "apt-001"},
    )
    appointment_result = await process_event(appointment_event)
    print_result(appointment_result)

    # --- Scenario 3: pharmacy delivery failed -------------------------------
    logger.info("[3] Delivery failed — del-003 (pharmacy delivery)")
    delivery_event = CareEvent(
        event_type="delivery_failed",
        care_recipient_id=care_recipient_id,
        payload={"delivery_id": "del-003", "failure_reason": "Address not accessible"},
    )
    delivery_result = await process_event(delivery_event)
    print_result(delivery_result)

    # --- Scenario 4: caregiver status query ----------------------------------
    logger.info("[4] Status query — 'How is the care recipient doing today?'")
    status = await query_status(
        care_recipient_id, "How is the care recipient doing today?"
    )
    logger.info("%s", status)


async def main() -> None:
    """Initialize CareBridge and run the demo scenario.

    Raises:
        FileNotFoundError: If required fixtures are missing.
    """
    # 1. Initialize the immutable audit database (schema + triggers).
    init_audit_db()

    # 2. Log startup.
    logger.info("CareBridge system starting up")

    # 3. Load fixtures to verify they exist.
    fixtures = load_fixtures()
    logger.info(
        "Loaded %d fixture files (%d total records)",
        len(fixtures),
        sum(len(records) for records in fixtures.values()),
    )

    # 4. Build the Supervisor Agent. Routing goes through the configured LLM
    #    when one is available; otherwise it degrades to the deterministic
    #    fallback table. This line is the demo-visible proof of which path is
    #    live (spec H) — never claim LLM orchestration that is not happening.
    #    get_supervisor_agent() is the cached accessor, so process_event() reuses
    #    this exact instance instead of rebuilding the specialists per event.
    supervisor = get_supervisor_agent()
    if supervisor is not None:
        logger.info(
            "Supervisor LLM provider: %s (%s)",
            get_provider_name(),
            get_configured_model_id() or "provider default",
        )
    else:
        logger.info("Supervisor using FALLBACK (no LLM)")

    # Log the MCP servers wired into the Supervisor (SPEC.md §6) — a visible
    # confirmation for the demo that the MCP integration layer is live.
    logger.info(
        "Attached MCP servers: %s",
        ", ".join(cfg["name"] for cfg in SUPERVISOR_MCP_SERVERS),
    )

    # 5. Run the demo scenario.
    await run_demo_scenario()

    # 6. Print summary of all actions and audit events.
    print_audit_summary()

    # 7. Log completion.
    logger.info("CareBridge demo completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
