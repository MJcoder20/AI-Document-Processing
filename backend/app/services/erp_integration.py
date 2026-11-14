
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction_result import ExtractionResult
from app.models.integration_log import IntegrationLog
from app.services.simulated_erp import SimulatedERP
from app.schemas.integration import IntegrationStatus


class ERPIntegrationError(Exception):
    """Raised when an ERP integration operation is invalid or fails."""


def integrate_document(
    db: Session,
    document_id: UUID,
) -> IntegrationLog:
    """Submit an approved invoice to the simulated ERP."""

    document = db.scalar(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
    )

    if document is None:
        raise ERPIntegrationError("Document not found.")

    if document.status != "approved":
        raise ERPIntegrationError(
            f"Document cannot be integrated from status: {document.status}"
        )

    extraction = db.scalar(
        select(ExtractionResult)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
    )

    if extraction is None:
        raise ERPIntegrationError(
            "Cannot integrate a document without extraction results."
        )

    validation = extraction.extracted_data.get("validation", {})

    if not validation.get("is_valid", False):
        raise ERPIntegrationError(
            "Cannot integrate an invoice that has not passed validation."
        )

    provider = SimulatedERP.provider
    operation = "create_invoice"

    # Prevent duplicate ERP submissions.
    existing_success = db.scalar(
        select(IntegrationLog.id).where(
            IntegrationLog.document_id == document_id,
            IntegrationLog.provider == provider,
            IntegrationLog.operation == operation,
            IntegrationLog.status == IntegrationStatus.SUCCESS.value,
        )
    )

    if existing_success is not None:
        raise ERPIntegrationError(
            "This document has already been integrated successfully."
        )

    # Calculate the next attempt number.
    previous_attempts = db.scalar(
        select(func.max(IntegrationLog.attempt_number)).where(
            IntegrationLog.document_id == document_id,
            IntegrationLog.provider == provider,
            IntegrationLog.operation == operation,
        )
    ) or 0

    attempt_number = previous_attempts + 1

    # Prepare a JSON-serializable ERP invoice payload.
    invoice_payload = {
        "supplier_name": extraction.supplier_name,
        "invoice_number": extraction.invoice_number,
        "invoice_date": (
            extraction.invoice_date.isoformat()
            if extraction.invoice_date else None
        ),
        "due_date": (
            extraction.due_date.isoformat()
            if extraction.due_date else None
        ),
        "currency": extraction.currency,
        "subtotal": (
            str(extraction.subtotal)
            if extraction.subtotal is not None else None
        ),
        "vat_amount": (
            str(extraction.vat_amount)
            if extraction.vat_amount is not None else None
        ),
        "total_amount": (
            str(extraction.total_amount)
            if extraction.total_amount is not None else None
        ),
    }

    # Record the attempt before communicating with the ERP.
    integration_log = IntegrationLog(
        document_id=document_id,
        provider=provider,
        operation=operation,
        status=IntegrationStatus.PROCESSING.value,
        attempt_number=attempt_number,
        request_payload=invoice_payload,
    )

    document.status = "integration_pending"
    db.add(integration_log)

    try:
        db.commit()
        db.refresh(integration_log)
    except Exception:
        db.rollback()
        raise

    # Submit the invoice to the ERP.
    try:
        erp = SimulatedERP(db)
        erp_response = erp.create_invoice(invoice_payload)

        integration_log.status = IntegrationStatus.SUCCESS.value
        integration_log.external_record_id = (
            erp_response["external_record_id"]
        )
        integration_log.response_payload = erp_response
        integration_log.error_message = None
        integration_log.completed_at = datetime.now(timezone.utc)

        document.status = "integrated"

        db.commit()
        db.refresh(integration_log)

        return integration_log

    except Exception as exc:
        db.rollback()

        # Reload records after rollback before updating their state.
        integration_log = db.get(IntegrationLog, integration_log.id)
        document = db.get(Document, document_id)

        if integration_log is not None:
            integration_log.status = IntegrationStatus.FAILED.value
            integration_log.error_message = str(exc)[:2000]
            integration_log.completed_at = datetime.now(timezone.utc)

        if document is not None:
            # Keep it approved so a failed attempt can be retried.
            document.status = "approved"

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        raise ERPIntegrationError(
            f"ERP integration failed: {exc}"
        ) from exc



def recover_stale_integrations(
    db: Session,
    stale_after_minutes: int = 10,
) -> dict[str, int]:
    """Recover integration attempts that have been processing too long."""

    from datetime import timedelta

    if stale_after_minutes <= 0:
        raise ValueError("stale_after_minutes must be greater than zero.")

    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=stale_after_minutes
    )

    stale_log_ids = db.scalars(
        select(IntegrationLog.id)
        .where(
            IntegrationLog.provider == SimulatedERP.provider,
            IntegrationLog.operation == "create_invoice",
            IntegrationLog.status == IntegrationStatus.PROCESSING.value,
            IntegrationLog.started_at < cutoff,
        )
        .order_by(IntegrationLog.started_at.asc())
    ).all()

    results = {
        "checked": 0,
        "recovered": 0,
        "retryable": 0,
        "errors": 0,
    }

    erp = SimulatedERP(db)

    for log_id in stale_log_ids:
        try:
            integration_log = db.scalar(
                select(IntegrationLog)
                .where(
                    IntegrationLog.id == log_id,
                    IntegrationLog.provider == SimulatedERP.provider,
                    IntegrationLog.operation == "create_invoice",
                    IntegrationLog.status == IntegrationStatus.PROCESSING.value,
                    IntegrationLog.started_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )

            if integration_log is None:
                continue

            results["checked"] += 1
            invoice_payload = integration_log.request_payload or {}

            existing_invoice = erp.find_invoice(
                supplier_name=invoice_payload.get("supplier_name", ""),
                invoice_number=invoice_payload.get("invoice_number", ""),
            )

            if existing_invoice is not None:
                integration_log.status = IntegrationStatus.SUCCESS.value
                integration_log.external_record_id = (
                    existing_invoice["external_record_id"]
                )
                integration_log.response_payload = existing_invoice
                integration_log.error_message = None
                integration_log.completed_at = datetime.now(timezone.utc)

                document = db.get(Document, integration_log.document_id)

                if document is not None:
                    document.status = "integrated"

                results["recovered"] += 1

            else:
                integration_log.status = IntegrationStatus.FAILED.value
                integration_log.error_message = (
                    "Stale integration recovered: no ERP invoice was found. "
                    "A new attempt can be made safely."
                )
                integration_log.completed_at = datetime.now(timezone.utc)

                document = db.get(Document, integration_log.document_id)

                if document is not None:
                    document.status = "approved"

                results["retryable"] += 1

            db.commit()

        except Exception as exc:
            db.rollback()
            results["errors"] += 1

    return results
