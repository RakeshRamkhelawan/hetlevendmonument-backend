"""
LLM Service - High-level orchestration layer

Provides:
- Retry logic with exponential backoff
- Token budget tracking
- Error handling and normalization
- Caching (future)
- Rate limiting (future)

This is the service layer applications should use.
"""

import asyncio
import ipaddress
import logging
import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:  # pragma: no cover - alleen voor de typecontrole
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.shared.model_deur import bewaakt_model_aanroep, bewaakt_model_stroom
from src.core.services.llm.base import (
    LLMAuthenticationError,
    LLMContentFilterError,
    LLMMessage,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMServiceError,
    LLMTimeoutError,
    TokenBudgetExceededError,
)
from src.core.services.llm.factory import ProviderFactory
from src.core.services.llm.providers.failover import FailoverProvider, KetenSchakel
from src.core.shared.config import is_production
from src.core.shared.tenant_llm_keuze import namaak_toegestaan

logger = logging.getLogger(__name__)


def _is_ip_adres(gastheer: str) -> bool:
    """Is dit een letterlijk IP-adres in plaats van een naam?

    Nodig voor de SNI-waarde: een IP is geen geldige servernaam in een TLS-handdruk, dus die
    mag er niet als `sni_hostname` in. Haken van een IPv6-adres gaan er eerst af, want
    `urlparse().hostname` levert `::1` en niet `[::1]`.
    """
    try:
        ipaddress.ip_address(gastheer.strip("[]"))
    except ValueError:
        return False
    return True


def _namaak_toegestaan() -> bool:
    """Een namaakmodel is alleen in tests toegestaan (`TESTING` staat in `tests/conftest.py`)."""
    return namaak_toegestaan()


