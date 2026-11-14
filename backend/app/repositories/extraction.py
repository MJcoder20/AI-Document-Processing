from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.extraction_result import ExtractionResult


def get_latest_extraction(
    db: Session,
    document_id: UUID,
) -> ExtractionResult | None:
    statement = (
        select(ExtractionResult)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
        .limit(1)
    )

    return db.scalars(statement).first()