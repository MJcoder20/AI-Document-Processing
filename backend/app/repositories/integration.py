
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integration_log import IntegrationLog


def list_document_integrations(
    db: Session,
    document_id: UUID,
) -> list[IntegrationLog]:
    """Retrieve integration attempts for a document, newest first."""

    statement = (
        select(IntegrationLog)
        .where(IntegrationLog.document_id == document_id)
        .order_by(IntegrationLog.attempt_number.desc())
    )

    return list(db.scalars(statement).all())
