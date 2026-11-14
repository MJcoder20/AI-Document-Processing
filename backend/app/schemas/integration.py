import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntegrationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class IntegrationLogCreate(BaseModel):
    """Request schema for initiating an ERP integration."""

    provider: str = Field(default="simulated_erp", min_length=1, max_length=100)
    operation: str = Field(default="create_invoice", min_length=1, max_length=100)
    request_payload: dict[str, Any] | None = None


class IntegrationLogResponse(BaseModel):
    """API response representing an ERP integration attempt."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID

    provider: str
    operation: str
    status: IntegrationStatus

    external_record_id: str | None = None
    attempt_number: int = Field(ge=1)

    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None

    error_message: str | None = None

    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime