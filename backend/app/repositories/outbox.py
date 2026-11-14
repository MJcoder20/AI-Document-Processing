
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.outbox_message import OutboxMessage


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
