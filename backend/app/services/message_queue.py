
import json
from uuid import UUID

from azure.servicebus import ServiceBusClient, ServiceBusMessage

from app.core.config import settings
from app.models.outbox_message import OutboxMessage


class MessageQueueError(Exception):
    """Raised when a document-processing message cannot be queued."""


def enqueue_document_processing(document_id: UUID) -> None:
    """
    Send a document-processing message to Azure Service Bus.
    """

    connection_string = settings.service_bus_connection_string

    if connection_string is None:
        raise MessageQueueError(
            "Azure Service Bus connection string is not configured."
        )

    payload = {
        "message_type": "process_document",
        "document_id": str(document_id),
        "version": 1,
    }

    try:
        with ServiceBusClient.from_connection_string(
            connection_string.get_secret_value()
        ) as client:
            with client.get_queue_sender(
                queue_name=settings.service_bus_queue_name
            ) as sender:
                message = ServiceBusMessage(
                    json.dumps(payload),
                    content_type="application/json",
                    subject="process_document",
                )
                sender.send_messages(message)

    except Exception as exc:
        raise MessageQueueError(
            f"Failed to enqueue document {document_id}: {exc}"
        ) from exc


def publish_outbox_message(message: OutboxMessage) -> None:
    """Publish an existing outbox message to Azure Service Bus."""

    connection_string = settings.service_bus_connection_string

    if connection_string is None:
        raise MessageQueueError(
            "Azure Service Bus connection string is not configured."
        )

    try:
        with ServiceBusClient.from_connection_string(
            connection_string.get_secret_value()
        ) as client:
            with client.get_queue_sender(
                queue_name=settings.service_bus_queue_name
            ) as sender:
                service_bus_message = ServiceBusMessage(
                    json.dumps(message.payload),
                    content_type="application/json",
                    subject=message.message_type,
                    message_id=str(message.id),
                )

                sender.send_messages(service_bus_message)

    except Exception as exc:
        raise MessageQueueError(
            f"Failed to publish outbox message {message.id}: {exc}"
        ) from exc