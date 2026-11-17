from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.request_context import (
    document_id_context,
    message_id_context,
    request_id_context,
)
from app.db.base import Base
from app.models.outbox_message import OutboxMessage
from app.services import outbox_dispatcher


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


@pytest.fixture
def pending_message(db_session):
    message = OutboxMessage(
        id=uuid4(),
        document_id=uuid4(),
        message_type="process_document",
        payload={"message_type": "process_document"},
        status="pending",
        attempt_count=0,
    )

    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)

    return message


def test_dispatch_success(db_session, pending_message, monkeypatch):
    def fake_publish(message):
        assert message.id == pending_message.id

    monkeypatch.setattr(
        outbox_dispatcher,
        "publish_outbox_message",
        fake_publish,
    )

    results = outbox_dispatcher.dispatch_pending_outbox_messages(
        db_session
    )

    db_session.refresh(pending_message)

    assert results == {"published": 1, "failed": 0}
    assert pending_message.status == "published"
    assert pending_message.attempt_count == 1
    assert pending_message.published_at is not None
    assert pending_message.next_attempt_at is None
    assert pending_message.error_message is None


def test_dispatch_failure_schedules_retry(
    db_session,
    pending_message,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "service_bus_max_delivery_count",
        5,
    )

    def fake_publish(message):
        raise outbox_dispatcher.MessageQueueError(
            "Service Bus unavailable"
        )

    monkeypatch.setattr(
        outbox_dispatcher,
        "publish_outbox_message",
        fake_publish,
    )

    before = datetime.now(timezone.utc)

    results = outbox_dispatcher.dispatch_pending_outbox_messages(
        db_session
    )

    db_session.refresh(pending_message)

    assert results == {"published": 0, "failed": 0}
    assert pending_message.status == "pending"
    assert pending_message.attempt_count == 1
    assert pending_message.error_message == "Service Bus unavailable"
    assert pending_message.next_attempt_at is not None
    retry_time = pending_message.next_attempt_at

    if retry_time.tzinfo is None:
        retry_time = retry_time.replace(tzinfo=timezone.utc)

    assert retry_time >= before


def test_dispatch_failure_reaches_max_attempts(
    db_session,
    pending_message,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "service_bus_max_delivery_count",
        1,
    )

    def fake_publish(message):
        raise outbox_dispatcher.MessageQueueError(
            "Service Bus unavailable"
        )

    monkeypatch.setattr(
        outbox_dispatcher,
        "publish_outbox_message",
        fake_publish,
    )

    results = outbox_dispatcher.dispatch_pending_outbox_messages(
        db_session
    )

    db_session.refresh(pending_message)

    assert results == {"published": 0, "failed": 1}
    assert pending_message.status == "failed"
    assert pending_message.attempt_count == 1
    assert pending_message.next_attempt_at is None



def test_dispatch_failure_records_integration_error(
    db_session,
    pending_message,
    monkeypatch,
):
    request_id = str(uuid4())

    pending_message.payload = {
        "request_id": request_id,
    }
    db_session.commit()

    captured = {}

    def fake_publish(message):
        raise outbox_dispatcher.MessageQueueError(
            "Service Bus tracking test failure"
        )

    def fake_record_error_event(exc, **kwargs):
        captured["exception"] = exc
        captured["kwargs"] = kwargs
        captured["request_id"] = request_id_context.get()
        captured["message_id"] = message_id_context.get()
        captured["document_id"] = document_id_context.get()

    monkeypatch.setattr(
        outbox_dispatcher,
        "publish_outbox_message",
        fake_publish,
    )
    monkeypatch.setattr(
        outbox_dispatcher,
        "record_error_event",
        fake_record_error_event,
    )

    results = outbox_dispatcher.dispatch_pending_outbox_messages(
        db_session
    )

    assert isinstance(
        captured["exception"],
        outbox_dispatcher.MessageQueueError,
    )

    assert captured["kwargs"]["category"] == "integration"
    assert captured["kwargs"]["severity"] == "error"
    assert captured["kwargs"]["endpoint"] == "outbox_dispatcher"
    assert captured["kwargs"]["method"] == "WORKER"

    assert captured["request_id"] == request_id
    assert captured["message_id"] == str(pending_message.id)
    assert captured["document_id"] == str(pending_message.document_id)

    assert results == {"published": 0, "failed": 0}

    db_session.refresh(pending_message)
    assert pending_message.status == "pending"
    assert pending_message.attempt_count == 1
    assert pending_message.next_attempt_at is not None

    assert request_id_context.get() == "-"
    assert message_id_context.get() == "-"
    assert document_id_context.get() == "-"
