"""
Pydantic schemas for Document CRUD operations.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    """Schema for document response."""

    id: int
    tenant_id: int
    filename: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    storage_backend: str
    storage_path: str | None = None
    checksum_sha256: str | None = None
    status: str
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Schema for list of documents with pagination."""

    data: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DocumentUpdateRequest(BaseModel):
    """Schema for updating document metadata."""

    filename: str | None = Field(None, min_length=1, max_length=500)
    status: str | None = Field(None, max_length=50)
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")  # TODO(TYPE): replace Any with concrete type
