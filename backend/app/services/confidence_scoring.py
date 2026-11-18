
import re
from decimal import Decimal
from typing import Any

from app.schemas.extraction import ExtractedInvoiceData


CONFIDENCE_HIGH = Decimal("0.95")
CONFIDENCE_UNSUPPORTED = Decimal("0.10")


def _normalize_text(value: Any) -> str:
    """Normalize text for case-insensitive evidence matching."""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _normalize_amount(value: Decimal) -> str:
    """Normalize monetary values for matching."""
    return format(value, ".2f")


def _field_value(invoice: ExtractedInvoiceData, field: str) -> Any:
    return getattr(invoice, field)


def _find_evidence(
    value: Any,
    document_text: str,
) -> bool:
    """Check whether an extracted value appears in document text."""
    if value is None or not document_text.strip():
        return False

    if isinstance(value, Decimal):
        candidates = {
            _normalize_amount(value),
            format(value, "f"),
            str(value),
        }
        normalized_document = _normalize_text(document_text)

        return any(
            _normalize_text(candidate) in normalized_document
            for candidate in candidates
        )

    return _normalize_text(value) in _normalize_text(document_text)


def calculate_field_confidence(
    invoice: ExtractedInvoiceData,
    document_text: str,
    tables: list | None = None,
) -> dict[str, Decimal | None]:
    """
    Calculate evidence-based heuristic confidence for invoice fields.

    Scores indicate source-text support, not statistically calibrated
    probabilities or guaranteed extraction accuracy.
    """
    fields = (
        "supplier_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
        "subtotal",
        "vat_amount",
        "total_amount",
    )

    combined_evidence = document_text or ""

    if tables:
        combined_evidence += "\n" + "\n".join(
            str(row)
            for table in tables
            for row in table
        )

    scores: dict[str, Decimal | None] = {}

    for field in fields:
        value = _field_value(invoice, field)

        if value is None:
            scores[field] = None
        elif _find_evidence(value, combined_evidence):
            scores[field] = CONFIDENCE_HIGH
        else:
            scores[field] = CONFIDENCE_UNSUPPORTED

    return scores
