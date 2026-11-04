"""
LLM Service - Provider-agnostic abstraction layer

Architecture:
- LLMProvider (ABC): Interface for all LLM providers
- ProviderFactory: Creates provider instances based on config
- Concrete providers: Ollama, DeepSeek, Gemini, etc.

Usage:
    from src.core.services.llm import LLMService

    service = LLMService(provider="ollama")  # or "deepseek", "gemini", etc.
    response = await service.generate([{"role": "user", "content": "Hello"}])
"""

from typing import Any

from src.core.services.llm.base import (
    LLMAuthenticationError,
    LLMContentFilterError,
    LLMProvider,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    TokenBudgetExceededError,
)
from src.core.services.llm.factory import ProviderFactory
from src.core.services.llm.service import LLMService

__all__ = [
    "LLMProvider",
    "LLMService",
    "ProviderFactory",
    "LLMServiceError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMAuthenticationError",
    "LLMContentFilterError",
    "TokenBudgetExceededError",
]
