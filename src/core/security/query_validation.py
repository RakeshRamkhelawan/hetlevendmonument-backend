"""
Query Validation Utilities for SQLAlchemy
=========================================

Provides safe utilities for building database queries with user input.
Prevents SQL injection by enforcing parameterized queries and validating
all inputs before they reach the database layer.

CRITICAL: This module ensures all user inputs are properly validated
before use in SQLAlchemy queries.

Usage:
    from src.core.security.query_validation import (
        SafeQueryBuilder,
        safe_filter_by_id,
        safe_like_filter,
        validate_sort_column,
    )

    # Safe filtering by ID
    query = safe_filter_by_id(select(User), User.tenant_id, tenant_id_input)

    # Safe LIKE filter
    query = safe_like_filter(select(User), User.name, search_term)

    # Validate sort column
    column = validate_sort_column(sort_by, allowed_columns=["name", "created_at"])

References:
- OWASP: SQL Injection Prevention Cheat Sheet
- SQLAlchemy: Using Textual SQL Safely
"""

import logging
from typing import Any, Generic, Optional, TypeVar
from collections.abc import Callable

from sqlalchemy import Column, Select, asc, desc
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.expression import ColumnElement

from src.core.security.input_sanitization import (
    InjectionProtector,
    escape_like_pattern,
    validate_integer_id,
    validate_search_query,
    validate_string_input,
)

logger = logging.getLogger(__name__)

RowT = TypeVar("RowT", bound=tuple[Any, ...])


# ============================================================================
# SAFE QUERY BUILDER
# ============================================================================


