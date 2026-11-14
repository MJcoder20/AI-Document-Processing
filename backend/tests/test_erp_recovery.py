
from datetime import datetime, timedelta, timezone
import uuid
from unittest.mock import MagicMock

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.document import Document
from app.models.erp_invoice import ERPInvoice
from app.models.integration_log import IntegrationLog
from app.schemas.integration import IntegrationStatus
from app.services.erp_integration import recover_stale_integrations


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def stale_integration():
    log = MagicMock()
    log.id = uuid.uuid4()
    log.document_id = uuid.uuid4()
    log.status = IntegrationStatus.PROCESSING.value
    log.started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    log.request_payload = {
        "supplier_name": "ABC Technologies",
        "invoice_number": "INV-2026-106",
    }
    return log


@pytest.fixture
def document():
    doc = MagicMock()
    doc.status = "integration_pending"
    return doc

@pytest.fixture
def real_db():
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

def configure_stale_log_query(mock_db, log):
    mock_db.scalars.return_value.all.return_value = [log.id]
    mock_db.scalar.return_value = log


def test_recover_stale_integration_when_erp_invoice_exists(
    mock_db,
    stale_integration,
    document,
    monkeypatch,
):
    configure_stale_log_query(mock_db, stale_integration)
    mock_db.get.return_value = document

    erp_response = {
        "success": True,
        "external_record_id": "ERP-INV-RECOVER123",
        "message": "Invoice successfully created.",
    }

    monkeypatch.setattr(
        "app.services.erp_integration.SimulatedERP.find_invoice",
        lambda self, supplier_name, invoice_number: erp_response,
    )

    result = recover_stale_integrations(mock_db)

    assert result == {
        "checked": 1,
        "recovered": 1,
        "retryable": 0,
        "errors": 0,
    }

    assert stale_integration.status == IntegrationStatus.SUCCESS.value
    assert stale_integration.external_record_id == "ERP-INV-RECOVER123"
    assert stale_integration.response_payload == erp_response
    assert stale_integration.error_message is None
    assert stale_integration.completed_at is not None
    assert document.status == "integrated"
    mock_db.commit.assert_called_once()


def test_recover_stale_integration_when_erp_invoice_does_not_exist(
    mock_db,
    stale_integration,
    document,
    monkeypatch,
):
    configure_stale_log_query(mock_db, stale_integration)
    mock_db.get.return_value = document

    monkeypatch.setattr(
        "app.services.erp_integration.SimulatedERP.find_invoice",
        lambda self, supplier_name, invoice_number: None,
    )

    result = recover_stale_integrations(mock_db)

    assert result == {
        "checked": 1,
        "recovered": 0,
        "retryable": 1,
        "errors": 0,
    }

    assert stale_integration.status == IntegrationStatus.FAILED.value
    assert "no ERP invoice was found" in stale_integration.error_message
    assert stale_integration.completed_at is not None
    assert document.status == "approved"
    mock_db.commit.assert_called_once()


def test_recovery_does_not_process_recent_attempts(mock_db):
    mock_db.scalars.return_value.all.return_value = []

    result = recover_stale_integrations(mock_db)

    assert result == {
        "checked": 0,
        "recovered": 0,
        "retryable": 0,
        "errors": 0,
    }

    mock_db.scalar.assert_not_called()
    mock_db.get.assert_not_called()
    mock_db.commit.assert_not_called()


def test_recovery_rejects_non_positive_threshold(mock_db):
    with pytest.raises(
        ValueError,
        match="stale_after_minutes must be greater than zero",
    ):
        recover_stale_integrations(mock_db, 0)

    with pytest.raises(
        ValueError,
        match="stale_after_minutes must be greater than zero",
    ):
        recover_stale_integrations(mock_db, -5)

    mock_db.scalars.assert_not_called()


def test_real_database_recovers_stale_attempt_without_erp_invoice(real_db):
    document = Document(
        original_filename="invoice.pdf",
        storage_path="documents/invoice.pdf",
        content_type="application/pdf",
        file_size=1024,
        document_type="invoice",
        status="integration_pending",
    )

    real_db.add(document)
    real_db.flush()

    integration_log = IntegrationLog(
        document_id=document.id,
        provider="simulated_erp",
        operation="create_invoice",
        status=IntegrationStatus.PROCESSING.value,
        attempt_number=1,
        request_payload={
            "supplier_name": "ABC Technologies",
            "invoice_number": "INV-2026-106",
        },
        started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )

    real_db.add(integration_log)
    real_db.commit()

    result = recover_stale_integrations(real_db)

    real_db.refresh(integration_log)
    real_db.refresh(document)

    assert result == {
        "checked": 1,
        "recovered": 0,
        "retryable": 1,
        "errors": 0,
    }

    assert integration_log.status == IntegrationStatus.FAILED.value
    assert "no ERP invoice was found" in integration_log.error_message
    assert integration_log.completed_at is not None
    assert document.status == "approved"