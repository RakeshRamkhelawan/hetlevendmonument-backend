"""
Futureproof LLM Health Check Endpoints

Provides comprehensive health monitoring and diagnostics for the LLM service.
Never fails - always returns useful information.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from src.core.api.dependencies import require_admin_user
from pydantic import BaseModel

from src.core.auth.api_deps import UserResponse
from src.core.shared.tenant_llm_keuze import namaak_toegestaan

from .dependencies import LLMProviderType, get_llm_service, require_platform_beheerder

router = APIRouter(prefix="/api/v1/system", tags=["System - LLM Health"])


class LLMHealthResponse(BaseModel):
    """LLM Health check response model"""

    status: str
    provider: str
    model: str
    initialized: bool
    available_providers: list[str]
    metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    config: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    recommendations: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type


class LLMTestResponse(BaseModel):
    """LLM test response model"""

    success: bool
    provider: str
    model: str
    response: str | None
    latency_ms: float
    error: str | None


@router.get("/llm-health", response_model=LLMHealthResponse)
async def llm_health_check(
    current_user: UserResponse = Depends(require_admin_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get comprehensive LLM health status.

    This endpoint provides:
    - Current provider status
    - Available fallback providers
    - Request metrics
    - Configuration summary
    - Recommendations for improvement

    Never fails - always returns valid health information.
    """
    try:
        service = await get_llm_service()
        health = await service.health_check()

        # Generate recommendations
        recommendations: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        if health["status"] == "degraded":
            recommendations.append(
                {
                    "severity": "warning",
                    "message": "Running in mock mode. Set DEEPSEEK_API_KEY or GOOGLE_API_KEY for real LLM.",
                    "action": "Add API key to .env file",
                }
            )
        elif health["status"] == "healthy":
            recommendations.append(
                {
                    "severity": "info",
                    "message": f"LLM service is operational with {health['provider']}",
                    "action": "No action needed",
                }
            )

        if health.get("metrics", {}).get("failed_requests", 0) > 10:
            recommendations.append(
                {
                    "severity": "error",
                    "message": "High failure rate detected",
                    "action": "Check provider API keys and network connectivity",
                }
            )

        return {
            "status": health["status"],
            "provider": health["provider"],
            "model": health["model"],
            "initialized": health["initialized"],
            "available_providers": health["available_providers"],
            "metrics": health["metrics"],
            "config": health["config"],
            "recommendations": recommendations,
        }

    except Exception as e:
        # Never fail - return error information
        return {
            "status": "error",
            "provider": "unknown",
            "model": "unknown",
            "initialized": False,
            "available_providers": [],
            "metrics": {},
            "config": {},
            "recommendations": [
                {
                    "severity": "critical",
                    "message": f"Health check failed: {type(e).__name__}",
                    "action": "Check application logs and restart if needed",
                }
            ],
        }


