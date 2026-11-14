import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Document
from app.repositories.document import (
    create_document,
    get_document,
    list_documents,
)


@pytest.fixture
def db_session():
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

    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_test_document(db_session, filename="invoice.pdf"):
    return create_document(
        db_session,
        original_filename=filename,
        storage_path=f"storage/{uuid.uuid4()}.pdf",
        content_type="application/pdf",
        file_size=1024,
    )


def test_create_document(db_session):
    document = create_test_document(db_session)

    assert document.id is not None
    assert document.original_filename == "invoice.pdf"
    assert document.content_type == "application/pdf"
    assert document.file_size == 1024
    assert document.status == "uploaded"


def test_get_document_by_id(db_session):
    created = create_test_document(db_session)

    document = get_document(db_session, created.id)

    assert document is not None
    assert document.id == created.id


def test_get_document_returns_none_for_missing_id(db_session):
    document = get_document(db_session, uuid.uuid4())

    assert document is None


def test_list_documents(db_session):
    create_test_document(db_session, "invoice1.pdf")
    create_test_document(db_session, "invoice2.pdf")
    create_test_document(db_session, "invoice3.pdf")

    documents = list_documents(db_session)

    assert len(documents) == 3


def test_list_documents_supports_pagination(db_session):
    for index in range(5):
        create_test_document(db_session, f"invoice{index}.pdf")

    documents = list_documents(
        db_session,
        limit=2,
        offset=1,
    )

    assert len(documents) == 2