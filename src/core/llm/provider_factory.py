"""
LLM Provider Factory - Enterprise Edition
Uses ProviderRegistry for dynamic provider discovery
"""

import logging
import os
from threading import Lock
from typing import Any, Optional, cast

from src.core.shared.tenant_llm_keuze import (
    LEVERANCIERS_ZONDER_VERWERKERSOVEREENKOMST,
    namaak_toegestaan,
)

from .llm_client import LLMClient, LLMModel, LLMProvider, LLMProviderProtocol
from .provider_registry import ProviderRegistry

__all__ = ["LLMProviderFactory", "LLMProviderProtocol", "LLMClient", "LLMProvider", "LLMModel"]

logger = logging.getLogger(__name__)


def _namaak_toegestaan() -> bool:
    """Een namaakmodel is alleen in tests toegestaan (en dan met een zichtbare melding in het log)."""
    return namaak_toegestaan()


class LLMProviderFactory:
    """
    Thread-safe factory for LLM providers.
    Now uses ProviderRegistry for automatic provider discovery.
    """

    _lock = Lock()
    _instances: dict[str, LLMClient] = {}

    @classmethod
    def get_provider(cls, provider_type: str = "auto") -> LLMClient:
        """
        Get an LLM provider instance. ALWAYS the platform default.

        Args:
            provider_type: "auto", "deepseek", "gemini", "openai", etc.

        Returns:
            LLMClient instance

        **De parameter `tenant_id` is op 2026-09-23 VERWIJDERD, en het was geen opschoning.**
        Hij werd geaccepteerd en genegeerd: de enige plek die hem gebruikte was
        `_get_provider_config`, en die keek in `_tenant_configs` -- een woordenboek dat in heel
        `src/` en `tests/` door NIETS werd gevuld (gemeten). Elke aanroep viel dus terug op de
        omgevingsvariabelen van het platform, ook met een tenant erbij.

        Dat is erger dan een ongebruikte parameter. De enige aanroeper
        (`agents/router_agent_service.py`) gaf een tenant mee en meldde bij een ontbrekende
        sleutel "No Gemini API Key found for tenant" -- een melding die een tenant-specifieke
        inrichting suggereert die niet bestond. Een handtekening die iets belooft wat hij niet
        doet, is een leugen die niemand rood maakt.

        Wie wel een provider PER TENANT wil: `LLMService.for_tenant()` in
        `src/core/services/llm/service.py` (BE-LLM-004). Die leest de echte keten uit
        `tenant_llm_providers`.
        """
        # Determine cache key
        cache_key = f"default:{provider_type}"

        # Check cache (read without lock for performance)
        if cache_key in cls._instances:
            return cls._instances[cache_key]

        # Thread-safe creation
        with cls._lock:
            # Double-check after acquiring lock
            if cache_key in cls._instances:
                return cls._instances[cache_key]

            # Create new provider
            config = cls._get_provider_config()

            # Auto-detect if needed
            if provider_type == "auto":
                provider_type = cls._detect_provider_type(config)

            # De registry zoekt hoofdletterongevoelig (`name.lower()`); de weigering moet dat ook zijn, anders
            # passeert `"DeepSeek"` uit een configuratiebestand (Gate 2 ronde 2).
            provider_type = provider_type.strip().lower()
            if provider_type in LEVERANCIERS_ZONDER_VERWERKERSOVEREENKOMST:
                # Ook een uitdrukkelijke `provider_type="deepseek"` (bijvoorbeeld uit een agentconfiguratie)
                # wordt hier geweigerd: de registry vindt `deepseek_provider.py` zelf (ADR-041 B14).
                raise ValueError(
                    f"{provider_type}: geen verwerkersovereenkomst, mag niet met klantgegevens (ADR-041 B14)"
                )

            # Get provider class from registry
            provider_class = ProviderRegistry.get(provider_type)

            if provider_class is None:
                logger.error(f"Provider '{provider_type}' not found in registry")
                available = ProviderRegistry.list_providers()
                logger.info(f"Available providers: {', '.join(available)}")
                # Een onbekende provider is een FOUT en geen reden voor een namaakmodel: buiten
                # tests zou elke typfout in LLM_PROVIDER stil nepantwoorden geven (ADR-041 B14).
                if not _namaak_toegestaan():
                    raise RuntimeError(
                        f"Onbekende taalmodel-provider '{provider_type}'. Beschikbaar: "
                        f"{', '.join(available)}. Er wordt bewust niet teruggevallen op een "
                        "namaakmodel."
                    )
                logger.warning(
                    "[MOCK] onbekende provider '%s': namaakmodel gebruikt (alleen tests)",
                    provider_type,
                )
                provider_class = ProviderRegistry.get("mock")
                if provider_class is None:
                    raise RuntimeError("No providers available, not even mock!")

            # Instantiate provider
            api_key = cls._get_api_key_for_provider(provider_type, config)
            # Create proper LLMConfig for provider
            from src.core.llm.llm_client import LLMConfig, LLMModel, LLMProvider

            # Map provider_type string to enum
            provider_map = {
                "google": LLMProvider.GOOGLE,
                "gemini": LLMProvider.GOOGLE,
                "deepseek": LLMProvider.DEEPSEEK,
                "mistral": LLMProvider.MISTRAL,
                "openai": LLMProvider.OPENAI,
                "anthropic": LLMProvider.ANTHROPIC,
                "local": LLMProvider.LOCAL,
                "ollama": LLMProvider.OLLAMA,
                "mock": LLMProvider.MOCK,
            }
            provider_enum = provider_map.get(provider_type, LLMProvider.MOCK)

            # Get default model for provider
            default_models = {
                LLMProvider.GOOGLE: LLMModel.GEMINI_2_5_PRO,
                LLMProvider.DEEPSEEK: LLMModel.DEEPSEEK_CHAT,
                LLMProvider.MISTRAL: LLMModel.MISTRAL_SMALL,
                LLMProvider.LOCAL: LLMModel.LLAMA_3,
                LLMProvider.OLLAMA: LLMModel.LLAMA_3,
                LLMProvider.MOCK: LLMModel.MOCK_MODEL,
            }
            model = default_models.get(provider_enum, LLMModel.MOCK_MODEL)

            llm_config = LLMConfig(
                provider=provider_enum,
                model=model,
                api_key=api_key or "",
                max_tokens=config.get("max_tokens", 2000),
                temperature=config.get("temperature", 0.7),
            )
            provider = provider_class(config=llm_config)

            # Initialize async providers
            if hasattr(provider, "initialize"):
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if not loop.is_running():
                        loop.run_until_complete(cast(Any, provider).initialize())  # TODO(TYPE): replace Any with concrete type
                    else:
                        # Schedule for later if loop is running
                        asyncio.create_task(cast(Any, provider).initialize())  # TODO(TYPE): replace Any with concrete type
                except Exception as e:
                    logger.error(f"Provider initialization failed: {e}")

            # Cache and return
            cls._instances[cache_key] = provider
            logger.info(f"Created LLM provider: {provider_type} (cache_key={cache_key})")
            return provider

    @classmethod
    def _get_provider_config(cls) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """The platform configuration from the environment.

        Hier stond een tak `if tenant_id and tenant_id in cls._tenant_configs` boven een
        woordenboek dat nergens werd gevuld -- zie `get_provider` voor de meting en waarom dat
        een belofte was in plaats van een functie.
        """
        # Return default config from environment
        return {
            "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
            "mistral_api_key": os.getenv("MISTRAL_API_KEY", ""),
            "local_llm_url": os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
            "default_model": os.getenv("DEFAULT_LLM_MODEL", "gemini-1.5-flash"),
            "llm_provider": os.getenv("LLM_PROVIDER", "auto"),
        }

    @classmethod
    def _detect_provider_type(cls, config: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Auto-detect which provider to use based on configuration.
        Priority: Explicit preference > API key availability
        """
        preferred = config.get("llm_provider", "").lower()

        if preferred == "deepseek" and config.get("mistral_api_key"):
            # De uitrol (CD) zet nog `LLM_PROVIDER=deepseek`; zie `services/llm/factory.create_from_env`.
            logger.warning(
                "LLM_PROVIDER=deepseek wordt genegeerd omdat MISTRAL_API_KEY gezet is: Mistral (EU) "
                "wordt gebruikt (ADR-041 B14)"
            )
            return "mistral"

        if preferred in LEVERANCIERS_ZONDER_VERWERKERSOVEREENKOMST:
            # Geen Mistralsleutel: de uitdrukkelijke keuze voor DeepSeek wordt NIET uitgevoerd, we vallen
            # terug op de automatische keuze hieronder (die DeepSeek niet kent).
            logger.error(
                "LLM_PROVIDER=%s wordt genegeerd: mag niet met klantgegevens (ADR-041 B14)", preferred
            )
            preferred = "auto"

        # If explicit preference is set and valid, use it
        if preferred and preferred != "auto":
            # Using get from registry to check existence
            provider_class = ProviderRegistry.get(preferred)
            if provider_class:
                # Verify API key exists for this provider
                api_key = cls._get_api_key_for_provider(preferred, config)
                if api_key or preferred == "local":  # Local might not need key
                    logger.info(f"Using preferred provider: {preferred}")
                    return cast(str, preferred)
                else:
                    logger.warning(f"Preferred provider '{preferred}' has no API key")

        # Fallback: Check API keys in priority order
        # Kimi proxy is special: no API key needed, just env flag

        # DeepSeek staat hier NIET in: de automatische keuze draait over klantgegevens en DeepSeek
        # (China, geen verwerkersovereenkomst) mag daar niet mee (ADR-041 B14). Wie DeepSeek voor
        # platformeigen werk wil, zet het uitdrukkelijk in `LLM_PROVIDER`.
        for provider_name in ["mistral", "gemini", "openai", "anthropic"]:
            api_key = cls._get_api_key_for_provider(provider_name, config)
            if api_key:
                logger.info(f"Auto-detected provider: {provider_name}")
                return provider_name

        # Last resort: local or mock
        if ProviderRegistry.get("local"):
            logger.info("No cloud API keys found, using local LLM")
            return "local"

        if not _namaak_toegestaan():
            raise RuntimeError(
                "Geen taalmodel beschikbaar: zet MISTRAL_API_KEY (of een andere sleutel) of "
                "start een lokaal model. Er wordt bewust niet teruggevallen op een namaakmodel."
            )
        logger.warning(
            "[MOCK] geen enkele provider beschikbaar: namaakmodel gebruikt (alleen tests)"
        )
        return "mock"

    @classmethod
    def _get_api_key_for_provider(cls, provider_name: str, config: dict[str, Any]) -> str | None:  # TODO(TYPE): replace Any with concrete type
        """Get the appropriate API key for a provider"""
        key_mapping = {
            "mistral": "mistral_api_key",
            "deepseek": "deepseek_api_key",
            "gemini": "google_api_key",
            "openai": "openai_api_key",
            "anthropic": "anthropic_api_key",
        }

        key_name = key_mapping.get(provider_name)
        if key_name:
            return cast(str, config.get(key_name, ""))

        return None

    @classmethod
    def reset(cls) -> None:
        """Reset all cached providers (for testing)"""
        with cls._lock:
            cls._instances.clear()
            logger.debug("LLM provider factory reset")


# Convenience function
def get_llm_provider(provider_type: str = "auto") -> LLMClient:
    """
    Get an LLM provider instance. Always the platform default.

    Example:
        provider = get_llm_provider()
        response = await provider.generate_response("Hello!")

    Voor een provider per tenant: `LLMService.for_tenant()`. Zie
    `LLMProviderFactory.get_provider` voor waarom `tenant_id` hier weg is.
    """
    return LLMProviderFactory.get_provider(provider_type)


def reset_llm_providers() -> None:
    """
    Reset all LLM providers. Use in test cleanup.
    """
    LLMProviderFactory.reset()
