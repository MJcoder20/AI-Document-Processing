
import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import (
    document_id_context,
    message_id_context,
    request_id_context,
)
from app.models.document import Document
from app.models.extraction_result import ExtractionResult
from app.models.outbox_message import OutboxMessage
from app.repositories.outbox import (
    claim_next_outbox_message,
    complete_outbox_claim,
    fail_outbox_claim,
    recover_expired_outbox_messages,
)
from app.services.document_processing import process_document


logger = logging.getLogger(__name__)


def _document_was_already_processed(
    db: Session,
    document_id: UUID,
) -> bool:
    """Check whether document processing was completed previously."""

    document = db.get(Document, document_id)

    if document is None:
        return False

    if document.status in {"uploaded", "failed", "processing"}:
        return False

    extraction = db.scalar(
        select(ExtractionResult.id)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
        .limit(1)
    )

    return extraction is not None


def process_pending_outbox_messages(
    db: Session,
    *,
    limit: int = 100,
) -> dict[str, int]:
    """Process pending messages using leased, exclusive claims."""

    results = {
        "processed": 0,
        "retried": 0,
        "failed": 0,
    }

    if limit <= 0:
        return results

    recovered = recover_expired_outbox_messages(db)

    if recovered:
        logger.warning(
            "Recovered %s expired outbox message leases",
            recovered,
        )

    for _ in range(limit):
        claim = claim_next_outbox_message(db)

        if claim is None:
            break

        message_id, lock_token = claim

        message = db.get(OutboxMessage, message_id)

        if message is None or message.lock_token != lock_token:
            continue

        # Restore the original request ID, or generate one for
        # legacy messages that do not contain a valid request ID.
        payload = message.payload or {}
        original_request_id = payload.get("request_id")

        try:
            correlation_id = str(UUID(str(original_request_id)))
        except (ValueError, TypeError, AttributeError):
            correlation_id = str(uuid4())

        request_token = request_id_context.set(correlation_id)
        message_token = message_id_context.set(str(message_id))
        document_token = document_id_context.set("-")

        try:
            if message.message_type != "process_document":
                raise ValueError(
                    f"Unsupported message type: {message.message_type}"
                )

            document_id = UUID(payload["document_id"])
            document_id_context.set(str(document_id))

            logger.info("outbox.message.processing")

            if not _document_was_already_processed(db, document_id):
                process_document(
                    db,
                    document_id,
                    from_queue=True,
                )

            completed = complete_outbox_claim(
                db,
                message_id=message_id,
                lock_token=lock_token,
            )

            if completed:
                results["processed"] += 1
                logger.info("outbox.message.completed")
            else:
                logger.warning(
                    "Lost lease for outbox message %s; "
                    "another worker may have reclaimed it",
                    message_id,
                )

        except Exception as exc:
            db.rollback()

            logger.exception("outbox.message.failed")

            outcome = fail_outbox_claim(
                db,
                message_id=message_id,
                lock_token=lock_token,
                error_message=str(exc),
            )

            if outcome == "retried":
                results["retried"] += 1
                logger.warning("outbox.message.retry_scheduled")
            elif outcome == "failed":
                results["failed"] += 1
                logger.error("outbox.message.permanently_failed")
            else:
                logger.warning(
                    "Could not update outbox message %s because "
                    "the worker no longer owns its lease",
                    message_id,
                )

        finally:
            # Prevent context from leaking into the next message.
            document_id_context.reset(document_token)
            message_id_context.reset(message_token)
            request_id_context.reset(request_token)

    return results
