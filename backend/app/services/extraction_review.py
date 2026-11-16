
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction_edit import ExtractionEdit
from app.models.extraction_result import ExtractionResult
from app.services.invoice_validation import validate_invoice


class ExtractionReviewError(Exception):
    """Raised when an extraction correction cannot be completed."""


EDITABLE_FIELDS = (
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "vat_amount",
    "total_amount",
)


def _serialize_value(value: Any) -> Any:
    """Convert values into JSON-compatible representations."""
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return value


def _snapshot(extraction: ExtractionResult) -> dict[str, Any]:
    return {
        field: _serialize_value(getattr(extraction, field))
        for field in EDITABLE_FIELDS
    }


def correct_extraction(
    db: Session,
    document_id: UUID,
    corrections: dict[str, Any],
    edited_by: str,
) -> ExtractionResult:
    """
    Apply reviewer corrections, revalidate the invoice,
    and preserve an audit record.
    """

    document = db.scalar(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
    )

    if document is None:
        raise ExtractionReviewError("Document not found.")

    if document.status != "pending_review":
        raise ExtractionReviewError(
            "Only documents pending review can be edited."
        )

    extraction = db.scalar(
        select(ExtractionResult)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
        .limit(1)
        .with_for_update()
    )

    if extraction is None:
        raise ExtractionReviewError(
            "No extraction result exists for this document."
        )

    unknown_fields = set(corrections) - set(EDITABLE_FIELDS)

    if unknown_fields:
        raise ExtractionReviewError(
            f"Unsupported correction fields: {', '.join(sorted(unknown_fields))}"
        )

    if not corrections:
        raise ExtractionReviewError("No corrections were provided.")

    before_data = _snapshot(extraction)
    changed_fields = []

    for field, value in corrections.items():
        if getattr(extraction, field) != value:
            setattr(extraction, field, value)
            changed_fields.append(field)

    if not changed_fields:
        raise ExtractionReviewError("No field values were changed.")

    validation = validate_invoice(db, extraction, document)

    extracted_data = dict(extraction.extracted_data or {})
    extracted_data["validation"] = validation
    extraction.extracted_data = extracted_data

    after_data = _snapshot(extraction)

    audit_record = ExtractionEdit(
        document_id=document.id,
        extraction_id=extraction.id,
        edited_by=edited_by,
        changed_fields=changed_fields,
        before_data=before_data,
        after_data=after_data,
    )

    db.add(audit_record)
    db.flush()

    return extraction
