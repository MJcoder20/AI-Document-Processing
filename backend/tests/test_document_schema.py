import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.document import (
    DocumentResponse,
    DocumentStatus,
    DocumentType,
)

def test_document_response_valid_data():
    now = datetime.now(timezone.utc)

    document = DocumentResponse(
        id=uuid.uuid4(),
        original_filename="invoice.pdf",
        content_type="application/pdf",
        file_size=1024,
        document_type=DocumentType.INVOICE,
        status=DocumentStatus.UPLOADED,
        error_message=None,
        created_at=now,
        updated_at=now,
    )

    assert document.original_filename == "invoice.pdf"
    assert document.document_type == DocumentType.INVOICE
    assert document.status == DocumentStatus.UPLOADED


def test_document_response_rejects_negative_file_size():
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        DocumentResponse(
            id=uuid.uuid4(),
            original_filename="invoice.pdf",
            content_type="application/pdf",
            file_size=-1,
            document_type=DocumentType.INVOICE,
            status=DocumentStatus.UPLOADED,
            created_at=now,
            updated_at=now,
        )


def test_document_type_rejects_unsupported_value():
    with pytest.raises(ValueError):
        DocumentType("spreadsheet")


def test_document_status_rejects_unsupported_value():
    with pytest.raises(ValueError):
        DocumentStatus("unknown_status")