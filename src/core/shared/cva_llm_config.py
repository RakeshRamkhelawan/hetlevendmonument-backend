"""
CVA-specific LLM Configuration
Special configuration for CVA agent to use premium models
"""

import logging
import os
from src.core.shared.config import get_settings
from src.core.shared.llm_client import (
    LLMClient,
    LLMConfig,
    LLMModel,
    LLMProvider,
    create_llm_client_from_config,
)

logger = logging.getLogger(__name__)


def get_cva_llm_config() -> LLMConfig:
    """Get CVA-specific LLM configuration with premium models"""
    settings = get_settings()

    # CVA gets the best available model that may process customer data.
    # Priority: Ollama > Google Gemini > Mock. DeepSeek staat er NIET in, ook niet bij een gezette
    # sleutel (ADR-041 B14, brief 2026-10-19).

    if hasattr(settings, "ollama_base_url") and settings.ollama_base_url:
        # Use premium Ollama model for CVA (30B parameters)
        return LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA_3,  # Efficient Llama3 model for CVA
            api_key=settings.ollama_base_url,
            max_tokens=4000,  # Increased for strategic planning
            temperature=0.8,  # Slightly higher for creative strategic thinking
            timeout=300.0,  # 5 minutes timeout for model loading
        )
    elif settings.google_api_key:
        # Use Gemini 2.5 Pro for CVA (premium Google model)
        return LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_2_5_FLASH,  # Premium Gemini model for CVA (Flash for reliability)
            api_key=settings.google_api_key,
            max_tokens=4000,  # Increased for strategic planning
            temperature=0.8,  # Slightly higher for creative strategic thinking
        )
    else:
        # No LLM provider available - fail in production
        environment = os.getenv("ENVIRONMENT", "development")
        if environment == "production":
            error_msg = (
                "CVA LLM Configuration Error: No LLM API keys configured. "
                "At least one of these environment variables must be set: "
                "OLLAMA_BASE_URL or GOOGLE_API_KEY"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Development: Fallback to mock with enhanced responses
        logger.warning("CVA: No LLM API keys configured, using mock LLM (development only)")
        return LLMConfig(
            provider=LLMProvider.MOCK,
            model=LLMModel.MOCK_MODEL,
            api_key="mock-key-development-only",  # gitleaks:allow
            max_tokens=4000,
            temperature=0.8,
        )


def get_agent_llm_config() -> LLMConfig:
    """Get standard agent LLM configuration (cost-effective models)"""
    settings = get_settings()

    # Standard agents get efficient models
    # Priority: Ollama default > Google Gemini 2.5 Flash > Mock

    if hasattr(settings, "ollama_base_url") and settings.ollama_base_url:
        # Use efficient Ollama model for standard agents
        return LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA_3,  # Efficient Llama3 model for agents
            api_key=settings.ollama_base_url,
            max_tokens=2000,
            temperature=0.7,
            timeout=300.0,  # 5 minutes timeout for model loading
        )
    elif settings.google_api_key:
        # Use Gemini 2.5 Flash for standard agents (cost-effective)
        return LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_2_5_FLASH,  # Cost-effective Gemini model
            api_key=settings.google_api_key,
            max_tokens=2000,
            temperature=0.7,
        )
    else:
        # No LLM provider available - fail in production
        environment = os.getenv("ENVIRONMENT", "development")
        if environment == "production":
            error_msg = (
                "Agent LLM Configuration Error: No LLM API keys configured. "
                "At least one of these environment variables must be set: "
                "OLLAMA_BASE_URL or GOOGLE_API_KEY"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Development: Fallback to mock
        logger.warning("Agent: No LLM API keys configured, using mock LLM (development only)")
        return LLMConfig(
            provider=LLMProvider.MOCK,
            model=LLMModel.MOCK_MODEL,
            api_key="mock-key-development-only",  # gitleaks:allow
            max_tokens=2000,
            temperature=0.7,
        )


def create_cva_llm_client() -> LLMClient:
    """Create LLM client specifically optimized for CVA"""
    config = get_cva_llm_config()
    return create_llm_client_from_config(config)


def create_agent_llm_client() -> LLMClient:
    """Create LLM client for standard agents"""
    config = get_agent_llm_config()
    return create_llm_client_from_config(config)
