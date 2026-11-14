import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.approval import (
    ApprovalDecision,
    DocumentApprovalCreate,
    DocumentApprovalResponse,
)


def test_approved_decision():
    approval = DocumentApprovalCreate(
        reviewed_by="Finance Manager",
        decision=ApprovalDecision.APPROVED,
        comments="Invoice details verified.",
    )

    assert approval.decision == ApprovalDecision.APPROVED
    assert approval.reviewed_by == "Finance Manager"


def test_rejected_decision():
    approval = DocumentApprovalCreate(
        reviewed_by="Finance Manager",
        decision=ApprovalDecision.REJECTED,
        comments="Incorrect invoice total.",
    )

    assert approval.decision == ApprovalDecision.REJECTED


def test_approval_rejects_invalid_decision():
    with pytest.raises(ValidationError):
        DocumentApprovalCreate(
            reviewed_by="Finance Manager",
            decision="pending",
        )


def test_approval_requires_reviewer():
    with pytest.raises(ValidationError):
        DocumentApprovalCreate(
            reviewed_by="",
            decision=ApprovalDecision.APPROVED,
        )


def test_approval_requires_decision():
    with pytest.raises(ValidationError):
        DocumentApprovalCreate(
            reviewed_by="Finance Manager",
        )


def test_approval_comments_are_optional():
    approval = DocumentApprovalCreate(
        reviewed_by="Finance Manager",
        decision=ApprovalDecision.APPROVED,
    )

    assert approval.comments is None


def test_approval_response_valid_data():
    now = datetime.now(timezone.utc)

    approval = DocumentApprovalResponse(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        reviewed_by="Finance Manager",
        decision=ApprovalDecision.APPROVED,
        comments="Verified.",
        reviewed_at=now,
        created_at=now,
    )

    assert approval.decision == ApprovalDecision.APPROVED
    assert approval.comments == "Verified."