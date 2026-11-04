"""Collective Knowledge Model - Shared agent memory with vector search."""

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID as PyUUID

from sqlalchemy.engine import Dialect

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class EmbeddingType(TypeDecorator[list[float]]):
    """Portable embedding column: Vector(384) in prod, LargeBinary in tests.

    CRITICAL FIX #5: Prevents type mismatch between PostgreSQL and SQLite.
    """

    impl = LargeBinary
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> object:  # type: ignore[override]
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(384))
        return dialect.type_descriptor(LargeBinary())

    def process_bind_param(
        self,
        value: object,
        dialect: Dialect,
    ) -> list[float] | None:
        if value is None:
            return None
        if dialect.name != "postgresql":
            import numpy as np

            return cast(list[float] | None, np.array(value, dtype=np.float32).tobytes())
        return cast(list[float] | None, value)

    def process_result_value(
        self,
        value: object,
        dialect: Dialect,
    ) -> list[float] | None:
        if value is None:
            return None
        if dialect.name != "postgresql":
            import numpy as np

            # Expliciet getypeerde tussenvariabele i.p.v. cast()/type:ignore op de
            # return-regel: numpy's eigen stubs typeren ndarray.tolist() niet overal
            # hetzelfde (Any in oudere versies, list[float] in recentere) -- een cast
            # is dan "redundant" in de ene omgeving en een ignore "unused" in de
            # andere. Deze vorm is in beide gevallen stil.
            resultaat: list[float] = np.frombuffer(cast(bytes, value), dtype=np.float32).tolist()
            return resultaat
        return cast(list[float] | None, value)


class CollectiveKnowledge(Base):  # type: ignore[misc]
    """Shared knowledge base for the symbiotic organism.

    Uses HNSW index for fast semantic search across all agent experiences.
    All knowledge is strictly tenant-isolated.
    """

    __tablename__ = "collective_knowledge"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # [RED] CRITICAL: Tenant isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content
    knowledge_type = mapped_column(String, nullable=False, index=True)  # pattern, solution, insight
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # For deduplication
    content: Mapped[object] = mapped_column(
        JSONB, nullable=False
    )  # The actual knowledge -- JSONB is heterogeneous

    # Vector embedding for semantic search
    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingType
    )  # list[float] in Postgres, bytes in SQLite (TypeDecorator handles conversion)
    embedding_model: Mapped[str | None] = mapped_column(String, default="all-MiniLM-L6-v2")

    # Metadata
    source_agent: Mapped[str | None] = mapped_column(String)  # Which agent contributed this
    confidence: Mapped[float | None] = mapped_column(Float, default=0.5)  # 0.0 - 1.0
    access_count: Mapped[int | None] = mapped_column(Integer, default=0)  # How many times retrieved

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Indexes
    __table_args__ = (
        Index("idx_collective_knowledge_tenant_type", "tenant_id", "knowledge_type"),
        Index("idx_collective_knowledge_hash", "content_hash"),
        # HNSW index created via Alembic migration
    )

    @validates("tenant_id")
    def validate_tenant_id(self, key: str, tenant_id: int) -> int:
        if not tenant_id or tenant_id <= 0:
            raise ValueError(f"Invalid tenant_id: {tenant_id}")
        return tenant_id

    @validates("confidence")
    def validate_confidence(self, key: str, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {value}")
        return value
