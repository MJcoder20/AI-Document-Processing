
import uuid
from unittest.mock import MagicMock

import pytest

from app.schemas.approval import ApprovalDecision
from app.services.document_approval import (
    DocumentApprovalError,
    review_document,
)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def pending_document():
    document = MagicMock()
    document.id = uuid.uuid4()
    document.status = "pending_review"
    return document


@pytest.fixture
def valid_extraction():
    extraction = MagicMock()
    extraction.extracted_data = {
        "validation": {
            "status": "valid",
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "duplicate_detected": False,
        }
    }
    return extraction


def test_approve_valid_document(
    mock_db, pending_document, valid_extraction
):
    mock_db.scalar.side_effect = [
        pending_document,
        valid_extraction,
    ]

    result = review_document(
        db=mock_db,
        document_id=pending_document.id,
        reviewed_by="Reviewer",
        decision=ApprovalDecision.APPROVED,
        comments="Verified invoice.",
    )

    assert pending_document.status == "approved"
    assert result.decision == "approved"
    assert result.reviewed_by == "Reviewer"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_reject_document(mock_db, pending_document):
    mock_db.scalar.return_value = pending_document

    result = review_document(
        db=mock_db,
        document_id=pending_document.id,
        reviewed_by="Reviewer",
        decision=ApprovalDecision.REJECTED,
        comments="Incorrect invoice details.",
    )

    assert pending_document.status == "rejected"
    assert result.decision == "rejected"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_cannot_approve_invalid_invoice(
    mock_db, pending_document
):
    invalid_extraction = MagicMock()
    invalid_extraction.extracted_data = {
        "validation": {
            "status": "invalid",
            "is_valid": False,
            "errors": ["Total amount mismatch."],
            "warnings": [],
            "duplicate_detected": False,
        }
    }

    mock_db.scalar.side_effect = [
        pending_document,
        invalid_extraction,
    ]

    with pytest.raises(
        DocumentApprovalError,
        match="Cannot approve an invoice",
    ):
        review_document(
            db=mock_db,
            document_id=pending_document.id,
            reviewed_by="Reviewer",
            decision=ApprovalDecision.APPROVED,
        )

    mock_db.commit.assert_not_called()
    mock_db.add.assert_not_called()


def test_cannot_approve_duplicate_invoice(
    mock_db, pending_document
):
    duplicate_extraction = MagicMock()
    duplicate_extraction.extracted_data = {
        "validation": {
            "status": "duplicate",
            "is_valid": False,
            "errors": [],
            "warnings": ["Duplicate invoice detected."],
            "duplicate_detected": True,
        }
    }

    mock_db.scalar.side_effect = [
        pending_document,
        duplicate_extraction,
    ]

    with pytest.raises(DocumentApprovalError):
        review_document(
            db=mock_db,
            document_id=pending_document.id,
            reviewed_by="Reviewer",
            decision=ApprovalDecision.APPROVED,
        )

    mock_db.commit.assert_not_called()


def test_cannot_review_non_pending_document(mock_db):
    document = MagicMock()
    document.status = "approved"
    mock_db.scalar.return_value = document

    with pytest.raises(
        DocumentApprovalError,
        match="cannot be reviewed",
    ):
        review_document(
            db=mock_db,
            document_id=document.id,
            reviewed_by="Reviewer",
            decision=ApprovalDecision.REJECTED,
        )

    mock_db.commit.assert_not_called()


def test_document_not_found(mock_db):
    mock_db.scalar.return_value = None

    with pytest.raises(
        DocumentApprovalError,
        match="Document not found",
    ):
        review_document(
            db=mock_db,
            document_id=uuid.uuid4(),
            reviewed_by="Reviewer",
            decision=ApprovalDecision.REJECTED,
        )

    mock_db.commit.assert_not_called()
