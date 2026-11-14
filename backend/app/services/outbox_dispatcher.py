
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.outbox import get_pending_outbox_messages
from app.services.message_queue import (
    MessageQueueError,
    publish_outbox_message,
)


def dispatch_pending_outbox_messages(
    db: Session,
    *,
    limit: int = 100,
) -> dict[str, int]:
    """
    Publish due outbox messages to Azure Service Bus.

    Each message is processed in its own transaction.
    Failed messages are scheduled for retry using exponential backoff.
    """

    results = {
        "published": 0,
        "failed": 0,
    }

    for _ in range(limit):
        messages = get_pending_outbox_messages(db, limit=1)

        if not messages:
            break

        message = messages[0]

        # Count this publication attempt.
        message.attempt_count += 1

        try:
            publish_outbox_message(message)

            message.status = "published"
            message.published_at = datetime.now(timezone.utc)
            message.error_message = None
            message.next_attempt_at = None

            results["published"] += 1

        except MessageQueueError as exc:
            message.error_message = str(exc)

            if message.attempt_count >= settings.service_bus_max_delivery_count:
                message.status = "failed"
                message.next_attempt_at = None
                results["failed"] += 1
            else:
                delay_seconds = min(
                    2 ** message.attempt_count,
                    3600,
                )

                message.next_attempt_at = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=delay_seconds)
                )

        # Persist the result and release the row lock.
        db.commit()

    return results
