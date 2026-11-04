# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Knowledge admin sub-router -- index rebuild.

Migrated from src/core/api/knowledge_endpoints.py (SP-API-003 Dag 5).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_scopes, OAuth2Scope
from src.core.collaboration.message_protocol import TaskAssignmentMessage
from src.core.collaboration.task_distributor import TaskDistributor
from src.core.dependencies import get_task_distributor
from src.core.shared.production_logging import SafeLogger

from .schemas import KnowledgeResponse

logger = SafeLogger(__name__)

router = APIRouter()


@router.post("/index/rebuild", response_model=KnowledgeResponse)
async def rebuild_knowledge_index(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
) -> KnowledgeResponse:
    """
    Rebuild knowledge base index (embeddings, search index, etc.).
    Requires: ADMIN_ALL
    """
    try:
        logger.info("User %s initiating knowledge index rebuild", current_user.id)

        if not task_distributor._running:
            await task_distributor.start()

        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="backend_knowledge_endpoint",
            recipient_id="knowledge_agent",
            task_name="rebuild_knowledge_index",
            task_type="knowledge_management",
            task_parameters={
                "action": "rebuild_index",
                "source": "backend_api",
                "initiated_by": current_user.id,
            },
        )

        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent",
            task_message=task_message,
            timeout_seconds=120,  # Longer timeout for index rebuild
        )

        if result.success:
            logger.info("User %s successfully initiated knowledge index rebuild", current_user.id)
            return KnowledgeResponse(
                success=True,
                message="Knowledge index rebuild initiated successfully",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Index rebuild failed: %s" % result.error_message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error rebuilding knowledge index: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rebuild index",
        )
