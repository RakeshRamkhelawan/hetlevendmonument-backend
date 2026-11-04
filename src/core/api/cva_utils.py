"""Shared utilities for CVA API endpoints."""

from fastapi import HTTPException, status


def handle_cva_value_error(e: ValueError, context: str = "operation") -> HTTPException:
    """
    Convert CVAService ValueError to appropriate HTTPException.

    Error Mapping:
        - "not found or access denied" -> 404 Not Found
        - other -> 422 Unprocessable Entity
    """
    error_msg = str(e).lower()

    if "not found or access denied" in error_msg:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied",
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
