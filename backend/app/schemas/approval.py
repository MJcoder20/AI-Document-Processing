import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class DocumentApprovalCreate(BaseModel):
    """Request schema for approving or rejecting a document."""

    decision: ApprovalDecision
    comments: str | None = None


class DocumentApprovalResponse(BaseModel):
    """API response representing a document approval record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    reviewed_by: str | None = None
    decision: ApprovalDecision
    comments: str | None = None
    reviewed_at: datetime
    created_at: datetime