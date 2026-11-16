import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from pydantic import SecretStr
from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.core.security import create_access_token, hash_password
from app.models.user import User
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
    storage_dir = tmp_path / "documents"

    monkeypatch.setattr(settings, "processing_mode", "inline")
    monkeypatch.setattr(settings, "document_storage_dir", str(storage_dir))
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        SecretStr("test-secret-key-for-document-api"),
    )

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

    # Create an administrator for the existing API tests.
    with TestingSessionLocal() as db:
        admin = User(
            email="admin@example.com",
            hashed_password=hash_password("TestPassword123!"),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        access_token = create_access_token(admin.id)

    try:
        with TestClient(app) as client:
            client.headers.update({
                "Authorization": f"Bearer {access_token}"
            })
            client.testing_session_factory = TestingSessionLocal
            client.admin_token = access_token
            yield client, storage_dir

    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_test_user(client, email: str, role: str = "user"):
    with client.testing_session_factory() as db:
        user = User(
            email=email,
            hashed_password=hash_password("TestPassword123!"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        user_id = user.id

    return create_access_token(user_id), user_id

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
    original_commit = Session.commit
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

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.post(
        f"/api/v1/documents/{document_id}/process"
    )

    assert response.status_code == 500

    monkeypatch.setattr(Session, "commit", original_commit)

    status_response = client.get(
        f"/api/v1/documents/{document_id}"
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "uploaded"

    with client.testing_session_factory() as db:
        messages = db.query(OutboxMessage).all()
        assert len(messages) == 0


def test_document_api_rejects_unauthenticated_requests(api_environment):
    client, _ = api_environment
    client.headers.pop("Authorization", None)

    response = client.get("/api/v1/documents/")

    assert response.status_code == 401


def test_users_can_only_access_their_own_documents(api_environment):
    client, _ = api_environment

    token_a, user_a_id = create_test_user(
        client, "usera@example.com"
    )
    token_b, _ = create_test_user(
        client, "userb@example.com"
    )

    # User A uploads a document.
    client.headers["Authorization"] = f"Bearer {token_a}"

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "private-invoice.pdf",
                b"Private invoice content",
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    with client.testing_session_factory() as db:
        from app.models.document import Document

        document = db.get(Document, UUID(document_id))
        assert document.owner_id == user_a_id

    # User B cannot access User A's document.
    client.headers["Authorization"] = f"Bearer {token_b}"

    response = client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 404

    # User B cannot see User A's document in the listing.
    response = client.get("/api/v1/documents/")

    assert response.status_code == 200
    assert response.json() == []

    # User A can still access the document.
    client.headers["Authorization"] = f"Bearer {token_a}"

    response = client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 200


def test_admin_can_access_another_users_document(api_environment):
    client, _ = api_environment

    token, _ = create_test_user(
        client, "documentowner@example.com"
    )

    client.headers["Authorization"] = f"Bearer {token}"

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.pdf",
                b"Invoice content",
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    # Switch back to the administrator.
    client.headers["Authorization"] = (
        f"Bearer {client.admin_token}"
    )

    response = client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 200


def test_review_uses_authenticated_user_identity(
    api_environment,
    monkeypatch,
):
    client, _ = api_environment

    token, _ = create_test_user(
        client, "realreviewer@example.com"
    )
    client.headers["Authorization"] = f"Bearer {token}"

    upload_response = client.post(
        "/api/v1/documents/",
        files={
            "file": (
                "invoice.pdf",
                b"Invoice content",
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    captured = {}

    def fake_review_document(**kwargs):
        captured.update(kwargs)

        now = datetime.now(timezone.utc)

        return SimpleNamespace(
            id=uuid4(),
            document_id=UUID(document_id),
            reviewed_by=kwargs["reviewed_by"],
            decision="rejected",
            comments=kwargs["comments"],
            reviewed_at=now,
            created_at=now,
        )

    monkeypatch.setattr(
        documents_api,
        "review_document",
        fake_review_document,
    )

    response = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "reviewed_by": "attacker@example.com",
            "decision": "rejected",
            "comments": "Rejected during testing.",
        },
    )

    assert response.status_code == 201
    assert captured["reviewed_by"] == "realreviewer@example.com"
    assert response.json()["reviewed_by"] == "realreviewer@example.com"


def create_pending_review_document(client, owner_id=None):
    """Create a pending-review document with a valid invoice extraction."""
    from datetime import date
    from decimal import Decimal

    from app.models.document import Document
    from app.models.extraction_result import ExtractionResult
    from app.models.user import User

    with client.testing_session_factory() as db:
        if owner_id is None:
            owner = db.query(User).filter_by(
                email="admin@example.com"
            ).first()
            owner_id = owner.id

        document = Document(
            owner_id=owner_id,
            original_filename="review-invoice.pdf",
            storage_path="test/review-invoice.pdf",
            content_type="application/pdf",
            file_size=1024,
            document_type="invoice",
            status="pending_review",
        )

        db.add(document)
        db.flush()

        extraction = ExtractionResult(
            document_id=document.id,
            supplier_name="Acme Ltd",
            invoice_number="INV-2026-001",
            invoice_date=date(2026, 11, 10),
            due_date=date(2026, 12, 10),
            currency="USD",
            subtotal=Decimal("100.00"),
            vat_amount=Decimal("15.00"),
            total_amount=Decimal("115.00"),
            confidence_score=Decimal("0.9500"),
            extracted_data={
                "text": "Original invoice text",
                "tables": [],
                "validation": {
                    "status": "valid",
                    "is_valid": True,
                    "errors": [],
                    "warnings": [],
                    "duplicate_detected": False,
                    "duplicate_of": None,
                },
            },
            extraction_provider="ollama",
            extraction_model="test-model",
        )

        db.add(extraction)
        db.commit()

        return str(document.id)



def test_correct_extraction_updates_fields_and_revalidates(
    api_environment,
):
    client, _ = api_environment
    document_id = create_pending_review_document(client)

    response = client.patch(
        f"/api/v1/documents/{document_id}/extraction",
        json={
            "subtotal": "105.00",
            "total_amount": "120.00",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["subtotal"] == "105.00"
    assert data["total_amount"] == "120.00"
    assert data["extracted_data"]["validation"]["status"] == "valid"
    assert data["extracted_data"]["validation"]["is_valid"] is True

    with client.testing_session_factory() as db:
        from app.models.extraction_edit import ExtractionEdit

        edits = db.query(ExtractionEdit).filter_by(
            document_id=UUID(document_id)
        ).all()

        assert len(edits) == 1
        assert edits[0].edited_by == "admin@example.com"
        assert set(edits[0].changed_fields) == {
            "subtotal",
            "total_amount",
        }
        assert edits[0].before_data["total_amount"] == "115.00"
        assert edits[0].after_data["total_amount"] == "120.00"


def test_correct_extraction_can_make_invoice_invalid(
    api_environment,
):
    client, _ = api_environment
    document_id = create_pending_review_document(client)

    response = client.patch(
        f"/api/v1/documents/{document_id}/extraction",
        json={"total_amount": "999.00"},
    )

    assert response.status_code == 200

    validation = response.json()["extracted_data"]["validation"]

    assert validation["status"] == "invalid"
    assert validation["is_valid"] is False
    assert "Invoice total does not equal subtotal plus VAT." in (
        validation["errors"]
    )


def test_extraction_correction_history_returns_audit_records(
    api_environment,
):
    client, _ = api_environment
    document_id = create_pending_review_document(client)

    correction_response = client.patch(
        f"/api/v1/documents/{document_id}/extraction",
        json={"invoice_number": "INV-2026-UPDATED"},
    )

    assert correction_response.status_code == 200

    response = client.get(
        f"/api/v1/documents/{document_id}/extraction/history"
    )

    assert response.status_code == 200

    history = response.json()

    assert len(history) == 1
    assert history[0]["edited_by"] == "admin@example.com"
    assert history[0]["changed_fields"] == ["invoice_number"]
    assert history[0]["before_data"]["invoice_number"] == (
        "INV-2026-001"
    )
    assert history[0]["after_data"]["invoice_number"] == (
        "INV-2026-UPDATED"
    )


def test_cannot_correct_extraction_for_non_pending_document(
    api_environment,
):
    client, _ = api_environment
    document_id = create_pending_review_document(client)

    with client.testing_session_factory() as db:
        from app.models.document import Document

        document = db.get(Document, UUID(document_id))
        document.status = "integrated"
        db.commit()

    response = client.patch(
        f"/api/v1/documents/{document_id}/extraction",
        json={"total_amount": "120.00"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only documents pending review can be edited."
    )


def test_user_cannot_correct_or_view_another_users_extraction(
    api_environment,
):
    client, _ = api_environment

    document_id = create_pending_review_document(client)

    user_token, _ = create_test_user(
        client,
        "anotheruser@example.com",
    )

    client.headers["Authorization"] = f"Bearer {user_token}"

    correction_response = client.patch(
        f"/api/v1/documents/{document_id}/extraction",
        json={"total_amount": "120.00"},
    )

    history_response = client.get(
        f"/api/v1/documents/{document_id}/extraction/history"
    )

    assert correction_response.status_code == 404
    assert history_response.status_code == 404



def test_invalid_corrected_invoice_cannot_be_approved(
    api_environment,
):
    client, _ = api_environment
    document_id = create_pending_review_document(client)

    # Correct the invoice with an inconsistent total.
    correction_response = client.patch(
        f"/api/v1/documents/{document_id}/extraction",
        json={"total_amount": "999.00"},
    )

    assert correction_response.status_code == 200

    validation = correction_response.json()["extracted_data"]["validation"]
    assert validation["is_valid"] is False
    assert validation["status"] == "invalid"

    # Attempt to approve the invalid invoice.
    approval_response = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "decision": "approved",
            "comments": "Attempting to approve an invalid invoice.",
        },
    )

    assert approval_response.status_code == 409
    assert "Cannot approve an invoice" in (
        approval_response.json()["detail"]
    )

    # Verify the document remains pending review.
    with client.testing_session_factory() as db:
        from app.models.document import Document

        document = db.get(Document, UUID(document_id))
        assert document.status == "pending_review"
