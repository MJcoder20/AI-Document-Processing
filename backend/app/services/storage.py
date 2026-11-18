
import uuid
from pathlib import Path
from tempfile import SpooledTemporaryFile

from fastapi import UploadFile

from app.core.config import settings
from app.services.s3_storage import upload_fileobj


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
    Save an uploaded file using local or S3 storage.

    Returns:
        A tuple containing the storage path or object key and file size.
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

        if settings.storage_provider == "s3":
            stored_filename = f"{uuid.uuid4()}{extension}"
            file_size = 0

            with SpooledTemporaryFile(
                max_size=CHUNK_SIZE,
                mode="w+b",
            ) as temporary_file:
                while chunk := await upload_file.read(CHUNK_SIZE):
                    file_size += len(chunk)

                    if file_size > max_size_bytes:
                        raise FileTooLargeError(
                            f"File exceeds the maximum size of "
                            f"{settings.max_upload_size_mb} MB."
                        )

                    temporary_file.write(chunk)

                temporary_file.seek(0)

                upload_fileobj(
                    temporary_file,
                    stored_filename,
                    upload_file.content_type or "application/octet-stream",
                )

            return stored_filename, file_size

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
