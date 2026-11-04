# orphan:exempt -- legacy shim, pre-migration flat endpoint
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.core.api.setup.app_state import app_state
from src.core.auth.api_deps import get_current_user, UserResponse
from src.core.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Learning & Conversations"])


@router.get("/api/v1/learning/conversations", dependencies=[Depends(get_current_user)])
async def get_learning_conversations(
    limit: int = 100, current_user: UserResponse = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not app_state.get("database_initialized", False):
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        learning_data = await ConversationService.get_learning_data(limit=limit)
        return {"success": True, "data": learning_data, "count": len(learning_data)}
    except Exception as e:
        logger.error("get_learning_conversations mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/api/v1/learning/analytics", dependencies=[Depends(get_current_user)])
async def get_conversation_analytics(
    days: int = 30, current_user: UserResponse = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not app_state.get("database_initialized", False):
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        analytics = await ConversationService.get_conversation_analytics(days=days)
        return {"success": True, "analytics": analytics}
    except Exception as e:
        logger.error("get_conversation_analytics mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.post("/api/v1/learning/feedback", dependencies=[Depends(get_current_user)])
async def add_conversation_feedback(
    feedback_data: dict[str, Any], current_user: UserResponse = Depends(get_current_user)  # TODO(TYPE): replace Any with concrete type
) -> dict[str, bool]:
    if not app_state.get("database_initialized", False):
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        conversation_id = feedback_data.get("conversation_id")
        feedback = feedback_data.get("feedback")
        if not conversation_id or not feedback:
            raise HTTPException(
                status_code=400,
                detail="conversation_id and feedback are required",
            )
        success = await ConversationService.add_feedback(
            str(conversation_id),
            str(feedback),
            feedback_data.get("details", ""),
        )
        return {"success": success}
    except Exception as e:
        logger.error("add_conversation_feedback mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/api/v1/conversations/{session_id}", dependencies=[Depends(get_current_user)])
async def get_conversation_history(
    session_id: str, limit: int = 50, current_user: UserResponse = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not app_state.get("database_initialized", False):
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        history = await ConversationService.get_conversation_history(session_id, limit=limit)
        return {"success": True, "history": history}
    except Exception as e:
        logger.error("get_conversation_history mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")
