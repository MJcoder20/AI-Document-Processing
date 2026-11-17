import json
import logging
from datetime import datetime, timezone

from app.core.request_context import get_document_id, get_message_id, get_request_id


class JSONFormatter(logging.Formatter):
    SAFE_EXTRA_FIELDS = (
        "method",
        "path",
        "status_code",
        "duration_ms",
    )

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        for field in self.SAFE_EXTRA_FIELDS:
            if hasattr(record, field):
                log_data[field] = getattr(record, field)

        context_fields = {
            "message_id": get_message_id(),
            "document_id": get_document_id(),
        }

        for field, value in context_fields.items():
            if value != "-":
                log_data[field] = value

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)