class SafeQueryBuilder(Generic[RowT]):
    """
    Builder for constructing safe SQLAlchemy queries with validated inputs.

    Features:
    - All inputs validated before use
    - Parameterized queries enforced
    - Column whitelist validation
    - Injection pattern detection

    Usage:
        builder = SafeQueryBuilder(select(User))
        query = (builder
            .filter_by_id(User.tenant_id, tenant_id)
            .filter_like(User.name, search_term)
            .order_by(User.created_at, descending=True)
            .limit(100)
            .build())
    """

    def __init__(
        self,
        base_query: Select[RowT],
        allowed_columns: set[str] | None = None,
    ) -> None:
        """
        Initialize the safe query builder.

        Args:
            base_query: The base SQLAlchemy select statement
            allowed_columns: set[str] of column names that can be used in filters/sorts
        """
        self.query: Select[RowT] = base_query
        self.allowed_columns = allowed_columns or set()
        self._protector = InjectionProtector()

    def _validate_column_name(self, column_name: str) -> bool:
        """Check if column name is in allowed list."""
        if not self.allowed_columns:
            return True  # No whitelist = allow all (less secure)
        return column_name in self.allowed_columns

    def filter_by_id(
        self,
        column: ColumnElement[int],
        value: object,
        field_name: str = "id",
    ) -> "SafeQueryBuilder[RowT]":
        """
        Add a safe ID filter.

        Args:
            column: SQLAlchemy column to filter
            value: ID value (will be validated)
            field_name: Name for error messages

        Returns:
            Self for chaining
        """
        validated_id = validate_integer_id(value, field_name=field_name)
        self.query = self.query.where(column == validated_id)
        return self

    def filter_by_ids(
        self,
        column: ColumnElement[int],
        values: list[object],
        field_name: str = "ids",
        max_ids: int = 1000,
    ) -> "SafeQueryBuilder[RowT]":
        """
        Add a safe IN filter for multiple IDs.

        Args:
            column: SQLAlchemy column to filter
            values: list[object] of ID values (each will be validated)
            field_name: Name for error messages
            max_ids: Maximum number of IDs allowed

        Returns:
            Self for chaining
        """
        if len(values) > max_ids:
            raise ValueError(f"{field_name}: Too many IDs (max: {max_ids})")

        validated_ids = [
            validate_integer_id(v, field_name=f"{field_name}[{i}]") for i, v in enumerate(values)
        ]
        self.query = self.query.where(column.in_(validated_ids))
        return self

    def filter_like(
        self,
        column: ColumnElement[str],
        pattern: object,
        field_name: str = "search",
        case_sensitive: bool = False,
    ) -> "SafeQueryBuilder[RowT]":
        """
        Add a safe LIKE filter.

        Args:
            column: SQLAlchemy column to filter
            pattern: Search pattern (will be validated and escaped)
            field_name: Name for error messages
            case_sensitive: Whether the search is case-sensitive

        Returns:
            Self for chaining
        """
        validated_pattern = validate_search_query(pattern, field_name=field_name)

        if not validated_pattern:
            return self  # Empty pattern = no filter

        # Escape LIKE special characters
        escaped = escape_like_pattern(validated_pattern)

        if case_sensitive:
            self.query = self.query.where(column.like(f"%{escaped}%", escape="\\"))
        else:
            self.query = self.query.where(column.ilike(f"%{escaped}%", escape="\\"))

        return self

    def filter_equals(
        self,
        column: ColumnElement[object],
        value: str | int | float | bool,
        field_name: str = "field",
        max_length: int = 500,
    ) -> "SafeQueryBuilder[RowT]":
        """
        Add a safe equality filter.

        Args:
            column: SQLAlchemy column to filter
            value: Value to match (will be validated)
            field_name: Name for error messages
            max_length: Maximum string length

        Returns:
            Self for chaining
        """
        if isinstance(value, str):
            validated = validate_string_input(
                value,
                max_length=max_length,
                field_name=field_name,
            )
            self.query = self.query.where(column == validated)
        elif isinstance(value, (int, float)):
            self.query = self.query.where(column == value)
        elif isinstance(value, bool):
            self.query = self.query.where(column == value)
        else:
            raise TypeError(f"{field_name}: Unsupported type {type(value).__name__}")

        return self

    def filter_in_list(
        self,
        column: ColumnElement[str],
        values: list[str],
        field_name: str = "values",
        max_items: int = 100,
        max_item_length: int = 200,
    ) -> "SafeQueryBuilder[RowT]":
        """
        Add a safe IN filter for string values.

        Args:
            column: SQLAlchemy column to filter
            values: list[str] of string values (each will be validated)
            field_name: Name for error messages
            max_items: Maximum number of items
            max_item_length: Maximum length per item

        Returns:
            Self for chaining
        """
        if len(values) > max_items:
            raise ValueError(f"{field_name}: Too many values (max: {max_items})")

        validated_values = [
            validate_string_input(
                v,
                max_length=max_item_length,
                field_name=f"{field_name}[{i}]",
            )
            for i, v in enumerate(values)
        ]
        self.query = self.query.where(column.in_(validated_values))
        return self

    def order_by_column(
        self,
        column_name: str,
        model_class: type[DeclarativeBase],
        descending: bool = False,
        allowed_columns: set[str] | None = None,
    ) -> "SafeQueryBuilder[RowT]":
        """
        Add safe ORDER BY clause with column validation.

        Args:
            column_name: Name of the column to sort by
            model_class: SQLAlchemy model class
            descending: Sort in descending order
            allowed_columns: Override for allowed columns

        Returns:
            Self for chaining
        """
        whitelist = allowed_columns or self.allowed_columns

        # Validate column name
        validated_name = validate_string_input(
            column_name,
            max_length=100,
            field_name="sort_column",
        )

        # Check whitelist
        if whitelist and validated_name not in whitelist:
            raise ValueError(
                f"Sort column '{validated_name}' not allowed. "
                f"Allowed columns: {sorted(whitelist)}"
            )

        # Get the actual column from the model
        if not hasattr(model_class, validated_name):
            raise ValueError(f"Column '{validated_name}' does not exist")

        column = getattr(model_class, validated_name)

        if descending:
            self.query = self.query.order_by(desc(column))
        else:
            self.query = self.query.order_by(asc(column))

        return self

    def limit(self, value: int, max_limit: int = 1000) -> "SafeQueryBuilder[RowT]":
        """
        Add safe LIMIT clause.

        Args:
            value: Number of rows to return
            max_limit: Maximum allowed limit

        Returns:
            Self for chaining
        """
        if not isinstance(value, int) or value < 0:
            raise ValueError("Limit must be a non-negative integer")

        if value > max_limit:
            raise ValueError(f"Limit exceeds maximum of {max_limit}")

        self.query = self.query.limit(value)
        return self

    def offset(self, value: int, max_offset: int = 100000) -> "SafeQueryBuilder[RowT]":
        """
        Add safe OFFSET clause.

        Args:
            value: Number of rows to skip
            max_offset: Maximum allowed offset

        Returns:
            Self for chaining
        """
        if not isinstance(value, int) or value < 0:
            raise ValueError("Offset must be a non-negative integer")

        if value > max_offset:
            raise ValueError(f"Offset exceeds maximum of {max_offset}")

        self.query = self.query.offset(value)
        return self

    def build(self) -> Select[RowT]:
        """Build and return the query."""
        return self.query


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def safe_filter_by_id(
    query: Select[RowT],
    column: ColumnElement[int],
    value: object,
    field_name: str = "id",
) -> Select[RowT]:
    """
    Add a safe ID filter to a query.

    Args:
        query: SQLAlchemy select statement
        column: Column to filter on
        value: ID value (will be validated)
        field_name: Name for error messages

    Returns:
        Modified query with filter applied
    """
    validated_id = validate_integer_id(value, field_name=field_name)
    return query.where(column == validated_id)


