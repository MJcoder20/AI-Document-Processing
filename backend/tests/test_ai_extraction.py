from decimal import Decimal

from app.services.ai_extraction import extract_invoice_data
import json

import httpx

from app.services.ai_extraction import extract_invoice_data


def test_extract_invoice_data_handles_nested_invoice_fields(monkeypatch):
    nested_response = {
        "supplier_name": None,
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "currency": None,
        "subtotal": None,
        "vat_amount": None,
        "total_amount": None,
        "confidence_score": None,
        "extracted_data": {
            "supplier_name": "Horizon Office Supplies Ltd.",
            "invoice_number": "HOS-2026-0148",
            "invoice_date": "2026-11-14",
            "due_date": "2026-12-14",
            "currency": "USD",
            "subtotal": 800.00,
            "vat_amount": 120.00,
            "total_amount": 920.00,
        },
    }

    # This test will be connected to the Ollama response parser
    # in the next step.

    response_body = {
        "message": {
            "content": json.dumps(nested_response)
        }
    }

    def mock_post(self, url, json=None):
        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    invoice = extract_invoice_data(
        document_text="Horizon Office Supplies Ltd. Invoice HOS-2026-0148",
    )

    assert invoice.supplier_name == "Horizon Office Supplies Ltd."
    assert invoice.invoice_number == "HOS-2026-0148"
    assert invoice.currency == "USD"
    assert str(invoice.total_amount) == "920.0"



def test_extract_invoice_data_handles_double_nested_invoice_fields(monkeypatch):
    nested_response = {
        "supplier_name": None,
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "currency": None,
        "subtotal": None,
        "vat_amount": None,
        "total_amount": None,
        "confidence_score": None,
        "extracted_data": {},
        "invoice": {
            "supplier_name": None,
            "invoice_number": None,
            "invoice_date": None,
            "due_date": None,
            "currency": None,
            "subtotal": None,
            "vat_amount": None,
            "total_amount": None,
            "confidence_score": None,
            "extracted_data": {
                "supplier_name": "Horizon Office Supplies Ltd.",
                "invoice_number": "HOS-2026-0149",
                "invoice_date": "2026-11-14",
                "due_date": "2026-12-14",
                "currency": "USD",
                "subtotal": 800.00,
                "vat_amount": 120.00,
                "total_amount": 920.00,
            },
        },
    }

    response_body = {
        "message": {
            "content": json.dumps(nested_response)
        }
    }

    def mock_post(self, url, json=None):
        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    invoice = extract_invoice_data(
        document_text="Horizon Office Supplies Ltd. Invoice HOS-2026-0149",
    )

    assert invoice.supplier_name == "Horizon Office Supplies Ltd."
    assert invoice.invoice_number == "HOS-2026-0149"
    assert str(invoice.invoice_date) == "2026-11-14"
    assert str(invoice.due_date) == "2026-12-14"
    assert invoice.currency == "USD"
    assert str(invoice.subtotal) == "800.0"
    assert str(invoice.vat_amount) == "120.0"
    assert str(invoice.total_amount) == "920.0"


def test_mock_provider_extracts_labeled_invoice_fields(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_extraction.settings.ai_provider",
        "mock",
    )

    invoice = extract_invoice_data(
        document_text=(
            "Supplier: ABC Technologies\n"
            "Invoice: INV-2026-105\n"
            "Invoice Date: 2026-11-12\n"
            "Due Date: 2026-12-12\n"
            "Currency: USD\n"
            "Subtotal: 500.00\n"
            "VAT: 75.00\n"
            "Total: 575.00\n"
        )
    )

    assert invoice.supplier_name == "ABC Technologies"
    assert invoice.invoice_number == "INV-2026-105"
    assert str(invoice.invoice_date) == "2026-11-12"
    assert str(invoice.due_date) == "2026-12-12"
    assert invoice.currency == "USD"
    assert invoice.subtotal == Decimal("500.00")
    assert invoice.vat_amount == Decimal("75.00")
    assert invoice.total_amount == Decimal("575.00")
    assert invoice.confidence_score is None


def test_mock_provider_does_not_invent_missing_fields(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_extraction.settings.ai_provider",
        "mock",
    )

    invoice = extract_invoice_data(
        document_text="Supplier: ABC Technologies"
    )

    assert invoice.supplier_name == "ABC Technologies"
    assert invoice.invoice_number is None
    assert invoice.invoice_date is None
    assert invoice.currency is None
    assert invoice.total_amount is None
    assert invoice.confidence_score is None


def test_extract_invoice_data_rejects_empty_content(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_extraction.settings.ai_provider",
        "mock",
    )

    from app.services.ai_extraction import AIExtractionError

    import pytest

    with pytest.raises(
        AIExtractionError,
        match="no extractable content",
    ):
        extract_invoice_data(document_text="")
