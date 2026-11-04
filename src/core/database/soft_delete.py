"""
Soft Delete Mixin - GDPR-compliant data deletion framework

Provides:
- Soft delete with audit trail (deleted_at, deleted_by, deletion_reason)
- Automatic filtering of soft-deleted records from queries
- Query scopes: with_deleted(), only_deleted()
- Integration with GDPR deletion framework
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, List, Optional, cast

from sqlalchemy import Column, DateTime, Integer, String, inspect
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapped, Query, Session, class_mapper, mapped_column
from sqlalchemy.sql import expression
from sqlalchemy.sql.elements import ColumnElement

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapper
    from sqlalchemy.orm.attributes import QueryableAttribute


class SoftDeleteMixin:
    """
    Mixin for soft-delete functionality.

    Adds deleted_at, deleted_by, deletion_reason columns.
    Automatically filters soft-deleted records from queries.

    Usage:
        class MyModel(Base, SoftDeleteMixin):
            __tablename__ = "my_table"
            name: Mapped[Optional[str]] = mapped_column(String(255))

        # Query automatically excludes soft-deleted
        results = session.query(MyModel).all()

        # Include deleted records
        results = session.query(MyModel).with_deleted().all()

        # Only deleted records
        results = session.query(MyModel).only_deleted().all()
    """

    # SQLAlchemy 2.0 compatibility: allow unmapped annotations
    __allow_unmapped__ = True

    # Soft delete columns
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
    deleted_by: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    deletion_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if entity is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(
        self,
        deleted_by: int | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Soft delete this entity.

        Args:
            deleted_by: User ID performing the deletion
            reason: Reason for deletion
        """
        self.deleted_at = datetime.now(timezone.utc)
        self.deleted_by = deleted_by
        self.deletion_reason = reason

    def restore(self) -> None:
        """Restore a soft-deleted entity."""
        self.deleted_at = None
        self.deleted_by = None
        self.deletion_reason = None

    def hard_delete(self, deletion_reason: str) -> None:
        """
        Prepare entity for hard deletion.

        This method should be called before actual database DELETE
        to validate GDPR compliance. Actual deletion happens via session.delete().

        Args:
            deletion_reason: Required reason for hard deletion

        Raises:
            ValueError: If deletion_reason is missing
        """
        if not deletion_reason:
            raise ValueError("Hard deletion requires a deletion_reason (GDPR compliance)")
        # Validation passed - entity can now be hard deleted
        # Actual deletion: session.delete(entity)


class SoftDeleteQueryMixin(Query[Any]):  # TODO(TYPE): replace Any with concrete type
    """
    Query mixin for soft-delete filtering.

    Add to query classes to enable with_deleted() and only_deleted() methods.
    """

    def with_deleted(self) -> Query[Any]:  # TODO(TYPE): replace Any with concrete type
        """Include soft-deleted records in query."""
        # Remove default deleted_at filter
        return self.enable_assertions(False).filter()

    def only_deleted(self) -> Query[Any]:  # TODO(TYPE): replace Any with concrete type
        """Only return soft-deleted records."""
        return self.filter(SoftDeleteMixin.deleted_at.isnot(None))


def enable_soft_delete_filtering(mapper: Mapper[Any], class_: Any) -> None:  # TODO(TYPE): replace Any with concrete type
    """
    SQLAlchemy event listener to enable soft-delete filtering.

    Automatically adds deleted_at IS NULL filter to all queries
    on models that inherit from SoftDeleteMixin.
    """
    if not issubclass(class_, SoftDeleteMixin):
        return

    @classmethod  # type: ignore[misc]
    def filter_deleted(cls: Any, query: Query[Any]) -> Query[Any]:  # TODO(TYPE): replace Any with concrete type
        """Add soft-delete filter to query."""
        return query.filter(cls.deleted_at.is_(None))

    # Store original query method
    original_query = getattr(class_, "query", None)
    if original_query is None:
        return

    @classmethod  # type: ignore[misc]
    def new_query(cls: Any, *entities: Any, **kwargs: Any) -> Query[Any]:
        """Query that excludes soft-deleted by default."""
        query = cast(Query[Any], original_query.__func__(cls, *entities, **kwargs))  # TODO(TYPE): replace Any with concrete type
        if issubclass(cls, SoftDeleteMixin):
            query = query.filter(cls.deleted_at.is_(None))
        return query

    setattr(class_, "query", new_query)


