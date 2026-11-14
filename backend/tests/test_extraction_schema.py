from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.extraction import ExtractedInvoiceData


def test_valid_invoice_extraction():
    invoice = ExtractedInvoiceData(
        supplier_name="ABC Technologies",
        invoice_number="INV-2026-001",
        invoice_date=date(2026, 11, 10),
        due_date=date(2026, 12, 10),
        currency="USD",
        subtotal=Decimal("1000.00"),
        vat_amount=Decimal("150.00"),
        total_amount=Decimal("1150.00"),
        confidence_score=Decimal("0.98"),
        extracted_data={"payment_terms": "Net 30"},
    )

    assert invoice.supplier_name == "ABC Technologies"
    assert invoice.invoice_number == "INV-2026-001"
    assert invoice.total_amount == Decimal("1150.00")
    assert invoice.confidence_score == Decimal("0.98")


def test_invoice_extraction_allows_missing_fields():
    invoice = ExtractedInvoiceData()

    assert invoice.supplier_name is None
    assert invoice.invoice_number is None
    assert invoice.total_amount is None
    assert invoice.extracted_data == {}


def test_invoice_extraction_rejects_invalid_currency():
    with pytest.raises(ValidationError):
        ExtractedInvoiceData(currency="US")


def test_invoice_extraction_rejects_lowercase_currency():
    with pytest.raises(ValidationError):
        ExtractedInvoiceData(currency="usd")


@pytest.mark.parametrize(
    "confidence",
    [
        Decimal("-0.01"),
        Decimal("1.01"),
    ],
)
def test_invoice_extraction_rejects_invalid_confidence(confidence):
    with pytest.raises(ValidationError):
        ExtractedInvoiceData(confidence_score=confidence)


def test_invoice_extraction_accepts_confidence_boundaries():
    lower = ExtractedInvoiceData(confidence_score=Decimal("0"))
    upper = ExtractedInvoiceData(confidence_score=Decimal("1"))

    assert lower.confidence_score == Decimal("0")
    assert upper.confidence_score == Decimal("1")


def test_invoice_extraction_uses_decimal_for_amounts():
    invoice = ExtractedInvoiceData(
        subtotal="1234.56",
        vat_amount="185.18",
        total_amount="1419.74",
    )

    assert isinstance(invoice.subtotal, Decimal)
    assert isinstance(invoice.vat_amount, Decimal)
    assert isinstance(invoice.total_amount, Decimal)


def test_extracted_data_uses_independent_default_dictionaries():
    first = ExtractedInvoiceData()
    second = ExtractedInvoiceData()

    first.extracted_data["reference"] = "PO-001"

    assert second.extracted_data == {}