from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class UsageRecord(Base):  # type: ignore[misc]
    """
    UsageRecord model for tracking resource consumption.
    Used for billing and quota management.
    """

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    metric_type = mapped_column(
        String(50), nullable=False, index=True
    )  # workflow_run, ai_token, etc.
    value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    metadata_json: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # TODO(TYPE): replace Any with concrete type

    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<UsageRecord(id={self.id}, tenant_id={self.tenant_id}, metric='{self.metric_type}', value={self.value})>"
