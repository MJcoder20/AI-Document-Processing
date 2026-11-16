
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExtractionEdit(Base):
    __tablename__ = "extraction_edits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    edited_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    changed_fields: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    before_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    after_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
