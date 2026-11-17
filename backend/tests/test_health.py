from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.main import app


@pytest.fixture
def health_client():
    app.dependency_overrides.clear()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_liveness_check(health_client):
    response = health_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_check_when_database_is_available(health_client):
    class FakeDB:
        def execute(self, query):
            return 1

    def override_get_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = override_get_db

    response = health_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
    }


def test_readiness_check_when_database_is_unavailable(health_client):
    class FakeDB:
        def execute(self, query):
            raise SQLAlchemyError("Database connection failed")

    def override_get_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = override_get_db

    response = health_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }


def test_worker_health_returns_queue_statistics(health_client):
    class FakeDB:
        def execute(self, query):
            return SimpleNamespace(
                all=lambda: [
                    ("pending", 3),
                    ("processing", 2),
                    ("processed", 10),
                    ("failed", 1),
                ]
            )

        def scalar(self, query):
            return 2

    def override_get_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = override_get_db

    response = health_client.get("/health/worker")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "queue": {
            "pending": 3,
            "processing": 2,
            "processed": 10,
            "failed": 1,
            "retrying": 2,
        },
    }


def test_worker_health_when_database_is_unavailable(health_client):
    class FakeDB:
        def execute(self, query):
            raise SQLAlchemyError("Database connection failed")

    def override_get_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = override_get_db

    response = health_client.get("/health/worker")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"



def test_operational_metrics_returns_document_and_outbox_statistics(
    health_client,
):
    class FakeDB:
        def __init__(self):
            self.results = iter([
                [
                    ("uploaded", 3),
                    ("processed", 7),
                    ("failed", 1),
                ],
                [
                    ("invoice", 8),
                    ("purchase_order", 3),
                ],
                [
                    ("pending", 4),
                    ("processing", 2),
                    ("processed", 10),
                    ("failed", 1),
                ],
            ])

        def execute(self, query):
            return SimpleNamespace(all=lambda: next(self.results))

        def scalar(self, query):
            return 2

    def override_get_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = override_get_db

    response = health_client.get("/health/metrics")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"

    assert data["documents"]["total"] == 11
    assert data["documents"]["by_status"] == {
        "uploaded": 3,
        "processed": 7,
        "failed": 1,
    }
    assert data["documents"]["by_type"] == {
        "invoice": 8,
        "purchase_order": 3,
    }

    assert data["outbox"]["total"] == 17
    assert data["outbox"]["by_status"]["pending"] == 4
    assert data["outbox"]["retrying"] == 2
    assert data["outbox"]["pending_backlog"] == 2


def test_operational_metrics_handles_database_failure(health_client):
    class FakeDB:
        def execute(self, query):
            raise SQLAlchemyError("Database unavailable")

    def override_get_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = override_get_db

    response = health_client.get("/health/metrics")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
