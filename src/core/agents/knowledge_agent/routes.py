"""
KnowledgeAgent Routes - Converted to APIRouter for Unified Server
Transformed from standalone FastAPI app to modular router component
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

# Import message protocol from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# NOTE: ADR-034 Cat B Stap 3D -- FastAPI route met Depends(get_db), correct DI-patroon.
# import-linter Contract 7 ignore_imports gedocumenteerd. Backlog: SP-AGT-005.
from src.core.database.database import get_db
from src.core.middleware.tenant_context import require_tenant_id
from src.core.collaboration.message_protocol import (
    TaskAssignmentMessage,
    TaskStatus,
    TaskStatusUpdateMessage,
    deserialize_message,
)
from src.core.knowledge.knowledge_service import (
    KnowledgeEntryCreate,
    KnowledgeEntryUpdate,
    KnowledgeService,
    create_knowledge_service,
)

# Configure logging
logger = logging.getLogger("knowledge_agent_router")

# Create APIRouter instead of FastAPI app
router = APIRouter(tags=["Knowledge Agent"])


class TaskExecutionRequest(BaseModel):
    """Request model voor task execution"""

    task_message: str = Field(description="Serialized TaskAssignmentMessage")


class TaskExecutionResponse(BaseModel):
    """Response model voor task execution"""

    status: str = Field(description="Execution status")
    result: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        description="Task execution result"
    )  # TODO(TYPE): replace Any with concrete type
    message: str = Field(description="Status message")


@router.get("/")
async def knowledge_root() -> dict[str, object]:
    """Root endpoint voor knowledge agent health check"""
    return {
        "agent": "knowledge_agent",
        "status": "online",
        "version": "1.0.0",
        "endpoints": ["/execute-task"],
    }


@router.get("/health")
async def knowledge_health_check() -> dict[str, str]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent_id": "knowledge_agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/execute-task")
async def execute_knowledge_task(
    request: TaskExecutionRequest, db: AsyncSession = Depends(get_db)
) -> TaskExecutionResponse:
    """
    Execute knowledge task endpoint - Now internal router method

    Functionaliteit:
    1. Accepteert TaskAssignmentMessage
    2. Valideert de taak (bv. action: "create_knowledge")
    3. Roept corresponderende KnowledgeService methode aan
    4. Retourneert TaskStatusUpdateMessage met resultaat
    """
    try:
        logger.info("Received knowledge task execution request")

        # Database session now injected via dependency
        # No manual initialization needed

        # Deserialize the task message
        try:
            task_message = deserialize_message(request.task_message)
            if not isinstance(task_message, TaskAssignmentMessage):
                raise ValueError(f"Expected TaskAssignmentMessage, got {type(task_message)}")
        except Exception as e:
            logger.error(f"Failed to deserialize task message: {e}")
            raise HTTPException(status_code=400, detail="Invalid task message format")

        # Log the task details
        logger.info(
            f"Processing knowledge task: {task_message.task_name} (type: {task_message.task_type})"
        )
        logger.info(f"Task ID: {task_message.task_id}")
        logger.info(f"Sender: {task_message.sender_id}")
        logger.info(f"Parameters: {task_message.task_parameters}")

        # Extract task parameters
        task_params = task_message.task_parameters or {}
        action = task_params.get("action", "unknown")

        # Get KnowledgeService instance with tenant isolation (ADR-005)
        knowledge_service = create_knowledge_service(db_session=db, tenant_id=require_tenant_id())

        # Process based on action type
        if action == "create_knowledge":
            result = await _handle_create_knowledge(knowledge_service, task_params)
        elif action == "get_knowledge":
            result = await _handle_get_knowledge(knowledge_service, task_params)
        elif action == "update_knowledge":
            result = await _handle_update_knowledge(knowledge_service, task_params)
        elif action == "delete_knowledge":
            result = await _handle_delete_knowledge(knowledge_service, task_params)
        else:
            raise ValueError(f"Unknown action: {action}")

        # Create TaskStatusUpdateMessage met resultaat
        TaskStatusUpdateMessage.create_status_update(
            sender_id="knowledge_agent",
            recipient_id=task_message.sender_id,
            task_id=task_message.task_id,
            original_assignment_id=task_message.message_id,
            status=TaskStatus.COMPLETED,
            progress_percentage=100.0,
            result=result,
        )

        logger.info(f"Knowledge task {task_message.task_id} completed successfully")

        # Return response in expected format
        return TaskExecutionResponse(
            status="completed",
            result=result,
            message=f"Knowledge task {task_message.task_name} executed successfully",
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error during knowledge task execution: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _handle_create_knowledge(
    service: KnowledgeService,
    params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Handle create_knowledge action"""
    try:
        # Extract required parameters
        content = params.get("content")
        knowledge_type = params.get("type", "general")
        metadata = params.get("metadata", {})
        confidence_score = params.get("confidence_score", 0.0)

        if not content:
            raise ValueError("Content is required for create_knowledge action")

        # Create knowledge entry
        entry_data = KnowledgeEntryCreate(
            content=content,
            type=knowledge_type,
            entry_metadata=metadata,
            confidence_score=confidence_score,
        )

        created_entry = await service.create_entry(entry_data)

        logger.info(f"Created knowledge entry {created_entry.id}")

        return {
            "action": "create_knowledge",
            "entry_id": created_entry.id,
            "content": created_entry.content,
            "type": created_entry.type,
            "confidence_score": created_entry.confidence_score,
            "created_at": created_entry.created_at.isoformat(),
            "agent": "knowledge_agent",
        }

    except Exception as e:
        logger.error(f"Error creating knowledge entry: {e}")
        raise


