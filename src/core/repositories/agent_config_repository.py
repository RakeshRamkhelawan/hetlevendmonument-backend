"""AgentConfigRepository -- CRUD + active-config loader for AgentRunner."""
from __future__ import annotations
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models.agent_config import AgentConfig

class AgentConfigRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, tenant_id: int, agent_type: str, agent_id: str, department: str | None = None, department_user_id: int | None = None, subscribed_topics: list[str] | None = None, is_active: bool = True, config_json: dict[str, Any] | None = None) -> AgentConfig:  # TODO(TYPE): replace Any with concrete type
        cfg = AgentConfig(tenant_id=tenant_id, agent_type=agent_type, agent_id=agent_id, department=department, department_user_id=department_user_id, subscribed_topics=subscribed_topics or [], is_active=is_active, config_json=config_json or {})
        self.db.add(cfg)
        await self.db.flush()
        await self.db.refresh(cfg)
        return cfg

    async def get_by_id(self, config_id: int, tenant_id: int | None = None) -> AgentConfig | None:
        stmt = select(AgentConfig).where(AgentConfig.id == config_id)
        if tenant_id is not None:
            stmt = stmt.where(AgentConfig.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_agent_id(self, agent_id: str, tenant_id: int | None = None) -> AgentConfig | None:
        stmt = select(AgentConfig).where(AgentConfig.agent_id == agent_id)
        if tenant_id is not None:
            stmt = stmt.where(AgentConfig.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_configs(
        self,
        tenant_id: int | None = None,
        active_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[AgentConfig]:
        stmt = select(AgentConfig)
        if active_only:
            stmt = stmt.where(AgentConfig.is_active.is_(True))
        if tenant_id is not None:
            stmt = stmt.where(AgentConfig.tenant_id == tenant_id)
        stmt = stmt.order_by(AgentConfig.tenant_id, AgentConfig.agent_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, config_id: int, tenant_id: int | None = None, **kwargs: Any) -> AgentConfig | None:
        cfg = await self.get_by_id(config_id, tenant_id=tenant_id)
        if cfg is None:
            return None
        allowed = {"agent_type", "agent_id", "department", "department_user_id", "subscribed_topics", "is_active", "config_json"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(cfg, key, value)
        await self.db.flush()
        await self.db.refresh(cfg)
        return cfg

    async def delete(self, config_id: int, tenant_id: int | None = None) -> bool:
        cfg = await self.get_by_id(config_id, tenant_id=tenant_id)
        if cfg is None:
            return False
        await self.db.delete(cfg)
        await self.db.flush()
        return True
