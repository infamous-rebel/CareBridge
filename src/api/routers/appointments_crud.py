"""CRUD endpoints for appointments (dashboard operational layer).

Prefix: ``/care-recipients/me/appointments``

Every mutation writes an audit event BEFORE the DB commit.
Every endpoint requires JWT auth.  Cross-user access returns 404.
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from src.api import user_store
from src.api.dependencies import get_current_user
from src.api.schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/care-recipients/me/appointments",
    tags=["appointments"],
)

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found"
)


def _care_recipient_id(user: dict) -> str:
    crid = user.get("care_recipient_id")
    if not crid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No care_recipient_id assigned to this user",
        )
    return crid


def _row_to_out(row: dict) -> AppointmentOut:
    return AppointmentOut(
        id=row["id"],
        care_recipient_id=row["care_recipient_id"],
        provider_name=row["provider_name"],
        specialty=row.get("specialty"),
        appointment_at=row["appointment_at"],
        location=row.get("location"),
        prep_required=row.get("prep_required", []),
        transportation_needed=bool(row.get("transportation_needed", False)),
        notes=row.get("notes"),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(
    user: dict = Depends(get_current_user),
) -> list[AppointmentOut]:
    """List all appointments for the current user's care recipient."""
    crid = _care_recipient_id(user)
    rows = user_store.list_appointments(crid)
    return [_row_to_out(r) for r in rows]


@router.post(
    "", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED
)
async def create_appointment(
    body: AppointmentCreate, user: dict = Depends(get_current_user)
) -> AppointmentOut:
    """Create a new appointment.

    Args:
        body: Appointment fields (appointment_at must be in the future).
        user: Injected authenticated user.

    Returns:
        The created appointment.
    """
    crid = _care_recipient_id(user)
    corr_id = str(uuid4())

    from src.models.audit_log import write_audit_event

    write_audit_event(
        actor="human",
        action_type="create_appointment",
        care_recipient_id=crid,
        rationale=(
            f"Create appointment with '{body.provider_name}' "
            f"at {body.appointment_at} for care_recipient={crid}"
        ),
        outcome="pending",
        correlation_id=corr_id,
    )

    row = user_store.create_appointment(
        care_recipient_id=crid,
        provider_name=body.provider_name,
        specialty=body.specialty,
        appointment_at=body.appointment_at,
        location=body.location,
        prep_required=body.prep_required,
        transportation_needed=body.transportation_needed,
        notes=body.notes,
    )

    write_audit_event(
        actor="human",
        action_type="create_appointment",
        care_recipient_id=crid,
        rationale=(
            f"Created appointment with '{body.provider_name}' "
            f"(id={row.get('id')})"
        ),
        outcome="success",
        correlation_id=corr_id,
    )
    logger.info("Created appointment %s for crid=%s", row.get("id"), crid)
    return _row_to_out(row)


@router.get("/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(
    appointment_id: str, user: dict = Depends(get_current_user)
) -> AppointmentOut:
    """Fetch a single appointment by ID."""
    crid = _care_recipient_id(user)
    row = user_store.get_appointment(appointment_id)
    if row is None or row["care_recipient_id"] != crid:
        raise _NOT_FOUND
    return _row_to_out(row)


@router.put("/{appointment_id}", response_model=AppointmentOut)
async def update_appointment(
    appointment_id: str,
    body: AppointmentUpdate,
    user: dict = Depends(get_current_user),
) -> AppointmentOut:
    """Update an existing appointment.

    Args:
        appointment_id: The appointment UUID.
        body: Fields to update (partial).
        user: Injected authenticated user.

    Returns:
        The updated appointment.
    """
    crid = _care_recipient_id(user)
    existing = user_store.get_appointment(appointment_id)
    if existing is None or existing["care_recipient_id"] != crid:
        raise _NOT_FOUND

    corr_id = str(uuid4())
    from src.models.audit_log import write_audit_event

    write_audit_event(
        actor="human",
        action_type="update_appointment",
        care_recipient_id=crid,
        rationale=(
            f"Update appointment with '{existing['provider_name']}' "
            f"(id={appointment_id})"
        ),
        outcome="pending",
        correlation_id=corr_id,
    )

    updates = body.model_dump(exclude_unset=True)
    row = user_store.update_appointment(appointment_id, updates)

    write_audit_event(
        actor="human",
        action_type="update_appointment",
        care_recipient_id=crid,
        rationale=(
            f"Updated appointment with '{existing['provider_name']}' "
            f"(id={appointment_id})"
        ),
        outcome="success",
        correlation_id=corr_id,
    )
    logger.info("Updated appointment %s for crid=%s", appointment_id, crid)
    return _row_to_out(row or {})


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment(
    appointment_id: str, user: dict = Depends(get_current_user)
) -> AppointmentOut:
    """Cancel an appointment (set status='cancelled').

    Args:
        appointment_id: The appointment UUID.
        user: Injected authenticated user.

    Returns:
        The cancelled appointment.
    """
    crid = _care_recipient_id(user)
    existing = user_store.get_appointment(appointment_id)
    if existing is None or existing["care_recipient_id"] != crid:
        raise _NOT_FOUND

    corr_id = str(uuid4())
    from src.models.audit_log import write_audit_event

    write_audit_event(
        actor="human",
        action_type="cancel_appointment",
        care_recipient_id=crid,
        rationale=(
            f"Cancel appointment with '{existing['provider_name']}' "
            f"(id={appointment_id})"
        ),
        outcome="pending",
        correlation_id=corr_id,
    )

    row = user_store.update_appointment(
        appointment_id, {"status": "cancelled"}
    )

    write_audit_event(
        actor="human",
        action_type="cancel_appointment",
        care_recipient_id=crid,
        rationale=(
            f"Cancelled appointment with '{existing['provider_name']}' "
            f"(id={appointment_id})"
        ),
        outcome="success",
        correlation_id=corr_id,
    )
    logger.info("Cancelled appointment %s for crid=%s", appointment_id, crid)
    return _row_to_out(row or {})
