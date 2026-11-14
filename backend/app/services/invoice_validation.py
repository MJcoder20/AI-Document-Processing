
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.extraction_result import ExtractionResult


class InvoiceValidationError(Exception):
    """Raised when invoice validation cannot be completed."""


def validate_invoice(
    db: Session,
    extraction: ExtractionResult,
) -> dict[str, Any]:
    """
    Validate extracted invoice fields and detect duplicate invoices.

    Returns validation status, errors, warnings, and duplicate information.
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

    # 4. Duplicate invoice detection
    duplicate = False

    if extraction.supplier_name and extraction.invoice_number:
        statement = select(ExtractionResult).where(
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

        duplicate_record = db.scalar(statement)
        duplicate = duplicate_record is not None

        if duplicate:
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
    }
