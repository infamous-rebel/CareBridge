"""CRUD endpoints for medications (dashboard operational layer).

Prefix: ``/care-recipients/me/medications``

Every mutation writes an audit event BEFORE the DB commit.
Every endpoint requires JWT auth.  Cross-user access returns 404.
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from src.api import user_store
from src.api.dependencies import get_current_user
from src.api.schemas import MedicationCreate, MedicationOut, MedicationUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/care-recipients/me/medications",
    tags=["medications"],
)

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")


def _care_recipient_id(user: dict) -> str:
    """Extract care_recipient_id or raise 403."""
    crid = user.get("care_recipient_id")
    if not crid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No care_recipient_id assigned to this user",
        )
    return crid


def _row_to_out(row: dict) -> MedicationOut:
    return MedicationOut(
        id=row["id"],
        care_recipient_id=row["care_recipient_id"],
        name=row["name"],
        dosage=row["dosage"],
        frequency=row["frequency"],
        refill_threshold=row["refill_threshold"],
        pharmacy_id=row.get("pharmacy_id"),
        notes=row.get("notes"),
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


@router.get("", response_model=list[MedicationOut])
async def list_medications(user: dict = Depends(get_current_user)) -> list[MedicationOut]:
    """List all active medications for the current user's care recipient.

    Args:
        user: Injected authenticated user.

    Returns:
        List of active medications.
    """
    crid = _care_recipient_id(user)
    rows = user_store.list_medications(crid)
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=MedicationOut, status_code=status.HTTP_201_CREATED)
async def create_medication(
    body: MedicationCreate, user: dict = Depends(get_current_user)
) -> MedicationOut:
    """Create a new medication for the current user's care recipient.

    Args:
        body: Medication fields.
        user: Injected authenticated user.

    Returns:
        The created medication.
    """
    crid = _care_recipient_id(user)
    corr_id = str(uuid4())

    # Audit BEFORE DB commit.
    from src.models.audit_log import write_audit_event

    write_audit_event(
        actor="human",
        action_type="create_medication",
        care_recipient_id=crid,
        rationale=f"Create medication '{body.name}' for care_recipient={crid}",
        outcome="pending",
        correlation_id=corr_id,
    )

    row = user_store.create_medication(
        care_recipient_id=crid,
        name=body.name,
        dosage=body.dosage,
        frequency=body.frequency,
        refill_threshold=body.refill_threshold,
        pharmacy_id=body.pharmacy_id,
        notes=body.notes,
    )

    # Audit success follow-up.
    write_audit_event(
        actor="human",
        action_type="create_medication",
        care_recipient_id=crid,
        rationale=f"Created medication '{body.name}' (id={row.get('id')})",
        outcome="success",
        correlation_id=corr_id,
    )
    logger.info("Created medication %s for crid=%s", row.get("id"), crid)
    return _row_to_out(row)


@router.get("/{medication_id}", response_model=MedicationOut)
async def get_medication(
    medication_id: str, user: dict = Depends(get_current_user)
) -> MedicationOut:
    """Fetch a single medication by ID.

    Args:
        medication_id: The medication UUID.
        user: Injected authenticated user.

    Returns:
        The medication.

    Raises:
        HTTPException: 404 if not found or belongs to a different care recipient.
    """
    crid = _care_recipient_id(user)
    row = user_store.get_medication(medication_id)
    if row is None or row["care_recipient_id"] != crid:
        raise _NOT_FOUND
    return _row_to_out(row)


@router.put("/{medication_id}", response_model=MedicationOut)
async def update_medication(
    medication_id: str,
    body: MedicationUpdate,
    user: dict = Depends(get_current_user),
) -> MedicationOut:
    """Update an existing medication.

    Args:
        medication_id: The medication UUID.
        body: Fields to update (partial).
        user: Injected authenticated user.

    Returns:
        The updated medication.

    Raises:
        HTTPException: 404 if not found or belongs to a different care recipient.
    """
    crid = _care_recipient_id(user)
    existing = user_store.get_medication(medication_id)
    if existing is None or existing["care_recipient_id"] != crid:
        raise _NOT_FOUND

    corr_id = str(uuid4())
    from src.models.audit_log import write_audit_event

    write_audit_event(
        actor="human",
        action_type="update_medication",
        care_recipient_id=crid,
        rationale=f"Update medication '{existing['name']}' (id={medication_id})",
        outcome="pending",
        correlation_id=corr_id,
    )

    updates = body.model_dump(exclude_unset=True)
    row = user_store.update_medication(medication_id, updates)

    write_audit_event(
        actor="human",
        action_type="update_medication",
        care_recipient_id=crid,
        rationale=f"Updated medication '{existing['name']}' (id={medication_id})",
        outcome="success",
        correlation_id=corr_id,
    )
    logger.info("Updated medication %s for crid=%s", medication_id, crid)
    return _row_to_out(row or {})


@router.delete("/{medication_id}", response_model=MedicationOut)
async def delete_medication(
    medication_id: str, user: dict = Depends(get_current_user)
) -> MedicationOut:
    """Soft-delete a medication (set active=0).

    Args:
        medication_id: The medication UUID.
        user: Injected authenticated user.

    Returns:
        The soft-deleted medication.

    Raises:
        HTTPException: 404 if not found or belongs to a different care recipient.
    """
    crid = _care_recipient_id(user)
    existing = user_store.get_medication(medication_id)
    if existing is None or existing["care_recipient_id"] != crid:
        raise _NOT_FOUND

    corr_id = str(uuid4())
    from src.models.audit_log import write_audit_event

    write_audit_event(
        actor="human",
        action_type="delete_medication",
        care_recipient_id=crid,
        rationale=f"Delete medication '{existing['name']}' (id={medication_id})",
        outcome="pending",
        correlation_id=corr_id,
    )

    row = user_store.soft_delete_medication(medication_id)

    write_audit_event(
        actor="human",
        action_type="delete_medication",
        care_recipient_id=crid,
        rationale=f"Deleted medication '{existing['name']}' (id={medication_id})",
        outcome="success",
        correlation_id=corr_id,
    )
    logger.info("Soft-deleted medication %s for crid=%s", medication_id, crid)
    return _row_to_out(row or {})
