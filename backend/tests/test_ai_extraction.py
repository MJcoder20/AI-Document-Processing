import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.services.ai_extraction import (
    AIExtractionError,
    _extract_gemini_invoice_data,
    extract_invoice_data,
)

def test_extract_invoice_data_handles_nested_invoice_fields(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_extraction.settings.ai_provider",
        "ollama",
    )
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

    def mock_post(self, url, json=None, headers=None):
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
    monkeypatch.setattr(
        "app.services.ai_extraction.settings.ai_provider",
        "ollama",
    )
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

    def mock_post(self, url, json=None, headers=None):
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



def test_gemini_provider_extracts_invoice_fields(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )
    monkeypatch.setattr(
        settings,
        "gemini_model",
        "gemini-3.8-flash",
    )

    response_body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "supplier_name": "ABC Technologies",
                                "invoice_number": "INV-2026-105",
                                "invoice_date": "2026-11-12",
                                "due_date": "2026-12-12",
                                "currency": "USD",
                                "subtotal": "500.00",
                                "vat_amount": "75.00",
                                "total_amount": "575.00",
                                "confidence_score": None,
                                "extracted_data": {},
                            })
                        }
                    ]
                }
            }
        ]
    }

    def mock_post(self, url, headers=None, json=None):
        assert "gemini-3.8-flash:generateContent" in url
        assert headers["x-goog-api-key"] == "test-api-key"

        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    invoice = _extract_gemini_invoice_data(
        document_text="Supplier: ABC Technologies",
    )

    assert invoice.supplier_name == "ABC Technologies"
    assert invoice.invoice_number == "INV-2026-105"
    assert invoice.currency == "USD"
    assert invoice.total_amount == Decimal("575.00")


def test_gemini_provider_rejects_missing_api_key(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(settings, "gemini_api_key", None)

    with pytest.raises(AIExtractionError, match="GEMINI_API_KEY"):
        _extract_gemini_invoice_data("Supplier: ABC")


def test_gemini_provider_handles_http_error(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    def mock_post(self, url, headers=None, json=None):
        return httpx.Response(
            429,
            json={"error": {"message": "Rate limit exceeded"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError, match="HTTP 429"):
        _extract_gemini_invoice_data("Supplier: ABC")


def test_gemini_provider_does_not_retry_daily_quota_exceeded(monkeypatch):
    from app.services.ai_extraction import settings
    import app.services.ai_extraction as ai_extraction

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    attempts = {"count": 0}

    def mock_post(self, url, headers=None, json=None):
        attempts["count"] += 1

        return httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "message": (
                        "Generate content requests per day limit "
                        "exceeded on Free Tier."
                    ),
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    monkeypatch.setattr(
        ai_extraction.time,
        "sleep",
        lambda _: None,
    )

    with pytest.raises(
        AIExtractionError,
        match="daily free-tier quota exceeded",
    ):
        _extract_gemini_invoice_data("Supplier: ABC")

    assert attempts["count"] == 1


def test_gemini_provider_retries_transient_503(monkeypatch):
    from app.services.ai_extraction import settings
    import app.services.ai_extraction as ai_extraction

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    monkeypatch.setattr(ai_extraction.time, "sleep", lambda _: None)

    attempts = {"count": 0}

    success_body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"supplier_name":"ABC",'
                                '"invoice_number":"INV-001",'
                                '"invoice_date":null,'
                                '"due_date":null,'
                                '"currency":"USD",'
                                '"subtotal":100,'
                                '"vat_amount":15,'
                                '"total_amount":115}'
                            )
                        }
                    ]
                },
            }
        ]
    }

    def mock_post(self, url, headers=None, json=None):
        attempts["count"] += 1

        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"error": {"message": "Service unavailable"}},
                request=httpx.Request("POST", url),
            )

        return httpx.Response(
            200,
            json=success_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    invoice = _extract_gemini_invoice_data("Supplier: ABC")

    assert attempts["count"] == 2
    assert invoice.supplier_name == "ABC"


def test_gemini_provider_stops_after_max_retries(monkeypatch):
    from app.services.ai_extraction import settings
    import app.services.ai_extraction as ai_extraction

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    monkeypatch.setattr(ai_extraction.time, "sleep", lambda _: None)

    attempts = {"count": 0}

    def mock_post(self, url, headers=None, json=None):
        attempts["count"] += 1
        return httpx.Response(
            503,
            json={"error": {"message": "Service unavailable"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError, match="HTTP 503"):
        _extract_gemini_invoice_data("Supplier: ABC")

    assert attempts["count"] == 3



def test_gemini_provider_handles_invalid_json(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    response_body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [{"text": "This is not valid JSON"}]
                }
            }
        ]
    }

    def mock_post(self, url, headers=None, json=None):
        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError, match="invalid invoice"):
        _extract_gemini_invoice_data("Supplier: ABC")


def test_gemini_provider_handles_empty_response(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    response_body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": []},
            }
        ]
    }

    def mock_post(self, url, headers=None, json=None):
        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError, match="empty response"):
        _extract_gemini_invoice_data("Supplier: ABC")


def test_gemini_provider_handles_timeout(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    def mock_post(self, url, headers=None, json=None):
        raise httpx.TimeoutException("Request timed out")

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError, match="timed out"):
        _extract_gemini_invoice_data("Supplier: ABC")


def test_gemini_provider_handles_invalid_schema(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    response_body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "currency": "US",
                                "confidence_score": 1.5,
                            })
                        }
                    ]
                },
            }
        ]
    }

    def mock_post(self, url, headers=None, json=None):
        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError):
        _extract_gemini_invoice_data("Supplier: ABC")


def test_gemini_provider_handles_max_tokens(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    response_body = {
        "candidates": [
            {
                "finishReason": "MAX_TOKENS",
                "content": {
                    "parts": [{"text": '{"supplier_name": "ABC"'}]
                },
            }
        ]
    }

    def mock_post(self, url, headers=None, json=None):
        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError, match="token limit"):
        _extract_gemini_invoice_data("Supplier: ABC")


def test_gemini_provider_handles_safety_block(monkeypatch):
    from app.services.ai_extraction import settings

    monkeypatch.setattr(
        settings,
        "gemini_api_key",
        SecretStr("test-api-key"),
    )

    response_body = {
        "candidates": [
            {
                "finishReason": "SAFETY",
                "content": {"parts": []},
            }
        ]
    }

    def mock_post(self, url, headers=None, json=None):
        return httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(AIExtractionError, match="safety"):
        _extract_gemini_invoice_data("Supplier: ABC")
