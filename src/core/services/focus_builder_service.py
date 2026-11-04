"""
src/core/services/focus_builder_service.py

Service-layer helpers for Focus Builder:
- save_accepted_workflow: persist accepted proposals to focus_builder_accepted_workflows
"""

from __future__ import annotations

from typing import Any, Optional, cast

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.twin_models import FocusBuilderAcceptedWorkflow


async def save_accepted_workflow(
    *,
    user_id: int,
    tenant_id: int,
    proposal_id: str,
    name: str | None,
    nodes: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    edges: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    intake_context: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    template_id: str | None = None,
    db: AsyncSession,
) -> None:
    """
    Persist an accepted proposal. Idempotent: duplicate proposal_id is silently ignored.
    """
    stmt = (
        pg_insert(FocusBuilderAcceptedWorkflow)
        .values(
            user_id=user_id,
            tenant_id=tenant_id,
            proposal_id=proposal_id,
            name=name,
            nodes=nodes,
            edges=edges,
            intake_context=intake_context,
            template_id=template_id,
        )
        .on_conflict_do_nothing(index_elements=["proposal_id"])
    )
    await db.execute(stmt)
    # Commit is the caller's responsibility (managed by FastAPI session middleware)
    logger.info("focus_builder_workflow_saved", proposal_id=proposal_id, user_id=user_id)
