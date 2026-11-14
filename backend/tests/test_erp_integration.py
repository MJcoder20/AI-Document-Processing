from datetime import date
import uuid
from unittest.mock import MagicMock

import pytest

from app.schemas.integration import IntegrationStatus
from app.services.erp_integration import (
    ERPIntegrationError,
    integrate_document,
)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def approved_document():
    document = MagicMock()
    document.id = uuid.uuid4()
    document.status = "approved"
    return document


@pytest.fixture
def valid_extraction():
    extraction = MagicMock()
    extraction.supplier_name = "ABC Technologies"
    extraction.invoice_number = "INV-2026-106"
    extraction.invoice_date = date(2026, 11, 12)
    extraction.due_date = None
    extraction.currency = "USD"
    extraction.subtotal = 500
    extraction.vat_amount = 75
    extraction.total_amount = 575
    extraction.extracted_data = {
        "validation": {"is_valid": True}
    }
    return extraction



def test_integrate_approved_document(
    mock_db,
    approved_document,
    valid_extraction,
    monkeypatch,
):
    mock_db.scalar.side_effect = [
        approved_document,
        valid_extraction,
        None,
        0,
    ]

    monkeypatch.setattr(
        "app.services.erp_integration.SimulatedERP.create_invoice",
        lambda self, invoice_data: {
            "success": True,
            "external_record_id": "ERP-INV-TEST123456",
            "message": "Invoice successfully created.",
            "invoice": invoice_data,
            "created_at": "2026-11-14T12:00:00+00:00",
        },
    )

    result = integrate_document(
        mock_db,
        approved_document.id,
    )

    assert approved_document.status == "integrated"
    assert result.status == IntegrationStatus.SUCCESS.value
    assert result.external_record_id == "ERP-INV-TEST123456"
    assert result.attempt_number == 1

    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2



def test_prevent_duplicate_integration(
    mock_db, approved_document, valid_extraction
):
    mock_db.scalar.side_effect = [
        approved_document,
        valid_extraction,
        uuid.uuid4(),
    ]

    with pytest.raises(
        ERPIntegrationError,
        match="already been integrated",
    ):
        integrate_document(
            mock_db,
            approved_document.id,
        )

    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


def test_reject_unapproved_document(mock_db):
    document = MagicMock()
    document.status = "pending_review"
    mock_db.scalar.return_value = document

    with pytest.raises(
        ERPIntegrationError,
        match="cannot be integrated",
    ):
        integrate_document(mock_db, uuid.uuid4())

    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


def test_reject_invalid_invoice(
    mock_db, approved_document, valid_extraction
):
    valid_extraction.extracted_data = {
        "validation": {"is_valid": False}
    }

    mock_db.scalar.side_effect = [
        approved_document,
        valid_extraction,
    ]

    with pytest.raises(
        ERPIntegrationError,
        match="has not passed validation",
    ):
        integrate_document(
            mock_db,
            approved_document.id,
        )

    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


def test_failed_erp_attempt_is_logged_and_retryable(
    mock_db,
    approved_document,
    valid_extraction,
    monkeypatch,
):
    mock_db.scalar.side_effect = [
        approved_document,
        valid_extraction,
        None,
        0,
    ]

    def fail_creation(self, invoice_data):
        raise RuntimeError("Simulated ERP connection failure")

    monkeypatch.setattr(
        "app.services.erp_integration.SimulatedERP.create_invoice",
        fail_creation,
    )

    def reload_record(model, record_id):
        if model.__name__ == "IntegrationLog":
            return mock_db.add.call_args.args[0]
        return approved_document

    mock_db.get.side_effect = reload_record

    with pytest.raises(
        ERPIntegrationError,
        match="Simulated ERP connection failure",
    ):
        integrate_document(
            mock_db,
            approved_document.id,
        )

    integration_log = mock_db.add.call_args.args[0]

    assert integration_log.status == IntegrationStatus.FAILED.value
    assert "connection failure" in integration_log.error_message
    assert approved_document.status == "approved"
    assert mock_db.commit.call_count == 2
    assert mock_db.rollback.call_count == 1
