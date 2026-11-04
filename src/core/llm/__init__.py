"""
LLM Integration Module
Provides multi-provider LLM support for Sanskriti Setu AI Platform

Architecture:
    - provider_factory.py: Lazy loading factory with dependency injection
    - mock_provider.py: Mock provider for testing
    - gemini_provider.py: Google Gemini implementation
    - llm_client.py: Base classes and protocols
    - llm_service.py: High-level service manager
    - intelligent_router.py: Request routing between models
"""

# New: Lazy loading factory pattern for testability
from typing import Any

from .gemini_provider import GeminiProvider
from .intelligent_router import IntelligentRouter, RoutingStrategy, get_router, initialize_router

# Phase 1 Enhancement: Exception hierarchy
from .llm_client import (
    LLMAuthenticationError,
    LLMClient,
    LLMContentFilterError,
    LLMModel,
    LLMProvider,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    TokenBudgetExceededError,
)
from .llm_service import LLMService
from .mock_provider import MockProvider
from .provider_factory import (
    LLMProviderFactory,
    LLMProviderProtocol,
    get_llm_provider,
    reset_llm_providers,
)

__all__ = [
    # Core classes
    "LLMClient",
    "LLMProvider",
    "LLMModel",
    "GeminiProvider",
    "LLMService",
    # Phase 1: Exception hierarchy
    "LLMServiceError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMAuthenticationError",
    "LLMContentFilterError",
    "TokenBudgetExceededError",
    # Routing
    "IntelligentRouter",
    "RoutingStrategy",
    "get_router",
    "initialize_router",
    # Factory pattern (RECOMMENDED for new code)
    "LLMProviderFactory",
    "LLMProviderProtocol",
    "get_llm_provider",
    "reset_llm_providers",
    # Testing support
    "MockProvider",
]
