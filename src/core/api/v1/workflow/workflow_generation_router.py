# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
VIBE Workflow Generation sub-router (SP-API-003 Dag 2).

Routes:
    POST      /api/v1/vibe/generate
    GET       /api/v1/vibe/agents
    WEBSOCKET /api/v1/vibe/ws/generate
    GET       /api/v1/vibe/health
    WEBSOCKET /api/v1/vibe/ws/generate/secure
"""

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.core.api.v1.workflow.dependencies import consent_read_limit, create_workflow_generator
from src.core.auth import UserResponse
from src.core.auth.api_deps import get_current_user_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vibe", tags=["vibe", "workflow-generation"])


# ============================================================================
# Request/Response Models
# ============================================================================


class VibeGenerateRequest(BaseModel):
    """Request to generate a workflow from natural language."""

    prompt: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Natural language workflow description",
    )
    complexity: str = Field(
        default="medium", description="Complexity level: simple, medium, complex"
    )


class VibeGenerateResponse(BaseModel):
    """Response with generated workflow or error."""

    success: bool
    correlation_id: str
    workflow: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error: str | None = None
    generation_time_ms: float = 0
    node_count: int = 0
    edge_count: int = 0
    is_mock: bool = False


# ============================================================================
# REST Endpoints
# ============================================================================


@router.post("/generate", response_model=VibeGenerateResponse)
async def generate_workflow(
    request: VibeGenerateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> VibeGenerateResponse:
    """Generate a workflow from natural language prompt."""
    correlation_id = str(uuid.uuid4())[:8]
    endpoint_start = time.time()

    try:
        logger.info(
            "[%s] Workflow generation request: complexity=%s, tenant_id=%s",
            correlation_id,
            request.complexity,
            current_user.tenant_id,
        )

        generator = await create_workflow_generator(
            tenant_id=current_user.tenant_id,
            correlation_id=correlation_id,
        )

        gen_start = time.time()
        success, workflow, error = await generator.generate_workflow(
            user_prompt=request.prompt, complexity=request.complexity
        )
        generation_time = (time.time() - gen_start) * 1000

        total_time = (time.time() - endpoint_start) * 1000

        if success and workflow:
            logger.info(
                "[%s] Generation successful: %s nodes, %s edges | Total: %.0fms",
                correlation_id,
                len(workflow.nodes),
                len(workflow.edges),
                total_time,
            )
            return VibeGenerateResponse(
                success=True,
                correlation_id=correlation_id,
                workflow=workflow.dict(),
                generation_time_ms=round(generation_time, 2),
                node_count=len(workflow.nodes),
                edge_count=len(workflow.edges),
                is_mock=generator.is_mock,
            )
        else:
            logger.warning(
                "[%s] Generation failed: %s | Total: %.0fms",
                correlation_id,
                error,
                total_time,
            )
            return VibeGenerateResponse(
                success=False,
                correlation_id=correlation_id,
                error=error or "Unknown error during generation",
                generation_time_ms=round(generation_time, 2),
                is_mock=generator.is_mock,
            )

    except Exception as e:
        total_time = (time.time() - endpoint_start) * 1000
        logger.error(
            "[%s] Unexpected error: %s: %s | Total: %.0fms",
            correlation_id,
            type(e).__name__,
            e,
            total_time,
            exc_info=True,
        )
        return VibeGenerateResponse(success=False, correlation_id=correlation_id, error="Er is een fout opgetreden.")


@router.get("/agents")
async def list_available_agents(
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List available agents for workflow generation."""
    generator = await create_workflow_generator(tenant_id=current_user.tenant_id)
    agents = await generator.get_available_agents()
    return {"tenant_id": current_user.tenant_id, "agent_count": len(agents), "agents": agents}


