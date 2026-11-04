"""
Futureproof LLM Configuration Module

This module ensures an LLM provider is ALWAYS available and properly configured.
Never fails to load - guarantees a working LLM configuration.

Key Principles:
1. ALWAYS_LOAD: An LLM provider is always loaded, never fails
2. SMART_DEFAULTS: Automatically selects best available provider
3. GRACEFUL_DEGRADATION: Falls back through multiple levels
4. SELF_HEALING: Reconnects automatically on failure
5. OBSERVABLE: Health checks and monitoring built-in

Environment Variables:
    LLM_PROVIDER: Preferred provider (deepseek, google, ollama, mock)
    LLM_AUTO_FALLBACK: Enable automatic fallback (default: true)
    LLM_HEALTH_CHECK_INTERVAL: Seconds between health checks (default: 60)
    LLM_MAX_RETRIES: Max retries on failure (default: 3)

    Provider-specific:
    DEEPSEEK_API_KEY: API key for DeepSeek
    GOOGLE_API_KEY: API key for Google Gemini
    OLLAMA_HOST: Ollama host (default: http://localhost:11434)

Usage:
    from src.core.llm.llm_config import get_llm_service, LLMConfig

    # Guaranteed to work - never raises
    service = await get_llm_service()

    # Check health
    health = await service.health_check()
    if health['status'] == 'healthy':
        response = await service.generate_response("Hello")
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, cast
from src.core.shared.model_deur import bewaakt_model_aanroep

logger = logging.getLogger(__name__)


class LLMProviderType(str, Enum):
    """Available LLM provider types"""

    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    OLLAMA = "ollama"
    MOCK = "mock"
    AUTO = "auto"


def _parse_provider_env() -> "LLMProviderType":
    """Parse LLM_PROVIDER env var, falling back to AUTO for unknown values."""
    raw = os.getenv("LLM_PROVIDER", "").lower()
    if not raw:
        return LLMProviderType.AUTO
    try:
        return LLMProviderType(raw)
    except ValueError:
        logger.warning("Unknown LLM_PROVIDER=%r, falling back to AUTO", raw)
        return LLMProviderType.AUTO


@dataclass
class LLMConfig:
    """Futureproof LLM Configuration

    This configuration guarantees an LLM is always available.
    """

    # Provider selection
    preferred_provider: LLMProviderType = field(default_factory=lambda: _parse_provider_env())

    # Fallback behavior
    auto_fallback: bool = field(
        default_factory=lambda: os.getenv("LLM_AUTO_FALLBACK", "true").lower() == "true"
    )

    # Retry configuration
    max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "3")))
    retry_delay: float = field(default_factory=lambda: float(os.getenv("LLM_RETRY_DELAY", "1.0")))

    # Health check configuration
    health_check_interval: int = field(
        default_factory=lambda: int(os.getenv("LLM_HEALTH_CHECK_INTERVAL", "60"))
    )
    enable_health_monitoring: bool = field(
        default_factory=lambda: os.getenv("LLM_ENABLE_HEALTH_MONITORING", "true").lower() == "true"
    )

    # Provider-specific settings
    deepseek_api_key: str | None = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY"))
    google_api_key: str | None = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    ollama_host: str = field(
        default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434")
    )

    # Feature flags
    enable_caching: bool = field(
        default_factory=lambda: os.getenv("LLM_ENABLE_CACHING", "true").lower() == "true"
    )
    enable_metrics: bool = field(
        default_factory=lambda: os.getenv("LLM_ENABLE_METRICS", "true").lower() == "true"
    )

    def __post_init__(self) -> None:
        """Validate and normalize configuration"""
        # Ensure we have a valid provider
        if isinstance(self.preferred_provider, str):
            try:
                self.preferred_provider = LLMProviderType(self.preferred_provider)
            except ValueError:
                logger.warning("Invalid LLM_PROVIDER '%s', using AUTO", self.preferred_provider)
                self.preferred_provider = LLMProviderType.AUTO

    @property
    def is_configured(self) -> bool:
        """Check if any real provider is configured"""
        return bool(self.google_api_key)

    @property
    def available_providers(self) -> list[LLMProviderType]:
        """List of providers that can be attempted"""
        providers = []

        # DeepSeek staat hier NIET, ook niet bij een gezette sleutel: deze service draait over klantgegevens
        # (ADR-041 B14, brief 2026-10-19).
        if self.google_api_key:
            providers.append(LLMProviderType.GOOGLE)
        # Ollama is always available (may fail at runtime)
        providers.append(LLMProviderType.OLLAMA)

        # Mock is always the final fallback
        providers.append(LLMProviderType.MOCK)

        return providers

    def get_provider_priority(self) -> list[LLMProviderType]:
        """Get provider initialization priority order"""
        available = self.available_providers

        # If preferred provider is specified and available, try it first
        if self.preferred_provider != LLMProviderType.AUTO:
            if self.preferred_provider in available:
                # Move preferred to front
                available.remove(self.preferred_provider)
                return [self.preferred_provider] + available

        # Default priority: Google > Ollama > Mock
        priority_order = [
            LLMProviderType.GOOGLE,
            LLMProviderType.OLLAMA,
            LLMProviderType.MOCK,
        ]

        # Return in priority order
        return [p for p in priority_order if p in available]


class GuaranteedLLMService:
    """
    Futureproof LLM Service that ALWAYS has a working provider.

    Key guarantees:
    1. Never fails to initialize - always has at least Mock provider
    2. Automatic failover between providers
    3. Health monitoring with automatic recovery
    4. Self-healing on connection failures

    Usage:
        service = GuaranteedLLMService()
        await service.initialize()  # Never raises

        # Always works
        response = await service.generate_response("Hello")
    """

    _instance: Optional["GuaranteedLLMService"] = None
    _initialized: bool = False

    def __new__(cls) -> "GuaranteedLLMService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.config = LLMConfig()
        self.providers: dict[
            LLMProviderType, Any  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self.current_provider: LLMProviderType = LLMProviderType.MOCK
        self.current_model: str = "mock-model"
        self._health_status: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "status": "unknown",
            "last_check": None,
            "failures": 0,
        }
        self._metrics: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "provider_switches": 0,
        }

    async def initialize(self) -> bool:
        """
        Initialize LLM service with guaranteed success.

        This method NEVER fails. It will always find at least a mock provider.

        Returns:
            bool: True if at least one provider initialized successfully
        """
        if self._initialized:
            return True

        logger.info("=" * 60)
        logger.info("FUTUREPROOF LLM SERVICE INITIALIZATION")
        logger.info("=" * 60)
        logger.info("Preferred provider: %s", self.config.preferred_provider.value)
        logger.info("Auto fallback: %s", self.config.auto_fallback)
        logger.info("Available providers: %s", [p.value for p in self.config.available_providers])

        # Try providers in priority order
        priority_list = self.config.get_provider_priority()
        initialization_success = False

        for provider_type in priority_list:
            try:
                success = await self._try_initialize_provider(provider_type)
                if success:
                    self.current_provider = provider_type
                    initialization_success = True
                    logger.info("Successfully initialized %s", provider_type.value)

                    # If this is not the mock provider, we can stop
                    if provider_type != LLMProviderType.MOCK:
                        break
                else:
                    logger.warning("%s initialization returned False", provider_type.value)
            except Exception as e:
                logger.error(
                    "%s initialization failed: %s: %s",
                    provider_type.value,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                continue

        # Guarantee: If nothing worked, force mock provider
        if not initialization_success or not self.providers:
            logger.warning("No providers initialized, forcing Mock provider")
            await self._force_mock_provider()

        self._initialized = True

        # Log final status
        logger.info("=" * 60)
        logger.info("LLM SERVICE READY")
        logger.info("   Provider: %s", self.current_provider.value)
        logger.info("   Model: %s", self.current_model)
        logger.info("   Health: %s", self._health_status["status"])
        logger.info("=" * 60)

        return True

    async def _try_initialize_provider(self, provider_type: LLMProviderType) -> bool:
        """Try to initialize a specific provider"""
        from .gemini_provider import GeminiProvider
        from .mock_provider import MockProvider
        from .ollama_provider import OllamaProvider

        provider_map = {
            LLMProviderType.GOOGLE: (
                GeminiProvider,
                self.config.google_api_key,
                "gemini-2.5-pro",
            ),
            LLMProviderType.OLLAMA: (OllamaProvider, None, "llama3:latest"),
            LLMProviderType.MOCK: (MockProvider, None, "mock-model"),
        }

        if provider_type not in provider_map:
            return False

        provider_class, api_key, default_model = provider_map[provider_type]

        try:
            if api_key:
                provider = provider_class(api_key=api_key)
            else:
                provider = provider_class()

            success = await provider.initialize()

            if success:
                self.providers[provider_type] = provider
                self.current_model = default_model
                return True
            return False

        except Exception as e:
            logger.debug("Provider %s init error: %s", provider_type.value, e)
            return False

    async def _force_mock_provider(self) -> None:
        """Force initialization of mock provider as last resort"""
        from .mock_provider import MockProvider

        try:
            provider = MockProvider()
            await provider.initialize()
            self.providers[LLMProviderType.MOCK] = provider
            self.current_provider = LLMProviderType.MOCK
            self.current_model = "mock-model"
            self._health_status["status"] = "degraded"
            logger.info("Mock provider initialized as fallback")
        except Exception as e:
            logger.error("CRITICAL: Even Mock provider failed: %s", e, exc_info=True)
            # This should never happen, but we handle it gracefully
            self._health_status["status"] = "critical"

    async def health_check(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Perform comprehensive health check.

        Returns:
            Dict with status, provider info, and metrics
        """
        # Test current provider
        try:
            current = self.providers.get(self.current_provider)
            if current:
                test_result = await current.test_connectivity()
                self._health_status.update(
                    {
                        "status": "healthy" if test_result.get("successful", 0) > 0 else "degraded",
                        "last_check": test_result,
                        "provider": self.current_provider.value,
                        "model": self.current_model,
                    }
                )
            else:
                self._health_status["status"] = "no_provider"
        except Exception as e:
            self._health_status["status"] = "error"
            self._health_status["error"] = str(e)

        return {
            "status": self._health_status["status"],
            "provider": self.current_provider.value,
            "model": self.current_model,
            "initialized": self._initialized,
            "available_providers": list(self.providers.keys()),
            "metrics": self._metrics.copy(),
            "config": {
                "auto_fallback": self.config.auto_fallback,
                "max_retries": self.config.max_retries,
            },
        }

    @bewaakt_model_aanroep
    async def generate_response(
        self, prompt: str, provider: LLMProviderType | None = None, **kwargs: Any
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate response with automatic failover.

        This method guarantees a response - never raises.
        Falls back through providers on failure.
        """
        self._metrics["total_requests"] += 1

        # Determine which provider to use
        target_provider = provider or self.current_provider

        # Try the primary provider first
        providers_to_try = [target_provider]

        # Add fallback providers if enabled
        if self.config.auto_fallback and target_provider != LLMProviderType.MOCK:
            for p in self.config.get_provider_priority():
                if p != target_provider and p in self.providers:
                    providers_to_try.append(p)

        last_error = None

        for attempt_provider in providers_to_try:
            try:
                provider_instance = self.providers.get(attempt_provider)
                if not provider_instance:
                    continue

                response = await provider_instance.generate_response(prompt, **kwargs)

                # Track metrics
                if response.get("success", False):
                    self._metrics["successful_requests"] += 1

                    # Switch to working provider if different
                    if attempt_provider != self.current_provider:
                        logger.info("Switching to working provider: %s", attempt_provider.value)
                        self.current_provider = attempt_provider
                        self._metrics["provider_switches"] += 1

                    return cast(
                        # TODO(TYPE): replace Any with concrete type
                        dict[str, Any],
                        response,  # TODO(TYPE): replace Any with concrete type
                    )  # TODO(TYPE): replace Any with concrete type
                else:
                    logger.warning(
                        "Provider %s returned unsuccessful response", attempt_provider.value
                    )

            except Exception as e:
                logger.warning("Provider %s failed: %s", attempt_provider.value, e)
                last_error = e
                continue

        # All providers failed - return graceful error
        self._metrics["failed_requests"] += 1
        return {
            "success": False,
            "error": "All LLM providers failed",
            "last_error": str(last_error) if last_error else "Unknown",
            "providers_tried": [p.value for p in providers_to_try],
        }


# Global instance
_llm_service_instance: GuaranteedLLMService | None = None


async def get_llm_service() -> GuaranteedLLMService:
    """
    Get the guaranteed LLM service instance.

    This function never fails and always returns a working service.

    Returns:
        GuaranteedLLMService: Configured and initialized service
    """
    global _llm_service_instance

    if _llm_service_instance is None:
        _llm_service_instance = GuaranteedLLMService()
        await _llm_service_instance.initialize()

    return _llm_service_instance


def reset_llm_service() -> None:
    """Reset the global instance (useful for testing)"""
    global _llm_service_instance
    _llm_service_instance = None