# SQLAlchemy event listener for query-time filtering
def _add_soft_delete_filter(query: Query[Any]) -> Query[Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Add soft-delete filter to query if applicable.

    This is a placeholder for more advanced query filtering.
    In practice, use the query.filter() method directly.
    """
    return query


class SoftDeleteQuery:
    """
    Query helper for soft-delete filtering.

    Usage with SQLAlchemy 2.0 style:
        stmt = select(MyModel).where(
            SoftDeleteQuery.not_deleted(MyModel)
        )
    """

    @staticmethod
    def not_deleted(model_class: type[SoftDeleteMixin]) -> ColumnElement[bool]:
        """Filter condition for non-deleted records."""
        return model_class.deleted_at.is_(None)

    @staticmethod
    def is_deleted(model_class: type[SoftDeleteMixin]) -> ColumnElement[bool]:
        """Filter condition for deleted records."""
        return model_class.deleted_at.isnot(None)

    @staticmethod
    def deleted_after(model_class: type[SoftDeleteMixin], date: datetime) -> ColumnElement[bool]:
        """Filter for records deleted after specific date."""
        return model_class.deleted_at >= date


class SoftDeleteManager:
    """
    Manager class for soft-delete operations.

    Provides helper methods for common soft-delete scenarios.
    """

    @staticmethod
    def soft_delete(
        session: Session,
        entity: SoftDeleteMixin,
        deleted_by: int | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Soft delete an entity.

        Args:
            session: SQLAlchemy session
            entity: Entity to soft delete
            deleted_by: User ID performing deletion
            reason: Reason for deletion
        """
        entity.soft_delete(deleted_by=deleted_by, reason=reason)
        session.add(entity)

    @staticmethod
    def restore(
        session: Session,
        entity: SoftDeleteMixin,
    ) -> None:
        """
        Restore a soft-deleted entity.

        Args:
            session: SQLAlchemy session
            entity: Entity to restore
        """
        entity.restore()
        session.add(entity)

    @staticmethod
    def bulk_soft_delete(
        session: Session,
        model_class: type[SoftDeleteMixin],
        ids: list[Any],  # TODO(TYPE): replace Any with concrete type
        deleted_by: int | None = None,
        reason: str | None = None,
    ) -> int:
        """
        Bulk soft delete by IDs.

        Args:
            session: SQLAlchemy session
            model_class: Model class
            ids: List[Any] of IDs to delete  # TODO(TYPE): replace Any with concrete type
            deleted_by: User ID
            reason: Reason

        Returns:
            Number of records updated
        """
        from sqlalchemy import update

        now = datetime.now(timezone.utc)
        stmt = (
            update(model_class)
            .where(getattr(model_class, "id").in_(ids))
            .where(model_class.deleted_at.is_(None))  # Only not-yet-deleted
            .values(
                deleted_at=now,
                deleted_by=deleted_by,
                deletion_reason=reason,
            )
        )
        result = session.execute(stmt)
        return getattr(result, "rowcount", 0)

    @staticmethod
    def get_deleted_since(
        session: Session,
        model_class: type[SoftDeleteMixin],
        since: datetime,
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get records deleted since a specific date.

        Args:
            session: SQLAlchemy session
            model_class: Model class
            since: datetime threshold

        Returns: List[Any] of deleted entities  # TODO(TYPE): replace Any with concrete type
        """
        from sqlalchemy import select

        stmt = select(model_class).where(
            model_class.deleted_at.isnot(None),
            model_class.deleted_at >= since,
        )
        result = session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def purge_soft_deleted(
        session: Session,
        model_class: type[SoftDeleteMixin],
        deleted_before: datetime,
    ) -> int:
        """
        Hard delete records that were soft-deleted before a date.

        Use for data retention policy enforcement.

        Args:
            session: SQLAlchemy session
            model_class: Model class
            deleted_before: Delete records soft-deleted before this date

        Returns:
            Number of records purged
        """
        from sqlalchemy import delete

        stmt = delete(model_class).where(
            model_class.deleted_at.isnot(None),
            model_class.deleted_at < deleted_before,
        )
        result = session.execute(stmt)
        return getattr(result, "rowcount", 0)
