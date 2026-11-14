
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
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
