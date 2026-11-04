import logging
import os
import shutil
import uuid
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

logger = logging.getLogger(__name__)


class AttachmentService:
    """
    Handles secure, tenant-isolated file storage for agent signals.
    """

    def __init__(self, base_path: str = "data/uploads") -> None:
        self.base_path = base_path
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path, exist_ok=True)

    async def store_attachment(self, tenant_id: int, file: UploadFile) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Stores a file and returns metadata."""
        tenant_path = os.path.join(self.base_path, str(tenant_id))
        os.makedirs(tenant_path, exist_ok=True)

        file_id = str(uuid.uuid4())
        extension = os.path.splitext(file.filename or "")[1]
        stored_filename = f"{file_id}{extension}"
        file_path = os.path.join(tenant_path, stored_filename)

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            logger.info(f"Attachment stored: {file_path} for tenant {tenant_id}")

            return {
                "id": file_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "storage_path": file_path,
                "size_bytes": os.path.getsize(file_path),
            }
        except Exception as e:
            logger.error(f"Failed to store attachment: {e}")
            raise

    def get_attachment_path(self, tenant_id: int, storage_path: str) -> str | None:
        """Validates and returns the path if it belongs to the tenant."""
        # Simple path traversal protection - check tenant_id is a path component
        # Use path separator to ensure we match the tenant directory, not random occurrences
        import os

        path_parts = storage_path.split(os.sep)
        if str(tenant_id) not in path_parts:
            logger.warning(f"Unauthorized access attempt to {storage_path} by tenant {tenant_id}")
            return None
        return storage_path if os.path.exists(storage_path) else None
