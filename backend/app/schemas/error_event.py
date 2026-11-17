import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ErrorEventStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


class ErrorEventListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: str | None
    message_id: str | None
    document_id: str | None
    severity: str
    category: str
    error_type: str
    message: str
    endpoint: str | None
    method: str | None
    status: ErrorEventStatus
    occurred_at: datetime
    resolved_at: datetime | None


class ErrorEventDetail(ErrorEventListItem):
    traceback: str | None


class ErrorEventListResponse(BaseModel):
    items: list[ErrorEventListItem]
    total: int
    limit: int
    offset: int


class ErrorEventStatusUpdate(BaseModel):
    status: ErrorEventStatus


class ErrorEventMetrics(BaseModel):
    total: int
    by_status: dict[str, int]
    by_severity: dict[str, int]
    by_category: dict[str, int]
    last_24_hours: int