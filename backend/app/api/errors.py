from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.error_event import ErrorEvent
from app.schemas.error_event import (
    ErrorEventDetail,
    ErrorEventListItem,
    ErrorEventListResponse,
    ErrorEventMetrics,
    ErrorEventStatus,
    ErrorEventStatusUpdate,
)


router = APIRouter(
    prefix="/errors",
    tags=["Error Management"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "/",
    response_model=ErrorEventListResponse,
)
def list_error_events(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: ErrorEventStatus | None = Query(
        default=None,
        alias="status",
    ),
    severity: str | None = Query(default=None, max_length=20),
    category: str | None = Query(default=None, max_length=50),
    search: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
):
    conditions = []

    if status_filter:
        conditions.append(ErrorEvent.status == status_filter.value)

    if severity:
        conditions.append(ErrorEvent.severity == severity)

    if category:
        conditions.append(ErrorEvent.category == category)

    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            or_(
                ErrorEvent.message.ilike(search_term),
                ErrorEvent.error_type.ilike(search_term),
                ErrorEvent.endpoint.ilike(search_term),
                ErrorEvent.request_id.ilike(search_term),
            )
        )

    total = db.scalar(
        select(func.count(ErrorEvent.id)).where(*conditions)
    ) or 0

    events = db.scalars(
        select(ErrorEvent)
        .where(*conditions)
        .order_by(ErrorEvent.occurred_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return ErrorEventListResponse(
        items=[
            ErrorEventListItem.model_validate(event)
            for event in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/metrics",
    response_model=ErrorEventMetrics,
)
def error_event_metrics(
    db: Session = Depends(get_db),
):
    def count_by(column):
        rows = db.execute(
            select(column, func.count(ErrorEvent.id))
            .group_by(column)
        ).all()

        return {
            key: count
            for key, count in rows
        }

    total = db.scalar(
        select(func.count(ErrorEvent.id))
    ) or 0

    last_24_hours = db.scalar(
        select(func.count(ErrorEvent.id)).where(
            ErrorEvent.occurred_at
            >= datetime.now(timezone.utc) - timedelta(hours=24)
        )
    ) or 0

    return ErrorEventMetrics(
        total=total,
        by_status=count_by(ErrorEvent.status),
        by_severity=count_by(ErrorEvent.severity),
        by_category=count_by(ErrorEvent.category),
        last_24_hours=last_24_hours,
    )


@router.get(
    "/{error_id}",
    response_model=ErrorEventDetail,
)
def get_error_event(
    error_id: UUID,
    db: Session = Depends(get_db),
):
    event = db.get(ErrorEvent, error_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Error event not found.",
        )

    return event


@router.patch(
    "/{error_id}/status",
    response_model=ErrorEventDetail,
)
def update_error_event_status(
    error_id: UUID,
    payload: ErrorEventStatusUpdate,
    db: Session = Depends(get_db),
):
    event = db.get(ErrorEvent, error_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Error event not found.",
        )

    new_status = payload.status.value

    if new_status == ErrorEventStatus.RESOLVED.value:
        if event.status != ErrorEventStatus.RESOLVED.value:
            event.resolved_at = datetime.now(timezone.utc)
    else:
        event.resolved_at = None

    event.status = new_status

    db.commit()
    db.refresh(event)

    return event