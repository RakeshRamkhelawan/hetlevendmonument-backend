"""
Decision contest model for GDPR art. 22 right-to-contest.

Kept separate from council/models.py to avoid circular imports
during test schema setup (import_all_models).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class DecisionContestRow(Base):  # type: ignore[misc]
    """GDPR art. 22 contestation of an AI decision."""

    __tablename__ = "decision_contests"

    contest_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    decision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("council_decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason_category: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolver_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
