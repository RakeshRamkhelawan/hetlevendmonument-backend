"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
Canvas Agent Blocks API

Endpoints for managing and executing AI agent blocks within canvases.
"""

from __future__ import annotations

from typing import Any, Optional, cast
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_current_user, get_db
from src.core.api.v1.canvas.schemas import StandardResponse
from src.core.auth import UserResponse
from src.core.middleware.tenant_context import get_tenant_id
from src.domains.canvas.agent_blocks import (
    AgentBlock,
    AgentBlockType,
    AgentChatConfig,
    AgentTaskConfig,
    CodeBlockConfig,
    ExecutionEnvironment,
    ExecutionStatus,
    agent_block_registry,
)

# Optional: agent block registry - deferred to Phase 22+ (post-MVP canvas features)
try:
    from src.domains.canvas.agent_block_registry import get_agent_block_registry

    agent_block_registry = get_agent_block_registry()
except ImportError:  # pragma: no cover - optional module, Phase 22+
    pass
from src.domains.canvas.execution_service import (
    ExecutionService,
    execution_service,
    streaming_manager,
)

router = APIRouter(prefix="/canvas/{canvas_id}/agent-blocks", tags=["canvas-agent-blocks"])


# ============================================================================
# Tenant Isolation Helper
# ============================================================================


async def _verify_canvas_access(
    canvas_id: UUID,
    db: AsyncSession,
    tenant_id: int,
    user_id: UUID,
) -> None:
    """Verify that the canvas belongs to the requesting tenant.

    Raises HTTPException(404) if canvas not found or belongs to different tenant.
    """
    from src.domains.canvas.service import CanvasService

    svc = CanvasService(db=db, tenant_id=tenant_id, user_id=user_id)
    try:
        await svc.get_canvas(canvas_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canvas not found")


# ============================================================================
# Request/Response Schemas
# ============================================================================


class CreateCodeBlockRequest(CodeBlockConfig):
    """Request to create a code execution block."""

    x: float = 0
    y: float = 0
    width: float = 400
    height: float = 300


class CreateAgentChatRequest(AgentChatConfig):
    """Request to create an agent chat block."""

    x: float = 0
    y: float = 0
    width: float = 400
    height: float = 500


class CreateAgentTaskRequest(AgentTaskConfig):
    """Request to create an agent task block."""

    x: float = 0
    y: float = 0
    width: float = 400
    height: float = 200


class AgentBlockResponse(StandardResponse):
    """Response with agent block data."""

    data: dict[str, Any] = {}  # pyright: ignore[reportIncompatibleVariableOverride]  # TODO(TYPE): replace Any with concrete type


class ExecutionRequest(StandardResponse):
    """Request to execute a block."""

    pass


class ExecutionResponse(StandardResponse):
    """Response with execution status."""

    data: dict[str, Any] = {}  # pyright: ignore[reportIncompatibleVariableOverride]  # TODO(TYPE): replace Any with concrete type


# ============================================================================
# Block Management Endpoints
# ============================================================================


@router.post("/code", response_model=AgentBlockResponse)
async def create_code_block(
    canvas_id: UUID,
    request: CreateCodeBlockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> AgentBlockResponse:
    """
    Create a new code execution block.

    Supports Python, SQL, JavaScript, and Bash execution with configurable
    timeouts and resource limits.
    """
    from src.domains.canvas.service import CanvasService

    # Verify canvas exists and user has access
    svc = CanvasService(db=db, tenant_id=tenant_id, user_id=cast(UUID, current_user.id))
    try:
        canvas = await svc.get_canvas(canvas_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not found",
        )

    # Create agent block
    block_id = UUID(int=0)  # Will be generated

    config = CodeBlockConfig(
        language=request.language,
        code=request.code,
        timeout_seconds=request.timeout_seconds,
        memory_limit_mb=request.memory_limit_mb,
        allowed_imports=request.allowed_imports,
        environment_variables=request.environment_variables,
        inputs=request.inputs,
    )

    block = AgentBlock(
        block_id=block_id,
        block_type=AgentBlockType.CODE_EXECUTOR,
        config=config,
        canvas_id=canvas_id,
        tenant_id=tenant_id,
    )

    agent_block_registry.register(block)

    logger.info(f"Created code block {block_id} in canvas {canvas_id} by user {current_user.id}")

    return AgentBlockResponse(
        success=True,
        data={
            "block_id": str(block_id),
            "type": AgentBlockType.CODE_EXECUTOR.value,
            "config": config.model_dump(),
            "position": {"x": request.x, "y": request.y},
            "dimensions": {"width": request.width, "height": request.height},
        },
    )


@router.post("/agent-chat", response_model=AgentBlockResponse)
async def create_agent_chat_block(
    canvas_id: UUID,
    request: CreateAgentChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> AgentBlockResponse:
    """Create a new agent chat block for interactive AI conversations."""
    await _verify_canvas_access(canvas_id, db, tenant_id, cast(UUID, current_user.id))

    block_id = UUID(int=0)  # Will be generated

    config = AgentChatConfig(
        agent_id=request.agent_id,
        system_prompt=request.system_prompt,
        conversation_history=request.conversation_history,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        streaming=request.streaming,
        tools=request.tools,
    )

    block = AgentBlock(
        block_id=block_id,
        block_type=AgentBlockType.AGENT_CHAT,
        config=config,
        canvas_id=canvas_id,
        tenant_id=tenant_id,
    )

    agent_block_registry.register(block)

    logger.info(f"Created agent chat block {block_id} in canvas {canvas_id}")

    return AgentBlockResponse(
        success=True,
        data={
            "block_id": str(block_id),
            "type": AgentBlockType.AGENT_CHAT.value,
            "config": config.model_dump(),
            "position": {"x": request.x, "y": request.y},
            "dimensions": {"width": request.width, "height": request.height},
        },
    )


@router.post("/agent-task", response_model=AgentBlockResponse)
async def create_agent_task_block(
    canvas_id: UUID,
    request: CreateAgentTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> AgentBlockResponse:
    """Create a new background agent task block."""
    from src.domains.canvas.service import CanvasService

    svc = CanvasService(db=db, tenant_id=tenant_id, user_id=cast(UUID, current_user.id))
    try:
        canvas = await svc.get_canvas(canvas_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not found",
        )

    block_id = UUID(int=0)  # Will be generated

    config = AgentTaskConfig(
        task_description=request.task_description,
        agent_id=request.agent_id,
        auto_execute=request.auto_execute,
        execution_interval=request.execution_interval,
        max_iterations=request.max_iterations,
        dependencies=request.dependencies,
    )

    block = AgentBlock(
        block_id=block_id,
        block_type=AgentBlockType.AGENT_TASK,
        config=config,
        canvas_id=canvas_id,
        tenant_id=tenant_id,
    )

    agent_block_registry.register(block)

    logger.info(f"Created agent task block {block_id} in canvas {canvas_id}")

    return AgentBlockResponse(
        success=True,
        data={
            "block_id": str(block_id),
            "type": AgentBlockType.AGENT_TASK.value,
            "config": config.model_dump(),
            "position": {"x": request.x, "y": request.y},
            "dimensions": {"width": request.width, "height": request.height},
        },
    )


@router.get("/{block_id}", response_model=AgentBlockResponse)
async def get_agent_block(
    canvas_id: UUID,
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> AgentBlockResponse:
    """Get details of an agent block."""
    await _verify_canvas_access(canvas_id, db, tenant_id, cast(UUID, current_user.id))

    block = agent_block_registry.get(block_id, tenant_id=tenant_id)
    if not block or block.canvas_id != canvas_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    return AgentBlockResponse(
        success=True,
        data=block.to_dict(),
    )


@router.delete("/{block_id}", response_model=StandardResponse)
async def delete_agent_block(
    canvas_id: UUID,
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> StandardResponse:
    """Delete an agent block."""
    await _verify_canvas_access(canvas_id, db, tenant_id, cast(UUID, current_user.id))

    block = agent_block_registry.get(block_id, tenant_id=tenant_id)
    if not block or block.canvas_id != canvas_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    # Cancel any running execution
    if block is not None:
        await block.cancel()

    # Unregister
    agent_block_registry.unregister(block_id)

    logger.info(f"Deleted agent block {block_id} from canvas {canvas_id}")

    return StandardResponse(success=True)


# ============================================================================
# Execution Endpoints
# ============================================================================


@router.post("/{block_id}/execute", response_model=ExecutionResponse)
async def execute_block(
    canvas_id: UUID,
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> ExecutionResponse:
    """
    Execute an agent block.

    Returns immediately with task ID. Use streaming endpoint or polling
    to get execution results.
    """
    await _verify_canvas_access(canvas_id, db, tenant_id, cast(UUID, current_user.id))

    block = agent_block_registry.get(block_id, tenant_id=tenant_id)
    if not block or block.canvas_id != canvas_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    try:
        task = await execution_service.execute_block(
            block_id=block_id,
            user_id=cast(UUID, current_user.id),
        )

        return ExecutionResponse(
            success=True,
            data={
                "task_id": str(task.task_id),
                "block_id": str(block_id),
                "status": task.status.value,
                "message": "Execution started",
            },
        )
    except ValueError as e:
        logger.opt(exception=True).error("execute_block mislukt: {}", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig verzoek.",
        )


@router.post("/{block_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(
    canvas_id: UUID,
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> ExecutionResponse:
    """Cancel ongoing block execution."""
    await _verify_canvas_access(canvas_id, db, tenant_id, cast(UUID, current_user.id))

    block = agent_block_registry.get(block_id, tenant_id=tenant_id)
    if not block or block.canvas_id != canvas_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    cancelled = await block.cancel()

    return ExecutionResponse(
        success=True,
        data={
            "block_id": str(block_id),
            "cancelled": cancelled,
            "status": block.status.value,
        },
    )


@router.get("/{block_id}/status", response_model=ExecutionResponse)
async def get_execution_status(
    canvas_id: UUID,
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> ExecutionResponse:
    """Get current execution status and history."""
    await _verify_canvas_access(canvas_id, db, tenant_id, cast(UUID, current_user.id))

    block = agent_block_registry.get(block_id, tenant_id=tenant_id)
    if not block or block.canvas_id != canvas_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    status_data = execution_service.get_block_status(block_id)

    if "error" in status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=status_data["error"],
        )

    return ExecutionResponse(
        success=True,
        data=status_data,
    )


@router.post("/execute-all", response_model=ExecutionResponse)
async def execute_all_blocks(
    canvas_id: UUID,
    block_type: Optional[AgentBlockType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> ExecutionResponse:
    """Execute all agent blocks in a canvas."""
    await _verify_canvas_access(canvas_id, db, tenant_id, cast(UUID, current_user.id))

    tasks = await execution_service.execute_canvas_blocks(
        canvas_id=canvas_id,
        user_id=cast(UUID, current_user.id),
        block_type=block_type,
    )

    return ExecutionResponse(
        success=True,
        data={
            "canvas_id": str(canvas_id),
            "tasks_started": len(tasks),
            "task_ids": [str(t.task_id) for t in tasks],
        },
    )


# ============================================================================
# Streaming WebSocket
# ============================================================================


@router.websocket("/{block_id}/stream")
async def execution_stream_websocket(
    websocket: WebSocket,
    canvas_id: UUID,
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    WebSocket endpoint for real-time execution streaming.

    Connect to receive live output from block execution.
    Authentication via JWT (query parameter fallback per CLAUDE.md AS.6.2).
    """
    from src.core.auth.websocket_auth import WebSocketAuthenticator

    authenticator = WebSocketAuthenticator()
    user = await authenticator.authenticate(websocket)

    if not user:
        return

    tenant_id = user.tenant_id

    try:
        await _verify_canvas_access(canvas_id, db, tenant_id, UUID(user.user_id))
    except HTTPException as e:
        await websocket.close(code=4403, reason="Canvas access denied")
        return

    block = agent_block_registry.get(block_id, tenant_id=tenant_id)
    if not block or block.canvas_id != canvas_id:
        await websocket.close(code=4004, reason="Block not found")
        return

    # Subscribe to streaming
    streaming_manager.subscribe(canvas_id, websocket, {block_id})

    try:
        # Send current status
        await websocket.send_json(
            {
                "type": "status",
                "block_id": str(block_id),
                "status": block.status.value,
            }
        )

        import json as _json

        # Keep connection open and handle client messages
        while True:
            message = await websocket.receive_text()
            data = _json.loads(message)

            if data.get("action") == "start":
                # Client requested execution start
                if block is not None and block.status != ExecutionStatus.RUNNING:
                    callback: Optional[
                        Callable[..., Any]
                    ] = (  # TODO(TYPE): replace Any with concrete type
                        streaming_manager.create_block_stream_callback(canvas_id, block_id)
                    )
                    await execution_service.execute_block(
                        block_id=block_id,
                        user_id=UUID(user.user_id),
                        stream_callback=callback,
                    )

            elif data.get("action") == "cancel":
                await block.cancel()

            elif data.get("action") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.debug(f"Execution stream disconnected for block {block_id}")
    except Exception as e:
        logger.error(
            "Execution stream error: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
    finally:
        streaming_manager.unsubscribe(canvas_id, websocket)


# ============================================================================
# Code Templates
# ============================================================================


@router.get("/templates/code", response_model=StandardResponse)
async def get_code_templates(
    current_user: UserResponse = Depends(get_current_user),
) -> StandardResponse:
    """Get available code templates for quick start."""
    templates = {
        "python_data_analysis": {
            "name": "Python Data Analysis",
            "description": "Load and analyze data with pandas",
            "language": ExecutionEnvironment.SAFE_PYTHON.value,
            "code": """import pandas as pd
import json

# Sample data analysis
data = {"col1": [1, 2, 3], "col2": ["a", "b", "c"]}
df = pd.DataFrame(data)

print("Data Summary:")
print(df.describe())

print("\\nFirst 5 rows:")
print(df.head())""",
        },
        "sql_query": {
            "name": "SQL Query",
            "description": "Execute SQL against connected database",
            "language": ExecutionEnvironment.SQL.value,
            "code": """SELECT
    column_name,
    COUNT(*) as row_count
FROM table_name
GROUP BY column_name
ORDER BY row_count DESC
LIMIT 10;""",
        },
        "api_request": {
            "name": "HTTP API Request",
            "description": "Make HTTP requests with error handling",
            "language": ExecutionEnvironment.SAFE_PYTHON.value,
            "code": """import requests
import json

url = "https://api.example.com/data"

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    print(json.dumps(data, indent=2))
except requests.RequestException as e:
    print(f"Request failed: {e}")""",
        },
    }

    return StandardResponse(
        success=True,
        data={"templates": templates},
    )
