
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document
from app.models.outbox_message import OutboxMessage


router = APIRouter(tags=["Health"])


@router.get("/health/live")
async def liveness_check():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
        }
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "unavailable",
            },
        )


@router.get("/health/worker")
async def worker_health(db: Session = Depends(get_db)):
    try:
        now = datetime.now(timezone.utc)

        rows = db.execute(
            select(
                OutboxMessage.status,
                func.count(OutboxMessage.id),
            ).group_by(OutboxMessage.status)
        ).all()

        counts = {
            "pending": 0,
            "processing": 0,
            "processed": 0,
            "failed": 0,
        }

        for status, count in rows:
            if status in counts:
                counts[status] = count

        retrying = db.scalar(
            select(func.count(OutboxMessage.id)).where(
                OutboxMessage.status == "pending",
                OutboxMessage.next_attempt_at > now,
            )
        ) or 0

        return {
            "status": "healthy",
            "queue": {
                **counts,
                "retrying": retrying,
            },
        }

    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "error": "Could not retrieve worker statistics",
            },
        )



@router.get("/health/metrics")
async def operational_metrics(db: Session = Depends(get_db)):
    try:
        # Document counts by status.
        document_status_rows = db.execute(
            select(
                Document.status,
                func.count(Document.id),
            ).group_by(Document.status)
        ).all()

        document_statuses = {
            status: count for status, count in document_status_rows
        }

        # Document counts by type.
        document_type_rows = db.execute(
            select(
                Document.document_type,
                func.count(Document.id),
            ).group_by(Document.document_type)
        ).all()

        document_types = {
            document_type: count
            for document_type, count in document_type_rows
        }

        # Outbox counts by status.
        outbox_rows = db.execute(
            select(
                OutboxMessage.status,
                func.count(OutboxMessage.id),
            ).group_by(OutboxMessage.status)
        ).all()

        outbox_statuses = {
            status: count for status, count in outbox_rows
        }

        now = datetime.now(timezone.utc)

        retrying = db.scalar(
            select(func.count(OutboxMessage.id)).where(
                OutboxMessage.status == "pending",
                OutboxMessage.next_attempt_at > now,
            )
        ) or 0

        total_documents = sum(document_statuses.values())
        total_outbox_messages = sum(outbox_statuses.values())
        pending = outbox_statuses.get("pending", 0)

        return {
            "status": "healthy",
            "documents": {
                "total": total_documents,
                "by_status": document_statuses,
                "by_type": document_types,
            },
            "outbox": {
                "total": total_outbox_messages,
                "by_status": outbox_statuses,
                "pending_backlog": pending - retrying,
                "retrying": retrying,
            },
        }

    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "error": "Could not retrieve operational metrics",
            },
        )
