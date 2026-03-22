"""
FilingStateMachine -- Enforces valid status transitions for filings.

Standalone version: no database dependency. Tracks status in memory.
"""
import logging
from enum import Enum
from datetime import datetime

from openklerk.core.exceptions import InvalidTransitionError

logger = logging.getLogger("openklerk")


class FilingStatus(str, Enum):
    SCHEDULED = "scheduled"
    TRIGGERED = "triggered"
    PREPARING = "preparing"
    READY = "ready"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    NEEDS_INPUT = "needs_input"
    AWAITING_PAYMENT = "awaiting_payment"
    AWAITING_USER_PAYMENT = "awaiting_user_payment"
    AWAITING_OWNER_PAYMENT = "awaiting_owner_payment"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


VALID_TRANSITIONS: dict[FilingStatus, list[FilingStatus]] = {
    FilingStatus.SCHEDULED: [
        FilingStatus.TRIGGERED, FilingStatus.CANCELLED, FilingStatus.OVERDUE,
    ],
    FilingStatus.TRIGGERED: [
        FilingStatus.PREPARING, FilingStatus.CANCELLED, FilingStatus.FAILED,
    ],
    FilingStatus.PREPARING: [
        FilingStatus.READY, FilingStatus.FAILED, FilingStatus.CANCELLED,
    ],
    FilingStatus.READY: [
        FilingStatus.QUEUED, FilingStatus.CANCELLED,
    ],
    FilingStatus.QUEUED: [
        FilingStatus.IN_PROGRESS, FilingStatus.FAILED, FilingStatus.CANCELLED,
    ],
    FilingStatus.IN_PROGRESS: [
        FilingStatus.NEEDS_INPUT, FilingStatus.AWAITING_PAYMENT,
        FilingStatus.AWAITING_USER_PAYMENT, FilingStatus.AWAITING_OWNER_PAYMENT,
        FilingStatus.COMPLETED, FilingStatus.FAILED, FilingStatus.CANCELLED,
    ],
    FilingStatus.NEEDS_INPUT: [
        FilingStatus.IN_PROGRESS, FilingStatus.FAILED, FilingStatus.CANCELLED,
    ],
    FilingStatus.AWAITING_PAYMENT: [
        FilingStatus.IN_PROGRESS, FilingStatus.FAILED, FilingStatus.CANCELLED,
    ],
    FilingStatus.AWAITING_USER_PAYMENT: [
        FilingStatus.COMPLETED, FilingStatus.FAILED, FilingStatus.CANCELLED,
    ],
    FilingStatus.AWAITING_OWNER_PAYMENT: [
        FilingStatus.IN_PROGRESS, FilingStatus.COMPLETED,
        FilingStatus.FAILED, FilingStatus.CANCELLED,
    ],
    FilingStatus.COMPLETED: [],
    FilingStatus.FAILED: [
        FilingStatus.QUEUED, FilingStatus.CANCELLED,
    ],
    FilingStatus.CANCELLED: [],
    FilingStatus.OVERDUE: [
        FilingStatus.QUEUED, FilingStatus.CANCELLED,
    ],
}


class FilingStateMachine:
    """Standalone state machine -- no database dependency."""

    def __init__(self, initial_status: FilingStatus = FilingStatus.SCHEDULED):
        self.status = initial_status
        self.updated_at = datetime.utcnow()

    def transition(self, new_status: FilingStatus) -> FilingStatus:
        """Transition to a new status. Raises InvalidTransitionError if invalid."""
        allowed = VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {self.status.value} to {new_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        old = self.status.value
        self.status = new_status
        self.updated_at = datetime.utcnow()
        logger.info(f"Filing status: {old} -> {new_status.value}")
        return self.status

    def can_transition(self, new_status: FilingStatus) -> bool:
        """Check if a transition is valid without performing it."""
        return new_status in VALID_TRANSITIONS.get(self.status, [])

    @property
    def is_terminal(self) -> bool:
        return self.status in (FilingStatus.COMPLETED, FilingStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self.status in (
            FilingStatus.QUEUED, FilingStatus.IN_PROGRESS,
            FilingStatus.NEEDS_INPUT, FilingStatus.AWAITING_PAYMENT,
        )
