"""
Translation Agent Routes - NEW AGENT for Unified Server
Provides text translation capabilities via FastAPI router
ASCII-only compliance enforced
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

# NOTE: ADR-034 Cat B Stap 3D -- FastAPI route met Depends(get_db), correct DI-patroon.
# import-linter Contract 7 ignore_imports gedocumenteerd. Backlog: SP-AGT-005.
from src.core.database.database import get_db

from .translation_service import create_translation_service

# Configure logging
logger = logging.getLogger("translation_agent_router")

# Create APIRouter for unified server integration
router = APIRouter(tags=["Translation Agent"])

# Agent configuration
AGENT_ID = "translation_agent"


class TaskExecutionRequest(BaseModel):
    """Request model for task execution (consistent with other agents)"""

    task_id: str = Field(description="Unique task identifier")
    description: str = Field(description="Task description")
    parameters: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Task parameters"
    )  # TODO(TYPE): replace Any with concrete type


class TaskExecutionResponse(BaseModel):
    """Response model for task execution (consistent with other agents)"""

    status: str = Field(description="Task execution status")
    result: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        description="Task execution result"
    )  # TODO(TYPE): replace Any with concrete type
    message: str = Field(description="Status message")


class TranslationRequest(BaseModel):
    """Direct translation request model"""

    text: str = Field(description="Text to translate")
    target_language: str = Field(description="Target language for translation")
    source_language: str = Field(default="auto", description="Source language (auto for detection)")


class LanguageDetectionRequest(BaseModel):
    """Language detection request model"""

    text: str = Field(description="Text to analyze for language detection")


# --- API Endpoints ---


@router.get("/")
async def translation_root() -> dict[str, object]:
    """Root endpoint for translation agent health check"""
    translation_service = create_translation_service()
    capabilities = await translation_service.get_translation_capabilities()

    return {
        "agent": "translation_agent",
        "status": "online",
        "version": "1.0.0",
        "endpoints": [
            "/execute_task",
            "/translate",
            "/detect_language",
            "/capabilities",
        ],
        "supported_languages": translation_service.get_supported_languages(),
        "capabilities": capabilities,
    }


@router.get("/health")
async def translation_health_check() -> dict[str, str]:
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "agent_id": AGENT_ID,
        "service": "text_translation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/execute_task", response_model=TaskExecutionResponse)
async def execute_translation_task(
    request: TaskExecutionRequest, db: AsyncSession = Depends(get_db)
) -> TaskExecutionResponse:
    """
    Execute translation task endpoint - Unified server integration
    Consistent interface with other agents for TaskPlanner integration
    """
    try:
        logger.info(f"Translation task received: {request.task_id}")
        logger.debug(f"Task description: {request.description}")
        logger.debug(f"Task parameters: {request.parameters}")

        # Extract action from parameters
        action = request.parameters.get("action", "translate_text")

        # Process based on action type
        if action == "translate_text":
            result = await _handle_text_translation(request.parameters)
        elif action == "detect_language":
            result = await _handle_language_detection(request.parameters)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {action}. Supported: translate_text, detect_language",
            )

        logger.info(f"Translation task {request.task_id} completed successfully")

        return TaskExecutionResponse(
            status="completed",
            result=result,
            message=f"Translation task '{action}' executed successfully",
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error during translation task execution: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/translate")
async def translate_text_direct(
    request: TranslationRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Direct translation endpoint for standalone usage
    """
    try:
        logger.info(f"Direct translation request: {request.target_language}")

        translation_service = create_translation_service()

        # Validate request
        if not translation_service.validate_translation_request(
            request.text, request.target_language
        ):
            raise HTTPException(status_code=400, detail="Invalid translation request parameters")

        # Perform translation
        result = await translation_service.translate_text(
            text=request.text,
            target_language=request.target_language,
            source_language=request.source_language,
        )

        logger.info(f"Direct translation completed: {request.target_language}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Direct translation failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.post("/detect_language")
async def detect_language_direct(
    request: LanguageDetectionRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Direct language detection endpoint
    """
    try:
        logger.info("Language detection request received")

        translation_service = create_translation_service()
        result = await translation_service.detect_language(request.text)

        logger.info(f"Language detection completed: {result.get('detected_language')}")
        return result

    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/capabilities")
async def get_translation_capabilities() -> object:
    """Get translation service capabilities"""
    try:
        translation_service = create_translation_service()
        capabilities = await translation_service.get_translation_capabilities()
        return capabilities

    except Exception as e:
        logger.error(f"Failed to get capabilities: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/languages")
async def get_supported_languages() -> dict[str, object]:
    """Get list of supported languages"""
    try:
        translation_service = create_translation_service()
        return {
            "supported_languages": translation_service.get_supported_languages(),
            "total_count": len(translation_service.get_supported_languages()),
        }

    except Exception as e:
        logger.error(f"Failed to get supported languages: {e}")
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get("/status")
async def translation_agent_status() -> dict[str, object]:
    """Agent status endpoint for agent registry"""
    translation_service = create_translation_service()

    return {
        "agent_id": "translation_agent",
        "agent_name": "Translation Agent",
        "agent_type": "translation_processor",
        "status": "online",
        "capabilities": ["text_translation", "language_processing"],
        "supported_task_types": ["translate_text", "detect_language"],
        "supported_languages": translation_service.get_supported_languages(),
        "endpoints": {
            "execute_task": "/execute_task",
            "translate": "/translate",
            "detect_language": "/detect_language",
            "capabilities": "/capabilities",
            "languages": "/languages",
            "health": "/health",
            "status": "/status",
        },
        "version": "1.0.0",
        "max_concurrent_tasks": 8,
    }


# --- Internal Task Handlers ---


async def _handle_text_translation(
    params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Handle translate_text action for TaskPlanner integration"""
    try:
        # Extract required parameters
        text = params.get("text", "")
        target_language = params.get("target_language", "english")
        source_language = params.get("source_language", "auto")

        if not text:
            raise ValueError("'text' is required parameter for translate_text action")

        # Create translation service
        translation_service = create_translation_service()

        # Validate request
        if not translation_service.validate_translation_request(text, target_language):
            raise ValueError(
                f"Invalid translation parameters: text='{text[:50]}...', target='{target_language}'"
            )

        # Perform translation
        result = await translation_service.translate_text(
            text=text, target_language=target_language, source_language=source_language
        )

        # Add agent metadata
        result.update(
            {
                "action": "translate_text",
                "agent": "translation_agent",
                "task_type": "text_translation",
            }
        )

        logger.info(f"Text translation completed: {target_language}")
        return result

    except Exception as e:
        logger.error(f"Error in text translation: {e}")
        raise


async def _handle_language_detection(
    params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Handle detect_language action"""
    try:
        # Extract required parameters
        text = params.get("text", "")

        if not text:
            raise ValueError("'text' is required parameter for detect_language action")

        # Create translation service
        translation_service = create_translation_service()

        # Perform language detection
        result = await translation_service.detect_language(text)

        # Add agent metadata
        result.update(
            {
                "action": "detect_language",
                "agent": "translation_agent",
                "task_type": "language_detection",
            }
        )

        logger.info(f"Language detection completed: {result.get('detected_language')}")
        return result

    except Exception as e:
        logger.error(f"Error in language detection: {e}")
        raise
