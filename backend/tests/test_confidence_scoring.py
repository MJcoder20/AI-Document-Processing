
from datetime import date
from decimal import Decimal

import pytest

from app.schemas.extraction import ExtractedInvoiceData
from app.services.confidence_scoring import calculate_field_confidence


def create_invoice(**overrides):
    data = {
        "supplier_name": "ABC Technologies",
        "invoice_number": "INV-2026-105",
        "invoice_date": date(2026, 11, 12),
        "due_date": date(2026, 12, 12),
        "currency": "USD",
        "subtotal": Decimal("500.00"),
        "vat_amount": Decimal("75.00"),
        "total_amount": Decimal("575.00"),
    }
    data.update(overrides)
    return ExtractedInvoiceData(**data)


def test_exactly_supported_fields_receive_high_confidence():
    invoice = create_invoice()

    document_text = """
    Supplier: ABC Technologies
    Invoice Number: INV-2026-105
    Invoice Date: 2026-11-12
    Due Date: 2026-12-12
    Currency: USD
    Subtotal: 500.00
    VAT: 75.00
    Total: 575.00
    """

    scores = calculate_field_confidence(invoice, document_text)

    assert set(scores) == {
        "supplier_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
        "subtotal",
        "vat_amount",
        "total_amount",
    }

    for score in scores.values():
        assert score is not None
        assert Decimal("0") <= score <= Decimal("1")
        assert score >= Decimal("0.8")


def test_missing_fields_have_no_confidence_score():
    invoice = create_invoice(
        supplier_name=None,
        invoice_number=None,
        invoice_date=None,
        due_date=None,
        currency=None,
        subtotal=None,
        vat_amount=None,
        total_amount=None,
    )

    scores = calculate_field_confidence(invoice, "")

    assert all(score is None for score in scores.values())


def test_unsupported_values_receive_low_confidence():
    invoice = create_invoice(
        supplier_name="Unknown Company",
        invoice_number="INV-9999",
        total_amount=Decimal("9999.99"),
    )

    document_text = """
    Supplier: ABC Technologies
    Invoice Number: INV-2026-105
    Total: 575.00
    """

    scores = calculate_field_confidence(invoice, document_text)

    assert scores["supplier_name"] < Decimal("0.8")
    assert scores["invoice_number"] < Decimal("0.8")
    assert scores["total_amount"] < Decimal("0.8")


def test_empty_document_does_not_produce_high_confidence():
    invoice = create_invoice()

    scores = calculate_field_confidence(invoice, "")

    assert all(
        score is None or score < Decimal("0.8")
        for score in scores.values()
    )

def test_table_values_receive_high_confidence():
    invoice = create_invoice()

    tables = [
        [
            ["Description", "Amount"],
            ["Subtotal", "500.00"],
            ["VAT", "75.00"],
            ["Total", "575.00"],
        ]
    ]

    scores = calculate_field_confidence(
        invoice,
        document_text="ABC Technologies INV-2026-105",
        tables=tables,
    )

    assert scores["subtotal"] == Decimal("0.95")
    assert scores["vat_amount"] == Decimal("0.95")
    assert scores["total_amount"] == Decimal("0.95")

