"""CareBridge shared Pydantic v2 data models.

All structured data exchanged between agents MUST use these models.
Agents return structured models only — never free-form strings.
"""

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Literal, Optional
from uuid import UUID, uuid4


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
    phone: Optional[str] = None
    email: Optional[str] = None
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
    authorization_ref: Optional[str] = None


class CareEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: Literal["refill_low", "appointment_upcoming", "delivery_failed", "adherence_deviation"]
    care_recipient_id: str
    payload: dict
    received_at: datetime = Field(default_factory=datetime.utcnow)


class ResolutionResult(BaseModel):
    event_id: UUID
    resolved: bool
    actions_taken: list[str]
    escalation_required: bool
    escalation_level: Optional[Literal["info", "alert", "emergency"]] = None
    audit_event_ids: list[UUID] = []


class RefillStatus(BaseModel):
    medication_id: str
    days_remaining: int
    refill_eligible: bool
    pharmacy_id: str


class RefillOrder(BaseModel):
    order_id: str
    medication_id: str
    status: Literal["placed", "failed"]
    estimated_delivery: Optional[date] = None
    failure_reason: Optional[str] = None


class AdherencePattern(BaseModel):
    medication_id: str
    missed_doses: int
    late_doses: int
    deviation_flag: bool
    severity: Literal["none", "mild", "moderate", "severe"]


class DeliveryStatus(BaseModel):
    delivery_id: str
    status: Literal["pending", "in_transit", "delivered", "failed"]
    expected_at: Optional[datetime] = None
    failure_reason: Optional[str] = None


class DeliveryOrder(BaseModel):
    order_id: str
    delivery_id: str
    status: Literal["placed", "failed"]
    expected_at: Optional[datetime] = None
    failure_reason: Optional[str] = None


class ChecklistResult(BaseModel):
    appointment_id: str
    checklist_sent: bool
    delivery_status: str
    sent_at: Optional[datetime] = None


class AlertResult(BaseModel):
    alert_id: str
    delivery_status: str
    channel_used: str
    sent_at: datetime


class StatusSummary(BaseModel):
    care_recipient_id: str
    summary_text: str
    recent_events: list[AuditEvent] = []
    pending_actions: list["PendingAction"] = []


class PendingAction(BaseModel):
    action_id: str
    action_type: str
    care_recipient_id: str
    rationale: str
    requested_at: datetime
    status: Literal["pending", "approved", "rejected"] = "pending"
    authorization_ref: Optional[str] = None


class FamilyPreferences(BaseModel):
    family_id: str
    members: list[FamilyMember]
    escalation_order: list[str]


# Resolve the PendingAction forward reference in StatusSummary.
StatusSummary.model_rebuild()
