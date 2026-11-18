import logging
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.confidence_scoring import calculate_field_confidence
from app.services.s3_storage import download_file_to_path

from app.core.config import settings
from app.models.document import Document
from app.models.extraction_result import ExtractionResult
from app.services.ai_extraction import extract_invoice_data
from app.services.document_extractor import extract_document
from app.services.invoice_validation import validate_invoice


logger = logging.getLogger(__name__)

MOCK_EXTRACTION_MODEL = "mock-regex-v1"


def get_extraction_model() -> str:
    if settings.ai_provider == "mock":
        return MOCK_EXTRACTION_MODEL

    if settings.ai_provider == "ollama":
        return settings.ollama_model

    if settings.ai_provider == "gemini":
        return settings.gemini_model

    return "unknown"


class DocumentProcessingError(Exception):
    """Raised when document processing fails."""

@contextmanager
def get_document_processing_path(storage_path: str) -> Iterator[Path]:
    """Provide a local path for processing locally or S3-stored documents."""

    if settings.storage_provider == "local":
        yield Path(storage_path)
        return

    suffix = Path(storage_path).suffix

    with TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory) / f"document{suffix}"

        download_file_to_path(
            key=storage_path,
            destination=temporary_path,
        )

        yield temporary_path

def process_document(
    db: Session,
    document_id: UUID,
    *,
    from_queue: bool = False,
) -> ExtractionResult:
    """
    Extract document content, identify invoice fields using AI,
    validate the result, and persist everything in the database.
    """

    document = db.get(Document, document_id)

    if document is None:
        raise DocumentProcessingError(
            f"Document {document_id} was not found."
        )

    allowed_statuses = {"uploaded", "failed"}

    if from_queue:
        allowed_statuses.add("processing")

    if document.status not in allowed_statuses:
        raise DocumentProcessingError(
            f"Document cannot be processed from status: {document.status}"
        )

    try:
        # Step 1: Mark the document as processing.
        document.status = "processing"
        document.error_message = None
        db.commit()

        # Step 2: Extract text and tables.
        with get_document_processing_path(document.storage_path) as file_path:
            extracted_content = extract_document(file_path)

        # Step 3: Extract structured invoice information using AI.
        invoice_data = extract_invoice_data(
            document_text=extracted_content.text,
            tables=extracted_content.tables,
        )

        field_confidence = calculate_field_confidence(
            invoice=invoice_data,
            document_text=extracted_content.text,
            tables=extracted_content.tables,
        )

        # Step 4: Create the extraction result.
        extraction_result = ExtractionResult(
            document_id=document.id,
            supplier_name=invoice_data.supplier_name,
            invoice_number=invoice_data.invoice_number,
            invoice_date=invoice_data.invoice_date,
            due_date=invoice_data.due_date,
            currency=invoice_data.currency,
            subtotal=invoice_data.subtotal,
            vat_amount=invoice_data.vat_amount,
            total_amount=invoice_data.total_amount,
            confidence_score=invoice_data.confidence_score,
            extracted_data={
                "text": extracted_content.text,
                "tables": extracted_content.tables,
                "invoice": invoice_data.model_dump(mode="json"),
                "field_confidence": {
                    field: (
                        str(score) if score is not None else None
                    )
                    for field, score in field_confidence.items()
                },
            },
            extraction_provider=settings.ai_provider,
            extraction_model=get_extraction_model(),
        )

        db.add(extraction_result)
        db.flush()

        # Step 5: Validate the extracted invoice.
        validation_result = validate_invoice(
            db=db,
            extraction=extraction_result,
            document=document,
        )

        # Step 6: Store validation results separately.
        extraction_result.extracted_data = {
            **extraction_result.extracted_data,
            "validation": validation_result,
        }

        # Step 7: Send the document for human review.
        document.status = "pending_review"
        document.error_message = None

        db.commit()
        db.refresh(extraction_result)

        logger.info(
            "Document %s processed using provider=%s, model=%s. "
            "Validation status: %s",
            document_id,
            settings.ai_provider,
            get_extraction_model(),
            validation_result["status"],
        )

        return extraction_result

    except Exception as exc:
        db.rollback()

        failed_document = db.get(Document, document_id)

        if failed_document is not None:
            failed_document.status = "failed"
            failed_document.error_message = str(exc)[:2000]

            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Could not persist failure status for document %s",
                    document_id,
                )

        logger.exception(
            "Document processing failed for document %s",
            document_id,
        )

        if isinstance(exc, DocumentProcessingError):
            raise

        raise DocumentProcessingError(
            f"Could not process document: {exc}"
        ) from exc
