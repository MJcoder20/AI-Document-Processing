import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
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
from app.models.worker_execution import WorkerExecution
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


def _finish_execution(
    db: Session,
    execution_id: UUID,
    *,
    outcome: str,
    started_at: datetime,
    error_message: str | None = None,
) -> None:
    """Persist the final outcome of a worker execution."""

    finished_at = datetime.now(timezone.utc)

    execution = db.get(WorkerExecution, execution_id)

    if execution is None:
        logger.error(
            "Worker execution record %s was not found",
            execution_id,
        )
        return

    execution.outcome = outcome
    execution.finished_at = finished_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    else:
        started_at = started_at.astimezone(timezone.utc)
    execution.duration_ms = max(
        0,
        int((finished_at - started_at).total_seconds() * 1000),
    )
    execution.error_message = (
        error_message[:2000] if error_message else None
    )

    db.commit()


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

    # Close execution records whose messages had expired leases.
    stale_executions = db.execute(
        select(WorkerExecution, OutboxMessage.status)
        .join(
            OutboxMessage,
            WorkerExecution.message_id == OutboxMessage.id,
        )
        .where(
            WorkerExecution.outcome == "active",
            or_(
                OutboxMessage.status != "processing",
                and_(
                    OutboxMessage.status == "processing",
                    WorkerExecution.lock_token.is_distinct_from(
                        OutboxMessage.lock_token
                    ),
                ),
            ),
        )
    ).all()

    for execution, message_status in stale_executions:
        outcome = (
            "processed"
            if message_status == "processed"
            else "interrupted"
        )

        _finish_execution(
            db,
            execution.id,
            outcome=outcome,
            started_at=execution.started_at,
            error_message=(
                None
                if outcome == "processed"
                else "Worker lease expired or was replaced."
            ),
        )

    for _ in range(limit):
        claim = claim_next_outbox_message(db)

        if claim is None:
            break

        message_id, lock_token = claim

        message = db.get(OutboxMessage, message_id)

        if message is None or message.lock_token != lock_token:
            continue

        started_at = datetime.now(timezone.utc)

        execution = WorkerExecution(
            message_id=message_id,
            lock_token=lock_token,
            outcome="active",
            started_at=started_at,
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        execution_id = execution.id

        original_request_id = (message.payload or {}).get("request_id")

        try:
            correlation_id = str(UUID(str(original_request_id)))
        except (ValueError, TypeError, AttributeError):
            correlation_id = str(uuid4())

        request_token = request_id_context.set(correlation_id)
        message_token = message_id_context.set(str(message_id))
        document_token = document_id_context.set("-")

        outcome = "interrupted"
        error_message = None

        try:
            if message.message_type != "process_document":
                raise ValueError(
                    f"Unsupported message type: {message.message_type}"
                )

            document_id = UUID(message.payload["document_id"])
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
                outcome = "processed"
                logger.info("outbox.message.completed")
            else:
                outcome = "lease_lost"
                logger.warning(
                    "Lost lease for outbox message %s",
                    message_id,
                )

        except Exception as exc:
            db.rollback()

            error_message = str(exc)

            logger.exception("outbox.message.failed")

            failure_outcome = fail_outbox_claim(
                db,
                message_id=message_id,
                lock_token=lock_token,
                error_message=error_message,
            )

            if failure_outcome == "retried":
                results["retried"] += 1
                outcome = "retried"
                logger.warning("outbox.message.retry_scheduled")

            elif failure_outcome == "failed":
                results["failed"] += 1
                outcome = "failed"
                logger.error("outbox.message.permanently_failed")

            else:
                outcome = "lease_lost"
                logger.warning(
                    "Could not update outbox message %s; "
                    "worker no longer owns its lease",
                    message_id,
                )

        finally:
            try:
                _finish_execution(
                    db,
                    execution_id,
                    outcome=outcome,
                    started_at=started_at,
                    error_message=error_message,
                )
            except Exception:
                db.rollback()
                logger.exception(
                    "Could not finalize worker execution %s",
                    execution_id,
                )

            document_id_context.reset(document_token)
            message_id_context.reset(message_token)
            request_id_context.reset(request_token)

    return results
