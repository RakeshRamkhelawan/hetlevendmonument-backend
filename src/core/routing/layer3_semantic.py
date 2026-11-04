import logging
from typing import Optional, cast

from sqlalchemy import text

from src.core.database.database import db_manager
from src.core.services.llm.service import LLMService
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)


class SemanticRouter:
    """
    Layer 3 (Sattva): Semantic routing using vector similarity search (pgvector).
    Compares task embedding with historical data or predefined department anchors.
    Target latency: <200ms.
    """

    def __init__(self) -> None:
        self.threshold = 0.85  # Minimum cosine similarity

    async def route(self, task: TaskData) -> str | None:
        """
        Routes the task based on semantic similarity in the vector database.
        """
        tenant_id = task.metadata.get("tenant_id")
        if not tenant_id:
            logger.warning("No tenant_id in task metadata, skipping Layer 3")
            return None

        try:
            # 1. Generate embedding for the task content
            content = f"{task.title}: {task.description}"
            # Het taalmodel van de tenant van de taak, niet het platformmodel (brief 2026-10-19).
            llm_service = await LLMService.for_tenant(int(tenant_id))
            query_embedding = await llm_service.get_embeddings(content)

            # 2. Perform vector search in PostgreSQL (pgvector)
            async with db_manager.get_session() as db:
                # Query matches embeddings in 'collective_knowledge' table
                # We filter by tenant_id for strict isolation
                stmt = text(
                    """
                    SELECT supervisor_id
                    FROM collective_knowledge
                    WHERE tenant_id = :tenant_id
                    AND (embedding <=> :embedding) < :threshold
                    ORDER BY (embedding <=> :embedding) ASC
                    LIMIT 1
                """
                )

                # <=> is the cosine distance operator in pgvector
                # Note: distance < 0.15 means similarity > 0.85
                result = await db.execute(
                    stmt,
                    {
                        "tenant_id": tenant_id,
                        "embedding": str(query_embedding),
                        "threshold": 1.0 - self.threshold,
                    },
                )

                target = result.scalar_one_or_none()
                if target:
                    logger.debug(f"Layer 3 Semantic Match: {target}")
                    return cast(str, target)

        except Exception as e:
            logger.error(f"Layer 3 Semantic Routing failed: {e}")

        return None
