from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class FocusBuilderFlow(Base):  # type: ignore[misc]
    """
    Focus Builder Flow Model.

    Stores the visual representation (React Flow) and mapping to ActivePieces.
    """

    __tablename__ = "focus_builder_flows"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), default="")
    react_flow_graph: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )

    # ActivePieces Mapping
    activepieces_flow_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    activepieces_project_id: Mapped[str | None] = mapped_column(String(255))
    activepieces_version: Mapped[int | None] = mapped_column(Integer, default=1)

    is_published: Mapped[bool | None] = mapped_column(Boolean, default=False, index=True)

    # Optimistic locking version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Audit
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