async def _gebruiker_voor_de_limiet(
    request: Request,
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> UserResponse:
    """De ingelogde medewerker, ook op `request.state.user` gezet.

    De snelheidsbegrenzing bepaalt haar sleutel (`<klant>:<medewerker>:<pad>`) uit `request.state.user` en valt anders terug
    op het IP-adres, dat achter de proxy voor iedereen gelijk is: een medewerker zette dan alle medewerkers van alle
    bedrijven op 429 (Gate 2 security, nazorg agentstap). Een dependency draait VOOR de wrapper van de limiet; de body van
    de route zou te laat zijn. Zelfde patroon als `api/v1/bonnen/dependencies.py`.
    """
    request.state.user = current_user
    return current_user


# De limiet staat ONDER `@router.get`: erboven registreert de router de ongewikkelde functie en doet hij niets.
@router.get("/agents/uitvoerbaar")
@consent_read_limit
async def list_executable_agents(
    request: Request,
    current_user: UserResponse = Depends(_gebruiker_voor_de_limiet),
) -> dict[str, object]:
    """De agents die een agentstap in een workflow voor deze klant kan uitvoeren (kiesbaar = uitvoerbaar, agentstap dag 1).

    Gefilterd op de pakketschakelaar van de klant. Pad: `/api/v1/vibe/agents/uitvoerbaar` (prefix van deze router).

    Een aparte lijst naast `/agents`: die biedt ook agents uit de database en ActivePieces-stukken aan die een
    workflowstap niet kan draaien. De bouwer kiest een agentstap uit DEZE lijst.
    """
    import importlib

    stap = importlib.import_module("src.core.als.agents.workflow_stap")
    agents = await stap.uitvoerbare_agents_voor_klant(current_user.tenant_id)
    return {
        "tenant_id": current_user.tenant_id,
        "agent_count": len(agents),
        "agents": agents,
        # Een lege lijst krijgt een Nederlandse uitleg, zodat het scherm niet stil leeg blijft.
        "uitleg": None if agents else stap.GEEN_AGENTS_UITLEG,
    }


# ============================================================================
# WebSocket Streaming Endpoint
# ============================================================================


@router.websocket("/ws/generate")
async def websocket_generate(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming workflow generation."""
    import json

    from src.core.auth.websocket_auth import websocket_auth

    user = await websocket_auth.authenticate(websocket)
    if not user:
        return

    try:
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)

            prompt = request_data.get("prompt", "")
            complexity = request_data.get("complexity", "medium")

            if not prompt or len(prompt) < 10:
                await websocket.send_json(
                    {"type": "error", "message": "Prompt must be at least 10 characters"}
                )
                continue

            correlation_id = str(uuid.uuid4())[:8]

            async def stream_update(update: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
                await websocket.send_json(update)

            generator = await create_workflow_generator(
                tenant_id=user.tenant_id, correlation_id=correlation_id
            )

            success, workflow, error = await generator.generate_workflow(
                user_prompt=prompt, complexity=complexity, stream_callback=stream_update
            )

            if success and workflow:
                await websocket.send_json(
                    {
                        "type": "result",
                        "success": True,
                        "workflow": workflow.dict(),
                        "correlation_id": correlation_id,
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "result",
                        "success": False,
                        "error": error,
                        "correlation_id": correlation_id,
                    }
                )

    except WebSocketDisconnect:
        websocket_auth.disconnect(user.user_id)
        logger.info("WebSocket client disconnected: tenant=%s", user.tenant_id)
    except Exception as e:
        logger.error("WebSocket error: %s: %s", type(e).__name__, e, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": "Er is een fout opgetreden."})
        except Exception as send_err:
            logger.debug(
                "Failed to send WebSocket error (client may be disconnected): %s: %s",
                type(send_err).__name__,
                send_err,
            )


# ============================================================================
# Health Check
# ============================================================================


@router.get("/health")
async def vibe_health() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Health check for VIBE workflow generation service."""
    return {
        "service": "vibe-workflow-generator",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "gemini-llm-integration",
            "multi-tenant-filtering",
            "websocket-streaming",
            "websocket-jwt-auth",
            "prometheus-metrics",
        ],
    }


# ============================================================================
# Secure WebSocket Endpoint (with JWT Auth)
# ============================================================================


@router.websocket("/ws/generate/secure")
async def websocket_generate_secure(websocket: WebSocket) -> None:
    """Secure WebSocket endpoint with JWT authentication."""
    import json

    from src.core.auth.websocket_auth import websocket_auth

    user = await websocket_auth.authenticate(websocket)
    if not user:
        return

    try:
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)

            prompt = request_data.get("prompt", "")
            complexity = request_data.get("complexity", "medium")

            if not prompt or len(prompt) < 10:
                await websocket.send_json(
                    {"type": "error", "message": "Prompt must be at least 10 characters"}
                )
                continue

            correlation_id = str(uuid.uuid4())[:8]

            async def stream_update_secure(update: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
                await websocket.send_json(update)

            generator = await create_workflow_generator(
                tenant_id=user.tenant_id, correlation_id=correlation_id
            )

            success, workflow, error = await generator.generate_workflow(
                user_prompt=prompt, complexity=complexity, stream_callback=stream_update_secure
            )

            if success and workflow:
                await websocket.send_json(
                    {
                        "type": "result",
                        "success": True,
                        "workflow": workflow.dict(),
                        "correlation_id": correlation_id,
                        "user_id": user.user_id,
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "result",
                        "success": False,
                        "error": error,
                        "correlation_id": correlation_id,
                    }
                )

    except WebSocketDisconnect:
        websocket_auth.disconnect(user.user_id)
        logger.info("Secure WebSocket disconnected: user=%s", user.user_id)
    except Exception as e:
        logger.error("Secure WebSocket error: %s: %s", type(e).__name__, e, exc_info=True)
        websocket_auth.disconnect(user.user_id)
