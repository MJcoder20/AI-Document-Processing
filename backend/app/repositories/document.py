from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User


def create_document(
    db: Session,
    *,
    original_filename: str,
    storage_path: str,
    content_type: str,
    file_size: int,
    owner_id: UUID | None = None,
) -> Document:
    """Create and persist a document record."""

    document = Document(
        original_filename=original_filename,
        storage_path=storage_path,
        content_type=content_type,
        file_size=file_size,
        owner_id=owner_id,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def get_document(
    db: Session,
    document_id: UUID,
    *,
    current_user: User | None = None,
) -> Document | None:
    """Retrieve a document, optionally enforcing ownership."""

    statement = select(Document).where(Document.id == document_id)

    if current_user is not None and current_user.role != "admin":
        statement = statement.where(
            Document.owner_id == current_user.id
        )

    return db.scalar(statement)


def list_documents(
    db: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    current_user: User | None = None,
) -> list[Document]:
    """Retrieve accessible documents with pagination, newest first."""

    statement = select(Document)

    if current_user is not None and current_user.role != "admin":
        statement = statement.where(
            Document.owner_id == current_user.id
        )

    statement = (
        statement
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(db.scalars(statement).all())