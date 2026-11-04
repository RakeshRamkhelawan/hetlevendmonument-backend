"""AgentConfig ORM model."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from src.core.database.database import Base

class AgentConfig(Base):  # type: ignore[misc]
    __tablename__ = "agent_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    subscribed_topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")  # TODO(TYPE): replace Any with concrete type
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    tenant = relationship("Tenant")
    department_user = relationship("User")
    __table_args__ = (
        Index("idx_agent_config_active", "tenant_id", "is_active"),
        Index("idx_agent_config_agent_id", "tenant_id", "agent_id", unique=True),
        Index("idx_agent_config_department", "department"),
    )

    def __init__(self, *, tenant_id: int, agent_type: str, agent_id: str, department: str | None = None, department_user_id: int | None = None, subscribed_topics: list[str] | None = None, is_active: bool = True, config_json: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tenant_id = tenant_id
        self.agent_type = agent_type
        self.agent_id = agent_id
        self.department = department
        self.department_user_id = department_user_id
        self.subscribed_topics = subscribed_topics if subscribed_topics is not None else []
        self.is_active = is_active
        self.config_json = config_json if config_json is not None else {}

    def __repr__(self) -> str:
        return f"<AgentConfig(id={self.id}, agent_id={self.agent_id!r}, tenant_id={self.tenant_id}, is_active={self.is_active})>"
