# orphan:exempt reason: SP-API-010 proxy stub -- TODO(SP-API-011): migreer naar v1/agentic/
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)
router = APIRouter(prefix="/api/v1/agentic", tags=["Agentic Workflow"])


class GenerateFlowRequest(BaseModel):
    prompt: str
    provider: str | None = None
    model: str | None = None


class GenerateFlowResponse(BaseModel):
    flow_structure: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    message: str


def _get_agentic_flow_service(
    current_user: UserResponse = Depends(get_current_user),
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Lazy dependency: only imports AgenticFlowService when a request arrives.

    De dienst krijgt de tenant van de ingelogde gebruiker: het taalmodel is de keuze van de klant
    (ADR-041 B14), niet van het platform of van het verzoek.
    """
    from src.domains.flows.agentic_service import AgenticFlowService

    return AgenticFlowService(tenant_id=current_user.tenant_id)


@router.post("/generate", response_model=GenerateFlowResponse, deprecated=True)
async def generate_workflow(
    request: GenerateFlowRequest,
    response: Response,
    current_user: UserResponse = Depends(get_current_user),
    service: Any = Depends(_get_agentic_flow_service),  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession = Depends(get_db),
) -> GenerateFlowResponse:
    """Generates a full workflow structure from a natural language prompt.

    Deprecated: use v1/agentic/ when available (SP-API-011).
    Governed by AgentCouncil deliberation before LLM execution.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Thu, 01 Jan 2028 00:00:00 GMT"
    # GEEN terugval op `current_user.id` (ADR-036 OP-52).
    #
    # Die terugval maakte van een gebruikers-id een tenant-id zodra `tenant_id` ontbrak of nul
    # was. De Council-poort hieronder krijgt die waarde als `tenant_id` en beslist erop; een
    # verkeerde waarde is daar geen schoonheidsfout maar een beslissing over de verkeerde
    # klant. De docstring van `require_council_approval` eist niet voor niets "from JWT/auth
    # context ONLY".
    #
    # Fail-closed: liever 403 dan een gok. Een token zonder tenant hoort hier niet te komen.
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geen tenantcontext in het token; deze aanroep kan niet worden beoordeeld.",
        )
    logger.info(
        "agentic.generate_request",
        extra={"user_id": current_user.id, "tenant_id": tenant_id},
    )

    # --- Governance gate (ADR-031) ---
    from src.core.copilot.council.factory import build_council
    from src.core.copilot.council.governance_gate import require_council_approval

    council = await build_council(db)
    await require_council_approval(
        council=council,
        tenant_id=tenant_id,
        user_id=current_user.id,
        action_type="agentic.generate_workflow",
        action_params={
            "prompt_length": len(request.prompt),
            "provider": request.provider or "default",
        },
        reasoning="User requested AI workflow generation from natural language prompt.",
        confidence=1.0,
        model_id=request.provider or "default",
        model_version=request.model or "1.0",
        context_snapshot={"prompt_preview": request.prompt[:100]},
        db=db,
    )

    try:
        result = await service.generate_flow_from_prompt(
            request.prompt,
            provider=request.provider,
            model=request.model,
            tenant_id=tenant_id,
        )

        return GenerateFlowResponse(
            flow_structure=result["flow_structure"],
            message=result["message"],
        )
    except Exception as e:
        logger.exception("Agentic Generation Failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        ) from e


# WebSocket Endpoint for Real-time Interaction
# TODO(SP-API-011): /ws/builder heeft geen v1/agentic/ equivalent -- v1/ biedt /ws/agent/stream (ander contract)
from fastapi import WebSocket, WebSocketDisconnect


@router.websocket("/ws/builder")
async def websocket_builder(websocket: WebSocket) -> None:
    """
    Real-time Focus Builder WebSocket.
    """
    from src.domains.flows.agentic_service import AgenticFlowService

    logger.info(f"[U+0001F50C] WS scope: {websocket.scope}")
    # 1. ACCEPT FIRST (Starlette 403 / TrustedHost workaround)
    logger.info("[U+0001F50C] WebSocket endpoint called - attempting connection")

    # Check for 'access_token' subprotocol (used by frontend for auth)
    protocols = websocket.scope.get("subprotocols", [])
    selected_protocol = "access_token" if "access_token" in protocols else None

    if selected_protocol:
        logger.info(f"[U+0001F91D] Accepting with subprotocol: {selected_protocol}")
        await websocket.accept(subprotocol=selected_protocol)
    else:
        await websocket.accept()

    logger.info("[OK] WebSocket accepted")

    # 2. AUTHENTICATE
    from src.core.auth.websocket_auth import websocket_auth

    user = await websocket_auth.authenticate_connected_user(websocket)

    if not user:
        # Auth failed, connection closed by authenticate_connected_user
        return

    # 3. Connection Established & Validated
    logger.info(f"WS Connected (User: {user.user_id})")

    logger.info(f"WS Connected (User: {user.user_id})")
    service = AgenticFlowService(tenant_id=user.tenant_id)  # imported at top of websocket_builder

    try:
        logger.info(f"[GREEN] WS Loop Started for User {user.user_id}")
        while True:
            logger.info("[WAIT] Waiting for WebSocket message...")
            data = await websocket.receive_json()
            logger.info(f"[U+0001F4E9] WS Message Received: {data}")

            msg_type = data.get("type")
            session_id = data.get("session_id") or str(user.user_id)

            # --- V4: Interactive Analysis Phase ---
            if msg_type == "analyze":
                prompt = data.get("payload") or data.get("prompt")
                if not prompt:
                    await websocket.send_json({"type": "error", "message": "Geen input ontvangen."})
                    continue

                await websocket.send_json(
                    {"type": "status", "status": "thinking", "message": "Analyseren..."}
                )

                try:
                    analysis = await service.start_interactive_session(prompt, session_id)
                    await websocket.send_json({"type": "assistant_message", "content": analysis})
                except Exception as e:
                    logger.error(f"Analysis Error: {e}")
                    await websocket.send_json({"type": "error", "message": "Er is een fout opgetreden."})

            # --- V4: Construction Phase ---
            elif msg_type == "confirm_build":
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "thinking",
                        "message": "Workflow bouwen...",
                    }
                )

                try:
                    result = await service.execute_approved_plan(session_id)
                    # Result is already a dict with type: 'flow_generated' | 'assistant_message' | 'error'
                    await websocket.send_json(result)
                except Exception as e:
                    logger.error(f"Build Error: {e}")
                    await websocket.send_json({"type": "error", "message": "Er is een fout opgetreden."})

            # --- V3 Legacy: Single-Shot Generation ---
            elif msg_type == "generate":
                prompt = data.get("prompt")
                # ... existing logic ...
                logger.info(f"[BRAIN] Processing GEN (Legacy). Prompt: {prompt[:50]}...")

                if not prompt:
                    logger.warning("[FAIL] No prompt provided in payload")
                    await websocket.send_json({"type": "error", "message": "No prompt provided"})
                    continue

                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "thinking",
                        "message": "Analyzing request...",
                    }
                )

                try:
                    provider = data.get("provider")
                    model = data.get("model")
                    # SECURITY: tenant_id MUST come from authenticated user context only.
                    # Never trust client-supplied tenant_id (ADR-003, ADR-031).
                    tenant_id = user.tenant_id

                    async def ws_status_callback(msg: str) -> None:
                        await websocket.send_json(
                            {"type": "status", "status": "thinking", "message": msg}
                        )

                    result = await service.generate_flow_from_prompt(
                        prompt,
                        provider=provider,
                        model=model,
                        status_callback=ws_status_callback,
                        tenant_id=tenant_id,
                    )

                    await websocket.send_json(
                        {
                            "type": "flow_generated",
                            "data": result["flow_structure"],
                            "message": result["message"],
                        }
                    )

                except Exception as e:
                    logger.error(f"[FAIL] WS Generation Error: {e}", exc_info=True)
                    await websocket.send_json({"type": "error", "message": "Er is een fout opgetreden."})

            else:
                logger.warning(f"[WARN] Unknown command received: {msg_type}")
                await websocket.send_json({"type": "error", "message": "Unknown command"})

    except WebSocketDisconnect:
        logger.info(f"Builder WebSocket disconnected (User: {user.user_id})")
    except Exception as e:
        logger.error(f"Builder WebSocket Error: {e}")
        try:
            await websocket.close()
        except Exception as ws_error:
            logger.debug(f"Failed to close builder websocket: {ws_error}")
