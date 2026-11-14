from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


def create_document(
    db: Session,
    *,
    original_filename: str,
    storage_path: str,
    content_type: str,
    file_size: int,
) -> Document:
    """Create and persist a document record."""

    document = Document(
        original_filename=original_filename,
        storage_path=storage_path,
        content_type=content_type,
        file_size=file_size,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def get_document(
    db: Session,
    document_id: UUID,
) -> Document | None:
    """Retrieve a document by its ID."""

    return db.get(Document, document_id)


def list_documents(
    db: Session,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[Document]:
    """Retrieve documents with pagination, newest first."""

    statement = (
        select(Document)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(db.scalars(statement).all())