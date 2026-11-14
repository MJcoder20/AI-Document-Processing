
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbox_message import OutboxMessage
from app.repositories.outbox import get_pending_outbox_messages
from app.services.document_processing import process_document


def process_pending_outbox_messages(
    db: Session,
    *,
    limit: int = 100,
) -> dict[str, int]:
    results = {"processed": 0, "retried": 0, "failed": 0}

    for _ in range(limit):
        messages = get_pending_outbox_messages(db, limit=1)

        if not messages:
            break

        message = messages[0]
        message_id = message.id
        message.attempt_count += 1
        db.commit()

        try:
            if message.message_type != "process_document":
                raise ValueError(
                    f"Unsupported message type: {message.message_type}"
                )

            document_id = UUID(message.payload["document_id"])

            process_document(
                db,
                document_id,
                from_queue=True,
            )

            message.status = "processed"
            message.error_message = None
            message.next_attempt_at = None
            results["processed"] += 1

            db.commit()

        except Exception as exc:
            db.rollback()

            failed_message = db.get(OutboxMessage, message_id)

            if failed_message is None:
                continue

            failed_message.error_message = str(exc)[:2000]

            if failed_message.attempt_count >= settings.service_bus_max_delivery_count:
                failed_message.status = "failed"
                failed_message.next_attempt_at = None
                results["failed"] += 1
            else:
                delay_seconds = min(
                    2 ** failed_message.attempt_count,
                    3600,
                )
                failed_message.next_attempt_at = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=delay_seconds)
                )
                results["retried"] += 1

            db.commit()

    return results
