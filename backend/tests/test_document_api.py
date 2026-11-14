import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.api import documents as documents_api
from app.models.outbox_message import OutboxMessage
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app

from uuid import UUID, uuid4


@pytest.fixture
def api_environment(tmp_path, monkeypatch):
    from app.core.config import settings

    storage_dir = tmp_path / "documents"
    monkeypatch.setattr(settings, "processing_mode", "inline")

    monkeypatch.setattr(
        settings,
        "document_storage_dir",
        str(storage_dir),
    )
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        client.testing_session_factory = TestingSessionLocal
        yield client, storage_dir

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_upload_document_success(api_environment):
    client, storage_dir = api_environment

    response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.pdf",
                b"Sample invoice content",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["original_filename"] == "invoice.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["file_size"] == len(b"Sample invoice content")
    assert data["document_type"] == "unknown"
    assert data["status"] == "uploaded"
    assert "storage_path" not in data

    stored_files = list(storage_dir.iterdir())
    assert len(stored_files) == 1


def test_upload_document_rejects_unsupported_file(api_environment):
    client, storage_dir = api_environment

    response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "malware.exe",
                b"Executable content",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 415
    assert not storage_dir.exists() or list(storage_dir.iterdir()) == []


def test_upload_document_rejects_oversized_file(api_environment):
    client, storage_dir = api_environment

    response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "large.pdf",
                b"A" * (1024 * 1024 + 1),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413
    assert list(storage_dir.iterdir()) == []


def test_upload_document_cleans_file_after_database_failure(
    api_environment,
    monkeypatch,
):
    client, storage_dir = api_environment

    def fail_create_document(*args, **kwargs):
        raise SQLAlchemyError("Simulated database failure")

    monkeypatch.setattr(
        "app.api.documents.create_document",
        fail_create_document,
    )

    response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.pdf",
                b"Sample invoice content",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Could not save the document record."
    )
    assert list(storage_dir.iterdir()) == []


def test_process_document_success(api_environment):
    client, _ = api_environment

    content = "Supplier: Acme Ltd\nInvoice Number: INV-2026-001\nTotal: 150.00"

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.txt",
                content.encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201

    document_id = upload_response.json()["id"]

    process_response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    assert process_response.status_code == 200

    data = process_response.json()

    assert data["document_id"] == document_id
    assert data["extraction_provider"] == "ollama"
    assert data["extracted_data"]["text"] == content
    assert data["extracted_data"]["tables"] == []


def test_process_document_not_found(api_environment):
    client, _ = api_environment

    missing_document_id = uuid4()

    response = client.post(
        f"/api/v1/documents/{missing_document_id}/process"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_process_document_twice_returns_conflict(api_environment):
    client, _ = api_environment

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.txt",
                b"Supplier: Acme Ltd\nTotal: 150.00",
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201

    document_id = upload_response.json()["id"]

    first_response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    assert second_response.status_code == 409



def test_get_document_success(api_environment):
    client, _ = api_environment

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.txt",
                b"Sample invoice content",
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    response = client.get(
        f"/api/v1/documents/{document_id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == document_id
    assert data["original_filename"] == "invoice.txt"
    assert data["document_type"] == "unknown"
    assert data["status"] == "uploaded"
    assert "storage_path" not in data


def test_get_document_not_found(api_environment):
    client, _ = api_environment

    missing_document_id = uuid4()

    response = client.get(
        f"/api/v1/documents/{missing_document_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_get_document_integration_history(api_environment):
    from datetime import datetime, timezone

    from app.db.session import get_db
    from app.models.document import Document
    from app.models.integration_log import IntegrationLog

    client, _ = api_environment

    # Create a document through the API.
    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.txt",
                b"Sample invoice content",
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    # Insert an integration log into the test database.
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)

    try:
        document = db.get(Document, uuid4())  # No existing record expected.
        assert document is None

        integration_log = IntegrationLog(
            document_id=UUID(document_id), # Replaced below with the actual document ID.
            provider="simulated_erp",
            operation="create_invoice",
            status="success",
            external_record_id="ERP-INV-TEST123",
            attempt_number=1,
            request_payload={"invoice_number": "INV-TEST-001"},
            response_payload={"success": True},
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )


        integration_log.document_id = UUID(document_id)

        db.add(integration_log)
        db.commit()
    finally:
        try:
            next(db_generator)
        except StopIteration:
            pass

    response = client.get(
        f"/api/v1/documents/{document_id}/integrations"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["provider"] == "simulated_erp"
    assert data[0]["status"] == "success"
    assert data[0]["external_record_id"] == "ERP-INV-TEST123"
    assert data[0]["attempt_number"] == 1


def test_get_document_integration_history_not_found(api_environment):
    client, _ = api_environment

    missing_document_id = uuid4()

    response = client.get(
        f"/api/v1/documents/{missing_document_id}/integrations"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_queue_document_processing_success(api_environment, monkeypatch):
    client, _ = api_environment

    monkeypatch.setattr(settings, "processing_mode", "azure_service_bus")

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.txt",
                b"Supplier: Acme Ltd\nTotal: 150.00",
                "text/plain",
            )
        },
    )

    document_id = upload_response.json()["id"]

    response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processing"

    with client.testing_session_factory() as db:
        messages = db.query(OutboxMessage).all()

        assert len(messages) == 1
        assert str(messages[0].document_id) == document_id
        assert messages[0].message_type == "process_document"
        assert messages[0].status == "pending"
        assert messages[0].payload["document_id"] == document_id
        assert messages[0].payload["version"] == 1


def test_queue_document_processing_twice_returns_conflict(
    api_environment,
    monkeypatch,
):
    client, _ = api_environment

    monkeypatch.setattr(settings, "processing_mode", "azure_service_bus")

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.txt",
                b"Sample invoice",
                "text/plain",
            )
        },
    )

    document_id = upload_response.json()["id"]

    first_response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    second_response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409

    with client.testing_session_factory() as db:
        messages = db.query(OutboxMessage).all()
        assert len(messages) == 1


def test_queue_database_failure_rolls_back_transaction(
    api_environment,
    monkeypatch,
):
    client, _ = api_environment

    monkeypatch.setattr(settings, "processing_mode", "azure_service_bus")

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.txt",
                b"Sample invoice",
                "text/plain",
            )
        },
    )

    document_id = upload_response.json()["id"]

    def fail_commit(self):
        raise SQLAlchemyError("Simulated database failure.")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    assert response.status_code == 500

    monkeypatch.undo()

    status_response = client.get(
        f"/api/v1/documents/{document_id}"
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "uploaded"

    with client.testing_session_factory() as db:
        messages = db.query(OutboxMessage).all()
        assert len(messages) == 0