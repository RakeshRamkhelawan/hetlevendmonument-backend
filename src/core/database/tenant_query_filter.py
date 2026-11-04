"""
SQLAlchemy 2.0 Auto-Filtering Hook (ASYNC Compatible)
CRITICAL for automatic tenant isolation on ALL queries

Design Principle:
- SQLAlchemy event hook intercepts EVERY query BEFORE execution
- Automatically adds WHERE tenant_id = <current_tenant> to ALL queries
- Developers CANNOT forget tenant filter = ZERO data leak risk
- Impossible to accidentally expose cross-tenant data

Implementation (SQLAlchemy 2.0):
- Use @event.listens_for(Session, "do_orm_execute")
- Extract tenant_id from ContextVar (thread-safe, async-safe)
- Inspect query for models with tenant_id column
- Auto-inject WHERE clause before execution
- Works with: SELECT, UPDATE, DELETE (not INSERT)

Performance:
- Overhead: <5ms per query (ContextVar lookup + filter injection)
- No N+1 query issues

Security:
- Bypass mechanism for system queries (migrations, admin)
- Fail-secure: If tenant_id missing, query returns EMPTY

UPDATED: tenant_id type changed from str to int for Phase 2
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from contextvars import ContextVar
from typing import Literal, Optional, Protocol, cast

from sqlalchemy import Executable, event, literal
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import ORMExecuteState, Session

logger = logging.getLogger(__name__)


class _Table(Protocol):
    name: str


class _TenantEntity(Protocol):
    tenant_id: object
    __name__: str
    __tablename__: str


class _WhereableStatement(Protocol):
    """Protocol for SQLAlchemy DML statements that support tenant filtering."""

    is_select: bool
    is_update: bool
    is_delete: bool
    column_descriptions: Iterable[Mapping[str, object]]
    table: _Table

    def where(self, *criteria: object) -> "_WhereableStatement": ...


# Global bypass flag (ContextVar for async safety)
# WARNING: Use with EXTREME caution - only for system operations
_bypass_tenant_filter: ContextVar[bool] = ContextVar("bypass_tenant_filter", default=False)

# Context variable to force real filtering (for no_bypass tests)
_force_real_filtering: ContextVar[bool] = ContextVar("force_real_filtering", default=False)


# ============================================================================
# CORE AUTO-FILTERING ENGINE (SQLAlchemy 2.0)
# ============================================================================


#: De geregistreerde listener, of None. Nodig omdat `auto_filter_by_tenant` een GENESTE functie
#: is: elke aanroep van `init_tenant_auto_filtering()` maakt een nieuw functieobject, en zonder
#: een verwijzing op moduleniveau is er niets om aan `event.remove()` te geven.
#:
#: Dit is de oorzaak van ADR-036 OP-20. De listener hangt aan de `Session`-KLASSE met
#: `propagate=True`, dus procesbreed: registreert een test hem, dan krijgt ELKE sessie in dat
#: proces een automatisch tenantfilter -- ook een in-memory-SQLite-sessie van een ander
#: testbestand. Fail-secure betekent daar: nul rijen, stil. Symptoom CLOSED 2026-08-01 door de
#: getroffen tests een `TenantFilterBypass` te geven; de oorzaak bleef open en dook op
#: 2026-08-11 op een vierde plek weer op.
#: Een LIJST en geen enkele verwijzing, en dat is bewust. `init_tenant_auto_filtering()` is
#: historisch niet idempotent: `app_lifespan.py` roept hem direct aan terwijl
#: `register_query_guard()` hetzelfde doet achter zijn eigen vlag, dus in een proces waar beide
#: paden lopen hangen er twee listeners. Ik heb geprobeerd dat te veranderen in een vroege
#: terugkeer, en dat brak `test_tenant_query_filter_mocked.py` en `..._fail_secure.py`: die mocken
#: `event` en leunen erop dat `init_...` altijd `listens_for` aanroept. Een lijst laat het bestaande
#: gedrag exact intact en maakt verwijderen alsnog volledig.
_registered_listeners: list[Callable[[ORMExecuteState], None]] = []

#: Een TWEEDE naam voor dezelfde `event`-module, vastgelegd bij import.
#:
#: `tests/unit/test_tenant_query_filter_fail_secure.py` en `..._mocked.py` vervangen het
#: module-attribuut `event` door een mock om de hook te onderscheppen zonder hem te registreren.
#: Zou de boekhouding hieronder datzelfde `event` gebruiken, dan meldt
#: `tenant_auto_filtering_is_active()` "actief" terwijl er niets aan `Session` hangt -- en dat is
#: precies wat er misging: de save/restore in `tests/conftest.py` hield daarna een LATERE, echte
#: registratie in stand omdat hij dacht dat die er al was. Gemeten aan de overgangen: actief werd
#: True in het fail-secure-bestand en kwam nooit meer uit.
#:
#: Patchen van `event` raakt deze naam niet, dus dit blijft de waarheid vertellen.
_sa_event = event


def tenant_auto_filtering_is_active() -> bool:
    """Of er nu minstens een listener DAADWERKELIJK aan `Session` hangt.

    Vraagt het aan SQLAlchemy en gelooft de eigen lijst niet: een test kan `event` hebben gemockt,
    en dan staat er wel iets in de lijst maar hangt er niets.
    """
    return any(
        _sa_event.contains(Session, "do_orm_execute", listener)
        for listener in _registered_listeners
    )


def remove_tenant_auto_filtering() -> None:
    """Haal ELKE geregistreerde tenantfilter-listener weg.

    Bedoeld voor testopstellingen, zodat een test hem niet naar de volgende kan lekken. In de
    applicatie blijft hij staan voor de hele levensduur van het proces.

    Alle listeners en niet alleen de laatste: bleef er een staan, dan lijkt het filter weg terwijl
    het nog werkt -- en dat is erger dan geen verwijdering, want dan zoek je op de verkeerde plek.

    LET OP: dit zet alleen de listener(s) uit. Wie het filter daarna weer aan wil kunnen zetten via
    `register_query_guard()` moet OOK de vlag in `tenant_query_guard` terugzetten -- gebruik
    daarvoor `tenant_query_guard.remove_query_guard()`, die beide doet. Zonder dat blijft het
    filter permanent afwezig, en dat is de gevaarlijke richting: fail-secure wordt dan geen filter.
    """
    while _registered_listeners:
        listener = _registered_listeners.pop()
        if not _sa_event.contains(Session, "do_orm_execute", listener):
            # Nooit echt aangehangen (een test had `event` gemockt tijdens het registreren), of al
            # weg. De eindtoestand is dan precies wat we willen; `remove` zou hier gooien.
            continue
        _sa_event.remove(Session, "do_orm_execute", listener)


def init_tenant_auto_filtering() -> Callable[[ORMExecuteState], None]:
    """
    Initialize SQLAlchemy 2.0 event hooks for automatic tenant filtering

    MUST call during app startup AFTER models are defined:
        from src.core.database.tenant_query_filter import init_tenant_auto_filtering
        init_tenant_auto_filtering()

    This registers a global event listener that intercepts ALL ORM queries.

    Geeft de geregistreerde listener terug zodat een aanroeper hem weer kan opruimen met
    `event.remove(Session, "do_orm_execute", listener)`. Dat is geen luxe: de listener hangt aan de
    `Session`-KLASSE met `propagate=True`, dus wie hem in een test registreert filtert vanaf dat
    moment elke ORM-query in dat proces -- ook die van een ander testbestand met een eigen
    in-memory-sessie. Zonder tenant in de ContextVar levert dat NUL rijen op. Dat is ADR-036 OP-20:
    zes tests vielen om zodra de xdist-sharding ze achter zo'n test plaatste, wat las als flakiness
    maar volledig deterministisch was.

    OP-20 noteerde dat er "geen enkele manier" was om de listener te verwijderen. Dat is gemeten en
    onjuist -- `event.remove` doet het -- maar je hebt de functie zelf nodig en die was een closure
    zonder uitweg. Vandaar deze returnwaarde: een fixture kan nu opruimen zonder in het private
    `_clslevel` van SQLAlchemy te graven. Dezelfde listener wordt OOK toegevoegd aan
    `_registered_listeners`, zodat `remove_tenant_auto_filtering()`/`tenant_auto_filtering_is_active()`
    kunnen opruimen zonder dat de aanroeper zelf de returnwaarde hoeft te bewaren.

    Let op: de functie is NIET idempotent. Twee aanroepen registreren twee listeners.
    """

    @event.listens_for(Session, "do_orm_execute", propagate=True)
    def auto_filter_by_tenant(orm_execute_state: ORMExecuteState) -> None:
        """
        SQLAlchemy 2.0 event hook - Auto-inject tenant_id filter

        Lifecycle:
        1. App makes query: session.execute(select(User))
        2. SQLAlchemy triggers this hook BEFORE database
        3. We inject: WHERE tenant_id = <current_tenant>
        4. Query executes with filter

        Security:
        - If no tenant context -> Returns EMPTY (fail-secure)
        - System queries can bypass via TenantFilterBypass context manager
        - All bypass attempts logged for audit

        Performance:
        - Adds ~2-5ms per query (ContextVar lookup)
        - No additional database round-trips
        - Filter compiled into SQL, not Python
        """

        # Import here to avoid circular dependency
        import os
        import sys

        from src.core.middleware.tenant_context import get_tenant_id

        # Check if this query should bypass tenant filter
        # BUT: If force_real_filtering=True (no_bypass tests), NEVER bypass
        # CRITICAL: Use module lookup for monkeypatch compatibility (closure issue)
        this_module = sys.modules[__name__]
        bypass_var = getattr(this_module, "_bypass_tenant_filter", _bypass_tenant_filter)
        force_var = getattr(this_module, "_force_real_filtering", _force_real_filtering)

        # Also check environment variable (most reliable across async boundaries)
        force_real_filtering_env = os.getenv("FORCE_REAL_TENANT_FILTERING") == "1"

        if force_real_filtering_env:
            logger.debug(
                "[tenant_query_filter] FORCE_REAL=1 active, bypass=%s, force=%s",
                bypass_var.get(),
                force_var.get(),
            )

        if bypass_var.get() and not (force_var.get() or force_real_filtering_env):
            logger.warning(
                "BYPASS: Tenant filter disabled for query (caller must have explicit permission)"
            )
            return

        # Get current tenant from context (returns int | None)
        tenant_id = get_tenant_id()

        # Inspect the statement to find entities with tenant_id
        if hasattr(orm_execute_state, "statement"):
            statement = cast(_WhereableStatement, orm_execute_state.statement)

            # Only filter SELECT/UPDATE/DELETE, not INSERT
            if statement.is_select or statement.is_update or statement.is_delete:
                try:
                    entity_class = None

                    # For SELECT queries: use column_descriptions
                    if statement.is_select and hasattr(statement, "column_descriptions"):
                        for entity in statement.column_descriptions:
                            entity_class = cast(
                                _TenantEntity | None,
                                entity.get("entity") or entity.get("type"),
                            )
                            if entity_class and hasattr(entity_class, "tenant_id"):
                                break

                    # For UPDATE/DELETE queries: get entity from table
                    elif statement.is_update or statement.is_delete:
                        # Get the table being updated/deleted
                        if hasattr(statement, "table"):
                            table = statement.table
                            # Find the mapped class for this table
                            from src.core.database.database import Base

                            for mapper in Base.registry.mappers:
                                # Use persist_selectable for SQLAlchemy 2.0
                                mapped_tbl = mapper.persist_selectable
                                if mapped_tbl is table or (
                                    hasattr(mapped_tbl, "name") and mapped_tbl.name == table.name
                                ):
                                    entity_class = mapper.class_
                                    break

                    # EEN antwoord op "hoort deze entiteit bij een tenant?", voor BEIDE
                    # takken hieronder.
                    #
                    # Hier stonden eerder twee verschillende antwoorden: de tak MET tenant
                    # keek naar `hasattr(entity_class, "tenant_id")` en liet tabellen
                    # zonder die kolom met rust, terwijl de tak ZONDER tenant `WHERE false`
                    # op ALLES zette. Die divergentie was een echt defect: `token_blacklist`
                    # heeft geen `tenant_id`, en `/api/v1/auth/*` draait bij ontwerp zonder
                    # tenantcontext -- dus vond `_is_token_blacklisted` een ingetrokken
                    # token nooit terug en bleven ingetrokken tokens geldig. Gemeten
                    # 2026-08-17: rij aanwezig in de database, ORM zonder tenantcontext
                    # None, met tenantcontext wel. De INSERT slaagde (die tak filtert niet),
                    # alleen de SELECT niet.
                    #
                    # Een entiteit die NIET kon worden herleid telt als tenant-gescheiden.
                    # Dat is bewust fail-secure: onbekend hoort dicht te staan, niet open.
                    tenant_gescheiden = entity_class is None or (
                        hasattr(entity_class, "tenant_id")
                        # `audit_logs` is bewust tenant-overstijgend: de auditketen moet ook
                        # een verzoek zonder geldige tenant kunnen vastleggen en teruglezen.
                        and getattr(entity_class, "__tablename__", "") != "audit_logs"
                    )

                    if not tenant_gescheiden:
                        logger.debug(
                            "Geen tenant-filter voor %s: die tabel is niet tenant-gescheiden",
                            getattr(entity_class, "__name__", "?"),
                        )
                        return

                    # Fail-secure: geen tenantcontext betekent geen gegevens.
                    if not tenant_id:
                        logger.debug("No tenant context - query will return empty (fail-secure)")
                        orm_execute_state.statement = cast(
                            Executable, statement.where(literal(False))
                        )
                        return

                    if entity_class is not None:
                        # Determine correct type for tenant_id comparison
                        try:
                            from sqlalchemy.sql.sqltypes import String as _SAString

                            col = getattr(entity_class, "tenant_id", None)
                            filter_value: int | str = tenant_id
                            if (
                                col is not None
                                and hasattr(col, "type")
                                and isinstance(col.type, _SAString)
                            ):
                                filter_value = str(tenant_id)
                        except Exception:
                            filter_value = tenant_id
                        statement = statement.where(entity_class.tenant_id == filter_value)
                        logger.debug(
                            "Auto-filtered %s by tenant_id=%s",
                            entity_class.__name__,
                            tenant_id,
                        )
                        orm_execute_state.statement = cast(Executable, statement)

                except (AttributeError, InvalidRequestError) as e:
                    logger.warning(
                        "Could not auto-filter query: %s: %s (query may not have column_descriptions)",
                        type(e).__name__,
                        e,
                    )
                    # Fail-secure: block the query rather than leaking cross-tenant data
                    if hasattr(orm_execute_state, "statement"):
                        statement = cast(_WhereableStatement, orm_execute_state.statement)
                        if statement.is_select or statement.is_update or statement.is_delete:
                            orm_execute_state.statement = cast(
                                Executable, statement.where(literal(False))
                            )

                except Exception as e:
                    logger.error(
                        "Error in auto-filter hook: %s: %s", type(e).__name__, e, exc_info=True
                    )
                    # Fail-secure: block the query rather than leaking cross-tenant data
                    if hasattr(orm_execute_state, "statement"):
                        statement = cast(_WhereableStatement, orm_execute_state.statement)
                        if statement.is_select or statement.is_update or statement.is_delete:
                            orm_execute_state.statement = cast(
                                Executable, statement.where(literal(False))
                            )

    # Hier stond `_filtering_initialized = True`: een LOKALE assignment zonder `global`, die dus
    # nooit iets deed. Er bestond geen module-variabele met die naam en niets las hem. Nu leggen we
    # de listener wel echt vast, want zonder verwijzing op moduleniveau is er niets om aan
    # `event.remove()` te geven -- en dat was de oorzaak van ADR-036 OP-20.
    _registered_listeners.append(auto_filter_by_tenant)
    logger.info("Tenant auto-filtering initialized successfully")

    # `event.listens_for` geeft op runtime de functie terug, maar is getypeerd als `None` -- vandaar
    # de cast. Hier stond even een expliciete `event.listen`-aanroep om die cast te vermijden; dat
    # brak zeven tests in twee bestanden die de hook opvangen door `listens_for` te patchen
    # (`test_tenant_query_filter_mocked.py`, `test_tenant_query_filter_fail_secure.py`). Het
    # registratiemechanisme is dus waarneembaar gedrag en geen implementatiedetail.
    return cast(Callable[[ORMExecuteState], None], auto_filter_by_tenant)


# ============================================================================
# BYPASS MECHANISM (Use with EXTREME caution)
# ============================================================================


class TenantFilterBypass:
    """
    Context manager to bypass tenant filtering

    DANGEROUS - Use ONLY for:
    - Database migrations (Alembic)
    - System admin operations
    - Health checks / monitoring
    - Test fixtures
    - Endpoints waar per definitie nog GEEN tenant bestaat (zie hieronder)

    Hier stond "NEVER use in user-facing endpoints". Dat is nooit waar geweest: `router_login.py`,
    `router_registration.py` en `auth_service.authenticate_user` doen het al sinds jaar en dag, met
    de reden erbij ("we don't have tenant context yet"). Die absolute regel was actief schadelijk --
    hij las als een verbod, terwijl het WEGLATEN van de bypass op zulke endpoints het echte defect
    is: alles onder `/api/v1/auth` valt buiten de tenant-middleware, dus zonder bypass geeft de
    fail-secure filter daar `WHERE false` en wordt er nooit een gebruiker gevonden. Dat gebeurde
    (ADR-036 OP-131): wachtwoordherstel was stil kapot.

    De echte regel is smaller en toetsbaar. Een bypass op een publiek endpoint mag alleen als:
    1. er op dat pad per definitie geen tenantcontext KAN zijn (pre-authenticatie), EN
    2. de lookup gaat op een waarde die de aanroeper niet vrij kan kiezen -- een geverifieerde JWT,
       een token uit Redis -- of op een globaal uniek gegeven zoals e-mail, EN
    3. de reden in commentaar op de aanroepplek staat.

    Een bypass om "even alle tenants te zien" in een endpoint dat WEL een tenant heeft, blijft
    verboden. Dat is het datalek waar deze klasse tegen beschermt.

    Usage:
        with TenantFilterBypass():
            # This query sees ALL tenants
            all_users = await session.execute(select(User))
            users = all_users.scalars().all()

    All bypass attempts are logged for security audit.
    """

    def __init__(self) -> None:
        self._previous_value: bool | None = None

    def __enter__(self) -> "TenantFilterBypass":
        logger.warning("BYPASS: Tenant filter DISABLED - This query will access ALL tenant data")
        # Store previous value and set bypass flag
        self._previous_value = _bypass_tenant_filter.get()
        _bypass_tenant_filter.set(True)
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> Literal[False]:
        # Restore previous bypass state
        if self._previous_value is not None:
            _bypass_tenant_filter.set(self._previous_value)
        else:
            _bypass_tenant_filter.set(False)

        logger.info("Tenant filter bypass restored to: %s", self._previous_value)
        return False  # Don't suppress exceptions


# Only export the safe public API -- bypass requires the TenantFilterBypass context manager
__all__ = [
    "init_tenant_auto_filtering",
    "remove_tenant_auto_filtering",
    "tenant_auto_filtering_is_active",
    "TenantFilterBypass",
]
