from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction_result import ExtractionResult
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
    search: str | None = None,
    status: str | None = None,
    document_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[Document], int]:
    """Retrieve filtered documents and their total count."""

    statement = select(Document)

    if current_user is not None and current_user.role != "admin":
        statement = statement.where(
            Document.owner_id == current_user.id
        )

    if search and search.strip():
        search_pattern = f"%{search.strip()}%"

        matching_extraction = (
            select(ExtractionResult.id)
            .where(
                ExtractionResult.document_id == Document.id,
                or_(
                    ExtractionResult.supplier_name.ilike(search_pattern),
                    ExtractionResult.invoice_number.ilike(search_pattern),
                ),
            )
            .exists()
        )

        statement = statement.where(
            or_(
                Document.original_filename.ilike(search_pattern),
                matching_extraction,
            )
        )

    if status:
        statement = statement.where(Document.status == status)

    if document_type:
        statement = statement.where(
            Document.document_type == document_type
        )

    if date_from:
        statement = statement.where(
            Document.created_at >= date_from
        )

    if date_to:
        next_day = datetime.combine(
            date_to + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        statement = statement.where(Document.created_at < next_day)

    count_statement = select(func.count()).select_from(
        statement.order_by(None).subquery()
    )
    total = db.scalar(count_statement) or 0

    documents_statement = (
        statement
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    )

    documents = list(db.scalars(documents_statement).all())

    return documents, total
