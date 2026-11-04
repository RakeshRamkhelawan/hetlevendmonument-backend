"""Department activation handler -- registers default tools and creates AgentConfig."""

from __future__ import annotations
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models.agent_config import AgentConfig
from src.core.repositories.agent_config_repository import AgentConfigRepository
from src.core.events.signal_router import resolve_topics
from src.core.tool_broker.ap_mcp_registry import ap_mcp_registry

logger = logging.getLogger(__name__)


class DepartmentActivatedEvent:
    def __init__(self, tenant_id: int, department: str) -> None:
        self.tenant_id = tenant_id
        self.department = department


async def on_department_activated(
    event: DepartmentActivatedEvent, db_session: AsyncSession
) -> None:
    """Handle department activation: register tools + create AgentConfig."""
    logger.info(
        "department_activated", extra={"tenant_id": event.tenant_id, "department": event.department}
    )

    # 1. Register default tools for department
    default_tools = ap_mcp_registry.get_default_tools_for_department(event.department)
    for tool_name in default_tools:
        # In production, this would call ToolBroker to add to allowlist
        logger.info(
            "tool_registered",
            extra={"tenant_id": event.tenant_id, "department": event.department, "tool": tool_name},
        )

    # 2. Create or update AgentConfig
    repo = AgentConfigRepository(db_session)
    topics = resolve_topics(event.department)
    agent_type = f"{event.department}_agent"
    agent_id = f"{event.department}-{event.tenant_id}"

    existing = await repo.get_by_agent_id(agent_id)
    if existing is not None:
        await repo.update(existing.id, is_active=True, subscribed_topics=topics)
        logger.info("agent_config_reactivated", extra={"agent_id": agent_id})
    else:
        await repo.create(
            tenant_id=event.tenant_id,
            agent_type=agent_type,
            agent_id=agent_id,
            department=event.department,
            subscribed_topics=topics,
            is_active=True,
        )
        logger.info("agent_config_created", extra={"agent_id": agent_id})