@router.post("/llm-test", response_model=LLMTestResponse)
async def llm_test_prompt(
    prompt: str = "Say 'Hello from SanskritiSetu' and nothing else.",
    current_user: UserResponse = Depends(require_admin_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Test LLM with a simple prompt.

    Useful for:
    - Verifying LLM connectivity
    - Testing response quality
    - Measuring latency
    - Debugging provider issues

    Args:
        prompt: Test prompt (optional, has default)

    Returns:
        Test results including success status, response, and latency
    """
    import time

    try:
        start_time: float = time.time()
        service = await get_llm_service()

        response: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ] = await service.generate_response(  # TODO(TYPE): replace Any with concrete type
            prompt=prompt, max_tokens=50, temperature=0.7
        )

        latency_ms: float = (time.time() - start_time) * 1000

        return {
            "success": response.get("success", False),
            "provider": service.current_provider.value,
            "model": service.current_model,
            "response": response.get("text") or response.get("content"),
            "latency_ms": round(latency_ms, 2),
            "error": response.get("error"),
        }

    except Exception as e:
        return {
            "success": False,
            "provider": "error",
            "model": "error",
            "response": None,
            "latency_ms": 0,
            "error": type(e).__name__,
        }


@router.get("/llm-providers")
async def llm_providers_info(
    current_user: UserResponse = Depends(require_admin_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get information about available LLM providers.

    Returns configuration status for each provider:
    - DeepSeek
    - Google Gemini
    - Ollama (local)
    - Mock (fallback)

    Useful for understanding what's configured and available.
    """
    import os

    return {
        "providers": {
            "deepseek": {
                "name": "DeepSeek",
                "configured": bool(os.getenv("DEEPSEEK_API_KEY")),
                "priority": 1,
                "description": "Fast cloud API (recommended)",
                "requirements": ["DEEPSEEK_API_KEY"],
            },
            "google": {
                "name": "Google Gemini",
                "configured": bool(os.getenv("GOOGLE_API_KEY")),
                "priority": 2,
                "description": "Google's multimodal AI",
                "requirements": ["GOOGLE_API_KEY"],
            },
            "ollama": {
                "name": "Ollama (Local)",
                "configured": True,  # Always available, may fail at runtime
                "priority": 3,
                "description": "Self-hosted local models",
                "requirements": ["OLLAMA_HOST (optional)"],
                "default_host": "http://localhost:11434",
            },
            "mock": {
                "name": "Mock Provider",
                "configured": True,  # Always available
                "priority": 99,
                "description": "Fallback for testing (always works)",
                "requirements": [],
            },
        },
        "configuration": {
            "preferred_provider": os.getenv("LLM_PROVIDER", "auto"),
            "auto_fallback": os.getenv("LLM_AUTO_FALLBACK", "true").lower() == "true",
            "health_check_interval": int(os.getenv("LLM_HEALTH_CHECK_INTERVAL", "60")),
        },
        "recommendations": [
            {
                "priority": 1,
                "action": "Set DEEPSEEK_API_KEY for best performance",
                "reason": "DeepSeek provides fast, reliable cloud API access",
            },
            {
                "priority": 2,
                "action": "Set GOOGLE_API_KEY as secondary",
                "reason": "Google Gemini offers multimodal capabilities",
            },
            {
                "priority": 3,
                "action": "Install Ollama for local processing",
                "reason": "Privacy-sensitive data never leaves your machine",
                "url": "https://ollama.com",
            },
        ],
    }


@router.post("/llm-switch-provider")
async def llm_switch_provider(
    provider: str,
    current_user: UserResponse = Depends(require_platform_beheerder),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Manually switch to a different LLM provider.

    Admin only endpoint for emergency provider switching.

    Args:
        provider: Provider name (google, ollama, mock)

    Returns:
        Status of the switch operation

    Raises:
        403: If user is not a platform administrator
        400: If provider is not available
    """
    try:
        service = await get_llm_service()

        # Validate provider
        try:
            target: LLMProviderType = LLMProviderType(provider.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider: {provider}. Valid: google, ollama, mock",
            )

        if target == LLMProviderType.MOCK and not namaak_toegestaan():
            raise HTTPException(
                status_code=400,
                detail="Een namaakmodel is alleen in tests toegestaan",
            )

        # Check if provider is available
        if target not in service.providers:
            raise HTTPException(
                status_code=400,
                detail=f"Provider {provider} is not available. Check configuration.",
            )

        # Switch provider
        old_provider: Any = service.current_provider  # TODO(TYPE): replace Any with concrete type
        service.current_provider = target

        return {
            "success": True,
            "previous_provider": old_provider.value,
            "current_provider": target.value,
            "message": f"Switched from {old_provider.value} to {target.value}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Provider switch failed")


@router.get("/llm-metrics")
async def llm_metrics(
    current_user: UserResponse = Depends(require_admin_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get LLM usage metrics.

    Returns:
        - Total requests
        - Success/failure rates
        - Provider switches
        - Average latency (if available)
    """
    try:
        service = await get_llm_service()
        metrics: dict[str, Any] = (  # TODO(TYPE): replace Any with concrete type
            service._metrics.copy()
        )  # TODO(TYPE): replace Any with concrete type

        # Calculate rates
        total: int = metrics.get("total_requests", 0)
        if total > 0:
            metrics["success_rate"] = metrics.get("successful_requests", 0) / total
            metrics["failure_rate"] = metrics.get("failed_requests", 0) / total
        else:
            metrics["success_rate"] = 0
            metrics["failure_rate"] = 0

        return {
            "metrics": metrics,
            "current_provider": service.current_provider.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        return {
            "error": type(e).__name__,
            "metrics": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
