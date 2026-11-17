
import logging
import re
import traceback
import uuid

from app.core.request_context import (
    get_document_id,
    get_message_id,
    get_request_id,
)
from app.db.session import SessionLocal
from app.models.error_event import ErrorEvent

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000
MAX_TRACEBACK_LENGTH = 20000

SENSITIVE_PATTERNS = [
    (
        re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)"
            r"(\s*[:=]\s*)[\"']?[^\"'\s,;&}]+"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)([?&](?:access_token|refresh_token|token|api_key|password)=)"
            r"[^&#\s]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"://[^:/@\s]+:[^@\s]+@"),
        "://[REDACTED]@",
    ),
]


def sanitize_error_text(value: str) -> str:
    """Remove common credential patterns from error text."""

    sanitized = value

    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def record_error_event(
    exc: Exception,
    *,
    category: str = "application",
    severity: str = "error",
    endpoint: str | None = None,
    method: str | None = None,
) -> uuid.UUID | None:
    """
    Persist an application error independently of the current DB session.

    Tracking failures must never replace the original application exception.
    """
    db = None

    try:
        db = SessionLocal()

        error_message = sanitize_error_text(str(exc))
        formatted_traceback = "".join(
            traceback.format_exception(
                type(exc),
                exc,
                exc.__traceback__,
            )
        )

        event = ErrorEvent(
            request_id=get_request_id() or None,
            message_id=get_message_id() or None,
            document_id=get_document_id() or None,
            severity=severity,
            category=category,
            error_type=type(exc).__name__,
            message=error_message[:MAX_MESSAGE_LENGTH],
            endpoint=endpoint,
            method=method,
            traceback=sanitize_error_text(
                formatted_traceback
            )[:MAX_TRACEBACK_LENGTH],
            status="open",
        )

        # Context variables use "-" when no context is available.
        if event.request_id == "-":
            event.request_id = None

        if event.message_id == "-":
            event.message_id = None

        if event.document_id == "-":
            event.document_id = None

        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(
            "error_event.recorded",
            extra={
                "error_event_id": str(event.id),
                "error_type": event.error_type,
                "category": event.category,
            },
        )

        return event.id

    except Exception as tracking_exc:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass

        # Do not log the raw exception or traceback here: they may contain
        # credentials or other sensitive information.
        logger.error(
            "error_event.record_failed",
            extra={"tracking_error_type": type(tracking_exc).__name__},
        )
        return None

    finally:
        if db is not None:
            try:
                db.close()
            except Exception as close_exc:
                # Closing the tracking session must not mask the original error.
                logger.error(
                    "error_event.session_close_failed",
                    extra={"tracking_error_type": type(close_exc).__name__},
                )
