import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


CHUNK_SIZE = 1024 * 1024  # 1 MB

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".txt",
}


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the configured size limit."""


class UnsupportedFileTypeError(Exception):
    """Raised when an uploaded file has an unsupported extension."""


async def save_upload(upload_file: UploadFile) -> tuple[str, int]:
    """
    Save an uploaded file using a generated UUID filename.

    Returns:
        A tuple containing the stored file path and file size in bytes.
    """

    destination = None

    try:
        original_filename = upload_file.filename or ""
        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"Unsupported file extension: {extension or 'none'}"
            )

        max_size_bytes = settings.max_upload_size_mb * 1024 * 1024

        storage_directory = Path(settings.document_storage_dir).resolve()
        storage_directory.mkdir(parents=True, exist_ok=True)

        stored_filename = f"{uuid.uuid4()}{extension}"
        destination = storage_directory / stored_filename

        file_size = 0

        with destination.open("wb") as destination_file:
            while chunk := await upload_file.read(CHUNK_SIZE):
                file_size += len(chunk)

                if file_size > max_size_bytes:
                    raise FileTooLargeError(
                        f"File exceeds the maximum size of "
                        f"{settings.max_upload_size_mb} MB."
                    )

                destination_file.write(chunk)

        return str(destination), file_size

    except Exception:
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise

    finally:
        await upload_file.close()