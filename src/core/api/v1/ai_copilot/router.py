import asyncio
import json
import logging
from typing import cast, Any
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.core.api._deprecation import (
    build_deprecation_headers,
    log_deprecated_call,
)
from src.core.api.dependencies import get_current_user
from src.core.api.v1.ai_copilot.dependencies import TenantTaalmodel

logger = logging.getLogger(__name__)

# Define router
router = APIRouter(prefix="/api/v1/ai-copilot", tags=["AI Copilot"])

SUCCESSOR_SUGGEST = "/api/v1/copilot/turn"


class CopilotRequest(BaseModel):
    query: str
    context: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


async def stream_generator(query: str, tenant_id: int | None = None) -> AsyncGenerator[str, None]:
    """
    Generates SSE events for the AI Copilot.

    Het taalmodel is dat van de TENANT van de gebruiker (brief 2026-10-20, ADR-041 B14); hier stond het
    platformmodel uit `LLM_PROVIDER` voor elke klant.
    """
    try:
        provider = TenantTaalmodel(tenant_id)

        # Initialize if not ready
        if hasattr(provider, "initialized") and not getattr(provider, "initialized", False):
            if hasattr(provider, "initialize"):
                await cast(Any, provider).initialize()  # TODO(TYPE): replace Any with concrete type

    except Exception as e:
        logger.error(f"Failed to get LLM provider: {e}")
        # Fallback: Send error to frontend
        yield f"event: error\ndata: {json.dumps({'message': 'LLM provider initialization failed'})}\n\n"
        return

    # 1. Reasoning phase
    yield "event: reasoning\ndata: Analyzing request context...\n\n"
    await asyncio.sleep(0.5)

    # 2. Stream content from LLM
    prompt = f"""
    You are an AI Co-Pilot for the SanskritiSetu platform.
    Help the user with: "{query}".
    Provide a concise and helpful response.
    """

    try:
        # [OK] Check if provider supports streaming
        if hasattr(provider, "stream_response"):
            async for chunk in cast(Any, provider).stream_response(  # TODO(TYPE): replace Any with concrete type
                prompt
            ):  # TODO(TYPE): replace Any with concrete type
                if "error" in chunk:
                    yield f"event: error\ndata: {json.dumps({'message': chunk['error']})}\n\n"
                    break
                if "text" in chunk:
                    payload = json.dumps({"token": chunk["text"]})
                    # Ensure JSON is valid for SSE
                    yield f"event: text\ndata: {payload}\n\n"
        else:
            # Fallback: Use non-streaming generate_response
            response = await provider.generate_response(prompt)
            if response.get("success"):
                content = response.get("content", "")
                # Simulate streaming by chunking
                words = content.split()
                for i, word in enumerate(words):
                    payload = json.dumps({"token": word + " "})
                    yield f"event: text\ndata: {payload}\n\n"
                    if i % 5 == 0:  # Add slight delay every 5 words
                        await asyncio.sleep(0.05)
            else:
                error_msg = response.get("error", "Unknown error")
                yield f"event: error\ndata: {json.dumps({'message': error_msg})}\n\n"

    except Exception as e:
        logger.error("stream_generator mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        logger.error(f"Streaming error: {e}")
        yield f"event: error\ndata: {json.dumps({'message': 'Er is een fout opgetreden.'})}\n\n"

    # 3. Simulate Tool Suggestions (Mock for Feature 1 MVP)
    # In full implementation, this comes from Router Agent or Tool Broker
    # We yield this as a 'data' event which the frontend can parse as suggested actions/tools
    tools = [
        {
            "name": "KnowledgeBase",
            "id": "kb-search",
            "description": "Search internal docs",
        },
        {
            "name": "WorkflowEngine",
            "id": "wf-create",
            "description": "Create a new workflow",
        },
    ]
    yield f"event: data\ndata: {json.dumps(tools)}\n\n"

    # End of stream
    yield "event: finish\ndata: {}\n\n"


@router.post(
    "/suggest-tools",
    summary="[DEPRECATED] Suggest tools (streaming)",
    description=(
        "**DEPRECATED**: Use `POST /api/v1/copilot/turn` instead. "
        "This endpoint will be removed on 2026-07-17."
    ),
    deprecated=True,
)
async def suggest_tools(
    request: CopilotRequest,
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> StreamingResponse:
    """
    Streams AI reasoning, text response, and tool suggestions.
    Feature 1: AI Co-Pilot (SSE Endpoint)

    DEPRECATED: Use POST /api/v1/copilot/turn instead.
    """
    log_deprecated_call(
        "/api/v1/ai-copilot/suggest-tools",
        tenant_id=getattr(current_user, "tenant_id", None),
        user_id=getattr(current_user, "id", None),
        successor=SUCCESSOR_SUGGEST,
    )
    return StreamingResponse(
        stream_generator(request.query, getattr(current_user, "tenant_id", None)),
        media_type="text/event-stream",
        headers=build_deprecation_headers(successor=SUCCESSOR_SUGGEST),
    )
