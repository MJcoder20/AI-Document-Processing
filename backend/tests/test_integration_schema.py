import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.integration import (
    IntegrationLogCreate,
    IntegrationLogResponse,
    IntegrationStatus,
)


def test_integration_log_create_defaults():
    integration = IntegrationLogCreate()

    assert integration.provider == "simulated_erp"
    assert integration.operation == "create_invoice"
    assert integration.request_payload is None


def test_integration_log_create_custom_values():
    integration = IntegrationLogCreate(
        provider="business_central",
        operation="create_invoice",
        request_payload={"invoice_number": "INV-001"},
    )

    assert integration.provider == "business_central"
    assert integration.request_payload["invoice_number"] == "INV-001"


@pytest.mark.parametrize(
    "status",
    [
        IntegrationStatus.PENDING,
        IntegrationStatus.PROCESSING,
        IntegrationStatus.SUCCESS,
        IntegrationStatus.FAILED,
    ],
)
def test_supported_integration_statuses(status):
    assert IntegrationStatus(status.value) == status


def test_integration_rejects_invalid_status():
    with pytest.raises(ValueError):
        IntegrationStatus("unknown")


def test_integration_log_response_valid_data():
    now = datetime.now(timezone.utc)

    integration = IntegrationLogResponse(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        provider="simulated_erp",
        operation="create_invoice",
        status=IntegrationStatus.SUCCESS,
        external_record_id="ERP-INV-001",
        attempt_number=1,
        request_payload={"invoice_number": "INV-001"},
        response_payload={"message": "Invoice created"},
        started_at=now,
        completed_at=now,
        created_at=now,
    )

    assert integration.status == IntegrationStatus.SUCCESS
    assert integration.external_record_id == "ERP-INV-001"


def test_integration_rejects_zero_attempt_number():
    with pytest.raises(ValidationError):
        IntegrationLogResponse(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            provider="simulated_erp",
            operation="create_invoice",
            status=IntegrationStatus.FAILED,
            attempt_number=0,
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )


def test_integration_response_allows_optional_fields():
    now = datetime.now(timezone.utc)

    integration = IntegrationLogResponse(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        provider="simulated_erp",
        operation="create_invoice",
        status=IntegrationStatus.PENDING,
        attempt_number=1,
        started_at=now,
        created_at=now,
    )

    assert integration.external_record_id is None
    assert integration.response_payload is None
    assert integration.completed_at is None
    assert integration.error_message is None