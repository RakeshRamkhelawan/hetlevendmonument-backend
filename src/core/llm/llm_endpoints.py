"""
LLM API Endpoints
FastAPI routes for LLM integration
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .llm_client import LLMModel, LLMProvider, ModelInfo
from .llm_service import LLMService

logger = logging.getLogger(__name__)

# Initialize LLM service
llm_service = LLMService()

# Router for LLM endpoints
router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


class ChatRequest(BaseModel):
    """Request model for LLM chat"""

    message: str
    provider: str | None = None
    model: str | None = None
    temperature: float | None = 0.7
    max_tokens: int | None = 1000


class ChatResponse(BaseModel):
    """Response model for LLM chat"""

    content: str
    success: bool
    provider: str
    model: str
    response_time: float | None = None
    usage: dict[str, int] | None = None
    error: str | None = None


@router.get("/test")
async def test_llm_connectivity() -> dict[str, object]:
    """Test LLM connectivity and status"""
    try:
        test_results = await llm_service.test_connectivity()
        return {
            "message": "LLM connectivity test completed",
            "service": "llm-integration",
            "status": "operational" if test_results["successful"] > 0 else "degraded",
            "results": test_results,
        }
    except Exception as e:
        logger.error(f"LLM test error: {e}")
        raise HTTPException(status_code=500, detail="LLM test failed")


@router.post("/chat", response_model=ChatResponse)
async def chat_with_llm(request: ChatRequest) -> ChatResponse:
    """Generate response using LLM"""
    try:
        # Convert string parameters to enums if provided
        provider = None
        if request.provider:
            try:
                provider = LLMProvider(request.provider)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid provider: {request.provider}")

        model: str | None = None
        if request.model:
            try:
                model_enum = LLMModel(request.model)
                model = model_enum.value
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")

        # Generate response
        response = await llm_service.generate_response(
            prompt=request.message,
            provider=provider,
            model=model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return ChatResponse(
            content=response.get("content", "No response generated"),
            success=response.get("success", False),
            provider=response.get("provider", "unknown"),
            model=response.get("model", "unknown"),
            response_time=response.get("response_time"),
            usage=response.get("usage"),
            error=response.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail="Chat failed")


@router.get("/status")
async def get_llm_status() -> dict[str, object]:
    """Get LLM service status"""
    try:
        status = await llm_service.get_service_status()
        return {
            "message": "LLM service status retrieved",
            "timestamp": "2025-01-16T12:00:00Z",  # Would use datetime.now(timezone.utc) in production
            "status": status,
        }
    except Exception as e:
        logger.error(f"Status error: {e}")
        raise HTTPException(status_code=500, detail="Status retrieval failed")


@router.get("/models")
async def get_available_models() -> list[ModelInfo]:
    """Get available LLM models with rich information from all providers"""
    try:
        # Get dynamic models info from service
        models_info = llm_service.get_models_info()

        # If no models discovered yet, initialize if needed
        if not models_info and not llm_service.initialized:
            await llm_service.initialize()
            models_info = llm_service.get_models_info()

        return models_info
    except Exception as e:
        logger.error(f"Models error: {e}")
        raise HTTPException(status_code=500, detail="Models retrieval failed")


@router.get("/providers")
async def get_providers() -> dict[str, object]:
    """Get available LLM providers"""
    try:
        providers: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for provider_name, provider_instance in llm_service.providers.items():
            providers[provider_name.value] = {
                "available": provider_instance.initialized,
                "models": provider_instance.model_names,
            }

        return {
            "message": "LLM providers information retrieved",
            "total_providers": len(providers),
            "providers": providers,
            "default": llm_service.default_provider.value,
        }
    except Exception as e:
        logger.error(f"Providers error: {e}")
        raise HTTPException(status_code=500, detail="Providers retrieval failed")


# Health check for LLM service
@router.get("/health")
async def llm_health_check() -> dict[str, object]:
    """LLM service health check"""
    try:
        status = await llm_service.get_service_status()

        healthy_providers = sum(
            1
            for provider_status in status["providers"].values()
            if provider_status.get("available", False)
        )

        health_status = "healthy" if healthy_providers > 0 else "unhealthy"

        return {
            "service": "llm",
            "status": health_status,
            "providers_total": status["total_providers"],
            "providers_healthy": healthy_providers,
            "default_provider": status["default_provider"],
            "ascii_compliance": "enforced",
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"service": "llm", "status": "error", "error": "Er is een fout opgetreden."}
