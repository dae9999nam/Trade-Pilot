from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Order, OrderEvent

ORDER_PENDING_APPROVAL = "PENDING_APPROVAL"
ORDER_APPROVED = "APPROVED"
ORDER_SUBMITTING = "SUBMITTING"
ORDER_SUBMITTED = "SUBMITTED"
ORDER_PARTIALLY_FILLED = "PARTIALLY_FILLED"
ORDER_FILLED = "FILLED"
ORDER_REJECTED = "REJECTED"
ORDER_SUBMISSION_FAILED = "SUBMISSION_FAILED"
ORDER_CANCELED = "CANCELED"

ORDER_OPEN_STATUSES = {
    ORDER_PENDING_APPROVAL,
    ORDER_APPROVED,
    ORDER_SUBMITTING,
    ORDER_SUBMITTED,
    ORDER_PARTIALLY_FILLED,
    ORDER_SUBMISSION_FAILED,
}
ORDER_TERMINAL_STATUSES = {ORDER_FILLED, ORDER_REJECTED, ORDER_CANCELED}
ORDER_APPROVABLE_STATUSES = {ORDER_PENDING_APPROVAL, ORDER_SUBMISSION_FAILED}

ORDER_TRANSITIONS: dict[str, set[str]] = {
    ORDER_PENDING_APPROVAL: {ORDER_APPROVED, ORDER_CANCELED},
    ORDER_APPROVED: {ORDER_SUBMITTING, ORDER_CANCELED},
    ORDER_SUBMITTING: {
        ORDER_SUBMITTED,
        ORDER_PARTIALLY_FILLED,
        ORDER_FILLED,
        ORDER_REJECTED,
        ORDER_SUBMISSION_FAILED,
        ORDER_CANCELED,
    },
    ORDER_SUBMISSION_FAILED: {ORDER_APPROVED, ORDER_CANCELED},
    ORDER_SUBMITTED: {ORDER_PARTIALLY_FILLED, ORDER_FILLED, ORDER_REJECTED, ORDER_CANCELED},
    ORDER_PARTIALLY_FILLED: {ORDER_FILLED, ORDER_REJECTED, ORDER_CANCELED},
    ORDER_FILLED: set(),
    ORDER_REJECTED: set(),
    ORDER_CANCELED: set(),
}


def can_transition(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True
    return to_status in ORDER_TRANSITIONS.get(from_status, set())


def can_approve(order: Order) -> bool:
    return order.status in ORDER_APPROVABLE_STATUSES


def is_terminal(order: Order) -> bool:
    return order.status in ORDER_TERMINAL_STATUSES


def transition_order(
    db: Session,
    order: Order,
    to_status: str,
    *,
    event_type: str,
    message: str | None = None,
    broker_order_id: str | None = None,
    event_payload: dict[str, Any] | None = None,
) -> None:
    from_status = order.status
    if not can_transition(from_status, to_status):
        raise ValueError(f"Invalid order status transition: {from_status} -> {to_status}.")

    now = datetime.now(UTC)
    order.status = to_status
    order.last_status_at = now
    if message is not None:
        order.message = message
    if broker_order_id is not None:
        order.broker_order_id = broker_order_id
    _stamp_status_time(order, to_status, now)

    db.add(
        OrderEvent(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            event_type=event_type,
            message=message,
            broker_order_id=broker_order_id,
            event_payload=event_payload,
        )
    )


def initialize_order_status(
    db: Session,
    order: Order,
    status: str,
    *,
    event_type: str,
    message: str | None = None,
    event_payload: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(UTC)
    order.status = status
    order.last_status_at = now
    if message is not None:
        order.message = message
    _stamp_status_time(order, status, now)
    db.add(
        OrderEvent(
            order_id=order.id,
            from_status=None,
            to_status=status,
            event_type=event_type,
            message=message,
            event_payload=event_payload,
        )
    )


def _stamp_status_time(order: Order, status: str, now: datetime) -> None:
    if status == ORDER_APPROVED:
        order.approved_at = order.approved_at or now
    elif status in {ORDER_SUBMITTING, ORDER_SUBMITTED}:
        order.submitted_at = order.submitted_at or now
    elif status == ORDER_FILLED:
        order.filled_at = order.filled_at or now
    elif status == ORDER_REJECTED:
        order.rejected_at = order.rejected_at or now
    elif status == ORDER_SUBMISSION_FAILED:
        order.failed_at = order.failed_at or now
    elif status == ORDER_CANCELED:
        order.canceled_at = order.canceled_at or now
