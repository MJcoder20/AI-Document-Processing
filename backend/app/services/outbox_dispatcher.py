
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import (
    document_id_context,
    message_id_context,
    request_id_context,
)
from app.repositories.outbox import get_pending_outbox_messages
from app.services.error_tracking import ( record_error_event, sanitize_error_text, )
from app.services.message_queue import (
    MessageQueueError,
    publish_outbox_message,
)

logger = logging.getLogger(__name__)


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

    if limit <= 0:
        return results

    for _ in range(limit):
        messages = get_pending_outbox_messages(db, limit=1)

        if not messages:
            break

        message = messages[0]

        request_token = request_id_context.set(
            str((message.payload or {}).get("request_id") or "-")
        )
        message_token = message_id_context.set(str(message.id))
        document_token = document_id_context.set(str(message.document_id))

        # Count this publication attempt.
        message.attempt_count += 1

        try:
            try:
                publish_outbox_message(message)

                message.status = "published"
                message.published_at = datetime.now(timezone.utc)
                message.error_message = None
                message.next_attempt_at = None

                results["published"] += 1

            except MessageQueueError as exc:
                # Avoid persisting credentials that might appear in an
                # integration exception message.
                message.error_message = sanitize_error_text(str(exc))[:4000]

                logger.error(
                    "outbox.dispatch.failed",
                    extra={"error_type": type(exc).__name__},
                )

                record_error_event(
                    exc,
                    category="integration",
                    severity="error",
                    endpoint="outbox_dispatcher",
                    method="WORKER",
                )

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

            # Commit only after success or a handled integration failure.
            db.commit()

        except Exception:
            db.rollback()
            raise

        finally:
            document_id_context.reset(document_token)
            message_id_context.reset(message_token)
            request_id_context.reset(request_token)

    return results
