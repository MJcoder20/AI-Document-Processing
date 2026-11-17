
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.document import Document
from app.models.extraction_result import ExtractionResult
from app.schemas.extraction import ExtractedInvoiceData
from app.services.document_processing import (
    DocumentProcessingError,
    process_document,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def mock_ai_extraction(monkeypatch):
    def fake_extract_invoice_data(document_text, tables=None):
        return ExtractedInvoiceData(
            supplier_name="ABC Technologies",
            invoice_number="INV-2026-105",
            invoice_date="2026-11-12",
            due_date="2026-12-12",
            currency="USD",
            subtotal=Decimal("500.00"),
            vat_amount=Decimal("75.00"),
            total_amount=Decimal("575.00"),
            confidence_score=None,
        )

    monkeypatch.setattr(
        "app.services.document_processing.extract_invoice_data",
        fake_extract_invoice_data,
    )


def create_test_document(
    db,
    tmp_path,
    filename="invoice.txt",
    content="Sample invoice",
):
    file_path = tmp_path / filename
    file_path.write_text(content, encoding="utf-8")

    document = Document(
        original_filename=filename,
        storage_path=str(file_path),
        content_type="text/plain",
        file_size=file_path.stat().st_size,
        document_type="unknown",
        status="uploaded",
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def test_process_document_success(db_session, tmp_path):
    document = create_test_document(
        db_session,
        tmp_path,
        content="Supplier: ABC Technologies\nInvoice: INV-2026-105",
    )

    result = process_document(db_session, document.id)

    db_session.refresh(document)

    assert document.status == "pending_review"
    assert document.error_message is None

    assert result.document_id == document.id

    # Verify structured AI extraction.
    assert result.supplier_name == "ABC Technologies"
    assert result.invoice_number == "INV-2026-105"
    assert str(result.invoice_date) == "2026-11-12"
    assert str(result.due_date) == "2026-12-12"
    assert result.currency == "USD"
    assert result.subtotal == Decimal("500.00")
    assert result.vat_amount == Decimal("75.00")
    assert result.total_amount == Decimal("575.00")
    assert result.confidence_score is None

    # Verify original document content is preserved.
    assert "ABC Technologies" in result.extracted_data["text"]
    assert "INV-2026-105" in result.extracted_data["text"]
    assert result.extracted_data["tables"] == []

    # Verify structured AI response is preserved.
    assert result.extracted_data["invoice"]["supplier_name"] == (
        "ABC Technologies"
    )

    assert result.extraction_provider == "ollama"
    assert result.extraction_model == "qwen2.5:7b"

    assert result.extracted_data["validation"]["status"] == "valid"
    assert result.extracted_data["validation"]["is_valid"] is True
    assert result.extracted_data["validation"]["errors"] == []
    assert result.extracted_data["validation"]["duplicate_detected"] is False


def test_process_document_persists_extraction_result(
    db_session,
    tmp_path,
):
    document = create_test_document(db_session, tmp_path)

    result = process_document(db_session, document.id)

    saved_result = db_session.get(ExtractionResult, result.id)

    assert saved_result is not None
    assert saved_result.document_id == document.id
    assert saved_result.supplier_name == "ABC Technologies"
    assert saved_result.invoice_number == "INV-2026-105"


def test_process_missing_document(db_session):
    import uuid

    with pytest.raises(DocumentProcessingError, match="not found"):
        process_document(db_session, uuid.uuid4())


def test_process_document_extraction_failure(db_session, tmp_path):
    document = create_test_document(
        db_session,
        tmp_path,
        filename="invoice.csv",
        content="Unsupported document",
    )

    with pytest.raises(
        DocumentProcessingError,
        match="Could not process",
    ):
        process_document(db_session, document.id)

    db_session.refresh(document)

    assert document.status == "failed"
    assert document.error_message is not None
    assert "Unsupported document format" in document.error_message


@pytest.mark.parametrize(
    "initial_status",
    ["processing", "extracted", "approved", "rejected", "integrated"],
)
def test_process_document_rejects_invalid_status(
    db_session,
    tmp_path,
    initial_status,
):
    document = create_test_document(db_session, tmp_path)

    document.status = initial_status
    db_session.commit()

    with pytest.raises(DocumentProcessingError):
        process_document(db_session, document.id)

    db_session.refresh(document)

    assert document.status == initial_status
    assert db_session.query(ExtractionResult).count() == 0


def test_process_failed_document_can_be_retried(
    db_session,
    tmp_path,
):
    document = create_test_document(db_session, tmp_path)

    document.status = "failed"
    document.error_message = "Previous processing failure"
    db_session.commit()

    result = process_document(db_session, document.id)

    db_session.refresh(document)

    assert document.status == "pending_review"
    assert document.error_message is None
    assert result.document_id == document.id
    assert result.supplier_name == "ABC Technologies"


def test_process_document_records_mock_provider_metadata(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.document_processing.settings.ai_provider",
        "mock",
    )

    document = create_test_document(
        db_session,
        tmp_path,
    )

    result = process_document(db_session, document.id)

    assert result.extraction_provider == "mock"
    assert result.extraction_model == "mock-regex-v1"