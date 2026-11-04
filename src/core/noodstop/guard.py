"""De controle die elke deur uitvoert: staat deze klant stil? (noodstop per klant)

**Het principe.** Een deur is elke plek waar een agent (of een achtergrondtaak namens een agent) een
ACTIE start: een tool uitvoeren, een besluit van de Council vragen, een workflowstap draaien, een
brief versturen. Elke deur roept `eis_klant_actief(tenant_id)` aan voor hij iets doet en geeft, als
dat een `KlantStilgezet` oplevert, een Nederlandse weigering. `tests/architecture/
test_elke_deur_controleert_de_noodstop.py` faalt als een deur die controle mist, of als er een nieuwe
deur bij komt die niet is ingedeeld.

**Fail-closed.** Alles wat niet met zekerheid "deze klant staat NIET stil" is, weigert:

- geen of een onleesbare klant (`None`, tekst, nul of negatief);
- de database is niet te bereiken, of de query faalt;
- elk ander antwoord dan een expliciet `False` van de lezer.

Een kapotte stand mag de noodstop nooit stil opheffen; de prijs is dat een storing in de database
de acties van agents tegenhoudt, en dat is hier de bedoelde kant.

**Waar de stand vandaan komt.** Uit de tabel `tenant_noodstop` (de bron, ADR-010), bij elke
controle opnieuw gelezen: geen cache, dus een stop geldt direct, in elke worker en elk proces, en
overleeft een herstart.

**Welke verbinding.** Twee wegen, naar de loop waarin de controle draait:

- *Een actor-run* (`draai_in_eigen_loop`: een eigen event loop met een eigen poolloze engine, want
  een gepoolde verbinding hangt daar aan een gesloten loop). De run geeft zijn engine door
  (`gebruik_eigen_run_engine`); de controle hergebruikt die, achter een semafoor
  (`MAX_GELIJKTIJDIG_IN_EEN_RUN`), zodat een run nooit meer dan een paar controles tegelijk een
  eigen verbinding laat openen. Er wordt geen engine per controle gebouwd.
- *Elke andere loop* (de requestcontext, de scheduler in het hoofdproces): een gedeelde engine met
  een KLEINE, EIGEN pool per loop, los van de pool van de applicatie. Zo kan een stortvloed aan
  controles de applicatiepool niet leegtrekken, en een uitgeputte noodstoppool geeft binnen een
  paar seconden een fout (fail-closed) in plaats van een wachtrij van 30 s.

Voorheen bouwde elke controle een eigen poolloze engine: gemeten ~109 ms mediaan en 206 ms max
per controle, plus een extra verbinding per actie. De meting na de wijziging staat in het rapport
van ronde 2.

**De klant komt van de AANROEPER** en is daar uit de JWT of de contextvariabele gehaald (of uit de
database-rij van de taak zelf); nooit uit een body of query.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

#: Meer controles tegelijk in EEN actor-run wachten op elkaar (zie de moduledocstring).
MAX_GELIJKTIJDIG_IN_EEN_RUN = 4

#: De kleine pool voor de loops zonder eigen run. Kort pool_timeout: uitputting geeft snel een fout.
KLEINE_POOL_GROOTTE = 2
KLEINE_POOL_OVERLOOP = 2
KLEINE_POOL_TIMEOUT_S = 5

#: De weigering voor een klant die stilgezet is. Staat hier op een plek, zodat elke deur dezelfde
#: tekst geeft en een test hem kan vergelijken.
MELDING_STIL = (
    "Uw bedrijf is stilgezet (noodstop). Er worden geen acties van agents uitgevoerd "
    "tot een beheerder de noodstop opheft."
)

#: De weigering als niet vast te stellen is of de klant stilstaat (fail-closed).
MELDING_ONBEKEND = (
    "Kon niet vaststellen of uw bedrijf actief is. De actie is uit voorzorg niet uitgevoerd."
)


#: De melding voor een CHATGEBRUIKER (besluit A, ronde 2): dezelfde vaste tekst in elke chat.
MELDING_CHAT_STIL = (
    "De agents van jouw organisatie staan tijdelijk stil. Neem contact op met je beheerder."
)

#: De chatmelding als niet vast te stellen is of de klant stilstaat (fail-closed).
MELDING_CHAT_ONBEKEND = (
    "Kon niet vaststellen of de agents van jouw organisatie actief zijn. "
    "Probeer het later opnieuw of neem contact op met je beheerder."
)


class KlantStilgezet(Exception):
    """Een deur weigert: de klant staat stil, of dat is niet met zekerheid te zeggen.

    `onbekend` is True als de weigering komt doordat de stand niet te lezen was; dat is een
    storing en geen besluit van een beheerder, en de aanroeper kan daar anders mee omgaan
    (bijvoorbeeld een taak later opnieuw proberen).
    """

    def __init__(self, bericht: str, *, onbekend: bool = False) -> None:
        super().__init__(bericht)
        self.bericht = bericht
        self.onbekend = onbekend


StandLezer = Callable[[int], Awaitable[bool]]


@dataclass
class _EigenRun:
    """De engine van een actor-run en de semafoor die de controles in die run begrenst."""

    engine: AsyncEngine
    semafoor: asyncio.Semaphore


#: De run waarin de controle nu draait (gezet door `draai_in_eigen_loop`), of None.
_eigen_run: ContextVar[_EigenRun | None] = ContextVar("noodstop_eigen_run", default=None)

#: De kleine-pool-engine per event loop (zwakke verwijzing: een gesloten loop ruimt zichzelf op).
_engines_per_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncEngine] = (
    weakref.WeakKeyDictionary()
)


@contextmanager
def gebruik_eigen_run_engine(engine: AsyncEngine) -> Iterator[None]:
    """Binnen dit blok hergebruikt de controle `engine` (de poolloze engine van de actor-run)."""
    token = _eigen_run.set(_EigenRun(engine, asyncio.Semaphore(MAX_GELIJKTIJDIG_IN_EEN_RUN)))
    try:
        yield
    finally:
        _eigen_run.reset(token)


def _engine_voor_deze_loop() -> AsyncEngine:
    """De gedeelde engine met een kleine, eigen pool voor de lopende loop (gebouwd bij eerste gebruik)."""
    from src.core.database.database import db_manager

    loop = asyncio.get_running_loop()
    engine = _engines_per_loop.get(loop)
    if engine is None:
        # Een gesloten loop laat een engine achter waarvan de verbindingen aan die loop hangen:
        # weggooien zonder te sluiten (sluiten zou op een dode loop moeten wachten).
        for oude_loop, oude_engine in list(_engines_per_loop.items()):
            if oude_loop.is_closed():
                oude_engine.sync_engine.dispose(close=False)
                del _engines_per_loop[oude_loop]
        engine = db_manager.create_small_pool_engine(
            pool_size=KLEINE_POOL_GROOTTE,
            max_overflow=KLEINE_POOL_OVERLOOP,
            pool_timeout=KLEINE_POOL_TIMEOUT_S,
        )
        _engines_per_loop[loop] = engine
    return engine


async def _lees_met_engine(engine: AsyncEngine, tenant_id: int) -> bool:
    """True als de klant stilstaat: een korte sessie op `engine`, alleen gelezen."""
    from src.core.database.bypass_session import adopt_tenant
    from src.core.repositories.tenant_noodstop_repository import TenantNoodstopRepository

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sessie:
        async with adopt_tenant(sessie, tenant_id):
            stilgezet = await TenantNoodstopRepository(sessie).is_stilgezet(tenant_id)
        await sessie.rollback()
        return stilgezet


async def _lees_uit_database(tenant_id: int) -> bool:
    """True als de klant stilstaat. De keuze van de verbinding staat in de moduledocstring."""
    run = _eigen_run.get()
    if run is not None:
        async with run.semafoor:
            return await _lees_met_engine(run.engine, tenant_id)
    return await _lees_met_engine(_engine_voor_deze_loop(), tenant_id)


#: De lezer van de stand. Een attribuut op moduleniveau zodat een test hem op de GRENS kan
#: vervangen (de database), terwijl al het andere in `eis_klant_actief` echt draait.
_lees_stand: StandLezer = _lees_uit_database


def _als_klant(tenant_id: object) -> int | None:
    """De klant als positief geheel getal, of None als dat niet met zekerheid kan."""
    if isinstance(tenant_id, bool):
        return None
    if isinstance(tenant_id, int):
        return tenant_id if tenant_id > 0 else None
    if isinstance(tenant_id, str):
        tekst = tenant_id.strip()
        if tekst.isascii() and tekst.isdecimal() and int(tekst) > 0:
            return int(tekst)
    return None


async def eis_klant_actief(tenant_id: object) -> None:
    """Gooit `KlantStilgezet` tenzij zeker is dat de klant NIET stilstaat (fail-closed)."""
    klant = _als_klant(tenant_id)
    if klant is None:
        logger.error("noodstop: klant onbekend of ongeldig, actie geweigerd (fail-closed)")
        raise KlantStilgezet(MELDING_ONBEKEND, onbekend=True)
    try:
        stilgezet = await _lees_stand(klant)
    except Exception as exc:
        logger.error(
            "noodstop: stand van klant %s niet te lezen, actie geweigerd (fail-closed): %s: %s",
            klant,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise KlantStilgezet(MELDING_ONBEKEND, onbekend=True) from exc
    if stilgezet is not False:
        # `is not False` en niet `if stilgezet`: alleen een expliciet False laat door.
        logger.warning("noodstop: actie van klant %s geweigerd, klant staat stil", klant)
        raise KlantStilgezet(MELDING_STIL)


async def eis_chat_actief(tenant_id: object) -> None:
    """Zoals `eis_klant_actief`, met de vaste melding voor een chatgebruiker (besluit A, ronde 2).

    Een chat stuurt klantgegevens naar een taalmodel en kan Prana kosten. De deur van een chat
    roept dit aan voor het eerste model-, council- of tegoedaanroep en vertaalt `KlantStilgezet`
    naar een weigering op de eigen manier (HTTP 403/503, een foutkader, een geblokkeerd antwoord).
    """
    try:
        await eis_klant_actief(tenant_id)
    except KlantStilgezet as stop:
        raise KlantStilgezet(
            MELDING_CHAT_ONBEKEND if stop.onbekend else MELDING_CHAT_STIL, onbekend=stop.onbekend
        ) from stop


async def klant_staat_stil(tenant_id: object) -> bool:
    """True als een deur zou weigeren. Voor een deur die overslaat in plaats van te gooien."""
    try:
        await eis_klant_actief(tenant_id)
    except KlantStilgezet:
        return True
    return False
