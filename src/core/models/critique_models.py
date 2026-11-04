"""ORM model voor agent critique persistentie (SP-AGT-005).

CritiqueRecord slaat kwaliteitsbeoordelingen op in PostgreSQL zodat
critique-data bewaard blijft na service-restart en via retention-cleanup
lifecycle beheerd wordt (ADR-019 audit, ADR-005 RLS).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class CritiqueRecord(Base):  # type: ignore[misc]
    """Persistente opslag voor CriticAgent beoordelingen per tenant."""

    __tablename__ = "agent_critiques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    critique_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    issues: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    suggestions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # TODO(TYPE): replace Any with concrete type
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
