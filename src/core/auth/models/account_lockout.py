"""
Account Lockout Model - Brute-Force Protection Database Layer

Tracks failed login attempts per user and IP address.
Part of SA-1.1 implementation for Security Stream A.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class AccountLockout(Base):  # type: ignore[misc]
    """
    Tracks failed login attempts for brute-force protection.

    Attributes:
        user_id: Foreign key to users table (CASCADE delete)
        failed_attempts: Counter for failed login attempts
        locked_until: Timestamp when lock expires (None = not locked)
        last_attempt_at: Timestamp of last failed attempt
        ip_address: Client IP address (supports IPv6)
        user_agent: Browser user agent for audit purposes
    """

    __tablename__ = "account_lockouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Foreign Key with Cascade Delete (Clean up if user is deleted)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Tracking counters
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Lockout timestamp (Null = not locked)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Metadata for audit and reset logic
    last_attempt_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 support
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Composite index for fast lookups during login
    __table_args__ = (Index("idx_lockout_user_ip", "user_id", "ip_address"),)

    def __repr__(self) -> str:
        return f"<AccountLockout(user_id={self.user_id}, attempts={self.failed_attempts}, locked_until={self.locked_until})>"
