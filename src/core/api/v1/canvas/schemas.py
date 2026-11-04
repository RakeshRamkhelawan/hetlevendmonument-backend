"""
Canvas API Schemas

Standard response and shared Pydantic models for canvas endpoints.
"""

from typing import Optional

from pydantic import BaseModel


class StandardResponse(BaseModel):
    """Standard API response wrapper for canvas endpoints."""

    success: bool = True
    data: dict[str, object] | list[object] | None = None
    error: str | None = None
    message: str | None = None
