from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.document import Document
from app.models.extraction_result import ExtractionResult


class InvoiceValidationError(Exception):
    """Raised when invoice validation cannot be completed."""


def validate_invoice(
    db: Session,
    extraction: ExtractionResult,
    document: Document,
) -> dict[str, Any]:
    """
    Validate extracted invoice fields and detect duplicates
    belonging to the same document owner.
    """

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Required fields
    required_fields = {
        "supplier_name": extraction.supplier_name,
        "invoice_number": extraction.invoice_number,
        "invoice_date": extraction.invoice_date,
        "currency": extraction.currency,
        "subtotal": extraction.subtotal,
        "vat_amount": extraction.vat_amount,
        "total_amount": extraction.total_amount,
    }

    for field_name, value in required_fields.items():
        if value is None or (
            isinstance(value, str) and not value.strip()
        ):
            errors.append(f"Missing required field: {field_name}")

    # 2. Monetary consistency
    if (
        extraction.subtotal is not None
        and extraction.vat_amount is not None
        and extraction.total_amount is not None
    ):
        expected_total = (
            Decimal(extraction.subtotal)
            + Decimal(extraction.vat_amount)
        )

        if expected_total != Decimal(extraction.total_amount):
            errors.append(
                "Invoice total does not equal subtotal plus VAT."
            )

    # 3. Date consistency
    if (
        extraction.invoice_date is not None
        and extraction.due_date is not None
        and extraction.due_date < extraction.invoice_date
    ):
        errors.append(
            "Due date cannot be earlier than invoice date."
        )

    # 4. Duplicate detection within the same owner's documents
    duplicate_record = None

    if extraction.supplier_name and extraction.invoice_number:
        statement = (
            select(ExtractionResult)
            .join(
                Document,
                ExtractionResult.document_id == Document.id,
            )
            .options(joinedload(ExtractionResult.document))
            .where(
                Document.owner_id == document.owner_id,
                ExtractionResult.id != extraction.id,
                ExtractionResult.document_id != extraction.document_id,
                ExtractionResult.supplier_name.ilike(
                    extraction.supplier_name.strip()
                ),
                ExtractionResult.invoice_number.ilike(
                    extraction.invoice_number.strip()
                ),
                ExtractionResult.created_at < extraction.created_at,
            )
            .order_by(ExtractionResult.created_at.asc())
            .limit(1)
        )

        duplicate_record = db.scalar(statement)

    duplicate = duplicate_record is not None
    duplicate_of = None

    if duplicate_record:
        previous_document = duplicate_record.document

        duplicate_of = {
            "document_id": str(duplicate_record.document_id),
            "filename": previous_document.original_filename,
            "supplier_name": duplicate_record.supplier_name,
            "invoice_number": duplicate_record.invoice_number,
            "invoice_date": (
                duplicate_record.invoice_date.isoformat()
                if duplicate_record.invoice_date
                else None
            ),
            "currency": duplicate_record.currency,
            "total_amount": (
                str(duplicate_record.total_amount)
                if duplicate_record.total_amount is not None
                else None
            ),
            "created_at": (
                duplicate_record.created_at.isoformat()
                if duplicate_record.created_at
                else None
            ),
        }

        warnings.append(
            "A possible duplicate invoice was detected "
            "for this supplier and invoice number."
        )

    # 5. Validation outcome
    is_valid = len(errors) == 0 and not duplicate

    if errors:
        status = "invalid"
    elif duplicate:
        status = "duplicate"
    else:
        status = "valid"

    return {
        "status": status,
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "duplicate_detected": duplicate,
        "duplicate_of": duplicate_of,
    }