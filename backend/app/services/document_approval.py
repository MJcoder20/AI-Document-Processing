
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_approval import DocumentApproval
from app.models.extraction_result import ExtractionResult
from app.schemas.approval import ApprovalDecision


class DocumentApprovalError(Exception):
    """Raised when a document approval operation is invalid."""


def review_document(
    db: Session,
    document_id: UUID,
    reviewed_by: str,
    decision: ApprovalDecision,
    comments: str | None = None,
) -> DocumentApproval:
    """Approve or reject a document after checking its review status."""

    document = db.scalar(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
    )

    if document is None:
        raise DocumentApprovalError("Document not found.")

    if document.status != "pending_review":
        raise DocumentApprovalError(
            f"Document cannot be reviewed from status: {document.status}"
        )

    if decision == ApprovalDecision.APPROVED:
        extraction = db.scalar(
            select(ExtractionResult)
            .where(ExtractionResult.document_id == document_id)
            .order_by(ExtractionResult.created_at.desc())
        )

        if extraction is None:
            raise DocumentApprovalError(
                "Cannot approve a document without extraction results."
            )

        validation = extraction.extracted_data.get("validation", {})

        if not validation.get("is_valid", False):
            raise DocumentApprovalError(
                "Cannot approve an invoice with validation errors "
                "or duplicate warnings."
            )

    approval = DocumentApproval(
        document_id=document_id,
        reviewed_by=reviewed_by.strip(),
        decision=decision.value,
        comments=comments.strip() if comments else None,
    )

    document.status = decision.value

    db.add(approval)

    try:
        db.commit()
        db.refresh(approval)
    except Exception:
        db.rollback()
        raise

    return approval