async def _handle_get_knowledge(
    service: KnowledgeService,
    params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Handle get_knowledge action"""
    try:
        entry_id = params.get("entry_id")
        if not entry_id:
            raise ValueError("entry_id is required for get_knowledge action")

        entry = await service.get_entry(entry_id)

        if not entry:
            return {
                "action": "get_knowledge",
                "entry_id": entry_id,
                "found": False,
                "agent": "knowledge_agent",
            }

        return {
            "action": "get_knowledge",
            "entry_id": entry.id,
            "content": entry.content,
            "type": entry.type,
            "confidence_score": entry.confidence_score,
            "found": True,
            "agent": "knowledge_agent",
        }

    except Exception as e:
        logger.error(f"Error retrieving knowledge entry: {e}")
        raise


async def _handle_update_knowledge(
    service: KnowledgeService,
    params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Handle update_knowledge action"""
    try:
        entry_id = params.get("entry_id")
        if not entry_id:
            raise ValueError("entry_id is required for update_knowledge action")

        # Build update data
        update_data = KnowledgeEntryUpdate()
        if "content" in params:
            update_data.content = params["content"]
        if "type" in params:
            update_data.type = params["type"]
        if "metadata" in params:
            update_data.entry_metadata = params["metadata"]
        if "confidence_score" in params:
            update_data.confidence_score = params["confidence_score"]

        updated_entry = await service.update_entry(entry_id, update_data)

        if not updated_entry:
            return {
                "action": "update_knowledge",
                "entry_id": entry_id,
                "updated": False,
                "agent": "knowledge_agent",
            }

        return {
            "action": "update_knowledge",
            "entry_id": updated_entry.id,
            "content": updated_entry.content,
            "type": updated_entry.type,
            "confidence_score": updated_entry.confidence_score,
            "updated": True,
            "agent": "knowledge_agent",
        }

    except Exception as e:
        logger.error(f"Error updating knowledge entry: {e}")
        raise


async def _handle_delete_knowledge(
    service: KnowledgeService,
    params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Handle delete_knowledge action"""
    try:
        entry_id = params.get("entry_id")
        if not entry_id:
            raise ValueError("entry_id is required for delete_knowledge action")

        deleted = await service.delete_entry(entry_id)

        return {
            "action": "delete_knowledge",
            "entry_id": entry_id,
            "deleted": deleted,
            "agent": "knowledge_agent",
        }

    except Exception as e:
        logger.error(f"Error deleting knowledge entry: {e}")
        raise


@router.get("/status")
async def knowledge_agent_status() -> dict[str, object]:
    """Agent status endpoint"""
    return {
        "agent_id": "knowledge_agent",
        "agent_name": "Knowledge Agent",
        "agent_type": "knowledge_processor",
        "status": "online",
        "capabilities": ["knowledge_management", "crud_operations"],
        "supported_task_types": [
            "create_knowledge",
            "get_knowledge",
            "update_knowledge",
            "delete_knowledge",
        ],
        "endpoints": {
            "execute_task": "/execute-task",
            "health": "/health",
            "status": "/status",
        },
        "version": "1.0.0",
    }
