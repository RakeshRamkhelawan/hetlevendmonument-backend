"""De providerketen van een klant, met een circuit breaker per schakel.

**Waarom deze klasse bestaat (BE-LLM-005, fase 3).** Fase 2b liet een agent het eindpunt van zijn
eigen klant gebruiken, maar nam alleen de EERSTE rij uit `tenant_llm_providers`. Die tabel is per
ontwerp geordend, dus er was een keten zonder failover: viel het eindpunt van een klant uit, dan
viel zijn agent uit. ADR-026 par. 1.2.1 belooft die keten met een circuit breaker.

**Waarom het een PROVIDER is en geen slimmigheid in `for_tenant`.** Failover is iets van de
AANROEP: een eindpunt faalt pas als je het gebruikt. Een functie die bij het opbouwen een rij
kiest, kan per constructie geen failover leveren -- hoe zorgvuldig hij ook kiest.

**De breaker is procesbreed en zijn ID is per tenant.** Twee dingen die samen moeten:

- De registry hieronder is een MODULE-globale. Een registry per exemplaar zou de tellers wissen
  bij elke nieuwe agenttaak, en dan opent een breaker alleen binnen een taak -- precies de
  situatie waarin hij niets bespaart. ADR-026 par. 1.2.1 accepteert expliciet per-worker
  toestand ("start with per-worker breakers, no shared state").
- Juist DAAROM moet die ID de tenant dragen. De twin sleutelt op `klassenaam#index`
  (`learning/interfaces/failover_llm_provider.py:70`); dat klopt voor zijn platformbrede keten,
  maar bij klantketens zouden twee tenants met elk een eigen eindpunt EEN breaker delen, en dan
  zet het uitvallen van klant A de provider van klant B op open. De ID wordt daarom door de
  aanroeper meegegeven als `tenant:<id>|<host>|<volgorde>`.

**Drie randvoorwaarden van die procesbrede keuze, alle drie in de Gate 2-ronde gemeten en hier
opgeschreven omdat ze anders alleen in iemands hoofd bestaan:**

1. *De drempel telt CUMULATIEF, niet opeenvolgend.* `CircuitBreaker._on_success` zet de
   fouten-teller in de staat CLOSED niet terug (nagemeten 2026-09-24: twee fouten, een succes,
   teller nog 2; de derde fout OOIT opent het circuit). Een schakel die zelden faalt gaat dus na
   de derde fout in het leven van dat proces zestig seconden dicht, en herstelt daarna via
   HALF_OPEN. Dat is acceptabel, en het is NIET wat "opeenvolgend" zou betekenen -- die eerdere
   formulering hier, in de featuredoc en in de brief was onwaar.
2. *De registry groeit monotoon.* Er is geen vervaltijd en geen maximum: per proces blijft er een
   breaker per unieke `tenant|host|volgorde`. Met worker-recycling (ADR-011, max_requests=1000)
   loopt dat niet uit de hand; wordt recycling ooit uitgezet, dan is dit een echt lek. Een
   neveneffect van host-en-volgorde in die ID: een klant die zijn rijen HERORDENT of een
   adres wijzigt, krijgt nieuwe ID's en dus een schone breaker, en laat een wees achter. Dat
   is een bewuste ruil -- een gewijzigde inrichting hoort een schone kans te krijgen -- en geen
   toeval.
3. *`asyncio`-primitieven en een nieuwe event loop per bericht.* De breakers en de registry
   gebruiken `asyncio.Lock`, en die bindt zich aan de eerste loop die hem onder CONTENTIE
   gebruikt. Het agentpad draait `asyncio.run()` per Dramatiq-bericht, dus een verse loop per
   bericht. Zolang de OODA-lus serieel is, raakt geen enkele aanroep dat gecontendeerde pad. Wie
   hier concurrency op zet, lost dit eerst op -- anders komt de fout als een onverklaarbare
   `RuntimeError` uit een worker en niet als een rode test.

**Wat NIET doorvalt, en waarom dat per foutsoort een besluit is.**

- `LLMContentFilterError`: de leverancier weigert de INHOUD, het eindpunt is gezond. Doorvallen
  zou dezelfde tekst bij de volgende leverancier aanbieden tot er een ja zegt -- een filter
  omzeilen door het vaak genoeg te vragen. Sinds 2026-09-24 maakt `OpenAICompatibleProvider` die
  fout ook echt (`finish_reason == "content_filter"`); tot die dag was deze belofte LEEG voor het
  enige providertype dat een klantketen kan bevatten, en dat is precies de onware toelichting
  waar `quality-gates.md` voor waarschuwt.
- `AttributeError`, `TypeError`, `KeyError`, `NameError`, `ImportError`: fouten van ONS, niet van
  het eindpunt. Ze de keten in laten lopen betekent dezelfde prompt naar leverancier 2 en 3
  vanwege een bug hier -- een wissel van subverwerker op eigen falen, terwijl dit bestand zo'n
  wissel elders juist met AVG art. 28 lid 2 verbiedt. Ze zouden bovendien als storing tellen op
  de breaker van een gezond eindpunt. Dezelfde vier laat `specialist_base._get_llm_service` om
  dezelfde reden door.
- `LLMAuthenticationError` valt WEL door, en dat is een keuze: een verlopen of ingetrokken sleutel
  op schakel 1 is juist waarvoor een keten bestaat.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass

from src.core.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
)
from src.core.services.llm.base import (
    LLMContentFilterError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMServiceError,
)

logger = logging.getLogger(__name__)

#: Na hoeveel fouten een schakel wordt overgeslagen, en hoelang. De waarden uit ADR-026
#: par. 1.2.1. Let op randvoorwaarde 1 in de moduledocstring: de teller is CUMULATIEF.
_DREMPEL = 3
_HERSTELTIJD = 60.0

#: Fouten die niet van het eindpunt komen. Zie de moduledocstring.
_FOUTEN_VAN_ONSZELF = (AttributeError, TypeError, KeyError, NameError, ImportError)

#: Procesbreed, met opzet. Zie de moduledocstring en de drie randvoorwaarden.
_REGISTRY = CircuitBreakerRegistry()


async def breaker_toestanden() -> dict[str, dict[str, object]]:
    """De staat van elke breaker, alleen-lezen.

    Elke andere failover- of breakerimplementatie in deze repo biedt zo'n venster
    (`learning/interfaces/failover_llm_provider.py`, `llm/fallback_chain.py`,
    `tool_broker/service.py`). Zonder dit is een schakel die zestig seconden dichtstaat alleen
    zichtbaar als losse waarschuwing in het log, en ziet de diagnostieklaag uit ADR-012 er niets
    van.
    """
    toestanden = await _REGISTRY.get_all_states()
    return {breaker_id: dict(staat) for breaker_id, staat in toestanden.items()}


async def _reset_alle_breakers() -> None:
    """Zet elke breaker terug op gesloten. UITSLUITEND voor tests.

    Onderstreept en niet publiek: dit wist de bescherming van elke tenant in dit proces. Zonder
    deze haak lekt toestand van de ene test naar de volgende, want de registry is procesbreed --
    dat is geen testgemak maar een eis, want een test die afhangt van zijn uitvoervolgorde meet
    niets.
    """
    await _REGISTRY.reset_all()


async def _eerste_stuk(stroom: AsyncGenerator[str, None]) -> str:
    """Open de stroom en haal het eerste stukje op, of gooi.

    **Waarom dit zo moet (Gate 2, 2026-09-24).** Hier stond eerst `await breaker.execute(_niets)`:
    een lege aanroep die per definitie slaagt, met de toelichting dat "de lus eronder bepaalt of
    het lukte". Dat was onwaar en tweemaal schadelijk, zelf nagemeten:

    - de breaker zag op het streampad NOOIT een fout, dus een kapot eindpunt werd bij elk verzoek
      opnieuw geprobeerd tot zijn tijdslimiet;
    - en erger: twee mislukte stromen brachten een OPEN breaker via HALF_OPEN terug naar CLOSED
      (gemeten verloop `OPEN -> HALF_OPEN -> CLOSED` na twee lege aanroepen). Een dood eindpunt
      verklaarde zichzelf gezond.

    Een async generator draait pas als je erover loopt, en dat was het probleem dat de lege
    aanroep leek op te lossen. De echte oplossing is de generator BINNEN de breaker openen en het
    eerste stukje ophalen: dan is succes ook echt succes. Een stroom zonder enkel stukje is geen
    geldig antwoord -- `_lees_antwoord` weigert een leeg antwoord op het gewone pad om dezelfde
    reden -- dus dat is hier een storing en geen stil succes.
    """
    async for stuk in stroom:
        return stuk
    raise LLMServiceError("de stroom leverde geen enkel stukje op")


@dataclass(frozen=True)
class KetenSchakel:
    """Een provider plus de ID waaronder zijn breaker leeft.

    **`breaker_id` en niet `sleutel` (Gate 2, 2026-09-24).** Dit veld heette eerst
    `sleutel`, en de bewaker die de klantsleutel uit logregels houdt werd daar terecht rood
    van: in deze codebase betekent "sleutel" een GEHEIM. Zes onschuldige logregels leken
    daardoor een sleutel te dragen. Dat is precies de "een woord, een betekenis"-regel uit
    CLAUDE.md -- het antwoord is niet de bewaker versoepelen maar het woord teruggeven aan
    zijn eigen betekenis.
    """

    breaker_id: str
    provider: LLMProvider


class FailoverProvider(LLMProvider):
    """Probeert de schakels op volgorde, slaat een open breaker over."""

    def __init__(self, schakels: list[KetenSchakel]) -> None:
        if not schakels:
            raise ValueError(
                "FailoverProvider zonder schakels. Een lege keten hoort bij de aanroeper te "
                "worden afgevangen (dan geldt de platformstandaard), niet hier te eindigen als "
                "een provider die niets kan."
            )
        self._schakels = schakels
        self._laatste: KetenSchakel = schakels[0]
        # De configuratie van de eerste schakel, zodat een aanroeper die `config.model` leest
        # een zinnig antwoord krijgt. `_validate_config` van deze klasse doet niets extra's:
        # elke schakel is bij zijn eigen constructie al gevalideerd.
        super().__init__(schakels[0].provider.config)

    def _validate_config(self) -> None:
        return None

    async def _breaker_voor(self, schakel: KetenSchakel) -> CircuitBreaker:
        """De breaker van deze schakel, op EEN plek opgehaald.

        Zowel `generate` als `stream` heeft hem nodig. Twee keer dezelfde regel zou betekenen dat
        een mutatietest op de breaker-id of de drempel twee ankers heeft en er per ongeluk maar een
        raakt -- precies hoe een guard groen blijft terwijl de helft van het gedrag is
        weggevallen. Gemeten: drie mutaties uit de eerste ronde struikelden hierover.
        """
        return await _REGISTRY.get_breaker(
            schakel.breaker_id,
            failure_threshold=_DREMPEL,
            recovery_timeout=_HERSTELTIJD,
        )

    @property
    def provider_name(self) -> str:
        """De naam van de schakel die het laatst heeft geantwoord.

        NIET "failover": die naam wordt op drie plekken in `src/` gelezen (de mock-controle voor
        productie, een logregel, en een veld in een API-antwoord), en daar hoort te staan WELK
        eindpunt het werk deed.

        **Dit is muteerbare toestand en dus niet de enige drager van het spoor.** Een
        `LLMService` uit `for_tenant` wordt door de agent gecachet; zouden er ooit twee aanroepen
        tegelijk over dezelfde instantie lopen, dan kan hier de schakel van de ANDERE aanroep
        staan. Daarom logt `generate` bij SUCCES zelf welke schakel antwoordde -- dat is het spoor
        dat AVG art. 30 vraagt, en het hangt niet aan dit veld.
        """
        return self._laatste.provider.provider_name

    @property
    def serves_mock(self) -> bool:
        """WAAR zodra een van de schakels een namaakmodel kan bedienen.

        Deze klasse overschrijft `provider_name`, en de basisklasse leidt `serves_mock` daaruit
        af -- precies de constructie waar
        `tests/architecture/test_een_provider_die_zijn_naam_kiest_kiest_ook_serves_mock.py` voor
        bestaat. Voor een samengestelde provider is het antwoord bovendien alleen veilig als het
        over de HELE keten gaat: een productiecontrole die alleen naar de eerste schakel kijkt,
        laat een namaakschakel verderop ongemoeid.
        """
        return any(schakel.provider.serves_mock for schakel in self._schakels)

    @property
    def supports_streaming(self) -> bool:
        """Alleen als ELKE schakel het kan.

        Anders zou een failover midden in een stroom kunnen uitkomen bij een schakel die niet kan
        streamen, en dan faalt de aanroep alsnog -- met een fout die niets zegt over de oorzaak.
        """
        return all(schakel.provider.supports_streaming for schakel in self._schakels)

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        laatste_fout: Exception | None = None

        for schakel in self._schakels:
            breaker = await self._breaker_voor(schakel)
            try:
                antwoord: LLMResponse = await breaker.execute(
                    schakel.provider.generate, messages, temperature, max_tokens
                )
            except CircuitOpenError:
                logger.warning(
                    "llm-keten: schakel overgeslagen, circuit open (breaker=%s)", schakel.breaker_id
                )
                continue
            except (LLMContentFilterError, *_FOUTEN_VAN_ONSZELF):
                # Zie de moduledocstring: geen van deze is een storing van het eindpunt.
                raise
            except Exception as exc:
                laatste_fout = exc
                logger.warning(
                    "llm-keten: schakel faalde (breaker=%s, %s: %s)",
                    schakel.breaker_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                continue

            self._laatste = schakel
            # Bij SUCCES vastleggen welke schakel het deed. Zonder deze regel is er bij een
            # geslaagde failover geen positieve vastlegging van het gebruikte eindpunt en moet een
            # lezer het afleiden uit de AFWEZIGHEID van een waarschuwing -- dat is geen
            # verwerkingsregister (AVG art. 30, AI Act art. 12).
            logger.info("llm-keten: antwoord van schakel %s", schakel.breaker_id)
            return antwoord

        raise LLMServiceError(
            "de hele providerketen van deze tenant is onbruikbaar "
            f"({len(self._schakels)} schakels geprobeerd of overgeslagen). "
            "Er wordt met opzet NIET teruggevallen op het platformmodel: deze klant heeft een "
            "eigen verwerker gekozen, en zijn gegevens daar stilzwijgend omheen sturen is een "
            "wissel van subverwerker die hij niet heeft goedgekeurd."
        ) from laatste_fout

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Failover tot het EERSTE stukje, daarna niet meer.

        Zodra er tekst naar de aanroeper is gegaan, is overschakelen niet meer eerlijk: die zou
        dan het begin van het ene antwoord en het vervolg van het andere krijgen, aan elkaar
        geplakt zonder dat iets dat meldt. Een storing halverwege gaat daarom omhoog.

        De breaker omhult het OPENEN plus het eerste stukje (`_eerste_stuk`) en niet de hele
        stroom -- zie die functie voor wat er misging toen hij een lege aanroep omhulde.
        `aclosing` sluit de binnenste generator deterministisch, ook als de aanroeper vroegtijdig
        stopt: die generator houdt een HTTP-verbinding vast.
        """
        laatste_fout: Exception | None = None

        for schakel in self._schakels:
            breaker = await self._breaker_voor(schakel)
            stroom = schakel.provider.stream(messages, temperature, max_tokens)
            async with aclosing(stroom):
                try:
                    eerste = await breaker.execute(_eerste_stuk, stroom)
                except CircuitOpenError:
                    logger.warning(
                        "llm-keten (stroom): schakel overgeslagen, circuit open (breaker=%s)",
                        schakel.breaker_id,
                    )
                    continue
                except (LLMContentFilterError, *_FOUTEN_VAN_ONSZELF):
                    raise
                except Exception as exc:
                    laatste_fout = exc
                    logger.warning(
                        "llm-keten (stroom): schakel faalde voor het eerste stukje "
                        "(breaker=%s, %s)",
                        schakel.breaker_id,
                        type(exc).__name__,
                        exc_info=True,
                    )
                    continue

                self._laatste = schakel
                logger.info("llm-keten (stroom): antwoord van schakel %s", schakel.breaker_id)
                yield eerste
                # Vanaf hier is er tekst geleverd en valt er niets meer door: een fout uit deze
                # lus gaat omhoog, precies zoals de docstring belooft.
                async for stuk in stroom:
                    yield stuk
                return

        raise LLMServiceError(
            "de hele providerketen van deze tenant is onbruikbaar voor een stroom"
        ) from laatste_fout

    async def get_embeddings(self, text: str) -> list[float]:
        """Geen failover: er is vandaag geen schakeltype dat embeddings aanbiedt.

        `OpenAICompatibleProvider` -- het enige type dat een klantrij oplevert -- implementeert ze
        niet. Hier een keten omheen bouwen zou een pad zijn dat nooit wordt gelopen en dus nooit
        wordt getoetst. Doorgeven aan de eerste schakel houdt het gedrag gelijk aan wat het zonder
        deze klasse was.
        """
        return await self._schakels[0].provider.get_embeddings(text)
