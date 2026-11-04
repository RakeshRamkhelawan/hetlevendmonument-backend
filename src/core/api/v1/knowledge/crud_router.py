# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Knowledge CRUD sub-router -- create, get, update, delete knowledge entries.

Migrated from src/core/api/knowledge_endpoints.py (SP-API-003 Dag 5).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.api.v1.knowledge.dependencies import AgentRegistry
from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_scopes, OAuth2Scope
from src.core.collaboration.message_protocol import TaskAssignmentMessage
from src.core.collaboration.task_distributor import TaskDistributor
from src.core.dependencies import get_agent_registry, get_task_distributor
from src.core.shared.production_logging import SafeLogger

from .schemas import KnowledgeCreateRequest, KnowledgeResponse, KnowledgeUpdateRequest

logger = SafeLogger(__name__)

router = APIRouter()


@router.post("/create", response_model=KnowledgeResponse)
async def create_knowledge(
    request: KnowledgeCreateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> KnowledgeResponse:
    """
    Voeg knowledge entry toe zoals gespecificeerd in FASE 3 STAP 3.3.
    Communiceert via TaskDistributor naar knowledge_agent.
    Requires: ADMIN_ALL
    """
    try:
        logger.info(
            "User %s creating knowledge entry: %s...", current_user.id, request.content[:50]
        )

        # Start TaskDistributor if not running
        if not task_distributor._running:
            await task_distributor.start()

        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="backend_knowledge_endpoint",
            recipient_id="knowledge_agent",
            task_name="create_knowledge_via_backend",
            task_type="knowledge_management",
            task_parameters={
                "action": "create_knowledge",
                "content": request.content,
                "type": request.type,
                "metadata": request.metadata or {},
                "source": request.source,
                "confidence_score": request.confidence_score,
                "created_by": current_user.id,
            },
        )

        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent", task_message=task_message, timeout_seconds=30
        )

        if result.success:
            logger.info("User %s successfully created knowledge entry", current_user.id)
            return KnowledgeResponse(
                success=True,
                message="Knowledge entry created successfully via agent",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            logger.error("Knowledge creation failed: %s", result.error_message)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Knowledge creation failed: %s" % result.error_message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in create knowledge endpoint: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/get", response_model=KnowledgeResponse)
async def get_knowledge(
    entry_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> KnowledgeResponse:
    """
    Haal knowledge entry op zoals gespecificeerd in FASE 3 STAP 3.3.
    Communiceert via TaskDistributor naar knowledge_agent.
    Requires: AGENTS_READ
    """
    try:
        logger.info("User %s retrieving knowledge entry: %s", current_user.id, entry_id)

        if not task_distributor._running:
            await task_distributor.start()

        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="backend_knowledge_endpoint",
            recipient_id="knowledge_agent",
            task_name="get_knowledge_via_backend",
            task_type="knowledge_management",
            task_parameters={
                "action": "get_knowledge",
                "entry_id": entry_id,
                "source": "backend_api",
            },
        )

        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent", task_message=task_message, timeout_seconds=15
        )

        if result.success:
            return KnowledgeResponse(
                success=True,
                message="Knowledge entry retrieved successfully via agent",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge entry not found: %s" % result.error_message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get knowledge endpoint: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.put("/update", response_model=KnowledgeResponse)
async def update_knowledge(
    request: KnowledgeUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> KnowledgeResponse:
    """
    Update knowledge entry zoals gespecificeerd in FASE 3 STAP 3.3.
    Communiceert via TaskDistributor naar knowledge_agent.
    Requires: ADMIN_ALL
    """
    try:
        logger.info("User %s updating knowledge entry: %s", current_user.id, request.entry_id)

        if not task_distributor._running:
            await task_distributor.start()

        update_params: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "action": "update_knowledge",
            "entry_id": request.entry_id,
            "updated_by": current_user.id,
        }
        if request.content is not None:
            update_params["content"] = request.content
        if request.type is not None:
            update_params["type"] = request.type
        if request.metadata is not None:
            update_params["metadata"] = request.metadata
        if request.confidence_score is not None:
            update_params["confidence_score"] = request.confidence_score
        update_params["source"] = "backend_api"

        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="backend_knowledge_endpoint",
            recipient_id="knowledge_agent",
            task_name="update_knowledge_via_backend",
            task_type="knowledge_management",
            task_parameters=update_params,
        )

        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent", task_message=task_message, timeout_seconds=20
        )

        if result.success:
            logger.info(
                "User %s successfully updated knowledge entry %s",
                current_user.id,
                request.entry_id,
            )
            return KnowledgeResponse(
                success=True,
                message="Knowledge entry updated successfully via agent",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge entry update failed: %s" % result.error_message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in update knowledge endpoint: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.delete("/delete", response_model=KnowledgeResponse)
async def delete_knowledge(
    entry_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
    agent_registry: AgentRegistry = Depends(get_agent_registry),
) -> KnowledgeResponse:
    """
    Verwijder knowledge entry zoals gespecificeerd in FASE 3 STAP 3.3.
    Communiceert via TaskDistributor naar knowledge_agent.
    Requires: ADMIN_ALL
    """
    try:
        logger.info("User %s deleting knowledge entry: %s", current_user.id, entry_id)

        if not task_distributor._running:
            await task_distributor.start()

        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="backend_knowledge_endpoint",
            recipient_id="knowledge_agent",
            task_name="delete_knowledge_via_backend",
            task_type="knowledge_management",
            task_parameters={
                "action": "delete_knowledge",
                "entry_id": entry_id,
                "source": "backend_api",
                "deleted_by": current_user.id,
            },
        )

        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent", task_message=task_message, timeout_seconds=15
        )

        if result.success:
            logger.info(
                "User %s successfully deleted knowledge entry %s", current_user.id, entry_id
            )
            return KnowledgeResponse(
                success=True,
                message="Knowledge entry deleted successfully via agent",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge entry deletion failed: %s" % result.error_message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in delete knowledge endpoint: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