class LLMService:
    """
    LLM Service - Provider-agnostic orchestration layer

    Features:
    - Automatic retries with exponential backoff
    - Token budget tracking
    - Unified error handling
    - Support for any LLM provider (Ollama, DeepSeek, Gemini, etc.)

    Usage:
        # From config
        service = LLMService(provider="ollama", model="llama2")

        # With token budget
        service = LLMService(
            provider="deepseek",
            model="deepseek-chat",
            api_key="...",
            token_budget=10000,
            max_retries=3
        )

        # Generate
        response = await service.generate([
            {"role": "user", "content": "Hello"}
        ])

        # With usage tracking
        response, usage = await service.generate(
            [{"role": "user", "content": "Hello"}],
            return_usage=True
        )
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
        token_budget: int | None = None,
        enable_cache: bool = True,  # Fix: Phase 6
        provider_instance: LLMProvider | None = None,
        **provider_config: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Initialize LLM Service

        `provider_instance` is de uitweg voor een aanroeper die de provider AL heeft gebouwd --
        vandaag alleen `for_tenant`, die hem uit de klantketen samenstelt. Bewust een parameter
        en geen `__new__`-truc: zo blijft dit de ENIGE plek waar de velden van deze klasse
        worden gezet, en krijgt het tenantpad automatisch elke controle die hier later bij komt.
        De productieguard verderop geldt er dus ook voor.
        """
        # Create provider
        try:
            if provider_instance is not None:
                self.provider = provider_instance
            elif provider and model:
                self.provider = ProviderFactory.create(provider, model, **provider_config)
            else:
                # Fallback to env vars
                self.provider = ProviderFactory.create_from_env(
                    provider=provider, model=model, **provider_config
                )
        except ValueError as e:
            # Een namaakmodel is alleen in TESTS een terugval (en dan met een zichtbare melding). Buiten
            # tests, dus ook op staging, is een onbruikbare configuratie een FOUT: anders krijgt een
            # klant stil verzonnen antwoorden (ADR-041 B14, gerichte review 2026-10-19).
            if is_production() or not _namaak_toegestaan():
                logger.error(
                    "LLM provider configuration invalid (%s). Falling back to MockProvider "
                    "is not allowed outside tests.",
                    e,
                    exc_info=True,
                )
                raise
            logger.warning(
                "[MOCK] LLM provider configuration invalid (%s): namaakmodel gebruikt (alleen tests)",
                e,
            )
            self.provider = ProviderFactory.create("mock", "mock-model")

        # `serves_mock` en NIET `provider_name == "mock"`. Gemeten 2026-09-21: die naam wordt
        # afgeleid van de klassenaam (`base.py:200`), dus een samengestelde provider heet
        # anders en glipt erlangs -- ook als hij intern alleen een namaakmodel kan bereiken.
        # Zie de docstring van `LLMProvider.serves_mock` voor het volledige waarom.
        if is_production() and self.provider.serves_mock:
            logger.error(
                "LLM provider resolved to MockProvider in production. "
                "Configure a real provider and API key."
            )
            raise RuntimeError(
                "LLM provider resolved to MockProvider in production. "
                "Configure a real provider and API key."
            )

        self.max_retries = max_retries
        self.token_budget = token_budget
        self.enable_cache = enable_cache
        self._tokens_used = 0

        logger.info(
            f"LLMService initialized: provider={self.provider.provider_name}, "
            f"model={self.provider.config.model}, "
            f"max_retries={max_retries}, "
            f"token_budget={token_budget}, cache={enable_cache}"
        )

    #: De klant voor wie deze dienst is gebouwd (`for_tenant`); de noodstop controleert die bij elke aanroep.
    #: `None` voor de platformstandaard: dan geldt de klant uit de context, of geen klant (systeemtaak).
    noodstop_tenant_id: int | None = None

    @classmethod
    async def for_tenant(cls, tenant_id: int) -> "LLMService":
        """De providerKETEN van deze klant, of de platformstandaard als hij er geen heeft.

        Dit is het sluitstuk van fase 2b: tot nu toe kon een klant zijn eigen eindpunt en
        sleutel laten inrichten (fase 2a) terwijl niets die keten opvroeg -- `keten()` had nul
        aanroepers. Opslag zonder gebruiker.

        **Drie dingen staan hier bewust zo.**

        1. **Een lege keten is geen fout.** Geen rijen, de noodknop uit, of elke rij
           overgeslagen: dan komt de platformstandaard terug. Dat is wat `keten()` in zijn
           eigen docstring belooft en het is de veilige kant -- een klant zonder eigen provider
           hoort gewoon te werken.
        2. **ALLE bruikbare rijen, op volgorde** (BE-LLM-005). Tot fase 2b werd alleen de
           eerste gebruikt; de tabel is per ontwerp een keten, dus dat was een keten zonder
           failover. Het doorvallen zelf zit in `FailoverProvider` en niet hier: een eindpunt
           faalt pas als je het GEBRUIKT, dus een functie die bij het opbouwen kiest kan per
           constructie geen failover leveren.
        3. **De naam van de rij is een etiket, nooit een keuze.** Zie
           `ProviderFactory.create_generic` voor wat er misgaat als je er wel op kiest.

        **De databasesessie gaat DICHT voordat het netwerkwerk begint (BE-LLM-005).** Deze
        methode opent hem zelf en kort: de rijen ophalen is databasewerk, de adrescontrole is
        een naamsopzoeking van maximaal vijf seconden PER RIJ. Tot fase 2b stond die opzoeking
        binnen de sessie van de aanroeper -- met een keten van vier rijen is dat twintig
        seconden verbindingsbezetting per agenttaak, op een database die op 40 van de 50
        verbindingen zit. `.claude/rules/database.md` verbiedt dat met zoveel woorden.

        Wat NIET verschuift is de VOLGORDE: het adres wordt nog steeds gecontroleerd voordat
        er iets mee gebeurt. Dat is de hele reden dat die hercontrole bestaat (DNS-rebinding,
        BE-LLM-004); hem verplaatsen naar na het gebruik zou de verbindingspool redden en het
        doel weggooien.

        Er wordt GEEN tweede productieguard toegevoegd: `__init__` weigert al een namaakmodel
        in productie, en de generieke provider kan er per constructie geen zijn.
        """
        # Beide imports staan HIER en niet bovenaan: dat houdt de opstartvolgorde vrij van een
        # cyclus tussen de LLM-laag en de database-/servicelaag. Bewust GEEN
        # `importlib.import_module`, hoewel dat in dit bestand de gewoonte is: een functie-import
        # telt gewoon mee in de koppelingsmeter en een importlib-aanroep niet. De rand is echt,
        # dus hij hoort geteld te worden -- dezelfde afweging als in de Gate 2-ronde van
        # BE-LLM-004, waar precies deze verstopping is teruggedraaid.
        from src.core.database.session import get_db_session
        from src.core.services.tenant_llm_provider_service import bouw_tenant_llm_service

        instellingen: dict[str, object] | None = None
        instellingen_fout: Exception | None = None
        async with get_db_session() as db:
            dienst_van_de_klant = bouw_tenant_llm_service(db)
            opgeslagen = await dienst_van_de_klant.opgeslagen_rijen(tenant_id)
            # De taalmodelkeuze van de klant (`tenants.settings`) leest in DEZELFDE korte sessie mee;
            # pas bij een lege keten telt hij. Een leesfout wordt dan een duidelijke fout, geen terugval.
            try:
                instellingen = await dienst_van_de_klant.instellingen_van_de_klant(tenant_id)
            except Exception as exc:
                instellingen_fout = exc

        # Sessie DICHT. Vanaf hier alleen nog adrescontrole en ontsleuteling -- geen database.
        keten = await dienst_van_de_klant.beproef(tenant_id, opgeslagen)
        if not keten:
            # **Ook deze weg laat een spoor na (Gate 2, 2026-09-23).** Hier stond niets, terwijl
            # de succesweg hieronder juist met AVG art. 28 lid 2 wordt gemotiveerd. Dat is de
            # verkeerde helft om stil te laten: dit is de weg waarop de gegevens van een klant
            # DIE WEL een eigen eindpunt heeft ingericht alsnog naar de standaardprovider gaan,
            # omdat elke rij is afgekeurd. `keten()` logt dan per rij waarom, maar zonder deze
            # regel is in het spoor niet te zien dat het gevolg een andere verwerker was.
            logger.info(
                "LLM per tenant: tenant=%s -> taalmodelkeuze van de klant (lege keten). Dit is "
                "normaal voor een tenant zonder eigen provider; staat er wel iets ingericht, dan "
                "zijn de rijen afgekeurd en staat de reden per rij hierboven in het log",
                tenant_id,
            )
            gekozen = cls._keuze_van_de_klant(tenant_id, instellingen, instellingen_fout)
            gekozen.noodstop_tenant_id = tenant_id  # noodstop: de klant gaat mee
            return gekozen

        schakels: list[KetenSchakel] = []
        for rij in keten:
            # De SNI-naam alleen als de host ook echt een NAAM is. Stond er al een IP in het
            # adres, dan is een IP geen geldige SNI-waarde en zou de handdruk stuklopen op iets
            # wat we zelf hebben toegevoegd.
            gastheer = urlparse(rij.base_url).hostname or ""
            is_naam = bool(gastheer) and not _is_ip_adres(gastheer)
            schakels.append(
                KetenSchakel(
                    # De sleutel draagt de TENANT, de host en de volgorde. Niet de klassenaam:
                    # de twin doet dat (`failover_llm_provider.py:70`) en voor een platformbrede
                    # keten klopt het, maar bij klantketens zouden twee tenants dan EEN breaker
                    # delen -- en zet het uitvallen van klant A de provider van klant B op open.
                    breaker_id=f"tenant:{tenant_id}|{gastheer or 'onbekend'}|{rij.volgorde}",
                    provider=ProviderFactory.create_generic(
                        rij.naam,
                        rij.model,
                        base_url=rij.base_url,
                        api_key=rij.api_key,
                        pinned_ip=rij.gevalideerd_ip,
                        sni_hostname=gastheer if is_naam else None,
                    ),
                )
            )

        dienst = cls(provider_instance=FailoverProvider(schakels))

        # WELK eindpunt een verzoek heeft verwerkt moet naderhand vast te stellen zijn: de
        # klant is verwerkingsverantwoordelijke en kiest zelf de bestemming (AVG art. 28 lid 2),
        # en dan hoort er een spoor te zijn van waar zijn gegevens heen gingen (art. 30, AI Act
        # art. 12). De HOST en het etiket gaan mee, de sleutel NOOIT -- en het pad ook niet,
        # want dat kan een identificator dragen.
        logger.info(
            "LLM per tenant: tenant=%s keten=%s schakels=%s",
            tenant_id,
            " -> ".join(s.provider.provider_name for s in schakels),
            len(schakels),
        )
        dienst.noodstop_tenant_id = tenant_id  # noodstop: de klant gaat mee
        return dienst

    @classmethod
    def _keuze_van_de_klant(
        cls,
        tenant_id: int,
        instellingen: dict[str, object] | None,
        instellingen_fout: Exception | None,
    ) -> "LLMService":
        """Het taalmodel voor een klant ZONDER eigen eindpunt: zijn keuze, standaard Mistral (EU).

        Dit verving `return cls()`, de PLATFORMSTANDAARD uit `LLM_PROVIDER`. Op staging en productie
        is dat DeepSeek (China, geen verwerkersovereenkomst), en een klantverzoek mag daar niet
        heen (ADR-041 B14). Nu geldt `tenants.settings["llm_provider"]`: `mistral` (standaard) of
        `ollama` (eigen model). Zie `src/core/shared/tenant_llm_keuze.py` voor de regels.

        **Geen terugval.** Een klant die `ollama` koos krijgt GEEN gehuurd model als terugval, en een
        ontbrekende `MISTRAL_API_KEY` is een duidelijke fout en geen namaakmodel. De provider wordt
        daarom HIER gebouwd en als `provider_instance` doorgegeven: `__init__` vangt een `ValueError`
        van de fabriek en maakt er buiten productie een MockProvider van, en dat is precies wat
        deze weg niet mag doen. De ongeldige instelling `llm_provider: deepseek` wordt geweigerd.
        """
        from src.core.services.llm.providers.mistral import gekozen_model
        from src.core.shared import tenant_llm_keuze
        from src.core.shared.tenant_llm_keuze import TenantLLMNietBeschikbaarError

        # Elke fout vanaf hier is een `TenantLLMKeuzeFout`: de agentdeur laat die DOOR en valt er
        # niet op terug. Kon de keuze niet gelezen worden, dan is niet te zeggen of de klant
        # `ollama` koos, en dan is een gehuurd model kiezen precies de stille terugval die niet mag.
        if instellingen_fout is not None:
            raise TenantLLMNietBeschikbaarError(
                "de taalmodelkeuze van deze omgeving kon niet worden gelezen"
            ) from instellingen_fout
        keuze = tenant_llm_keuze.keuze_uit_instellingen(instellingen)

        try:
            if keuze == "ollama":
                provider = ProviderFactory.create(
                    "ollama",
                    model=os.getenv("OLLAMA_MODEL", "llama3.2"),
                    base_url=os.getenv("OLLAMA_URL") or None,
                )
            else:
                provider = ProviderFactory.create("mistral", model=gekozen_model())
        except ValueError as exc:
            raise TenantLLMNietBeschikbaarError(str(exc)) from exc

        logger.info(
            "LLM per tenant: tenant=%s keuze=%s provider=%s (geen eigen eindpunt ingericht)",
            tenant_id,
            keuze,
            provider.provider_name,
        )
        return cls(provider_instance=provider)

    @bewaakt_model_aanroep
    async def get_embeddings(self, text: str) -> list[float]:
        """
        Generate embeddings for the given text.
        """
        return await self.provider.get_embeddings(text)

    @bewaakt_model_aanroep
    async def generate(
        self,
        messages: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
        | list[LLMMessage],  # TODO(TYPE): replace Any with concrete type
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        return_usage: bool = False,
        tenant_id: int | None = None,  # Required for cache isolation
    ) -> str | tuple[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate completion from LLM with retry logic and semantic caching.
        """
        # Validate messages
        if not messages:
            raise ValueError("Messages cannot be empty")

        # Convert to List[LLMMessage], converting dicts if needed
        local_messages: list[LLMMessage]
        if messages and isinstance(messages[0], dict):
            dict_messages: list[dict[str, Any]] = [m for m in messages if isinstance(m, dict)]  # noqa: E501  # TODO(TYPE): replace Any with concrete type
            local_messages = [
                LLMMessage(role=msg["role"], content=msg["content"]) for msg in dict_messages
            ]
        else:
            local_messages = [m for m in messages if isinstance(m, LLMMessage)]

        # Add system prompt if provided
        if system_prompt:
            local_messages = [LLMMessage(role="system", content=system_prompt)] + local_messages

        # 1. CACHE CHECK (Phase 6)
        if self.enable_cache and tenant_id:
            from src.core.services.llm.cache import SemanticCache

            cache = SemanticCache()

            # DEBUG: Log content for hash verification
            prompt_debug = "\\n".join([f"{m.role}: {m.content}" for m in local_messages])
            import hashlib

            h = hashlib.sha256(prompt_debug.encode()).hexdigest()
            logger.info(f"LLMService Cache Check: tenant={tenant_id}, hash={h[:10]}")

            cached_res = await cache.get(tenant_id, local_messages)
            if cached_res:
                if return_usage:
                    # Cache hits consume 0 real tokens
                    return cached_res, {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "model": "cache",
                    }
                return cached_res

        # Check token budget before calling
        if self.token_budget and self._tokens_used >= self.token_budget:
            raise TokenBudgetExceededError(
                f"Token budget exceeded: {self._tokens_used}/{self.token_budget}"
            )

        # Retry loop
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                # Generate response
                response: LLMResponse = await self.provider.generate(
                    messages=local_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                # Track token usage
                self._tokens_used += response.total_tokens

                # Check for content filter
                if response.finish_reason == "content_filter":
                    raise LLMContentFilterError("Content was filtered by safety system")

                # 2. CACHE STORE (Phase 6)
                if self.enable_cache and tenant_id:
                    from src.core.services.llm.cache import SemanticCache

                    cache = SemanticCache()
                    await cache.set(tenant_id, local_messages, response.content)

                # Return response
                if return_usage:
                    usage = {
                        "prompt_tokens": response.prompt_tokens,
                        "completion_tokens": response.completion_tokens,
                        "total_tokens": response.total_tokens,
                        "model": response.model,
                    }
                    return response.content, usage
                else:
                    return response.content

            except (ConnectionError, OSError) as e:
                # Transient errors - retry
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 0.5 * (attempt + 1)  # Exponential backoff
                    logger.warning(
                        f"Transient error (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue

            except (
                LLMTimeoutError,
                LLMRateLimitError,
                LLMAuthenticationError,
                LLMContentFilterError,
                TokenBudgetExceededError,
            ):
                # Non-retryable errors - raise immediately
                raise

            except Exception as e:
                # Other errors - wrap and raise
                last_error = e
                break

        # All retries failed
        if last_error:
            # `from last_error`: de workflowengine beoordeelt aan de OORZAAK of een nieuwe poging zin heeft (een 503 of een
            # verbindingsfout wel, een ongeldige aanvraag niet); zonder dit is die oorzaak hier weg.
            if isinstance(last_error, (ConnectionError, OSError)):
                raise LLMServiceError(
                    f"LLM request failed after {self.max_retries} retries: {last_error}"
                ) from last_error
            else:
                raise LLMServiceError(f"LLM error: {last_error}") from last_error

        raise LLMServiceError(
            f"LLM request failed after {self.max_retries} retries with no response"
        )

    @bewaakt_model_stroom
    async def stream_generate(
        self,
        # TODO(TYPE): replace Any with concrete type
        messages: list[dict[str, Any]]
        | list[LLMMessage],  # TODO(TYPE): replace Any with concrete type
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tenant_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from LLM provider.

        Falls back to chunked non-streaming generate() if provider lacks streaming support.
        Checks token budget and semantic cache (cache hits are yielded without LLM call).
        """
        if not messages:
            raise ValueError("Messages cannot be empty")

        # Convert to list[LLMMessage] (same pattern as generate())
        local_messages: list[LLMMessage]
        if messages and isinstance(messages[0], dict):
            # TODO(TYPE): replace Any with concrete type
            dict_messages: list[dict[str, Any]] = [
                m for m in messages if isinstance(m, dict)
            ]  # TODO(TYPE): replace Any with concrete type
            local_messages = [
                LLMMessage(role=msg["role"], content=msg["content"]) for msg in dict_messages
            ]
        else:
            local_messages = [m for m in messages if isinstance(m, LLMMessage)]

        # System prompt prepend (same order as generate())
        if system_prompt:
            local_messages = [LLMMessage(role="system", content=system_prompt)] + local_messages

        # Cache check - yield cached response in chunks without hitting LLM
        if self.enable_cache and tenant_id:
            from src.core.services.llm.cache import SemanticCache

            cache = SemanticCache()
            cached_res = await cache.get(tenant_id, local_messages)
            if cached_res:
                for i in range(0, len(cached_res), 30):
                    yield cached_res[i : i + 30]
                return

        # Token budget check before streaming
        if self.token_budget and self._tokens_used >= self.token_budget:
            raise TokenBudgetExceededError(
                f"Token budget exceeded: {self._tokens_used}/{self.token_budget}"
            )

        # Stream from provider or fall back to chunked non-streaming
        full_chunks: list[str] = []
        if hasattr(self.provider, "stream") and self.provider.supports_streaming:
            async for chunk in self.provider.stream(
                local_messages, temperature=temperature, max_tokens=max_tokens
            ):
                full_chunks.append(chunk)
                yield chunk
        else:
            result = await self.provider.generate(
                local_messages, temperature=temperature, max_tokens=max_tokens
            )
            self._tokens_used += result.total_tokens
            for i in range(0, len(result.content), 30):
                chunk = result.content[i : i + 30]
                full_chunks.append(chunk)
                yield chunk

        # Update token budget (approximate for streaming: 4 chars per token)
        accumulated = "".join(full_chunks)
        if full_chunks and self.provider.supports_streaming:
            self._tokens_used += max(1, len(accumulated) // 4)

        # Cache store after streaming completes
        if self.enable_cache and tenant_id and accumulated:
            from src.core.services.llm.cache import SemanticCache

            cache = SemanticCache()
            await cache.set(tenant_id, local_messages, accumulated)

    @property
    def tokens_used(self) -> int:
        """Get total tokens used so far"""
        return self._tokens_used

    @property
    def tokens_remaining(self) -> int | None:
        """Get remaining tokens in budget (None if no budget set)"""
        if self.token_budget:
            return max(0, self.token_budget - self._tokens_used)
        return None

    def reset_token_counter(self) -> None:
        """Reset token usage counter"""
        self._tokens_used = 0
        logger.info("Token counter reset")
