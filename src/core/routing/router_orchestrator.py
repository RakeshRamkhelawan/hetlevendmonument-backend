import logging
from typing import Optional

from pydantic import BaseModel

from src.core.routing.layer1_keyword import KeywordRouter
from src.core.routing.layer3_semantic import SemanticRouter
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)


class RouterRequest(BaseModel):
    """Data model for a routing request."""

    task: TaskData
    tenant_id: int


class RouterResponse(BaseModel):
    """Data model for a routing response."""

    target_supervisor: str
    layer_used: str
    confidence: float = 1.0


class GunaRouter:
    """
    GunaRouter: The intelligent multi-layer routing engine of SanskritiSetu.
    """

    def __init__(self) -> None:
        self.layer1 = KeywordRouter()
        self.layer3 = SemanticRouter()

    async def route(self, request: RouterRequest) -> RouterResponse:
        """
        Routes the task using the hierarchical Guna layers.
        """
        task = request.task
        task.metadata["tenant_id"] = request.tenant_id

        # 1. Try Layer 1 (Tamas)
        target = self.layer1.route(task)
        if target:
            return RouterResponse(target_supervisor=target, layer_used="layer1")

        # 2. Try Layer 3 (Sattva)
        target = await self.layer3.route(task)
        if target:
            return RouterResponse(target_supervisor=target, layer_used="layer3")

        # 3. NEW: Layer 4 (Learned) - Check adaptation rules
        learned_target = await self._check_adaptation_rules(request.tenant_id, task)
        if learned_target:
            logger.info(f"GunaRouter: Routed via Learned Layer -> {learned_target}")
            return RouterResponse(target_supervisor=learned_target, layer_used="layer_learned")

        # 4. Fallback to Meta Layer
        return RouterResponse(target_supervisor="cva_supervisor", layer_used="layer4")

    async def _check_adaptation_rules(self, tenant_id: int, task: TaskData) -> str | None:
        """Queries the database for specific adaptation rules learned by the system."""
        from sqlalchemy import text

        from src.core.database.database import db_manager

        content = f"{task.title} {task.description}".lower()

        try:
            async with db_manager.get_session() as db:
                # Look for matching trigger conditions
                stmt = text(
                    """
                    SELECT target_supervisor
                    FROM adaptation_rules
                    WHERE tenant_id = :tenant_id AND is_active = true
                    AND (
                        EXISTS (
                            SELECT 1 FROM UNNEST(trigger_keywords) kw
                            WHERE :content ILIKE '%' || kw || '%'
                        )
                        OR EXISTS (
                            SELECT 1 FROM UNNEST(trigger_patterns) pat
                            WHERE :content ~ pat
                        )
                    )
                    LIMIT 1
                """
                )
                result = await db.execute(stmt, {"tenant_id": tenant_id, "content": content})
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to check adaptation rules: {e}")
            return None
