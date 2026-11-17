
from unittest.mock import MagicMock, patch
import uuid

from app.core.request_context import (
    request_id_context,
    message_id_context,
    document_id_context,
)
from app.models.error_event import ErrorEvent
from app.services.error_tracking import (
    record_error_event,
    sanitize_error_text,
)


def test_sanitize_password_and_api_key():
    value = "password=example123 api_key=secret456"

    result = sanitize_error_text(value)

    assert "example123" not in result
    assert "secret456" not in result
    assert result.count("[REDACTED]") == 2


def test_sanitize_url_credentials():
    value = "Connection failed: postgresql://admin:secret123@localhost:5432/db"

    result = sanitize_error_text(value)

    assert "secret123" not in result
    assert "admin:secret123" not in result
    assert "[REDACTED]" in result


def test_sanitize_query_string_tokens():
    value = "https://example.com?access_token=abc123&password=secret"

    result = sanitize_error_text(value)

    assert "abc123" not in result
    assert "secret" not in result
    assert "[REDACTED]" in result


def test_record_error_event_persists_event_and_context():
    db = MagicMock()
    request_id = str(uuid.uuid4())
    db.refresh.side_effect = lambda event: setattr(
        event,
        "id",
        uuid.uuid4(),
    )
    message_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())

    request_token = request_id_context.set(request_id)
    message_token = message_id_context.set(message_id)
    document_token = document_id_context.set(document_id)

    try:
        with patch(
            "app.services.error_tracking.SessionLocal",
            return_value=db,
        ):
            error_id = record_error_event(
                ValueError("Invalid document"),
                category="document_processing",
                severity="error",
                endpoint="/api/v1/documents",
                method="POST",
            )

        assert isinstance(error_id, uuid.UUID)

        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()

        event = db.add.call_args.args[0]

        assert isinstance(event, ErrorEvent)
        assert event.request_id == request_id
        assert event.message_id == message_id
        assert event.document_id == document_id
        assert event.error_type == "ValueError"
        assert event.message == "Invalid document"
        assert event.category == "document_processing"
        assert event.severity == "error"
        assert event.endpoint == "/api/v1/documents"
        assert event.method == "POST"
        assert event.status == "open"
        assert event.traceback is not None

        db.close.assert_called_once()

    finally:
        document_id_context.reset(document_token)
        message_id_context.reset(message_token)
        request_id_context.reset(request_token)


def test_record_error_event_handles_database_failure():
    db = MagicMock()
    db.commit.side_effect = RuntimeError("Database unavailable")

    with patch(
        "app.services.error_tracking.SessionLocal",
        return_value=db,
    ):
        error_id = record_error_event(
            RuntimeError("Original application error")
        )

    assert error_id is None
    db.add.assert_called_once()
    db.rollback.assert_called_once()
    db.close.assert_called_once()


def test_record_error_event_handles_session_creation_failure():
    with patch(
        "app.services.error_tracking.SessionLocal",
        side_effect=RuntimeError("Database session unavailable"),
    ):
        error_id = record_error_event(
            RuntimeError("Original application error")
        )

    assert error_id is None

def test_record_error_event_handles_session_close_failure():
    db = MagicMock()
    db.close.side_effect = RuntimeError("Session close failed")

    db.refresh.side_effect = lambda event: setattr(
        event,
        "id",
        uuid.uuid4(),
    )

    with patch(
        "app.services.error_tracking.SessionLocal",
        return_value=db,
    ):
        error_id = record_error_event(
            RuntimeError("Original application error")
        )

    assert isinstance(error_id, uuid.UUID)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    db.close.assert_called_once()

def test_record_error_event_does_not_log_session_creation_details(caplog):
    sensitive_message = "password=SuperSecret123"

    with patch(
        "app.services.error_tracking.SessionLocal",
        side_effect=RuntimeError(sensitive_message),
    ):
        error_id = record_error_event(
            RuntimeError("Original application error")
        )

    assert error_id is None
    assert "SuperSecret123" not in caplog.text
    assert "error_event.record_failed" in caplog.text


