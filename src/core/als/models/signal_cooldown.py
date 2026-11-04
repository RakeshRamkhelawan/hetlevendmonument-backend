"""Signal Cooldown Model - Prevents broadcast storms."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class SignalCooldown(Base):  # type: ignore[misc]
    """Tracks cooldown periods for signals to prevent spam.

    When an agent sends too many signals of the same type,
    they enter a cooldown period where those signals are dropped.
    """

    __tablename__ = "signal_cooldowns"

    # [RED] CRITICAL: Tenant isolation (part of composite PK)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    sender: Mapped[str] = mapped_column(String, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Composite primary key
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "signal_type", "sender"),
        Index("idx_cooldown_expires", "expires_at"),
    )

    @validates("tenant_id")
    def validate_tenant_id(
        self,
        key: str,
        tenant_id: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        if not tenant_id or tenant_id <= 0:
            raise ValueError(f"Invalid tenant_id: {tenant_id}")
        return tenant_id

    def is_expired(self) -> bool:
        """Check if cooldown has expired."""
        return datetime.now(timezone.utc) >= self.expires_at
