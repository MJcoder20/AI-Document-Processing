from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models.document import Document
from app.models.extraction_result import ExtractionResult
from app.models.outbox_message import OutboxMessage
from app.repositories.outbox import (
    claim_next_outbox_message,
    complete_outbox_claim,
    fail_outbox_claim,
    recover_expired_outbox_messages,
)
from app.services import local_outbox_processor

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

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


def create_document(db, *, status="uploaded"):
    document = Document(
        original_filename="invoice.txt",
        storage_path="storage/invoice.txt",
        content_type="text/plain",
        file_size=100,
        document_type="invoice",
        status=status,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def create_message(db, document, *, status="pending", attempt_count=0):
    message = OutboxMessage(
        document_id=document.id,
        message_type="process_document",
        payload={"document_id": str(document.id)},
        status=status,
        attempt_count=attempt_count,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def create_extraction(db, document):
    extraction = ExtractionResult(
        document_id=document.id,
        supplier_name="ABC Technologies",
        invoice_number="INV-2026-105",
        extracted_data={"invoice": {"supplier_name": "ABC Technologies"}},
        extraction_provider="ollama",
        extraction_model="qwen2.5:7b",
    )

    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    return extraction


def test_claim_message_exclusively(db_session):
    document = create_document(db_session)
    message = create_message(db_session, document)

    first_claim = claim_next_outbox_message(db_session)
    second_claim = claim_next_outbox_message(db_session)

    assert first_claim is not None
    assert first_claim[0] == message.id
    assert first_claim[1]
    assert second_claim is None

    db_session.refresh(message)

    assert message.status == "processing"
    assert message.attempt_count == 1
    assert message.lock_token == first_claim[1]
    assert message.locked_at is not None


def test_local_worker_processes_message(
    db_session,
    monkeypatch,
):
    document = create_document(db_session)
    message = create_message(db_session, document)

    def fake_process_document(db, document_id, *, from_queue=False):
        assert document_id == document.id
        assert from_queue is True

        saved_document = db.get(Document, document_id)
        saved_document.status = "pending_review"
        db.add(
            ExtractionResult(
                document_id=document_id,
                supplier_name="ABC Technologies",
                invoice_number="INV-2026-105",
                extracted_data={},
                extraction_provider="ollama",
                extraction_model="qwen2.5:7b",
            )
        )
        db.commit()

    monkeypatch.setattr(
        local_outbox_processor,
        "process_document",
        fake_process_document,
    )

    print("Document status:", document.status)
    print("Document ID:", document.id)

    extraction = db_session.scalar(
        select(ExtractionResult.id).where(
            ExtractionResult.document_id == document.id
        )
    )
    print("Extraction found:", extraction)

    print(
        "Helper result:",
        local_outbox_processor._document_was_already_processed(
            db_session,
            document.id,
        ),
    )

    results = local_outbox_processor.process_pending_outbox_messages(
        db_session
    )

    db_session.refresh(message)

    print("Outbox status:", message.status)
    print("Outbox error:", message.error_message)
    print("Attempt count:", message.attempt_count)
    print("Lock token:", message.lock_token)

    assert results == {
        "processed": 1,
        "retried": 0,
        "failed": 0,
    }
    assert message.status == "processed"
    assert message.attempt_count == 1
    assert message.lock_token is None
    assert message.locked_at is None
    assert message.error_message is None


def test_local_worker_retries_failed_message(
    db_session,
    monkeypatch,
):
    document = create_document(db_session)
    message = create_message(db_session, document)

    monkeypatch.setattr(
        settings,
        "service_bus_max_delivery_count",
        5,
    )

    def fake_process_document(*args, **kwargs):
        raise RuntimeError("Temporary extraction failure")

    monkeypatch.setattr(
        local_outbox_processor,
        "process_document",
        fake_process_document,
    )

    results = local_outbox_processor.process_pending_outbox_messages(
        db_session
    )

    db_session.refresh(message)

    assert results == {
        "processed": 0,
        "retried": 1,
        "failed": 0,
    }
    assert message.status == "pending"
    assert message.attempt_count == 1
    assert message.error_message == "Temporary extraction failure"
    assert message.next_attempt_at is not None
    assert message.lock_token is None


def test_local_worker_fails_after_max_attempts(
    db_session,
    monkeypatch,
):
    document = create_document(db_session)
    message = create_message(db_session, document)

    monkeypatch.setattr(
        settings,
        "service_bus_max_delivery_count",
        1,
    )

    def fake_process_document(*args, **kwargs):
        raise RuntimeError("Permanent extraction failure")

    monkeypatch.setattr(
        local_outbox_processor,
        "process_document",
        fake_process_document,
    )

    results = local_outbox_processor.process_pending_outbox_messages(
        db_session
    )

    db_session.refresh(message)

    assert results == {
        "processed": 0,
        "retried": 0,
        "failed": 1,
    }
    assert message.status == "failed"
    assert message.attempt_count == 1
    assert message.next_attempt_at is None
    assert message.lock_token is None


def test_worker_recovers_already_processed_document(
    db_session,
    monkeypatch,
):
    document = create_document(
        db_session,
        status="pending_review",
    )
    create_extraction(db_session, document)
    message = create_message(db_session, document)

    print("Document status:", document.status)
    print("Document ID:", document.id)

    extraction = db_session.scalar(
        select(ExtractionResult.id).where(
            ExtractionResult.document_id == document.id
        )
    )
    print("Extraction found:", extraction)

    print(
        "Helper result:",
        local_outbox_processor._document_was_already_processed(
            db_session,
            document.id,
        ),
    )

    def unexpected_processing(*args, **kwargs):
        pytest.fail(
            "Already processed document should not be processed again"
        )

    monkeypatch.setattr(
        local_outbox_processor,
        "process_document",
        unexpected_processing,
    )

    results = local_outbox_processor.process_pending_outbox_messages(
        db_session
    )

    db_session.refresh(message)

    print("Outbox status:", message.status)
    print("Outbox error:", message.error_message)
    print("Attempt count:", message.attempt_count)
    print("Lock token:", message.lock_token)

    assert results == {
        "processed": 1,
        "retried": 0,
        "failed": 0,
    }
    assert message.status == "processed"


def test_expired_lease_is_recovered(db_session, monkeypatch):
    monkeypatch.setattr(
        settings,
        "local_worker_lease_seconds",
        300,
    )

    document = create_document(db_session)
    message = create_message(
        db_session,
        document,
        status="processing",
        attempt_count=1,
    )

    message.locked_at = datetime.now(timezone.utc) - timedelta(
        seconds=600
    )
    message.lock_token = str(uuid4())
    db_session.commit()

    recovered = recover_expired_outbox_messages(db_session)

    db_session.refresh(message)

    assert recovered == 1
    assert message.status == "pending"
    assert message.lock_token is None
    assert message.locked_at is None
    assert message.next_attempt_at is not None


def test_stale_worker_cannot_complete_claim(db_session):
    document = create_document(db_session)
    message = create_message(db_session, document)

    claim = claim_next_outbox_message(db_session)

    assert claim is not None

    message_id, original_token = claim

    message.lock_token = str(uuid4())
    db_session.commit()

    completed = complete_outbox_claim(
        db_session,
        message_id=message_id,
        lock_token=original_token,
    )

    db_session.refresh(message)

    assert completed is False
    assert message.status == "processing"


def test_expired_worker_cannot_fail_or_retry_claim(db_session):
    document = create_document(db_session)
    message = create_message(db_session, document)

    claim = claim_next_outbox_message(db_session)

    assert claim is not None
    message_id, lock_token = claim

    db_session.refresh(message)

    # Simulate a worker whose lease has expired.
    message.locked_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=settings.local_worker_lease_seconds + 10)
    )
    db_session.commit()

    outcome = fail_outbox_claim(
        db_session,
        message_id=message_id,
        lock_token=lock_token,
        error_message="Simulated processing failure",
    )

    db_session.refresh(message)

    assert outcome is None
    assert message.status == "processing"
    assert message.lock_token == lock_token