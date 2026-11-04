# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
Assistant API Endpoints
Handles requests for the Context-Aware Agentic Assistant.
Integrated with Ultimate CVA System Prompt and Tools.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.api.assistant_endpoints_dependencies import ConversationMemory
from src.core.api.assistant_endpoints_dependencies import UltimateExecutionResult
from src.core.api.assistant_endpoints_dependencies import get_redis_client
from src.core.auth.api_deps import UserResponse, get_current_user

router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)

# ============================================================================
# Models
# ============================================================================


class ClientContext(BaseModel):
    route: str = Field(default="/", description="Current page route")
    active_selection: str | None = Field(default=None, description="Selected text")
    language: str | None = Field(default="en", description="User interface language")


class AssistantRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    client_context: ClientContext = Field(default_factory=ClientContext)
    model: str | None = Field(default="gemini", description="Model to use")


class AssistantResponse(BaseModel):
    message: str
    actions: list[dict[str, Any]] | None = None  # TODO(TYPE): replace Any with concrete type
    suggestions: list[str] | None = None
    confidence: float = 0.0
    plan: list[str] | None = None
    thought_process: str | None = None
    data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/ask", response_model=AssistantResponse)
async def ask_assistant(
    request: AssistantRequest,
    current_user: UserResponse = Depends(get_current_user),
) -> AssistantResponse:
    """
    Process user query with context-awareness and persistent memory.
    """
    try:
        # 1. Initialize Memory
        redis = await get_redis_client()
        memory = ConversationMemory(redis, tenant_id=current_user.tenant_id)

        # 2. Get History
        history = await memory.get_history(current_user.id, limit=10)

        # 3. Initialize Agent
        # Note: In production we might use a registry, but for now we use UltimateCVAAgent
        # 3. Initialize Agent
        # Note: In production we might use a registry, but for now we use UltimateCVAAgent
        # Use factory to ensure initialization (LLM service, etc.)
        from src.core.api.assistant_endpoints_dependencies import create_ultimate_cva_agent

        agent = await create_ultimate_cva_agent()

        # 4. Prepare Context
        full_context = {
            "route": request.client_context.route,
            "selection": request.client_context.active_selection,
            "language": request.client_context.language,
            "history": history,
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "model": request.model,
        }

        # 5. Process Command
        result: UltimateExecutionResult = await agent.process_command(
            user_input=request.query, context=full_context
        )

        # 6. Save to Memory
        await memory.add_message(current_user.id, {"role": "user", "content": request.query})

        # Handle dict response from UltimateExecutionResult
        res_data = (
            result.response
            if isinstance(result.response, dict)
            else {"message": str(result.response)}
        )
        res_message = res_data.get("message", str(result.response))

        await memory.add_message(current_user.id, {"role": "assistant", "content": res_message})

        # 7. Extract Actions and Data
        raw_actions = res_data.get("actions", [])
        actions: list[dict[str, Any]] | None = None  # TODO(TYPE): replace Any with concrete type
        if isinstance(raw_actions, list):
            actions = raw_actions

        # Extract Plan and Thought Process from result.data dict
        result_data = result.data if result.data is not None else {}
        plan = result_data.get("plan")
        thought_process = result_data.get("thought_process")

        # If adjusted, use the adjusted/final versions
        if result_data.get("adjusted"):
            thought_process = result_data.get("final_thought") or thought_process

        return AssistantResponse(
            message=res_message,
            actions=actions,
            suggestions=result.suggestions,
            confidence=result.confidence,
            plan=plan,
            thought_process=thought_process,
            data=result.data,
        )

    except Exception as e:
        logger.error(f"Assistant error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


# Compatibility alias for legacy test patches
try:
    from src.core.api.assistant_endpoints_dependencies import UltimateCVAAgent  # noqa: F401
except Exception:
    UltimateCVAAgent = None  # type: ignore[misc,assignment]
