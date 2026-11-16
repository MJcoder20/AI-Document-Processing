
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
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

        try:
            message = db.get(OutboxMessage, message_id)

            if message is None or message.lock_token != lock_token:
                continue

            if message.message_type != "process_document":
                raise ValueError(
                    f"Unsupported message type: {message.message_type}"
                )

            document_id = UUID(message.payload["document_id"])

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
            else:
                logger.warning(
                    "Lost lease for outbox message %s; "
                    "another worker may have reclaimed it",
                    message_id,
                )

        except Exception as exc:
            db.rollback()

            outcome = fail_outbox_claim(
                db,
                message_id=message_id,
                lock_token=lock_token,
                error_message=str(exc),
            )

            if outcome == "retried":
                results["retried"] += 1
            elif outcome == "failed":
                results["failed"] += 1
            else:
                logger.warning(
                    "Could not update outbox message %s because "
                    "the worker no longer owns its lease",
                    message_id,
                )

    return results
