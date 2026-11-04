"""
Pagination Utility

Standardized pagination parameters and helpers for API endpoints.

Part of SC-8.2 implementation.
"""

from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy.sql import Select

T = TypeVar("T")


class PageParams:
    """
    Dependency for pagination parameters.

    Usage:
        @router.get("/items")
        async def list_items(pagination: PageParams = Depends()):
            skip = pagination.skip
            limit = pagination.limit
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        size: int = Query(20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.size = size
        self.skip = (page - 1) * size
        self.limit = size


class PageInfo(BaseModel):
    """Pagination metadata for responses."""

    page: int = Field(..., description="Current page number")
    size: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of items")
    pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.

    Usage:
        return PaginatedResponse[UserResponse](
            items=users,
            page_info=PageInfo(...)
        )
    """

    items: list[T]
    page_info: PageInfo


def create_page_info(page: int, size: int, total: int) -> PageInfo:
    """
    Create PageInfo from pagination parameters.

    Args:
        page: Current page number
        size: Items per page
        total: Total number of items

    Returns:
        PageInfo object with computed values
    """
    pages = (total + size - 1) // size if size > 0 else 0
    return PageInfo(
        page=page,
        size=size,
        total=total,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )


def paginate_query(query: Select[Any], params: PageParams) -> Select[Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Apply pagination to a SQLAlchemy query.

    Args:
        query: SQLAlchemy query object
        params: PageParams instance

    Returns:
        Query with offset and limit applied
    """
    return query.offset(params.skip).limit(params.limit)
