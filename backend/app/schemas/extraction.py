import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractedInvoiceData(BaseModel):
    """Structured invoice information extracted by the AI."""

    supplier_name: str | None = Field(default=None, max_length=255)
    invoice_number: str | None = Field(default=None, max_length=100)

    invoice_date: date | None = None
    due_date: date | None = None

    currency: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
        description="Three-letter ISO currency code, e.g. USD or EUR.",
    )

    subtotal: Decimal | None = None
    vat_amount: Decimal | None = None
    total_amount: Decimal | None = None

    confidence_score: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Overall extraction confidence between 0 and 1.",
    )

    extracted_data: dict[str, Any] = Field(default_factory=dict)


class ExtractionResultResponse(BaseModel):
    """API response representing a stored extraction result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID

    supplier_name: str | None = None
    invoice_number: str | None = None

    invoice_date: date | None = None
    due_date: date | None = None

    currency: str | None = None

    subtotal: Decimal | None = None
    vat_amount: Decimal | None = None
    total_amount: Decimal | None = None

    confidence_score: Decimal | None = None

    extracted_data: dict[str, Any] = Field(default_factory=dict)

    extraction_provider: str | None = None
    extraction_model: str | None = None

    created_at: datetime