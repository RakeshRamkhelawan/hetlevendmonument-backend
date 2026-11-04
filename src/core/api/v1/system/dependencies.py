"""System domain dependencies (ADR-033 Laag 1).

Centraliseert forbidden imports uit llm_status.py en llm_health.py
zodat de router-bestanden geen directe domein-imports meer hebben.
"""
from fastapi import Depends, HTTPException

from src.core.agents.config.registry import get_registry
from src.core.api.dependencies import get_current_user
from src.core.auth.api_deps import UserResponse, is_platform_superuser
from src.core.llm.llm_config import LLMProviderType, get_llm_service
from src.core.llm.provider_factory import get_llm_provider
from src.core.llm.provider_registry import ProviderRegistry

async def require_platform_beheerder(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Alleen een PLATFORMbeheerder. `require_admin_user` is beheer binnen een tenant.

    De providerwissel zet een gedeelde singleton van het platform om voor iedereen; dat mag geen tenantbeheerder
    zijn (Gate 2, 2026-10-20).
    """
    if not is_platform_superuser(current_user):
        raise HTTPException(status_code=403, detail="Platform administrator privileges required")
    return current_user


__all__ = [
    "require_platform_beheerder",
    "get_registry",
    "LLMProviderType",
    "get_llm_service",
    "get_llm_provider",
    "ProviderRegistry",
]
