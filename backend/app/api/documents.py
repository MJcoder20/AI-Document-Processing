from pathlib import Path
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.extraction_edit import ExtractionEdit
from app.schemas.extraction import ExtractionEditResponse
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.repositories.document import (
    create_document,
    get_document,
    list_documents,
)
from app.repositories.extraction import get_latest_extraction
from app.repositories.integration import list_document_integrations
from app.repositories.outbox import create_outbox_message
from app.schemas.approval import (
    DocumentApprovalCreate,
    DocumentApprovalResponse,
)
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentType,
)
from app.schemas.extraction import (
    ExtractionCorrection,
    ExtractionResultResponse,
)
from app.schemas.integration import IntegrationLogResponse
from app.services.document_approval import (
    DocumentApprovalError,
    review_document,
)
from app.services.document_processing import (
    DocumentProcessingError,
    process_document,
)
from app.services.erp_integration import (
    ERPIntegrationError,
    integrate_document,
)
from app.services.extraction_review import (
    ExtractionReviewError,
    correct_extraction,
)
from app.services.storage import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    save_upload,
)


router = APIRouter(prefix="/documents", tags=["Documents"])


def _get_accessible_document(
    db: Session,
    document_id: UUID,
    current_user: User,
) -> Document:
    """Retrieve a document only if the user is allowed to access it."""

    document = get_document(
        db,
        document_id,
        current_user=current_user,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return document



@router.get(
    "/",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
)
def get_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=255),
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    document_type: DocumentType | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve filtered and paginated documents accessible to the user."""

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from cannot be later than date_to.",
        )

    documents, total = list_documents(
        db,
        limit=limit,
        offset=offset,
        current_user=current_user,
        search=search,
        status=status_filter.value if status_filter else None,
        document_type=document_type.value if document_type else None,
        date_from=date_from,
        date_to=date_to,
    )

    return DocumentListResponse(
        items=documents,
        total=total,
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
    current_user: User = Depends(get_current_user),
):
    """Upload a document and assign it to the authenticated user."""

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
            owner_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
):
    """Process an accessible document inline or in the background."""

    document = _get_accessible_document(
        db,
        document_id,
        current_user,
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
    current_user: User = Depends(get_current_user),
):
    """Approve or reject an accessible document."""

    _get_accessible_document(
        db,
        document_id,
        current_user,
    )

    try:
        return review_document(
            db=db,
            document_id=document_id,
            reviewed_by=current_user.email,
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
    current_user: User = Depends(get_current_user),
):
    """Integrate an accessible approved document with the ERP system."""

    _get_accessible_document(
        db,
        document_id,
        current_user,
    )

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
    current_user: User = Depends(get_current_user),
):
    """Retrieve an accessible document and its processing status."""

    return _get_accessible_document(
        db,
        document_id,
        current_user,
    )


@router.get(
    "/{document_id}/extraction",
    response_model=ExtractionResultResponse,
    status_code=status.HTTP_200_OK,
)
def get_document_extraction(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the latest extraction for an accessible document."""

    _get_accessible_document(
        db,
        document_id,
        current_user,
    )

    extraction = get_latest_extraction(db, document_id)

    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No extraction result found for this document.",
        )

    return extraction

@router.get(
    "/{document_id}/extraction/history",
    response_model=list[ExtractionEditResponse],
    status_code=status.HTTP_200_OK,
)
def get_document_extraction_history(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve correction history for an accessible document."""

    _get_accessible_document(
        db,
        document_id,
        current_user,
    )

    statement = (
        select(ExtractionEdit)
        .where(ExtractionEdit.document_id == document_id)
        .order_by(ExtractionEdit.created_at.desc())
    )

    return db.scalars(statement).all()


@router.patch(
    "/{document_id}/extraction",
    response_model=ExtractionResultResponse,
    status_code=status.HTTP_200_OK,
)
def correct_document_extraction(
    document_id: UUID,
    corrections: ExtractionCorrection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Correct extracted invoice fields and record an audit entry."""

    _get_accessible_document(
        db,
        document_id,
        current_user,
    )

    try:
        extraction = correct_extraction(
            db=db,
            document_id=document_id,
            corrections=corrections.model_dump(exclude_unset=True),
            edited_by=current_user.email,
        )

        db.commit()
        db.refresh(extraction)

        return extraction

    except ExtractionReviewError as exc:
        db.rollback()

        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc) in {
                "Document not found.",
                "No extraction result exists for this document.",
            }
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
            detail="A database error occurred while correcting the extraction.",
        ) from exc


@router.get(
    "/{document_id}/integrations",
    response_model=list[IntegrationLogResponse],
    status_code=status.HTTP_200_OK,
)
def get_document_integration_history(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve integration history for an accessible document."""

    _get_accessible_document(
        db,
        document_id,
        current_user,
    )

    return list_document_integrations(db, document_id)