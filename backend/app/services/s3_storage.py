from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


class S3StorageError(Exception):
    """Raised when an S3 storage operation fails."""


def get_s3_client():
    """Create an S3-compatible client for Filebase."""

    if not all([
        settings.s3_endpoint_url,
        settings.s3_bucket_name,
        settings.s3_access_key_id,
        settings.s3_secret_access_key,
    ]):
        raise S3StorageError("S3 storage configuration is incomplete.")

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(signature_version="s3v4"),
    )


def check_bucket_access() -> bool:
    """Check whether the configured bucket is accessible."""

    try:
        client = get_s3_client()
        client.head_bucket(Bucket=settings.s3_bucket_name)
        return True


    except (BotoCoreError, ClientError) as exc:
        raise S3StorageError(
            "Unable to access the configured S3 bucket."
        ) from exc


def upload_fileobj(
    file_obj: BinaryIO,
    key: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload a file-like object and return its object key."""

    try:
        get_s3_client().upload_fileobj(
            file_obj,
            settings.s3_bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return key


    except (BotoCoreError, ClientError) as exc:
        raise S3StorageError("Unable to upload document to S3 storage.") from exc


def download_file_to_path(key: str, destination: Path) -> Path:
    """Download an object to a local temporary or destination path."""

    try:
        get_s3_client().download_file(
            settings.s3_bucket_name,
            key,
            str(destination),
        )
        return destination


    except (BotoCoreError, ClientError) as exc:
        raise S3StorageError("Unable to download document from S3 storage.") from exc


def delete_object(key: str) -> None:
    """Delete an object from the configured bucket."""

    try:
        get_s3_client().delete_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
        )


    except (BotoCoreError, ClientError) as exc:
        raise S3StorageError("Unable to delete document from S3 storage.") from exc


def open_download(key: str):
    """Open an S3 object for streaming."""

    try:
        response = get_s3_client().get_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
        )
        return response["Body"]


    except (BotoCoreError, ClientError) as exc:
        raise S3StorageError("Unable to retrieve document from S3 storage.") from exc