def safe_filter_by_tenant(
    query: Select[RowT],
    column: ColumnElement[int],
    tenant_id: object,
) -> Select[RowT]:
    """
    Add a safe tenant filter to a query.

    CRITICAL: Use this for all tenant-filtered queries.

    Args:
        query: SQLAlchemy select statement
        column: Tenant ID column
        tenant_id: Tenant ID (will be strictly validated)

    Returns:
        Modified query with tenant filter
    """
    validated_tenant_id = validate_integer_id(
        tenant_id,
        field_name="tenant_id",
        min_value=1,
    )
    return query.where(column == validated_tenant_id)


def safe_like_filter(
    query: Select[RowT],
    column: ColumnElement[str],
    pattern: str,
    field_name: str = "search",
    case_sensitive: bool = False,
) -> Select[RowT]:
    """
    Add a safe LIKE filter to a query.

    Args:
        query: SQLAlchemy select statement
        column: Column to search
        pattern: Search pattern
        field_name: Name for error messages
        case_sensitive: Whether search is case-sensitive

    Returns:
        Modified query with LIKE filter
    """
    validated_pattern = validate_search_query(pattern, field_name=field_name)

    if not validated_pattern:
        return query  # Empty = no filter

    escaped = escape_like_pattern(validated_pattern)

    if case_sensitive:
        return query.where(column.like(f"%{escaped}%", escape="\\"))
    else:
        return query.where(column.ilike(f"%{escaped}%", escape="\\"))


def validate_sort_column(
    column_name: str,
    allowed_columns: set[str],
    default: str | None = None,
) -> str:
    """
    Validate a sort column name against a whitelist.

    Args:
        column_name: Column name to validate
        allowed_columns: set[str] of allowed column names
        default: Default column if validation fails (if None, raises error)

    Returns:
        Validated column name

    Raises:
        ValueError: If column not in whitelist and no default
    """
    validated = validate_string_input(
        column_name,
        max_length=100,
        field_name="sort_column",
        allow_empty=bool(default),
    )

    if not validated and default:
        return default

    if validated not in allowed_columns:
        if default:
            logger.warning(f"Invalid sort column '{validated}', using default '{default}'")
            return default
        raise ValueError(
            f"Invalid sort column '{validated}'. " f"Allowed: {sorted(allowed_columns)}"
        )

    return validated


