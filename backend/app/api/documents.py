from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document
from app.repositories.document import (
    create_document,
    get_document,
    list_documents,
)
from app.repositories.extraction import get_latest_extraction
from app.repositories.integration import list_document_integrations
from app.repositories.outbox import create_outbox_message
from app.schemas.integration import IntegrationLogResponse
from app.schemas.approval import (
    DocumentApprovalCreate,
    DocumentApprovalResponse,
)
from app.schemas.integration import IntegrationLogResponse
from app.services.erp_integration import (
    ERPIntegrationError,
    integrate_document,
)
from app.services.document_approval import (
    DocumentApprovalError,
    review_document,
)

from app.schemas.document import DocumentResponse
from app.core.config import settings
from app.schemas.extraction import ExtractionResultResponse
from app.services.document_processing import (
    DocumentProcessingError,
    process_document,
)
from app.services.storage import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    save_upload,
)


router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get(
    "/",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_200_OK,
)
def get_documents(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Retrieve documents with pagination."""

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 100.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Offset cannot be negative.",
        )

    return list_documents(
        db,
        limit=limit,
        offset=offset,
    )

@router.post(
    "/",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a document and create its database record."""

    original_filename = file.filename or "unnamed"
    content_type = file.content_type or "application/octet-stream"

    try:
        storage_path, file_size = await save_upload(file)

    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc

    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc

    try:
        document = create_document(
            db,
            original_filename=original_filename,
            storage_path=storage_path,
            content_type=content_type,
            file_size=file_size,
        )

        return document

    except SQLAlchemyError as exc:
        db.rollback()
        Path(storage_path).unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the document record.",
        ) from exc



@router.post(
    "/{document_id}/process",
    response_model=ExtractionResultResponse | DocumentResponse,
    status_code=status.HTTP_200_OK,
)
def process_uploaded_document(
    document_id: UUID,
    db: Session = Depends(get_db),
):
    """Process a document inline or enqueue it for background processing."""

    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    if settings.processing_mode in {
        "local_worker",
        "azure_service_bus",
    }:
        if document.status not in ("uploaded", "failed"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document cannot be queued from status '{document.status}'.",
            )

        try:
            document.status = "processing"
            document.error_message = None

            create_outbox_message(
                db,
                document_id=document_id,
                message_type="process_document",
                payload={
                    "message_type": "process_document",
                    "document_id": str(document_id),
                    "version": 1,
                },
            )

            # Save both changes in one transaction.
            db.commit()
            db.refresh(document)

            return document

        except SQLAlchemyError as exc:
            db.rollback()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred while queueing the document.",
            ) from exc
    try:
        return process_document(db, document_id)

    except DocumentProcessingError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred during document processing.",
        ) from exc


@router.post(
    "/{document_id}/review",
    response_model=DocumentApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
def review_uploaded_document(
    document_id: UUID,
    review_data: DocumentApprovalCreate,
    db: Session = Depends(get_db),
):
    """Approve or reject a document after human review."""

    try:
        return review_document(
            db=db,
            document_id=document_id,
            reviewed_by=review_data.reviewed_by,
            decision=review_data.decision,
            comments=review_data.comments,
        )

    except DocumentApprovalError as exc:
        db.rollback()

        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc) == "Document not found."
            else status.HTTP_409_CONFLICT
        )

        raise HTTPException(
            status_code=error_status,
            detail=str(exc),
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred during document review.",
        ) from exc

@router.post(
    "/{document_id}/integrate",
    response_model=IntegrationLogResponse,
    status_code=status.HTTP_201_CREATED,
)
def integrate_uploaded_document(
    document_id: UUID,
    db: Session = Depends(get_db),
):
    """Send an approved invoice to the ERP system."""
    try:
        return integrate_document(
            db=db,
            document_id=document_id,
        )

    except ERPIntegrationError as exc:
        db.rollback()

        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc) == "Document not found."
            else status.HTTP_409_CONFLICT
        )

        raise HTTPException(
            status_code=error_status,
            detail=str(exc),
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred during ERP integration.",
        ) from exc


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
def get_uploaded_document(
    document_id: UUID,
    db: Session = Depends(get_db),
):
    """Retrieve a document and its current processing status."""

    document = get_document(db, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return document

@router.get(
    "/{document_id}/extraction",
    response_model=ExtractionResultResponse,
    status_code=status.HTTP_200_OK,
)
def get_document_extraction(
    document_id: UUID,
    db: Session = Depends(get_db),
):
    """Retrieve the latest extraction result for a document."""

    document = get_document(db, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    extraction = get_latest_extraction(db, document_id)

    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No extraction result found for this document.",
        )

    return extraction

@router.get(
    "/{document_id}/integrations",
    response_model=list[IntegrationLogResponse],
    status_code=status.HTTP_200_OK,
)
def get_document_integration_history(
    document_id: UUID,
    db: Session = Depends(get_db),
):
    """Retrieve all ERP integration attempts for a document."""

    document = get_document(db, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return list_document_integrations(db, document_id)


