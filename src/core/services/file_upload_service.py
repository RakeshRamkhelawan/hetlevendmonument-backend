"""
SC-9.1: File Upload Service with S3 Support
Handles file uploads with local and S3 storage backends.
"""

import logging
import mimetypes
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Optional

logger = logging.getLogger(__name__)

# Try to import boto3
boto3: Any = None
ClientError: type[Exception] = Exception
try:
    import boto3 as _boto3
    from botocore.exceptions import ClientError as _ClientError

    boto3 = _boto3
    ClientError = _ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False


@dataclass
class UploadedFile:
    """Represents an uploaded file."""

    id: str
    filename: str
    original_filename: str
    content_type: str
    size: int
    storage_path: str
    url: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def upload(self, file: BinaryIO, filename: str, content_type: str) -> UploadedFile:
        pass

    @abstractmethod
    async def download(self, file_id: str) -> bytes | None:
        pass

    @abstractmethod
    async def delete(self, file_id: str) -> bool:
        pass

    @abstractmethod
    async def get_url(self, file_id: str, expires_in: int = 3600) -> str | None:
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_path: str = "uploads") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def upload(self, file: BinaryIO, filename: str, content_type: str) -> UploadedFile:
        file_id = str(uuid.uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"

        # Organize by date
        date_path = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        full_path = self.base_path / date_path
        full_path.mkdir(parents=True, exist_ok=True)

        file_path = full_path / safe_filename

        # Read and save file
        content = file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        return UploadedFile(
            id=file_id,
            filename=safe_filename,
            original_filename=filename,
            content_type=content_type,
            size=len(content),
            storage_path=str(file_path),
            url=f"/files/{date_path}/{safe_filename}",
        )

    async def download(self, file_id: str) -> bytes | None:
        # Search for file
        for file_path in self.base_path.rglob(f"{file_id}*"):
            if file_path.is_file():
                return file_path.read_bytes()
        return None

    async def delete(self, file_id: str) -> bool:
        for file_path in self.base_path.rglob(f"{file_id}*"):
            if file_path.is_file():
                file_path.unlink()
                return True
        return False

    async def get_url(self, file_id: str, expires_in: int = 3600) -> str | None:
        for file_path in self.base_path.rglob(f"{file_id}*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.base_path)
                return f"/files/{rel_path}"
        return None


class S3StorageBackend(StorageBackend):
    """Amazon S3 storage backend."""

    def __init__(
        self,
        bucket_name: str,
        region: str = "eu-west-1",
        access_key: str | None = None,
        secret_key: str | None = None,
        prefix: str = "uploads",
    ) -> None:
        if not S3_AVAILABLE:
            raise RuntimeError("boto3 not installed. Install with: pip install boto3")

        self.bucket_name = bucket_name
        self.region = region
        self.prefix = prefix

        if boto3 is None:
            raise RuntimeError("boto3 not installed")
        self.s3 = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=secret_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
        )

    async def upload(self, file: BinaryIO, filename: str, content_type: str) -> UploadedFile:
        file_id = str(uuid.uuid4())
        ext = Path(filename).suffix

        # Organize by date
        date_path = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        s3_key = f"{self.prefix}/{date_path}/{file_id}{ext}"

        content = file.read()

        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content,
                ContentType=content_type,
                Metadata={"original_filename": filename},
            )

            return UploadedFile(
                id=file_id,
                filename=f"{file_id}{ext}",
                original_filename=filename,
                content_type=content_type,
                size=len(content),
                storage_path=s3_key,
                url=await self.get_url(file_id),
            )
        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            raise

    async def download(self, file_id: str) -> bytes | None:
        # Find object by prefix search
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket_name, Prefix=self.prefix, MaxKeys=1000
            )

            for obj in response.get("Contents", []):
                if file_id in obj["Key"]:
                    result = self.s3.get_object(Bucket=self.bucket_name, Key=obj["Key"])
                    body_bytes: bytes = result["Body"].read()
                    return body_bytes

            return None
        except ClientError as e:
            logger.error(f"S3 download failed: {e}")
            return None

    async def delete(self, file_id: str) -> bool:
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=self.prefix)

            for obj in response.get("Contents", []):
                if file_id in obj["Key"]:
                    self.s3.delete_object(Bucket=self.bucket_name, Key=obj["Key"])
                    return True

            return False
        except ClientError as e:
            logger.error(f"S3 delete failed: {e}")
            return False

    async def get_url(self, file_id: str, expires_in: int = 3600) -> str | None:
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=self.prefix)

            for obj in response.get("Contents", []):
                if file_id in obj["Key"]:
                    url_result: str = self.s3.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": self.bucket_name, "Key": obj["Key"]},
                        ExpiresIn=expires_in,
                    )
                    return url_result

            return None
        except ClientError as e:
            logger.error(f"S3 URL generation failed: {e}")
            return None


class FileUploadService:
    """
    SC-9.1: Main file upload service.

    Supports multiple storage backends with a unified interface.
    """

    ALLOWED_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self, backend: StorageBackend | None = None) -> None:
        self.backend = backend or LocalStorageBackend()

    async def upload(
        self, file: BinaryIO, filename: str, content_type: str | None = None
    ) -> UploadedFile:
        """Upload a file."""
        # Validate extension
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError(f"File type not allowed: {ext}")

        # Detect content type
        if not content_type:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        return await self.backend.upload(file, filename, content_type)

    async def download(self, file_id: str) -> bytes | None:
        """Download a file."""
        return await self.backend.download(file_id)

    async def delete(self, file_id: str) -> bool:
        """Delete a file."""
        return await self.backend.delete(file_id)

    async def get_url(self, file_id: str, expires_in: int = 3600) -> str | None:
        """Get a URL for a file."""
        return await self.backend.get_url(file_id, expires_in)


# Factory function
def create_file_service() -> FileUploadService:
    """Create file service based on environment."""
    storage_type = os.getenv("FILE_STORAGE", "local")

    backend: StorageBackend
    if storage_type == "s3":
        backend = S3StorageBackend(
            bucket_name=os.getenv("S3_BUCKET", "sanskriti-uploads"),
            region=os.getenv("S3_REGION", "eu-west-1"),
        )
    else:
        backend = LocalStorageBackend(base_path=os.getenv("UPLOAD_PATH", "uploads"))

    return FileUploadService(backend)


# Singleton
file_service = create_file_service()
