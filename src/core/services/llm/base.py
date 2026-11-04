"""
Base LLM Provider - Abstract interface for all LLM providers

Any LLM (Ollama, DeepSeek, Gemini, OpenAI, Claude, Kimi K2, etc.)  # TODO(TYPE): replace Any with concrete type
can be integrated by implementing this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Union
from collections.abc import AsyncGenerator
from src.core.shared.model_deur import bewaak_modelmethoden

# ============================================
# EXCEPTIONS
# ============================================


class LLMServiceError(Exception):
    """Base exception for LLM service errors"""

    pass


class LLMTimeoutError(LLMServiceError):
    """LLM request timed out"""

    pass


class LLMRateLimitError(LLMServiceError):
    """LLM rate limit exceeded"""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMAuthenticationError(LLMServiceError):
    """LLM authentication failed"""

    pass


class LLMContentFilterError(LLMServiceError):
    """Content blocked by safety filter"""

    pass


class TokenBudgetExceededError(LLMServiceError):
    """Token budget exceeded"""

    pass


class LLMProviderUnknownError(LLMServiceError):
    """De opgegeven providernaam bestaat niet en er is geen eindpunt meegegeven.

    **Waarom dit GEEN ValueError is, en dat is de hele reden dat dit type bestaat.**
    `LLMService.__init__` vangt `ValueError` en valt buiten productie stil terug op de
    MockProvider -- bedoeld als gemak wanneer er geen API-sleutel is. Een onbekende
    providerNAAM is iets anders dan een ontbrekende sleutel: dat is een typefout of een
    verkeerde configuratie, en stil een namaakmodel gebruiken verbergt hem.

    Gemeten 2026-09-20: `.env` zette `LLM_PROVIDER=moonshot`, de fabriek kende die naam niet,
    en `LLMService(provider="moonshot", model="kimi-k2")` gaf provider `mock` terug -- met
    alleen een `logger.warning`. De agent praatte daarna met een verzinsel dat er geslaagd
    uitzag. Dat is de faalvorm uit ADR-036 paragraaf 1.

    Omdat dit geen `ValueError` is, glipt hij door dat except-blok heen en valt de aanroep
    luid om, ook in ontwikkeling en staging. In productie gedroeg het zich altijd al zo; dit
    maakt de drie omgevingen gelijk.
    """

    pass


# ============================================
# DATA MODELS
# ============================================


@dataclass
class LLMMessage:
    """Standard message format for all providers"""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Standard response format from all providers"""

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    finish_reason: str | None = None  # "stop", "length", "content_filter", etc.


@dataclass
class LLMConfig:
    """Configuration for LLM provider"""

    model: str
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout: int = 30
    # `repr=False` sinds 2026-09-23 (Gate 2 op BE-LLM-004), om dezelfde reden als bij
    # `ProviderRij.api_key`: sinds fase 2b reist de ONTSLEUTELDE sleutel van een klant tot in
    # dit object, en zonder die vlag zet een enkele `logger.debug("%s", self.config)` hem in
    # klare tekst in het logbestand. Gemeten dat er vandaag geen enkele plek in `src/` is die
    # deze dataclass rendert -- dit sluit dus een route af die nog niemand gebruikt, en dat is
    # het goedkoopste moment.
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None  # For Ollama, custom endpoints
    extra_params: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    #: Het IP-adres waarnaar dit verzoek MOET gaan, en de naam waarvoor het certificaat moet
    #: gelden. Samen zijn ze het antwoord op DNS-rebinding: zonder vastpinnen controleert de
    #: SSRF-laag een naam en zoekt de HTTP-client die naam DAARNA nog een keer op, waarna het
    #: antwoord een ander adres kan zijn. Die TOCTOU-vorm is in 2026 tweemaal als
    #: kwetsbaarheid uitgebracht in precies deze constructie (Langflow's URL-component,
    #: `mcp-atlassian` CVE-2026-27826).
    #:
    #: Alleen gevuld voor een eindpunt dat van een KLANT komt (BE-LLM-004). Voor de
    #: platformstandaard uit de uitrol blijven ze leeg: daar is geen pad van buiten naar dit
    #: veld, en `http://127.0.0.1:11434` -- de lokale bodem van de keten -- moet gewoon
    #: blijven werken.
    pinned_ip: str | None = None
    sni_hostname: str | None = None


# ============================================
# ABSTRACT PROVIDER
# ============================================


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers

    Any new LLM can be integrated by implementing this interface:  # TODO(TYPE): replace Any with concrete type
    - generate(): Generate completion
    - stream(): Stream completion (optional)
    - validate_config(): Validate provider-specific config
    """

    def __init_subclass__(cls) -> None:
        # Noodstop (ronde 3): elke subklasse bewaakt zijn modelaanroepen, ook een nieuwe.
        super().__init_subclass__()
        bewaak_modelmethoden(
            cls,
            (
                "generate",
                "stream",
                "get_embeddings",
            ),
        )

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """
        Validate provider-specific configuration
        Raises ValueError if invalid
        """
        pass

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Generate completion from LLM

        Args:
            messages: list[Any] of messages  # TODO(TYPE): replace Any with concrete type
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            LLMResponse with content and token usage

        Raises:
            LLMTimeoutError: Request timed out
            LLMRateLimitError: Rate limit exceeded
            LLMAuthenticationError: Invalid credentials
            LLMContentFilterError: Content blocked
            LLMServiceError: Other errors
        """
        pass

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion from LLM (optional - not all providers support streaming)

        Yields:
            str: Chunks of generated text
        """
        if False:
            yield ""
        raise NotImplementedError(f"{self.__class__.__name__} does not support streaming")

    async def get_embeddings(self, text: str) -> list[float]:
        """
        Generate embeddings for the given text.

        Not all providers support embeddings. Override in subclass if supported.
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support embeddings")

    @property
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming"""
        return False

    @property
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'ollama', 'deepseek', 'gemini')"""
        return self.__class__.__name__.replace("Provider", "").lower()

    @property
    def serves_mock(self) -> bool:
        """Whether an answer from this provider can come from a mock model.

        **Waarom dit naast `provider_name` bestaat en niet in plaats daarvan.** De
        productieguard in `LLMService.__init__` vroeg tot 2026-09-21
        `self.provider.provider_name == "mock"`. Die naam is geen veld maar een afleiding van
        de KLASSENAAM (zie hierboven), dus elk object met een andere klassenaam passeert die
        controle -- ook als het INTERN alleen een namaakmodel kan bereiken. Een samengestelde
        provider (de failoverketen van fase 2b) zou `"keten"` heten en er zo langs glippen,
        zonder dat een test rood wordt.

        De standaard hieronder leidt het antwoord af uit dezelfde naam, zodat elke bestaande
        provider zich onveranderd gedraagt. Een provider die ANDERE providers omvat hoort hem
        te overschrijven en `True` te geven zodra een van zijn schakels een namaakmodel kan
        opleveren.

        `provider_name` blijft ongemoeid: 55 bestanden in `src/` en `tests/` noemen hem, en
        zijn betekenis -- "hoe heet deze provider" -- is een andere vraag dan deze.
        """
        return self.provider_name == "mock"
