import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services import message_queue
from app.models.outbox_message import OutboxMessage
from app.services.message_queue import (
    MessageQueueError,
    enqueue_document_processing,
    publish_outbox_message,
)

def test_enqueue_document_processing_success(monkeypatch):
    document_id = uuid4()

    client = MagicMock()
    sender = MagicMock()

    client_context = MagicMock()
    client_context.__enter__.return_value = client

    sender_context = MagicMock()
    sender_context.__enter__.return_value = sender

    client.get_queue_sender.return_value = sender_context

    factory = MagicMock(return_value=client_context)
    monkeypatch.setattr(
        message_queue.ServiceBusClient,
        "from_connection_string",
        factory,
    )

    created_messages = []

    def create_message(body, **kwargs):
        created_messages.append((body, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        message_queue,
        "ServiceBusMessage",
        create_message,
    )

    monkeypatch.setattr(
        settings,
        "service_bus_connection_string",
        SecretStr("test-connection-string"),
    )

    monkeypatch.setattr(
        settings,
        "service_bus_queue_name",
        "test-queue",
    )

    enqueue_document_processing(document_id)

    factory.assert_called_once_with("test-connection-string")
    client.get_queue_sender.assert_called_once_with(
        queue_name="test-queue"
    )
    sender.send_messages.assert_called_once()

    body, kwargs = created_messages[0]
    payload = json.loads(body)

    assert payload["message_type"] == "process_document"
    assert payload["document_id"] == str(document_id)
    assert payload["version"] == 1
    assert kwargs["content_type"] == "application/json"
    assert kwargs["subject"] == "process_document"


def test_enqueue_document_processing_without_connection_string(monkeypatch):
    monkeypatch.setattr(
        settings,
        "service_bus_connection_string",
        None,
    )

    with pytest.raises(
        MessageQueueError,
        match="connection string is not configured",
    ):
        enqueue_document_processing(uuid4())


def test_enqueue_document_processing_service_bus_failure(monkeypatch):
    monkeypatch.setattr(
        settings,
        "service_bus_connection_string",
        SecretStr("test-connection-string"),
    )

    def raise_connection_error(*args, **kwargs):
        raise RuntimeError("Connection failed")

    monkeypatch.setattr(
        message_queue.ServiceBusClient,
        "from_connection_string",
        raise_connection_error,
    )

    with pytest.raises(
        MessageQueueError,
        match="Connection failed",
    ):
        enqueue_document_processing(uuid4())


def test_publish_outbox_message_success(monkeypatch):
    message_id = uuid4()
    document_id = uuid4()

    outbox_message = OutboxMessage(
        id=message_id,
        document_id=document_id,
        message_type="process_document",
        payload={
            "message_type": "process_document",
            "document_id": str(document_id),
            "version": 1,
        },
        status="pending",
    )

    client = MagicMock()
    sender = MagicMock()

    client_context = MagicMock()
    client_context.__enter__.return_value = client

    sender_context = MagicMock()
    sender_context.__enter__.return_value = sender

    client.get_queue_sender.return_value = sender_context

    factory = MagicMock(return_value=client_context)
    monkeypatch.setattr(
        message_queue.ServiceBusClient,
        "from_connection_string",
        factory,
    )

    created_messages = []

    def create_message(body, **kwargs):
        created_messages.append((body, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        message_queue,
        "ServiceBusMessage",
        create_message,
    )

    monkeypatch.setattr(
        settings,
        "service_bus_connection_string",
        SecretStr("test-connection-string"),
    )

    monkeypatch.setattr(
        settings,
        "service_bus_queue_name",
        "test-queue",
    )

    publish_outbox_message(outbox_message)

    factory.assert_called_once_with("test-connection-string")
    client.get_queue_sender.assert_called_once_with(
        queue_name="test-queue"
    )
    sender.send_messages.assert_called_once()

    body, kwargs = created_messages[0]
    assert json.loads(body) == outbox_message.payload
    assert kwargs["content_type"] == "application/json"
    assert kwargs["subject"] == "process_document"
    assert kwargs["message_id"] == str(message_id)


def test_publish_outbox_message_without_connection_string(monkeypatch):
    monkeypatch.setattr(
        settings,
        "service_bus_connection_string",
        None,
    )

    outbox_message = OutboxMessage(
        id=uuid4(),
        document_id=uuid4(),
        message_type="process_document",
        payload={"message_type": "process_document"},
        status="pending",
    )

    with pytest.raises(
        MessageQueueError,
        match="connection string is not configured",
    ):
        publish_outbox_message(outbox_message)


def test_publish_outbox_message_service_bus_failure(monkeypatch):
    monkeypatch.setattr(
        settings,
        "service_bus_connection_string",
        SecretStr("test-connection-string"),
    )

    def raise_connection_error(*args, **kwargs):
        raise RuntimeError("Connection failed")

    monkeypatch.setattr(
        message_queue.ServiceBusClient,
        "from_connection_string",
        raise_connection_error,
    )

    outbox_message = OutboxMessage(
        id=uuid4(),
        document_id=uuid4(),
        message_type="process_document",
        payload={"message_type": "process_document"},
        status="pending",
    )

    with pytest.raises(
        MessageQueueError,
        match="Connection failed",
    ):
        publish_outbox_message(outbox_message)