def validate_pagination(
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
) -> tuple[int, int, int]:
    """
    Validate pagination parameters.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        max_page_size: Maximum allowed page size

    Returns: tuple[int, int, int] of (validated_page, validated_page_size, offset)
    """
    # Validate page
    if not isinstance(page, int) or page < 1:
        page = 1

    # Validate page_size
    if not isinstance(page_size, int) or page_size < 1:
        page_size = 20
    elif page_size > max_page_size:
        page_size = max_page_size

    # Calculate offset
    offset = (page - 1) * page_size

    return page, page_size, offset


def safe_json_contains_filter(
    query: Select[RowT],
    column: ColumnElement[Any],  # TODO(TYPE): replace Any with concrete type
    key: str,
    value: str | int | bool | float | None,
    field_name: str = "json_filter",
) -> Select[RowT]:
    """
    Add a safe JSON containment filter (PostgreSQL).

    Args:
        query: SQLAlchemy select statement
        column: JSON/JSONB column
        key: Key to search for
        value: Value to match
        field_name: Name for error messages

    Returns:
        Modified query with JSON filter
    """
    # Validate key
    key = validate_string_input(
        key,
        max_length=100,
        field_name=f"{field_name}_key",
    )

    # Validate value based on type
    if isinstance(value, str):
        value = validate_string_input(
            value,
            max_length=500,
            field_name=f"{field_name}_value",
        )
    elif isinstance(value, int):
        value = validate_integer_id(
            value,
            field_name=f"{field_name}_value",
            min_value=-2147483648,  # Allow negative for non-ID integers
        )
    elif not isinstance(value, (bool, float, type(None))):
        raise TypeError(f"{field_name}: Unsupported value type {type(value).__name__}")

    # Build the filter using PostgreSQL JSONB containment
    return query.where(column.contains({key: value}))


# ============================================================================
# QUERY PARAMETER VALIDATION FOR ENDPOINTS
# ============================================================================


class QueryParams:
    """
    Validated query parameters container.

    Usage:
        @router.get("/items")
        async def list_items(
            page: int = 1,
            page_size: int = 20,
            search: str = "",
            sort_by: str = "created_at",
        ):
            params = QueryParams(
                page=page,
                page_size=page_size,
                search=search,
                sort_by=sort_by,
                allowed_sort_columns={"name", "created_at", "updated_at"},
            )
            # Use params.page, params.search, etc.
    """

    def __init__(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        sort_by: str = "",
        sort_order: str = "asc",
        allowed_sort_columns: set[str] | None = None,
        max_page_size: int = 100,
        default_sort_column: str = "id",
    ) -> None:
        # Validate pagination
        self.page, self.page_size, self.offset = validate_pagination(
            page=page,
            page_size=page_size,
            max_page_size=max_page_size,
        )

        # Validate search
        self.search = (
            validate_search_query(
                search or "",
                field_name="search",
            )
            if search
            else ""
        )

        # Validate sort column
        if allowed_sort_columns:
            self.sort_by = validate_sort_column(
                sort_by or default_sort_column,
                allowed_columns=allowed_sort_columns,
                default=default_sort_column,
            )
        else:
            self.sort_by = validate_string_input(
                sort_by or default_sort_column,
                max_length=100,
                field_name="sort_by",
            )

        # Validate sort order
        sort_order_lower = (sort_order or "asc").lower()
        if sort_order_lower not in ("asc", "desc"):
            sort_order_lower = "asc"
        self.sort_order = sort_order_lower
        self.descending = sort_order_lower == "desc"

    def to_dict(self) -> dict[str, int | str]:
        """Convert to dictionary for logging/debugging."""
        return {
            "page": self.page,
            "page_size": self.page_size,
            "offset": self.offset,
            "search": self.search,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
        }


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Classes
    "SafeQueryBuilder",
    "QueryParams",
    # Filter functions
    "safe_filter_by_id",
    "safe_filter_by_tenant",
    "safe_like_filter",
    "safe_json_contains_filter",
    # Validation functions
    "validate_sort_column",
    "validate_pagination",
]
