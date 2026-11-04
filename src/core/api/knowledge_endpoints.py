# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/knowledge/ (SP-API-003)
"""
Knowledge Endpoints - FASE 3 ML/AI Operations with RBAC
REST API endpoints voor knowledge base management met complete RBAC bescherming.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_scopes, OAuth2Scope
from src.core.collaboration.message_protocol import TaskAssignmentMessage
from src.core.collaboration.task_distributor import TaskDistributor
from src.core.dependencies import get_task_distributor
from src.core.knowledge.models import KnowledgeEntry
from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)

# Create the router
router = APIRouter()

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class KnowledgeCreateRequest(BaseModel):
    """Request model voor het aanmaken van knowledge entries."""

    content: str = Field(description="Knowledge content")
    type: str = Field(description="Type of knowledge (fact, procedure, rule, etc.)")
    metadata: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Additional metadata"
    )  # TODO(TYPE): replace Any with concrete type
    source: str | None = Field(default="manual", description="Source of knowledge")
    confidence_score: float | None = Field(default=1.0, description="Confidence score (0.0-1.0)")


class KnowledgeUpdateRequest(BaseModel):
    """Request model voor het updaten van knowledge entries."""

    entry_id: int = Field(description="ID of the knowledge entry to update")
    content: str | None = Field(default=None, description="Updated content")
    type: str | None = Field(default=None, description="Updated type")
    metadata: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Updated metadata"
    )  # TODO(TYPE): replace Any with concrete type
    confidence_score: float | None = Field(default=None, description="Updated confidence score")


class KnowledgeResponse(BaseModel):
    """Response model voor knowledge operations."""

    success: bool
    message: str
    task_id: str | None = None
    agent_response: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class KnowledgeListResponse(BaseModel):
    """Response model voor knowledge listing."""

    entries: list[dict[str, Any]] = Field(  # TODO(TYPE): replace Any with concrete type
        description="List of knowledge entries"
    )  # TODO(TYPE): replace Any with concrete type
    total: int = Field(description="Total number of entries")
    timestamp: str = Field(description="Response timestamp")


class KnowledgeSearchRequest(BaseModel):
    """Request model voor knowledge search."""

    query: str = Field(description="Search query")
    type_filter: str | None = Field(default=None, description="Filter by knowledge type")
    min_confidence: float | None = Field(default=None, description="Minimum confidence score")
    limit: int | None = Field(default=10, description="Max results to return")


class KnowledgeCategoriesResponse(BaseModel):
    """Response model voor knowledge categories."""

    categories: list[str] = Field(description="List of knowledge categories/types")
    count_per_category: dict[str, int] = Field(description="Count of entries per category")
    timestamp: str = Field(description="Response timestamp")


# ============================================================================
# KNOWLEDGE ENDPOINTS - FASE 3 (8 endpoints with RBAC)
# ============================================================================


@router.post("/create", response_model=KnowledgeResponse)
async def create_knowledge(
    request: KnowledgeCreateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
) -> KnowledgeResponse:
    """
    Voeg knowledge entry toe zoals gespecificeerd in FASE 3 STAP 3.3
    Communiceert via TaskDistributor naar knowledge_agent
    Requires: ADMIN_ALL
    """
    try:
        logger.info(f"User {current_user.id} creating knowledge entry: {request.content[:50]}...")

        # Start TaskDistributor if not running
        if not task_distributor._running:
            await task_distributor.start()

        # Create TaskAssignmentMessage voor knowledge creation
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

        # Dispatch task via TaskDistributor
        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent", task_message=task_message, timeout_seconds=30
        )

        if result.success:
            logger.info(f"User {current_user.id} successfully created knowledge entry")
            return KnowledgeResponse(
                success=True,
                message="Knowledge entry created successfully via agent",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            logger.error(f"Knowledge creation failed: {result.error_message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Knowledge creation failed: {result.error_message}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in create knowledge endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/get", response_model=KnowledgeResponse)
async def get_knowledge(
    entry_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
) -> KnowledgeResponse:
    """
    Haal knowledge entry op zoals gespecificeerd in FASE 3 STAP 3.3
    Communiceert via TaskDistributor naar knowledge_agent
    Requires: AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} retrieving knowledge entry: {entry_id}")

        # Start TaskDistributor if not running
        if not task_distributor._running:
            await task_distributor.start()

        # Create TaskAssignmentMessage voor knowledge retrieval
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

        # Dispatch task via TaskDistributor
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
                detail=f"Knowledge entry not found: {result.error_message}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get knowledge endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.put("/update", response_model=KnowledgeResponse)
