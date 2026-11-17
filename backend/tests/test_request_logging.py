import json
import logging
from fastapi.testclient import TestClient

from app.main import app
from app.core.logging import JSONFormatter
from app.core.request_context import (
    request_id_context,
    message_id_context,
    document_id_context,
)

client = TestClient(app)

def test_json_formatter_includes_request_context_and_metadata():
    request_id = "12345678-1234-1234-1234-123456789012"
    message_id = "87654321-4321-4321-4321-210987654321"
    document_id = "11111111-2222-3333-4444-555555555555"

    request_token = request_id_context.set(request_id)
    message_token = message_id_context.set(message_id)
    document_token = document_id_context.set(document_id)

    try:
        record = logging.LogRecord(
            name="app.middleware.request_logging",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request.completed",
            args=(),
            exc_info=None,
        )

        record.method = "GET"
        record.path = "/health"
        record.status_code = 200
        record.duration_ms = 12.5
        record.authorization = "sensitive-value"

        output = JSONFormatter().format(record)
        payload = json.loads(output)

        assert payload["message"] == "request.completed"
        assert payload["request_id"] == request_id
        assert payload["message_id"] == message_id
        assert payload["document_id"] == document_id

        assert payload["level"] == "INFO"
        assert payload["method"] == "GET"
        assert payload["path"] == "/health"
        assert payload["status_code"] == 200
        assert payload["duration_ms"] == 12.5
        assert "timestamp" in payload
        assert "logger" in payload
        assert "authorization" not in payload

    finally:
        document_id_context.reset(document_token)
        message_id_context.reset(message_token)
        request_id_context.reset(request_token)


def test_http_request_emits_structured_completion_log(caplog):
    with caplog.at_level(logging.INFO):
        response = client.get("/health")

    assert response.status_code == 200

    records = [
        record
        for record in caplog.records
        if record.name == "app.middleware.request_logging"
        and record.getMessage() == "request.completed"
    ]

    assert len(records) == 1

    record = records[0]

    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0
    assert response.headers["X-Request-ID"]
    assert len(response.headers["X-Request-ID"]) == 36


def test_json_formatter_omits_empty_background_context():
    record = logging.LogRecord(
        name="app.services.document_processing",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="document.processed",
        args=(),
        exc_info=None,
    )

    output = JSONFormatter().format(record)
    payload = json.loads(output)

    assert payload["request_id"] == "-"
    assert "message_id" not in payload
    assert "document_id" not in payload