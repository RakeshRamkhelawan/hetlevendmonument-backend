"""
LLM Provider Health Check Endpoint
Allows monitoring which provider is active and its status
"""

from typing import cast, Any

from fastapi import APIRouter, Depends
from src.core.api.dependencies import require_admin_user

from datetime import datetime, timezone
from .dependencies import get_registry, get_llm_provider, ProviderRegistry
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["System"])


@router.get("/llm-status")
async def llm_status(
    current_user: Any = Depends(require_admin_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get current LLM provider status and configuration.

    Returns:
        - active_provider: Which provider is currently in use
        - available_providers: All registered providers
        - connection_status: Health check result
        - models: Available models for active provider
    """
    try:
        # Get active provider
        provider = get_llm_provider()
        provider_name = provider.provider.value if hasattr(provider, "provider") else "unknown"

        # Test connection
        connection_result = await provider.validate_connection()

        # Handle different return types (Protocol vs Base Class mismatch)
        status_value = "unknown"
        if isinstance(connection_result, bool):
            status_value = "connected" if connection_result else "disconnected"
        elif isinstance(connection_result, dict):
            status_value = connection_result.get("status", "unknown")

        # Get available models
        models: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if hasattr(provider, "model_names"):
            models = cast(Any, provider).model_names  # TODO(TYPE): replace Any with concrete type
        elif hasattr(provider, "get_available_models"):
            models = await cast(
                Any, provider  # TODO(TYPE): replace Any with concrete type
            ).get_available_models()  # TODO(TYPE): replace Any with concrete type

        return {
            "status": "ok",
            "active_provider": provider_name,
            "available_providers": ProviderRegistry.list_providers(),
            "connection_status": status_value,
            "models": models,
            "initialized": getattr(provider, "initialized", False),
        }

    except Exception as e:
        logger.error("llm_status mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        return {
            "status": "error",
            "error": "Er is een fout opgetreden.",
            "available_providers": ProviderRegistry.list_providers(),
        }


# Admin endpoints for agent config cache management


@router.post("/agents/config-cache/reload/{agent_name}")
async def reload_agent_config(
    agent_name: str,
    current_user: Any = Depends(require_admin_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Force reload specific agent config from disk.

    Admin only endpoint for emergency config updates.
    Invalidates all caches and reloads from YAML file.

    Args:
        agent_name: Name of the agent to reload (e.g., "PythonProAgent")

    Returns:
        Status of reload operation

    Raises:
        403: If user is not an admin
        404: If agent config not found
    """
    registry = get_registry()

    try:
        success = await registry.reload(agent_name)

        if success:
            return {
                "agent_name": agent_name,
                "status": "reloaded",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404,
                detail=f"Agent config not found or reload failed: {agent_name}",
            )
    except Exception as e:
        logger.error("reload_agent_config mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Reload failed")


@router.post("/agents/config-cache/reload-all")
async def reload_all_configs(
    current_user: Any = Depends(require_admin_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Force reload all agent configs from disk.

    Admin only endpoint for bulk config updates.
    Invalidates all caches and reloads all YAML files.

    Returns:
        Status of reload operation with count of loaded configs

    Raises:
        403: If user is not an admin
    """
    registry = get_registry()

    try:
        count = await registry.reload_all()

        return {
            "status": "all_configs_reloaded",
            "count": count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("reload_all_configs mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Reload failed")


@router.get("/agents/config-cache/stats")
async def get_config_cache_stats(
    current_user: Any = Depends(require_admin_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get agent config cache statistics.

    Returns information about cached configs, memory usage, and hit rates.
    Admin only endpoint.

    Returns:
        Cache statistics dictionary

    Raises:
        403: If user is not an admin
    """
    registry = get_registry()

    return {
        "registry": registry.get_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