async def update_knowledge(
    request: KnowledgeUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
) -> KnowledgeResponse:
    """
    Update knowledge entry zoals gespecificeerd in FASE 3 STAP 3.3
    Communiceert via TaskDistributor naar knowledge_agent
    Requires: ADMIN_ALL
    """
    try:
        logger.info(f"User {current_user.id} updating knowledge entry: {request.entry_id}")

        # Start TaskDistributor if not running
        if not task_distributor._running:
            await task_distributor.start()

        # Build update parameters (only non-None values)
        update_params = {
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

        # Create TaskAssignmentMessage voor update operation
        task_message = TaskAssignmentMessage.create_task_assignment(
            sender_id="backend_knowledge_endpoint",
            recipient_id="knowledge_agent",
            task_name="update_knowledge_via_backend",
            task_type="knowledge_management",
            task_parameters=update_params,
        )

        # Dispatch task via TaskDistributor
        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent", task_message=task_message, timeout_seconds=20
        )

        if result.success:
            logger.info(
                f"User {current_user.id} successfully updated knowledge entry {request.entry_id}"
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
                detail=f"Knowledge entry update failed: {result.error_message}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in update knowledge endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/delete", response_model=KnowledgeResponse)
async def delete_knowledge(
    entry_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    task_distributor: TaskDistributor = Depends(get_task_distributor),
) -> KnowledgeResponse:
    """
    Verwijder knowledge entry zoals gespecificeerd in FASE 3 STAP 3.3
    Communiceert via TaskDistributor naar knowledge_agent
    Requires: ADMIN_ALL
    """
    try:
        logger.info(f"User {current_user.id} deleting knowledge entry: {entry_id}")

        # Start TaskDistributor if not running
        if not task_distributor._running:
            await task_distributor.start()

        # Create TaskAssignmentMessage voor delete operation
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

        # Dispatch task via TaskDistributor
        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent", task_message=task_message, timeout_seconds=15
        )

        if result.success:
            logger.info(f"User {current_user.id} successfully deleted knowledge entry {entry_id}")
            return KnowledgeResponse(
                success=True,
                message="Knowledge entry deleted successfully via agent",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Knowledge entry deletion failed: {result.error_message}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in delete knowledge endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/", response_model=KnowledgeListResponse)
async def list_knowledge(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    type_filter: str | None = Query(default=None),
) -> KnowledgeListResponse:
    """
    List all knowledge entries with pagination and optional type filtering from database.
    Requires: AGENTS_READ
    """
    try:
        logger.info(
            f"User {current_user.id} listing knowledge entries (skip={skip}, limit={limit}, type={type_filter})"
        )

        # Convert tenant_id to int if it's a string
        tenant_id_int = int(tenant_id) if isinstance(tenant_id, str) else tenant_id

        # Build query for knowledge entries
        query = select(KnowledgeEntry).where(KnowledgeEntry.tenant_id == tenant_id_int)

        # Apply type filter if provided
        if type_filter:
            query = query.where(KnowledgeEntry.type == type_filter)

        # Order by created date descending (most recent first)
        query = query.order_by(KnowledgeEntry.created_at.desc())

        # Get total count
        count_query = select(func.count(KnowledgeEntry.id)).where(
            KnowledgeEntry.tenant_id == tenant_id_int
        )
        if type_filter:
            count_query = count_query.where(KnowledgeEntry.type == type_filter)

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        entries = result.scalars().all()

        # Convert to response format
        entries_data = [
            {
                "id": entry.id,
                "content": (
                    entry.content[:200] + "..." if len(entry.content) > 200 else entry.content
                ),  # Summary
                "type": entry.type,
                "confidence_score": entry.confidence_score,
                "metadata": entry.entry_metadata,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            }
            for entry in entries
        ]

        return KnowledgeListResponse(
            entries=entries_data,
            total=total,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception(f"Error listing knowledge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/search", response_model=KnowledgeListResponse)
async def search_knowledge(
    request: KnowledgeSearchRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> KnowledgeListResponse:
    """
    Search knowledge base with query and filters using full-text search.
    Requires: AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} searching knowledge: {request.query}")

        # Convert tenant_id to int if it's a string
        tenant_id_int = int(tenant_id) if isinstance(tenant_id, str) else tenant_id

        # Build search query - searches content field
        search_pattern = f"%{request.query}%"
        query = select(KnowledgeEntry).where(
            and_(
                KnowledgeEntry.tenant_id == tenant_id_int,
                KnowledgeEntry.content.ilike(search_pattern),  # Case-insensitive search
            )
        )

        # Apply type filter if provided
        if request.type_filter:
            query = query.where(KnowledgeEntry.type == request.type_filter)

        # Apply minimum confidence filter if provided
        if request.min_confidence is not None:
            query = query.where(KnowledgeEntry.confidence_score >= request.min_confidence)

        # Order by confidence score descending
        query = query.order_by(KnowledgeEntry.confidence_score.desc())

        # Limit results
        limit = request.limit or 10
        query = query.limit(limit)

        result = await db.execute(query)
        entries = result.scalars().all()

        # Convert to response format
        entries_data = [
            {
                "id": entry.id,
                "content": (
                    entry.content[:200] + "..." if len(entry.content) > 200 else entry.content
                ),  # Summary
                "type": entry.type,
                "confidence_score": entry.confidence_score,
                "metadata": entry.entry_metadata,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            }
            for entry in entries
        ]

        return KnowledgeListResponse(
            entries=entries_data,
            total=len(entries_data),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception(f"Error searching knowledge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/categories", response_model=KnowledgeCategoriesResponse)
async def get_knowledge_categories(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> KnowledgeCategoriesResponse:
    """
    Get all knowledge categories/types with entry counts from database.
    Requires: AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting knowledge categories")

        # Convert tenant_id to int if it's a string
        tenant_id_int = int(tenant_id) if isinstance(tenant_id, str) else tenant_id

        # Query for distinct knowledge types and count

        query = (
            select(KnowledgeEntry.type, func.count(KnowledgeEntry.id).label("count"))
            .where(KnowledgeEntry.tenant_id == tenant_id_int)
            .group_by(KnowledgeEntry.type)
        )

        result = await db.execute(query)
        rows = result.all()

        # Build response
        categories: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        count_per_category: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for row in rows:
            category_type, count = row
            if category_type:
                categories.append(category_type)
                count_per_category[category_type] = count

        return KnowledgeCategoriesResponse(
            categories=sorted(categories),  # Return sorted for consistency
            count_per_category=count_per_category,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception(f"Error getting knowledge categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


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
        logger.info(f"User {current_user.id} initiating knowledge index rebuild")

        # Start TaskDistributor if not running
        if not task_distributor._running:
            await task_distributor.start()

        # Create TaskAssignmentMessage voor index rebuild
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

        # Dispatch task via TaskDistributor
        result = await task_distributor.dispatch_task(
            agent_id="knowledge_agent",
            task_message=task_message,
            timeout_seconds=120,  # Longer timeout for index rebuild
        )

        if result.success:
            logger.info(f"User {current_user.id} successfully initiated knowledge index rebuild")
            return KnowledgeResponse(
                success=True,
                message="Knowledge index rebuild initiated successfully",
                task_id=str(task_message.task_id),
                agent_response=result.response_data,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Index rebuild failed: {result.error_message}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error rebuilding knowledge index: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# ============================================================================
# FASE 3 COMPLETION STATUS
# ============================================================================
# Total endpoints in this file: 8
# - POST /create               (create_knowledge)         - ADMIN permission
# - GET /get                   (get_knowledge)            - READ permission
# - PUT /update                (update_knowledge)         - ADMIN permission
# - DELETE /delete             (delete_knowledge)         - ADMIN permission
# - GET /                      (list_knowledge)           - READ permission
# - POST /search               (search_knowledge)         - READ permission
# - GET /categories            (get_knowledge_categories) - READ permission
# - POST /index/rebuild        (rebuild_knowledge_index)  - ADMIN permission
# ============================================================================
