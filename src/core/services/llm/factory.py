"""
Provider Factory - Creates LLM providers based on configuration

Usage:
    factory = ProviderFactory()
    provider = factory.create("ollama", config)
    response = await provider.generate(messages)
"""

import logging
import os
from typing import Any, Optional, cast

from src.core.services.llm.base import LLMConfig, LLMProvider, LLMProviderUnknownError
from src.core.services.llm.providers import (
    DeepSeekProvider,
    GeminiProvider,
    MistralProvider,
    MockProvider,
    OllamaProvider,
)
from src.core.services.llm.providers.mistral import STANDAARD_MODEL
from src.core.shared.tenant_llm_keuze import (
    LEVERANCIERS_ZONDER_VERWERKERSOVEREENKOMST,
    namaak_toegestaan,
)
from src.core.services.llm.providers.openai_compatible import (
    PROVIDER_LABEL,
    OpenAICompatibleProvider,
)

logger = logging.getLogger(__name__)


class ProviderFactory:
    """
    Factory for creating LLM providers

    Supports:
    - ollama: Local Ollama models
    - deepseek: DeepSeek API
    - gemini: Google Gemini API

    New providers can be registered via register_provider()
    """

    # Registry of available providers
    _providers: dict[str, type[LLMProvider]] = {
        "ollama": OllamaProvider,
        "deepseek": DeepSeekProvider,
        "gemini": GeminiProvider,
        "mistral": MistralProvider,
        "mock": MockProvider,
    }

    @classmethod
    def register_provider(cls, name: str, provider_class: type[LLMProvider]) -> None:
        """
        Register a new provider

        Args:
            name: Provider name (e.g., "deepseek", "claude")
            provider_class: Provider class implementing LLMProvider
        """
        if not issubclass(provider_class, LLMProvider):
            raise ValueError(f"{provider_class} must inherit from LLMProvider")

        cls._providers[name.lower()] = provider_class
        logger.info(f"Registered LLM provider: {name}")

    @classmethod
    def create(
        cls,
        provider: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        timeout: int = 30,
        api_key: str | None = None,
        base_url: str | None = None,
        **extra_params: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> LLMProvider:
        """
        Create an LLM provider instance

        Args:
            provider: Provider name ("ollama", "deepseek", "gemini", etc.)
            model: Model name
            temperature: Generation temperature (0-1)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            api_key: API key (if required by provider)
            base_url: Custom base URL (if needed)
            **extra_params: Additional provider-specific parameters

        Returns:
            LLMProvider instance

        Raises:
            LLMProviderUnknownError: de naam is onbekend EN er is geen base_url meegegeven.
                Bewust geen ValueError: `LLMService.__init__` vangt die en valt buiten
                productie terug op de MockProvider, waardoor een verkeerde providernaam stil
                een namaakmodel werd. Zie de docstring van dat fouttype in base.py.
            ValueError: de provider zelf weigert zijn configuratie (ontbrekend model,
                ongeldig of onvolledig adres, inloggegevens in de url).

        Example:
            # Ollama (local)
            provider = ProviderFactory.create("ollama", model="llama2")

            # DeepSeek (API)
            provider = ProviderFactory.create(
                "deepseek",
                model="deepseek-chat",
                api_key=os.getenv("DEEPSEEK_API_KEY")
            )

            # Gemini (API)
            provider = ProviderFactory.create(
                "gemini",
                model="gemini-pro",
                api_key=os.getenv("GOOGLE_API_KEY")
            )
        """
        provider_name = provider.lower()

        # Een naam die wij niet kennen is GEEN fout zolang er een adres bij zit: dan is het een
        # OpenAI-compatibel eindpunt dat de klant zelf opgeeft. Dit is het anti-lock-in-pad
        # (besluit Rakesh 2026-09-20) -- een nieuwe leverancier kost een regel configuratie en
        # nooit meer een klasse in onze code. Zie providers/openai_compatible.py.
        #
        # De naam van de aanroeper gaat mee als LABEL. `provider_name` wordt op drie plekken in
        # `src/` gelezen -- de mock-controle voor productie en een logregel in
        # `services/llm/service.py`, plus een veld in een API-antwoord in
        # `services/cva_service.py`. Zonder label zou daar de klassenaam of de host staan, en
        # "openaicompatible" bij een aanroep naar DeepSeek is een onwaar record.
        #
        # Een eerdere versie van deze comment noemde ook metrics en de ADR-019-auditketen.
        # Dat is NAGEMETEN en niet zo (Gate 2, ronde 1): ADR-019 noemt het woord provider niet,
        # en de enige metrics met een providerlabel halen hun waarde uit `type(provider).__name__`
        # in `learning/interfaces/failover_llm_provider.py`, niet uit deze property.
        if provider_name not in cls._providers:
            if not base_url:
                available = ", ".join(cls._providers.keys())
                # `LLMProviderUnknownError` en NIET `ValueError`: `LLMService.__init__` vangt
                # ValueError en valt buiten productie stil terug op de MockProvider. Gemeten
                # 2026-09-20 gaf `LLMService(provider="moonshot", model="kimi-k2")` daardoor
                # provider `mock` terug met alleen een waarschuwing in het log -- exact de
                # storing die deze hele wijziging moest oplossen. Zie de docstring van dat
                # fouttype in base.py.
                raise LLMProviderUnknownError(
                    f"Unknown provider: {provider}. Available: {available}. "
                    "Elk ANDER OpenAI-compatibel eindpunt werkt zonder codewijziging: geef "
                    "een base_url mee (omgeving: LLM_BASE_URL) plus een model, en eventueel "
                    "een sleutel."
                )
            return OpenAICompatibleProvider(
                LLMConfig(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    api_key=api_key,
                    base_url=base_url,
                    extra_params={**extra_params, PROVIDER_LABEL: provider_name},
                )
            )

        # Build config
        config = LLMConfig(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            api_key=api_key,
            base_url=base_url,
            extra_params=extra_params or None,
        )

        # Create provider instance
        provider_class = cls._providers[provider_name]
        return provider_class(config)

    @classmethod
    def create_generic(
        cls,
        label: str,
        model: str,
        *,
        base_url: str,
        api_key: str | None = None,
        pinned_ip: str | None = None,
        sni_hostname: str | None = None,
        timeout: int = 30,
    ) -> LLMProvider:
        """Altijd de generieke provider, ongeacht hoe het eindpunt HEET.

        **Waarom dit niet via `create()` mag (BE-LLM-004).** `create()` kiest op NAAM: staat de
        naam in de registry, dan komt de specifieke klasse. Voor een eindpunt dat een KLANT
        heeft ingericht is dat een gat, want die naam is een vrij tekstveld. Gemeten: een rij
        die "mock" heet zou de MockProvider opleveren (en in productie een harde fout op de
        eigen guard van `LLMService`), een rij die "gemini" heet de Google-klasse -- met het
        adres van de klant genegeerd en zijn sleutel naar een leverancier die hij niet koos.
        Dat is dezelfde faalvorm die op 2026-09-21 al eens is gerepareerd: beslissen op een
        naam in plaats van op wat iets doet.

        Hier is de naam dus uitsluitend een ETIKET, en de klasse ligt vast. Bewaakt door
        `tests/architecture/test_een_klantrij_gaat_nooit_op_naam_naar_een_provider.py`.

        `pinned_ip` en `sni_hostname` staan als EXPLICIETE parameters en niet in
        `extra_params`: dat veld wordt door `_payload()` in het JSON-lichaam van het verzoek
        gekopieerd, dus daar zouden ze als verzonnen modelparameters bij de leverancier
        aankomen.
        """
        return OpenAICompatibleProvider(
            LLMConfig(
                model=model,
                timeout=timeout,
                api_key=api_key,
                base_url=base_url,
                pinned_ip=pinned_ip,
                sni_hostname=sni_hostname,
                extra_params={PROVIDER_LABEL: label},
            )
        )

    @classmethod
    def create_from_env(
        cls,
        provider: str | None = None,
        model: str | None = None,
        **overrides: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> LLMProvider:
        """
        Create provider from environment variables

        Environment variables:
        - LLM_PROVIDER: Provider name (default: "ollama")
        - LLM_MODEL: Model name (required)
        - LLM_TEMPERATURE: Temperature (default: 0.7)
        - LLM_MAX_TOKENS: Max tokens (default: 1000)
        - LLM_TIMEOUT: Timeout in seconds (default: 30)
        - LLM_API_KEY: API key (if needed)
        - LLM_BASE_URL: Custom base URL (if needed)

        Args:
            provider: Override provider from env
            model: Override model from env
            **overrides: Override other config values

        Returns:
            LLMProvider instance

        Example:
            # Set env vars:
            # export LLM_PROVIDER=gemini
            # export LLM_MODEL=gemini-pro
            # export GOOGLE_API_KEY=...

            provider = ProviderFactory.create_from_env()
        """
        provider_str: str = (provider or os.getenv("LLM_PROVIDER") or "").strip()
        if not provider_str:
            # Hier stond `"mock"` als standaard: een omgeving zonder `LLM_PROVIDER` kreeg dan stil een
            # namaakmodel (regie 2026-10-19, punt 2a). Buiten tests is dat een fout.
            if os.getenv("MISTRAL_API_KEY"):
                provider_str = "mistral"
            elif namaak_toegestaan():
                provider_str = "mock"
            else:
                raise ValueError(
                    "LLM_PROVIDER staat niet gezet en er is geen MISTRAL_API_KEY: er is geen taalmodel "
                    "gekozen. Een namaakmodel is alleen in tests (of met LLM_PROVIDER=mock) toegestaan."
                )
        model = model or os.getenv("DEFAULT_LLM_MODEL") or os.getenv("LLM_MODEL")

        if provider_str.lower() in LEVERANCIERS_ZONDER_VERWERKERSOVEREENKOMST:
            if not os.getenv("MISTRAL_API_KEY"):
                raise ValueError(
                    "DeepSeek (China, geen verwerkersovereenkomst) mag niet met klantgegevens "
                    "(ADR-041 B14): zet MISTRAL_API_KEY, of kies per klant een eigen eindpunt"
                )
            # De uitrol (CD) zet nog `LLM_PROVIDER=deepseek`. Staat de sleutel van Mistral er, dan
            # gebruiken we die. De sleutel en het adres uit `LLM_API_KEY` en `LLM_BASE_URL` horen bij
            # DeepSeek en gaan NIET naar Mistral.
            logger.warning(
                "LLM_PROVIDER=deepseek wordt genegeerd omdat MISTRAL_API_KEY gezet is: Mistral (EU) "
                "wordt gebruikt (ADR-041 B14)"
            )
            provider_str = "mistral"
            if not model or "deepseek" in model.lower():
                model = STANDAARD_MODEL
            overrides.setdefault("api_key", None)
            overrides.setdefault("base_url", None)

        if provider_str.lower() == "mistral" and not model:
            model = STANDAARD_MODEL

        if not model:
            if provider_str.lower() == "mock":
                model = "mock-model"
            else:
                raise ValueError("Model must be specified via argument or LLM_MODEL env var")

        config = {
            "model": model,
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "1000")),
            "timeout": int(os.getenv("LLM_TIMEOUT", "30")),
            "api_key": os.getenv("LLM_API_KEY") or os.getenv(f"{provider_str.upper()}_API_KEY"),
            "base_url": os.getenv("LLM_BASE_URL"),
        }

        # Apply overrides
        config.update(overrides)

        return cls.create(
            provider_str,
            model=cast(str, config.get("model", "")),
            temperature=cast(float, config.get("temperature", 0.7)),
            max_tokens=cast(int, config.get("max_tokens", 1000)),
            timeout=cast(int, config.get("timeout", 30)),
            api_key=cast(Optional[str], config.get("api_key")),
            base_url=cast(Optional[str], config.get("base_url")),
        )

    @classmethod
    def available_providers(cls) -> list[str]:
        """Get list of available provider names"""
        return list(cls._providers.keys())
