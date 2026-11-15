import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.extraction_result import ExtractionResult
from app.models.document import Document
from app.services.invoice_validation import validate_invoice


@pytest.fixture
def valid_document():
    document = MagicMock(spec=Document)
    document.id = uuid.uuid4()
    document.owner_id = uuid.uuid4()
    document.original_filename = "invoice.pdf"
    return document

@pytest.fixture
def valid_invoice():
    invoice = MagicMock(spec=ExtractionResult)
    invoice.id = uuid.uuid4()
    invoice.document_id = uuid.uuid4()
    invoice.created_at = date(2026, 11, 14)
    invoice.supplier_name = "ABC Technologies"
    invoice.invoice_number = "INV-2026-105"
    invoice.invoice_date = date(2026, 11, 12)
    invoice.due_date = date(2026, 12, 12)
    invoice.currency = "USD"
    invoice.subtotal = Decimal("500.00")
    invoice.vat_amount = Decimal("75.00")
    invoice.total_amount = Decimal("575.00")
    return invoice


@pytest.fixture
def mock_db():
    return MagicMock()


def test_valid_invoice(valid_invoice, mock_db, valid_document):
    mock_db.scalar.return_value = None

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["status"] == "valid"
    assert result["is_valid"] is True
    assert result["errors"] == []
    assert result["duplicate_detected"] is False


def test_missing_required_field(valid_invoice, mock_db, valid_document):
    valid_invoice.supplier_name = None
    mock_db.scalar.return_value = None

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["status"] == "invalid"
    assert result["is_valid"] is False
    assert "Missing required field: supplier_name" in result["errors"]


def test_total_mismatch(valid_invoice, mock_db, valid_document):
    valid_invoice.total_amount = Decimal("600.00")
    mock_db.scalar.return_value = None

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["status"] == "invalid"
    assert (
        "Invoice total does not equal subtotal plus VAT."
        in result["errors"]
    )


def test_due_date_before_invoice_date(valid_invoice, mock_db, valid_document):
    valid_invoice.due_date = date(2026, 11, 10)
    mock_db.scalar.return_value = None

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["status"] == "invalid"
    assert (
        "Due date cannot be earlier than invoice date."
        in result["errors"]
    )


def test_original_invoice_is_not_duplicate(valid_invoice, mock_db, valid_document):
    mock_db.scalar.return_value = None

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["status"] == "valid"
    assert result["is_valid"] is True
    assert result["duplicate_detected"] is False


def test_later_invoice_is_duplicate(valid_invoice, mock_db, valid_document):
    duplicate_record = MagicMock(spec=ExtractionResult)
    previous_document = MagicMock(spec=Document)

    duplicate_record.id = uuid.uuid4()
    duplicate_record.document_id = uuid.uuid4()
    duplicate_record.supplier_name = "ABC Technologies"
    duplicate_record.invoice_number = "INV-2026-105"
    duplicate_record.invoice_date = date(2026, 11, 12)
    duplicate_record.currency = "USD"
    duplicate_record.total_amount = Decimal("575.00")
    duplicate_record.created_at = date(2026, 11, 13)
    duplicate_record.document = previous_document

    previous_document.original_filename = "previous_invoice.pdf"

    mock_db.scalar.return_value = duplicate_record

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["status"] == "duplicate"
    assert result["is_valid"] is False
    assert result["duplicate_detected"] is True
    assert len(result["warnings"]) == 1

    assert result["duplicate_of"] == {
        "document_id": str(duplicate_record.document_id),
        "filename": "previous_invoice.pdf",
        "supplier_name": "ABC Technologies",
        "invoice_number": "INV-2026-105",
        "invoice_date": "2026-11-12",
        "currency": "USD",
        "total_amount": "575.00",
        "created_at": "2026-11-13",
    }


def test_duplicate_lookup_is_scoped_to_document_owner(
    valid_invoice,
    mock_db,
    valid_document,
):
    mock_db.scalar.return_value = None

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["duplicate_detected"] is False
    assert result["duplicate_of"] is None

    statement = mock_db.scalar.call_args.args[0]
    compiled = statement.compile()

    assert "documents.owner_id" in str(compiled)
    assert valid_document.owner_id in compiled.params.values()


def test_multiple_validation_errors(valid_invoice, mock_db, valid_document):
    valid_invoice.supplier_name = None
    valid_invoice.total_amount = Decimal("600.00")
    valid_invoice.due_date = date(2026, 11, 10)
    mock_db.scalar.return_value = None

    result = validate_invoice(mock_db, valid_invoice, valid_document)

    assert result["status"] == "invalid"
    assert len(result["errors"]) == 3
