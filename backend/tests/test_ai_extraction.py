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
