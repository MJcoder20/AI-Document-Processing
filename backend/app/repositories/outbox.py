
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbox_message import OutboxMessage


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def create_outbox_message(
    db: Session,
    *,
    document_id: UUID,
    message_type: str,
    payload: dict,
) -> OutboxMessage:
    """Add an outbox message to the current database transaction."""

    message = OutboxMessage(
        document_id=document_id,
        message_type=message_type,
        payload=payload,
        status="pending",
    )

    db.add(message)
    return message


def get_pending_outbox_messages(
    db: Session,
    *,
    limit: int = 100,
) -> list[OutboxMessage]:
    """Retrieve pending messages whose retry time is due."""

    now = datetime.now(timezone.utc)

    statement = (
        select(OutboxMessage)
        .where(
            OutboxMessage.status == "pending",
            or_(
                OutboxMessage.next_attempt_at.is_(None),
                OutboxMessage.next_attempt_at <= now,
            ),
        )
        .order_by(OutboxMessage.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    return list(db.scalars(statement).all())


def recover_expired_outbox_messages(db: Session) -> int:
    """Return expired worker claims to the pending queue or fail them."""
    now = datetime.now(timezone.utc)

    expired_before = datetime.fromtimestamp(
        now.timestamp() - settings.local_worker_lease_seconds,
        tz=timezone.utc,
    )

    expired_messages = db.scalars(
        select(OutboxMessage)
        .where(
            OutboxMessage.status == "processing",
            OutboxMessage.locked_at.is_not(None),
            OutboxMessage.locked_at <= expired_before,
        )
        .with_for_update(skip_locked=True)
    ).all()

    recovered = 0

    for message in expired_messages:
        message.lock_token = None
        message.locked_at = None
        message.error_message = (
            "Worker lease expired before processing was acknowledged."
        )

        if message.attempt_count >= settings.service_bus_max_delivery_count:
            message.status = "failed"
            message.next_attempt_at = None
        else:
            message.status = "pending"
            message.next_attempt_at = now

        recovered += 1

    db.commit()
    return recovered


def claim_next_outbox_message(
    db: Session,
) -> tuple[UUID, str] | None:
    """Atomically claim one due message for a local worker."""

    now = datetime.now(timezone.utc)

    message = db.scalar(
        select(OutboxMessage)
        .where(
            OutboxMessage.status == "pending",
            or_(
                OutboxMessage.next_attempt_at.is_(None),
                OutboxMessage.next_attempt_at <= now,
            ),
        )
        .order_by(OutboxMessage.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    if message is None:
        return None

    token = str(uuid4())

    message.status = "processing"
    message.locked_at = now
    message.lock_token = token
    message.attempt_count += 1

    message_id = message.id

    db.commit()

    return message_id, token


def complete_outbox_claim(
    db: Session,
    *,
    message_id: UUID,
    lock_token: str,
) -> bool:
    message = db.scalar(
        select(OutboxMessage)
        .where(
            OutboxMessage.id == message_id,
            OutboxMessage.status == "processing",
            OutboxMessage.lock_token == lock_token,
        )
        .with_for_update()
    )

    if message is None or message.locked_at is None:
        return False

    now = datetime.now(timezone.utc)
    locked_at = _as_utc(message.locked_at)

    lease_age = (now - locked_at).total_seconds()

    if lease_age > settings.local_worker_lease_seconds:
        return False

    message.status = "processed"
    message.error_message = None
    message.next_attempt_at = None
    message.locked_at = None
    message.lock_token = None

    db.commit()
    return True


def fail_outbox_claim(
    db: Session,
    *,
    message_id: UUID,
    lock_token: str,
    error_message: str,
) -> str | None:
    """Retry or fail a message if the worker still owns its lease."""
    message = db.scalar(
        select(OutboxMessage)
        .where(
            OutboxMessage.id == message_id,
            OutboxMessage.status == "processing",
            OutboxMessage.lock_token == lock_token,
        )
        .with_for_update()
    )

    if message is None or message.locked_at is None:
        return None

    now = datetime.now(timezone.utc)
    locked_at = _as_utc(message.locked_at)

    lease_age = (now - locked_at).total_seconds()

    if lease_age >= settings.local_worker_lease_seconds:
        return None

    message.error_message = error_message[:2000]
    message.locked_at = None
    message.lock_token = None

    if message.attempt_count >= settings.service_bus_max_delivery_count:
        message.status = "failed"
        message.next_attempt_at = None
        result = "failed"
    else:
        delay_seconds = min(2 ** message.attempt_count, 3600)

        message.status = "pending"
        message.next_attempt_at = datetime.fromtimestamp(
            now.timestamp() + delay_seconds,
            tz=timezone.utc,
        )
        result = "retried"

    db.commit()
    return result
