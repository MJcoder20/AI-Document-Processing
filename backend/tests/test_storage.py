from io import BytesIO

import pytest
from fastapi import UploadFile

from app.services.storage import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    save_upload,
)


@pytest.fixture
def storage_directory(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(
        settings,
        "document_storage_dir",
        str(tmp_path / "documents"),
    )
    monkeypatch.setattr(settings, "max_upload_size_mb", 10)

    return tmp_path / "documents"


def create_upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
    )


@pytest.mark.asyncio
async def test_save_pdf_upload(storage_directory):
    upload = create_upload("invoice.pdf", b"PDF test content")

    stored_path, file_size = await save_upload(upload)

    assert file_size == len(b"PDF test content")
    assert stored_path.endswith(".pdf")
    assert storage_directory.exists()

    with open(stored_path, "rb") as file:
        assert file.read() == b"PDF test content"


@pytest.mark.asyncio
async def test_save_upload_uses_generated_filename(storage_directory):
    upload = create_upload("my_invoice.pdf", b"Invoice content")

    stored_path, _ = await save_upload(upload)

    assert "my_invoice" not in stored_path


@pytest.mark.asyncio
async def test_save_upload_rejects_unsupported_extension():
    upload = create_upload("invoice.exe", b"Executable content")

    with pytest.raises(UnsupportedFileTypeError):
        await save_upload(upload)


@pytest.mark.asyncio
async def test_save_upload_rejects_missing_extension():
    upload = create_upload("invoice", b"Invoice content")

    with pytest.raises(UnsupportedFileTypeError):
        await save_upload(upload)


@pytest.mark.asyncio
async def test_save_upload_rejects_oversized_file(
    storage_directory,
    monkeypatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_size_mb", 1)

    upload = create_upload(
        "large.pdf",
        b"A" * (1024 * 1024 + 1),
    )

    with pytest.raises(FileTooLargeError):
        await save_upload(upload)

    assert list(storage_directory.iterdir()) == []


@pytest.mark.asyncio
async def test_save_upload_accepts_supported_extensions(storage_directory):
    extensions = [".pdf", ".docx", ".xlsx", ".txt"]

    for extension in extensions:
        upload = create_upload(
            f"document{extension}",
            b"Test content",
        )

        stored_path, _ = await save_upload(upload)

        assert stored_path.endswith(extension)


@pytest.mark.asyncio
async def test_save_upload_closes_file_after_success():
    upload = create_upload("invoice.pdf", b"Content")

    await save_upload(upload)

    assert upload.file.closed


@pytest.mark.asyncio
async def test_save_upload_closes_file_after_failure():
    upload = create_upload("invoice.exe", b"Content")

    with pytest.raises(UnsupportedFileTypeError):
        await save_upload(upload)

    assert upload.file.closed