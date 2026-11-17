import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.core.dependencies import get_current_user
from app.api.errors import router
from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.error_event import ErrorEvent


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def client(db):
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    test_app.dependency_overrides[get_db] = lambda: db
    test_app.dependency_overrides[require_admin] = lambda: MagicMock(
        role="admin"
    )

    return TestClient(test_app)


def make_error_event(**overrides):
    values = {
        "id": uuid.uuid4(),
        "request_id": str(uuid.uuid4()),
        "message_id": None,
        "document_id": None,
        "severity": "error",
        "category": "application",
        "error_type": "RuntimeError",
        "message": "Something went wrong",
        "endpoint": "/api/v1/documents",
        "method": "POST",
        "traceback": "Traceback details",
        "status": "open",
        "occurred_at": datetime.now(timezone.utc),
        "resolved_at": None,
    }
    values.update(overrides)
    return ErrorEvent(**values)


def test_list_errors(client, db):
    event = make_error_event()

    db.scalar.return_value = 1
    db.scalars.return_value.all.return_value = [event]

    response = client.get("/api/v1/errors/")

    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["error_type"] == "RuntimeError"
    assert "traceback" not in data["items"][0]


def test_list_errors_with_filters(client, db):
    db.scalar.return_value = 0
    db.scalars.return_value.all.return_value = []

    response = client.get(
        "/api/v1/errors/",
        params={
            "status": "open",
            "severity": "error",
            "category": "application",
            "search": "RuntimeError",
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_error_metrics(client, db):
    db.scalar.side_effect = [3, 2]
    db.execute.side_effect = [
        MagicMock(all=MagicMock(return_value=[("open", 2), ("resolved", 1)])),
        MagicMock(all=MagicMock(return_value=[("error", 3)])),
        MagicMock(all=MagicMock(
            return_value=[
                ("application", 2),
                ("document_processing", 1),
            ]
        )),
    ]

    response = client.get("/api/v1/errors/metrics")

    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 3
    assert data["last_24_hours"] == 2
    assert data["by_status"]["open"] == 2
    assert data["by_severity"]["error"] == 3


def test_get_error_details(client, db):
    event = make_error_event()
    db.get.return_value = event

    response = client.get(f"/api/v1/errors/{event.id}")

    assert response.status_code == 200
    assert response.json()["traceback"] == "Traceback details"


def test_get_nonexistent_error(client, db):
    db.get.return_value = None

    response = client.get(f"/api/v1/errors/{uuid.uuid4()}")

    assert response.status_code == 404


def test_resolve_error(client, db):
    event = make_error_event()
    db.get.return_value = event

    response = client.patch(
        f"/api/v1/errors/{event.id}/status",
        json={"status": "resolved"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert event.resolved_at is not None

    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(event)


def test_reopen_error_for_investigation(client, db):
    event = make_error_event(
        status="resolved",
        resolved_at=datetime.now(timezone.utc),
    )
    db.get.return_value = event

    response = client.patch(
        f"/api/v1/errors/{event.id}/status",
        json={"status": "investigating"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "investigating"
    assert event.resolved_at is None


def test_invalid_error_status(client, db):
    event = make_error_event()
    db.get.return_value = event

    response = client.patch(
        f"/api/v1/errors/{event.id}/status",
        json={"status": "unknown"},
    )

    assert response.status_code == 422
    db.commit.assert_not_called()


def test_regular_user_cannot_access_error_events(db):
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    regular_user = SimpleNamespace(
        role="user",
        is_active=True,
    )

    test_app.dependency_overrides[get_db] = lambda: db
    test_app.dependency_overrides[get_current_user] = lambda: regular_user

    client = TestClient(test_app)

    response = client.get("/api/v1/errors/")

    assert response.status_code == 403
    assert response.json()["detail"] == "Administrator privileges required."


def test_unauthenticated_user_cannot_access_error_events(db):
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    test_app.dependency_overrides[get_db] = lambda: db

    client = TestClient(test_app)

    response = client.get("/api/v1/errors/")

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid or expired authentication credentials."
    )