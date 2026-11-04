"""Een aparte databaseverbinding voor pre-authenticatie-lookups (ADR-036 OP-154).

**Het probleem.** De applicatie verbindt vandaag als EIGENAAR van de tabellen, en
PostgreSQL slaat Row Level Security voor de eigenaar over. Alle policies in de keten zijn
daarmee inert (OP-151). De omschakeling naar de niet-eigenaar `sanskritisetu_app` loopt
vast op een ding: het inlogpad zoekt een gebruiker op e-mailadres VOORDAT de tenant bekend
is, en zonder tenantcontext geeft die lookup nul rijen.

Gemeten 2026-09-15 op PostgreSQL 15.19, policy-vorm uit
`src/alembic/versions/20260522_add_rls_core_tables.py:38-43`:

    als eigenaar, geen tenantcontext          1 rij
    als sanskritisetu_app, geen tenantcontext 0 rijen     <-- inloggen valt stil
    als sanskritisetu_app, tenant 1 gezet     1 rij

**Waarom een aparte VERBINDING en geen rolwissel.** Het voor de hand liggende alternatief
is een tweede rol met `BYPASSRLS` die aan de applicatierol wordt gegrant, waarna het
authenticatiepad met `SET ROLE` omschakelt. Gemeten vanaf een ECHTE inlogverbinding als
`sanskritisetu_app`:

    rol gegrant, INHERIT     -> `SET ROLE` lukt  -> 2 van 2 rijen (ALLE tenants)
    rol gegrant, NOINHERIT   -> `SET ROLE` lukt  -> 2 van 2 rijen (ALLE tenants)
    rol NIET gegrant         -> permission denied to set role

`BYPASSRLS` is een rol-ATTRIBUUT en geen overerfbaar privilege, en `NOINHERIT` geldt niet
voor rol-attributen (https://www.postgresql.org/docs/15/role-attributes.html). Wie het
grant legt, geeft de applicatieverbinding dus een permanente uitweg uit alle policies --
niet alleen binnen een bypass-blok. De veiligheid zit volledig in NIET koppelen, en dat is
precies wat een aparte verbinding doet. Besluit van Rakesh, 2026-08-17.

**Waarom een EIGEN pool.** Een tweede sessie die uit dezelfde pool komt kan onder druk
vastlopen: de buitenste sessie houdt een verbinding vast terwijl de binnenste op een vrije
verbinding wacht (https://github.com/sqlalchemy/sqlalchemy/issues/5546). De pool hier is
bewust klein: dit pad bedient alleen pre-authenticatie-lookups, geen verkeer.

**Waarom de engine lui wordt aangemaakt.** Een client op moduleniveau maakt zijn
verbinding (of zijn bestanden) aan zodra iemand de module importeert -- ook een test die
er niets mee doet. Dat is de fout uit OP-179 en OP-220. `initialize()` doet het werk, de
import niet.

**Fail-secure.** Is er GEEN bypass-DSN geconfigureerd, dan is dit pad uit en verandert er
niets: `is_configured()` geeft False en de aanroeper houdt zijn huidige gedrag. Is er WEL
een DSN maar werkt hij niet, dan volgt een fout. Er wordt nooit stil teruggevallen op de
gewone sessie, want die geeft onder de applicatierol nul rijen -- en een lege uitkomst is
hier niet te onderscheiden van "gebruiker bestaat niet".

**Let op bij het gebruik.** Wie BINNEN dit blok leest en DAARBUITEN schrijft, schrijft op
een andere sessie dan waar het object vandaan komt. Gemeten gevolg: de UPDATE raakt nul
rijen, de commit slaagt, en er verandert niets -- zonder foutmelding. Lezen en schrijven
horen allebei binnen hetzelfde blok. Bewaakt door
`tests/architecture/test_bypass_lezen_en_schrijven_blijven_bij_elkaar.py`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

__all__ = [
    "BypassNietBeschikbaar",
    "adopt_tenant",
    "bypass_is_configured",
    "bypass_session",
    "close_bypass_engine",
    "initialize_bypass_engine",
    "pre_auth_lookup",
]

logger = logging.getLogger(__name__)

#: Naam van de omgevingsvariabele met de aparte verbinding. Bewust NIET afgeleid van
#: DATABASE_URL: dan zou een verkeerd gezette DATABASE_URL stilzwijgend ook dit pad
#: bepalen, en is er geen verschil meer tussen "niet geconfigureerd" en "per ongeluk
#: dezelfde rol".
BYPASS_DSN_ENV = "BYPASS_DATABASE_URL"

#: Klein, maar NIET "geen verkeer" -- die geruststelling stond hier eerst en is onjuist:
#: na stap 3 loopt ELKE inlogpoging hierlangs, botverkeer en credential stuffing incluis.
#: Vier gelijktijdige verbindingen (pool + overflow) is dan de smalste plek in de hele
#: applicatie. Dit getal is NIET gemeten tegen een verwachte gelijktijdigheid -- er is geen
#: meting, en dat hoort hier te staan in plaats van een gevoel. Wie stap 3 uitvoert, meet
#: het aantal gelijktijdige logins en stelt dit bij.
_POOL_SIZE = 2
_MAX_OVERFLOW = 2

#: Expliciet, niet de SQLAlchemy-default van 30 seconden: op een pre-authenticatiepad is
#: lang wachten op een verbinding erger dan snel falen. Een verzoek dat hier vastloopt
#: houdt ook een verbinding uit de APPLICATIEpool bezet.
_POOL_TIMEOUT = 5

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None
_slot: asyncio.Lock | None = None


def _het_slot() -> asyncio.Lock:
    """Lui aangemaakt slot.

    Niet op moduleniveau: een `asyncio.Lock()` bij import bindt zich in oudere Python aan de
    lus die dan toevallig draait, en dit project heeft daar een eigen guard voor
    (`tests/architecture/test_no_import_time_asyncio_primitives.py`).
    """
    global _slot
    if _slot is None:
        _slot = asyncio.Lock()
    return _slot


class BypassNietBeschikbaar(RuntimeError):
    """De bypass-verbinding is geconfigureerd maar onbruikbaar.

    Dit is bewust GEEN stille terugval. Onder de applicatierol geeft de gewone sessie nul
    rijen op een pre-authenticatie-lookup, en dat is niet te onderscheiden van "gebruiker
    bestaat niet" -- inloggen zou dan stil weigeren in plaats van luid te falen.
    """


def _dsn() -> str:
    return os.getenv(BYPASS_DSN_ENV, "").strip()


def bypass_is_configured() -> bool:
    """True zolang er een aparte verbinding is opgegeven.

    Zonder DSN is dit hele pad uit en gedraagt de applicatie zich exact zoals vandaag.
    Dat is wat OP-154 stap 1 onzichtbaar maakt voor elke draaiende omgeving.
    """
    return bool(_dsn())


async def _toets_de_rol(conn: AsyncConnection) -> None:
    """Toetst dat deze verbinding ECHT de bypass-rol is, en niets anders.

    **Waarom `SELECT 1` niet volstaat.** Het hele veiligheidsargument van OP-154 is dat
    deze verbinding naar een aparte, smal gerechtigde rol gaat. Die belofte stond eerst
    alleen in proza; `SELECT 1` slaagt namelijk ook als de DSN per ongeluk naar iets anders
    wijst, en dan passeren precies de twee misconfiguraties die ertoe doen:

    - **naar de eigenaar of een superuser** -- het pre-authenticatiepad krijgt dan
      ongelimiteerde toegang tot elke tabel, en de smalle rechtenset uit de migratie is
      betekenisloos. Geen enkele test of log zou dat opmerken.
    - **naar `sanskritisetu_app`** -- dan geeft de inloglookup nul rijen: exact de stille
      storing waarvoor deze module bestaat.

    De migratie beschermt tegen `SET ROLE`; deze toets beschermt tegen een verkeerde DSN.
    Dat zijn twee verschillende aanvalswegen en de eerste dekt de tweede niet.
    """
    rij = (
        await conn.execute(
            text(
                "SELECT current_user, "
                "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user), "
                "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
            )
        )
    ).first()

    if rij is None:  # pragma: no cover - PostgreSQL geeft hier altijd een rij
        raise BypassNietBeschikbaar("De rolcontrole op de bypass-verbinding gaf geen antwoord.")

    rol, bypassrls, is_superuser = rij
    if is_superuser:
        raise BypassNietBeschikbaar(
            f"{BYPASS_DSN_ENV} verbindt als SUPERUSER ({rol!r}). Het pre-authenticatiepad "
            "zou dan elke tabel kunnen lezen en schrijven, buiten elke policy om. "
            "Wijs de DSN naar de rol uit `20260915_bypass_databaserol` (ADR-036 OP-154)."
        )
    if not bypassrls:
        raise BypassNietBeschikbaar(
            f"{BYPASS_DSN_ENV} verbindt als {rol!r}, een rol ZONDER BYPASSRLS. Op het "
            "pre-authenticatiepad geeft die nul rijen zonder foutmelding -- precies de "
            "stille storing die deze verbinding moet voorkomen (ADR-036 OP-154)."
        )


async def initialize_bypass_engine() -> None:
    """Maakt de engine aan en toetst hem meteen. Idempotent.

    Wordt de verbinding niet gelegd, dan volgt `BypassNietBeschikbaar`. De toets staat hier
    en niet bij het eerste gebruik, zodat een verkeerde configuratie bij het opstarten
    opvalt en niet pas wanneer de eerste gebruiker probeert in te loggen.
    """
    dsn = _dsn()
    if not dsn:
        logger.debug("bypass_session: geen %s gezet -- pad blijft uit", BYPASS_DSN_ENV)
        return
    if _engine is not None:
        return

    async with _het_slot():
        # Tweede controle BINNEN het slot. Zonder deze bouwen twee gelijktijdige eerste
        # aanroepers allebei een engine; een ervan wordt nooit toegewezen en nooit
        # gedisposed, en lekt zijn pool.
        if _engine is not None:
            return
        await _bouw_de_engine(dsn)


async def _bouw_de_engine(dsn: str) -> None:
    """Bouwt en toetst de engine. Alleen aanroepen met `_het_slot()` vast."""
    global _engine, _session_maker

    try:
        engine = create_async_engine(
            dsn,
            pool_size=_POOL_SIZE,
            max_overflow=_MAX_OVERFLOW,
            pool_timeout=_POOL_TIMEOUT,
            pool_pre_ping=True,
        )
    except (SQLAlchemyError, ValueError) as exc:
        # Een onleesbare DSN (typefout, onbekende driver) werpt hier al, VOOR de try
        # hieronder. Zonder deze vangst zou de aanroeper een `ArgumentError` krijgen in
        # plaats van het afgesproken `BypassNietBeschikbaar`, en dan is het contract
        # "dit pad faalt luid en op een herkenbare manier" niet waar.
        raise BypassNietBeschikbaar(
            f"De waarde van {BYPASS_DSN_ENV} is geen bruikbare verbindingsreeks: "
            f"{type(exc).__name__}. (De reeks zelf wordt niet gelogd -- hij bevat een "
            "wachtwoord.)"
        ) from exc

    try:
        async with engine.connect() as conn:
            await _toets_de_rol(conn)
    except BypassNietBeschikbaar:
        await engine.dispose()
        raise
    except (SQLAlchemyError, OSError) as exc:
        await engine.dispose()
        # exc_info: zonder de stacktrace is een DSN-fout niet te onderscheiden van een
        # netwerkfout, en dat kost bij het eerste incident de meeste tijd.
        logger.error(
            "bypass_session: verbinding uit %s is onbruikbaar: %s: %s",
            BYPASS_DSN_ENV,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise BypassNietBeschikbaar(
            f"De bypass-verbinding uit {BYPASS_DSN_ENV} kan niet worden gelegd. "
            "Het pre-authenticatiepad valt bewust NIET terug op de gewone sessie: "
            "die geeft onder de applicatierol nul rijen (ADR-036 OP-154)."
        ) from exc

    _engine = engine
    _session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    logger.info("bypass_session: aparte verbinding actief (pool_size=%d)", _POOL_SIZE)


@asynccontextmanager
async def bypass_session() -> AsyncIterator[AsyncSession]:
    """Levert een sessie op de APARTE verbinding.

    De aanroeper houdt zijn eigen sessie en zijn eigen lopende transactie -- gemeten
    2026-09-15: `in_transaction=True` na afloop van dit blok.

    Roept `initialize_bypass_engine()` aan als dat nog niet is gebeurd, zodat een
    aanroeper niet hoeft te weten of het opstarten al langs is gekomen.
    """
    if not bypass_is_configured():
        raise BypassNietBeschikbaar(
            f"{BYPASS_DSN_ENV} is niet gezet. Toets eerst `bypass_is_configured()`; "
            "zonder aparte verbinding hoort de aanroeper zijn huidige gedrag te houden."
        )
    if _session_maker is None:
        await initialize_bypass_engine()
    if _session_maker is None:  # pragma: no cover - initialize werpt al bij een fout
        raise BypassNietBeschikbaar("bypass_session is niet geinitialiseerd")

    async with _session_maker() as sessie:
        yield sessie


@asynccontextmanager
async def pre_auth_lookup(db: AsyncSession) -> AsyncIterator[AsyncSession]:
    """De sessie waarop een opzoeking VOOR authenticatie mag draaien (OP-154 stap 2).

    Is de aparte verbinding ingericht, dan die. Zo niet, dan de sessie van de aanroeper --
    exact het gedrag van vandaag. Daardoor verandert deze omzetting niets aan een draaiende
    omgeving tot iemand `BYPASS_DATABASE_URL` zet.

    **In BEIDE gevallen ook binnen `TenantFilterBypass`.** De applicatieve tenantfilter is
    geregistreerd op de KLASSE `Session` met `propagate=True`, dus een vreemde sessionmaker
    ontsnapt er niet aan: zonder de bypass krijgt ook de aparte verbinding `WHERE false`.
    Dat is in stap 1 door een Gate 2-reviewer nagemeten.

    **Een helper, en geen acht losse `if`-statements op de aanroepplekken.** Acht losse
    keuzes zijn acht kansen om er een verkeerd te maken, en de verkeerde keuze faalt hier
    stil. Beide reviewers vroegen hier expliciet om.

    Wat je met het resultaat MAG doen: `id` en `tenant_id` aflezen. Wat je er NIET mee doet:
    het object meenemen naar buiten dit blok om het daar te wijzigen. Het hoort dan bij een
    andere sessie, en de schrijfactie raakt nul rijen zonder foutmelding -- gemeten
    2026-09-15. Neem de tenant aan met `adopt_tenant()` en laad opnieuw op `db`.
    """
    from src.core.database.tenant_query_filter import TenantFilterBypass

    with TenantFilterBypass():
        if bypass_is_configured():
            async with bypass_session() as sessie:
                yield sessie
        else:
            yield db


@asynccontextmanager
async def adopt_tenant(db: AsyncSession, tenant_id: int) -> AsyncIterator[None]:
    """Neemt de tenant aan zodra de gebruiker vaststaat (OP-154 stap 2).

    Vanaf dat moment is er niets meer te omzeilen: we weten bij welke klant deze gebruiker
    hoort, dus lezen en schrijven kan gewoon op de NORMALE verbinding, netjes binnen de
    grenzen van die ene klant. **Daardoor hoeft de bypass-rol nooit schrijfrechten te
    krijgen** -- die blijft SELECT-only, en de zorg van beide Gate 2-reviewers dat die
    rechtenset stap voor stap zou uitdijen vervalt.

    **Waarom op TWEE plekken, en niet op een.** Gemeten 2026-09-15 via SQLAlchemy+asyncpg:

        zonder tenantcontext                       0 rijen
        tenant gezet in de LOPENDE transactie      1 rij      -> UPDATE raakt 1 rij
        na commit(), dus een NIEUWE transactie     0 rijen    <-- weer weg

    `set_config(..., true)` is transactie-lokaal; de volgende transactie haalt zijn waarde
    uit de ContextVar via de `Engine.begin`-listener in `database.py`. Zetten we alleen de
    transactie, dan raakt alles na de eerste `commit()` de tenant weer kwijt. Zetten we
    alleen de ContextVar, dan mist de AL LOPENDE transactie hem. Dus allebei.

    **Waarom een blok met een gegarandeerde terugzet.** De middleware ruimt de tenantcontext
    op in een `finally`, maar ALLEEN op het geauthenticeerde pad
    (`tenant_middleware.py:385`). De publieke doorlaat -- het pad van inloggen en
    wachtwoordherstel -- wist aan het begin en keert daarna terug zonder opruiming
    (`:344`, `:366-367`). Een tenant die daar blijft staan kan meeliften naar een volgend
    verzoek; Starlette kent zo'n lek gedocumenteerd bij hergebruikte verbindingen met
    formulierdata, en het is gesloten als "not planned"
    (https://github.com/Kludex/starlette/issues/2335). Dit blok zet daarom zelf de VORIGE
    waarde terug -- hetzelfde patroon als `TenantFilterBypass` -- op BEIDE plekken waar het
    zet: de ContextVar EN de transactielokale instelling.

    Die tweede helft ontbrak in de eerste versie terwijl deze docstring toch beweerde dat
    er "niets kan overleven". Dat was onwaar, is door de Gate 2-review van 2026-09-15
    weerlegd, en is gerepareerd in plaats van de claim af te zwakken -- zonder die helft
    wees de ContextVar na het blok naar de vorige tenant terwijl dezelfde, nog OPEN
    transactie op databaseniveau nog de aangenomen tenant had.

    Niet `clear_tenant_context()` bij het verlaten: op een geauthenticeerd pad
    (`change_password`) heeft de middleware al een tenant gezet, en die hoort te blijven.

    **Wat dit blok NIET dekt -- lees dit voor je het uitbreidt.**

    - **Een taak die BINNEN dit blok wordt gestart.** `asyncio.create_task()` geeft de
      nieuwe taak een KOPIE van de context op het moment van aanmaken. Die taak houdt de
      aangenomen tenant dus vast nadat dit blok is afgelopen, en dit `finally` kan daar
      niets aan doen. Start geen achtergrondtaak binnen een `adopt_tenant`-blok.
    - **De herkomst van `tenant_id` is de verantwoordelijkheid van de AANROEPER.** Deze
      functie valideert de waarde (via `set_tenant_id`) maar weet niet waar hij vandaan
      komt. Op het inlogpad komt hij uit een gebruiker die de aanvrager bij e-mailadres
      NOEMT, en dat gebeurt VOOR de wachtwoordcontrole. Dat is daar veilig omdat er binnen
      het blok niets naar buiten komt dat niet aan die gevonden gebruiker hangt -- maar het
      is een eigenschap om te bewaken. `tenant_id` mag NOOIT uit een request-body of
      formulier komen (CLAUDE.md NOOIT-lijst).
    """
    from src.core.middleware.tenant_context import (
        clear_tenant_context,
        get_tenant_id,
        set_tenant_id,
    )

    vorige = get_tenant_id()
    # Voor de `finally`: die moet weten of de transactielokale waarde is gezet, ook als het
    # zetten hieronder nooit is bereikt.
    is_postgres = False
    set_tenant_id(tenant_id)
    try:
        # De listener heeft voor de AL LOPENDE transactie al gedraaid; die moet apart.
        # Bindparameter en geen samengestelde SQL: de waarde is al door `set_tenant_id`
        # gevalideerd, maar een utility-statement met interpolatie blijft een slecht idee.
        #
        # ALLEEN op PostgreSQL. SQLite kent `set_config` niet en kent geen RLS; daar is de
        # ContextVar hierboven het hele verhaal. Zelfde afweging als
        # `_zet_tenantcontext` in `database.py:156`, die om dezelfde reden vroeg terugkeert.
        # Zonder deze controle werpt elke unit-test die dit pad raakt een OperationalError,
        # die in `login` door het algemene vangnet wordt opgevangen en een 500 oplevert --
        # gemeten 2026-09-15: `test_failed_attempts_accumulate_on_one_record` vond daardoor
        # nul lockout-records.
        # `getattr` en geen `db.bind`: een sessie hoeft geen bind te hebben, en een
        # testdubbel met `spec=AsyncSession` heeft het attribuut soms niet. Zonder dit
        # werpt deze regel `AttributeError` op een plek die daar niets mee te maken heeft.
        bind = getattr(db, "bind", None)
        if bind is not None and getattr(bind, "dialect", None) is not None:
            is_postgres = bind.dialect.name == "postgresql"
        if is_postgres:
            await db.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(int(tenant_id))},
            )
        yield
    finally:
        if vorige is None:
            clear_tenant_context()
        else:
            set_tenant_id(vorige)

        # Ook de TRANSACTIELOKALE waarde terugzetten, niet alleen de ContextVar.
        #
        # Een eerdere versie deed dit niet, en de docstring beweerde toch dat er "niets kan
        # overleven". Onwaar, en gevonden door de Gate 2-review op 2026-09-15: na het blok
        # wees de ContextVar naar de vorige tenant terwijl dezelfde, nog OPEN transactie op
        # databaseniveau nog de aangenomen tenant had -- tot de eerstvolgende commit. Een
        # aanroeper zonder commit in het blok (zoals `get_or_create_lockout_record`) werkte
        # daarna verder met twee verschillende antwoorden op "welke tenant ben ik".
        if is_postgres:
            try:
                await db.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": "" if vorige is None else str(int(vorige))},
                )
            except SQLAlchemyError:
                # De transactie kan al afgebroken zijn (de aanroeper wierp). Dan is de
                # instelling sowieso weg en is er niets te herstellen. Niet onderdrukken
                # zonder spoor: de oorspronkelijke fout is belangrijker dan deze.
                logger.debug(
                    "adopt_tenant: tenantcontext op de transactie niet teruggezet; "
                    "de transactie is waarschijnlijk al afgebroken.",
                    exc_info=True,
                )


async def close_bypass_engine() -> None:
    """Sluit de aparte pool. Idempotent."""
    global _engine, _session_maker

    try:
        if _engine is not None:
            await _engine.dispose()
    finally:
        # In een `finally`: werpt `dispose()`, dan zouden de globals anders naar een engine
        # blijven wijzen die half is afgebroken, en een volgende aanroeper zou die krijgen.
        _engine = None
        _session_maker = None
