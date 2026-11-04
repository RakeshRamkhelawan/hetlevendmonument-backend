"""HR-leestool voor de ALS-piloot: `query_hr_database` (ADR-036 D10 stap 3, BE-AGT-044).

De eerste van de 27 gedeclareerde tools die daadwerkelijk resolvet. Gemodelleerd naar
`business_registry.py`: een tenant-gescoped brug tussen een ToolBroker-payload en de database,
onafhankelijk van de Council- en Copilot-laag.

**Wat deze tools WEL en NIET kunnen, en waarom.**

`query_hr_database` telt de bezetting per functie uit de RBAC-tabellen: wie er is en welke
rollen die heeft.

`analyze_skill_gap` (toegevoegd 2026-08-15) doet de eigenlijke kloofanalyse en leest daarvoor
`skills`, `role_required_skills` en `employee_skills` -- de drie tabellen die met OP-26 zijn
toegevoegd. **Let op: dit lost het gegevensprobleem NIET op.** De tabellen bestaan, maar ze
zijn leeg tot een tenant zijn vaardigheden en beoordelingen aanlevert; waar die data vandaan
komt (import, koppeling met een HR-systeem, onderhoud in de applicatie) is nog steeds een
productbeslissing. Een lege tabel geeft hier een eerlijke uitkomst: nul beoordeelden en dus
een volledige kloof, niet een verzonnen getal.

Een eerdere versie van deze tekst stelde dat `skills`, `trainings` en `competencies` niet
bestaan. Dat gold tot 2026-08-15; `trainings` bestaat nog steeds niet, en het toewijzen van
een cursus is bewust buiten deze knip gehouden (ADR-036 D10).

**Waarom tellingen en geen individuele rijen.** Alles wat een tool teruggeeft gaat de event bus
op (`service.py::_publish_tool_event`) en het leersubsysteem persisteert dat
(`events/handlers/learning_event_handler._record_tool_event` schrijft `observation_data`
inclusief het volledige `result`). Rij-data zou daarmee persoonsgegevens in een leeropslag
zetten -- dezelfde klasse als de audit-keten-bevinding uit de Gate 2-review van BE-AGT-042.
Zie OP-27. Voor een gap-analyse zijn aantallen per rol bovendien bruikbaarder dan een
namenlijst.

**Waarom de tenant een expliciet argument is en niet uit de payload komt.** De payload is de
`json.loads` van een `TOOL_CALL`-directive en dus door het model beschreven. Zolang de tenant
daaruit werd gelezen, hing de isolatie eraan dat elke aanroeper een `context` meegeeft --
en die parameter is optioneel. Geen live aanroeper deed dat verkeerd, maar een invariant die
op gewoonte rust is geen invariant. De broker resolvet de tenant nu uit de context en geeft
hem als los argument door; `execute_hr_tool` accepteert hem niet meer uit de payload.
(Gate 2-review BE-AGT-044, HIGH-4.)

**Tenantfilter: dubbel, en zonder bypass.** De query filtert expliciet op `Role.tenant_id` EN
`User.tenant_id` -- de koppeltabel `user_roles` heeft zelf geen tenantkolom, dus een vervuilde
associatierij zou anders vreemde gebruikers meetellen. Daarnaast wordt de tenant-ContextVar
voor de duur van de query gezet en daarna hersteld, zodat de ADR-004-hook `do_orm_execute`
gewoon aan blijft staan en als tweede laag meefiltert. Eerder gebruikte deze module
`TenantFilterBypass`; dat is teruggedraaid omdat het (a) de hook uitschakelt in een venster
waar ook sessies worden opgezet, (b) bij elke routineuze leesactie een WARNING "tenant filter
DISABLED" produceerde en daarmee een detectiesignaal tot ruis maakte. Dat de expliciete filter
niet stilzwijgend kan verdwijnen wordt bewaakt door een test op de gecompileerde SQL, niet
door de omgevingsfilter uit te zetten. (Gate 2-review BE-AGT-044, MEDIUM-4.)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from sqlalchemy import Integer, Select, and_, case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tool_broker.exceptions import ToolExecutionException

logger = logging.getLogger(__name__)

TOOL_NAME = "query_hr_database"

#: De tweede HR-tool (ADR-036 OP-26): de daadwerkelijke vaardighedenkloof per functie.
#: Bewust een EIGEN tool en geen extra `view`-parameter op `query_hr_database`: die tool heeft
#: een eigen contract, een eigen risiconiveau en een eigen regel in `PAYLOAD_POLICY`, en een
#: schakelaar die het antwoordformaat omgooit maakt al die drie meerduidig.
GAP_TOOL_NAME = "analyze_skill_gap"

#: De eerste SCHRIJFtool van deze registry (2026-09-21). Tot vandaag deed hij alleen lezen.
#:
#: **Waarom hij bestaat.** De acceptatiemeting (`scripts/acceptance_thread.py`) komt tot stap 2
#: van 7, en stap 6 vraagt "de schrijfactie bestaat en heeft een risicoklasse". Een keten die
#: alleen kan lezen levert nooit een besluit op; dit is de handeling waar een gap-analyse toe
#: leidt: de aanbevolen training aan een medewerker toewijzen.
#:
#: **Waarom hij HIGH is en niet MEDIUM.** De leestools hiernaast zijn MEDIUM omdat ze niets
#: muteren. Deze wel, en op personeelsdata (EU AI Act bijlage III punt 4). Alleen HIGH opent de
#: HITL-poort (zie de toelichting in `src/core/config/tool_risk_levels.yml`), en een agent die
#: ongevraagd een training aan een mens toewijst is precies waarvoor die poort bestaat.
SCHEDULE_TOOL_NAME = "schedule_training"

#: Het VOCABULAIRE van de schrijftool. Dezelfde drie namen staan in
#: `redaction.PAYLOAD_POLICY["schedule_training"].params`, en
#: `tests/architecture/test_tool_policy_matches_the_tools.py` toetst dat die twee niet uit elkaar
#: lopen. Een sleutel die hier niet in staat wordt GEWEIGERD -- zie `_schedule_training`.
_SCHEDULE_FIELDS = frozenset({"user_email", "training_name", "status"})

#: Bovengrenzen, gelijk aan de KOLOMBREEDTES: `User.email` is String(255)
#: (`rbac_models.py:302`), `Training.name` String(150) (`hr_training_models.py:77`) en
#: `EmployeeTraining.status` String(20) (`:124`). Langer kan per definitie niets matchen; de grens
#: voorkomt dat zo'n waarde wel volledig naar de database en het logbestand gaat.
#:
#: Hier stond 320 voor `user_email` met "de RFC-grens" als toelichting. Dat was onjuist en een
#: Gate 2-reviewer heeft het nagemeten: de kolom is 255, `String(320)` komt in heel `src/` alleen
#: in die twee comments van mij voor, en het venster 256-320 passeerde dus ongehinderd -- precies
#: wat deze grens moest tegenhouden. Een grens die niet de kolom is, is geen grens.
_MAX_VELDLENGTE = {"user_email": 255, "training_name": 150, "status": 20}

#: De ENIGE status die deze tool zet. De tabel kent er drie; zie de docstring van
#: `_schedule_training` voor waarom inplannen en afronding-vastleggen geen dezelfde handeling zijn.
TOEGESTANE_SCHEDULE_STATUS = "assigned"




def _onbekende_velden(payload: dict[str, object], vocabulaire: frozenset[str]) -> list[str]:
    """Sleutels die de tool niet kent -- AFGELEID, niet opgesomd.

    **Waarom dit geen eigen lijst is.** De eerste versie had een eigen
    `_BROKER_INJECTED_FIELDS = {"tenant_id", "_hitl_ticket_ref"}`, en die miste `user_id`.
    `service.py:190-195` injecteert BEIDE sleutels uit de executiecontext en filtert er daarna
    alleen `tenant_id` weer uit, dus op het goedkeuringspad kwam `user_id` bij de registry aan.
    Gemeten in Gate 2 (2026-09-21): de tool weigerde met "onbekende velden: user_id" NADAT
    `redeem_approval` het ticket al op `consumed` had gezet -- de menselijke goedkeuring was
    verbruikt en niet herhaalbaar. Er was geen enkel pad waarop deze tool kon slagen.

    Erger dan de fout: mijn test somde dezelfde twee namen op als de code, dus twee kopieen van
    dezelfde handmatige lijst konden elkaar niet controleren.

    `BROKER_INJECTED_KEYS` is de bestaande bron (`redaction.py:709`) en wordt door een AST-guard
    gelijk gehouden aan de injectieplekken in `service.py`
    (`tests/unit/tool_broker/test_hitl_approval_is_bounded.py`). De `_`-prefix is dezelfde
    conventie die `approval_binding` gebruikt voor servermetadata.
    """
    from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

    return sorted(
        sleutel
        for sleutel in payload
        if not sleutel.startswith("_")
        and sleutel not in vocabulaire
        and sleutel not in BROKER_INJECTED_KEYS
    )


def _een_logregel(tekst: str, maximum: int = 200) -> str:
    """Maak van modeltekst EEN logregel: regeleinden weg, afgekapt.

    Zonder dit maakt een `\\n` in een door het model gekozen waarde er twee logregels van, en de
    tweede kan alles beweren wat op een echt logrecord lijkt (CWE-117). Gemeten in Gate 2 op
    2026-09-21: een trainingsnaam met een regeleinde leverde een record op waarvan de tweede
    regel een succes claimde dat niet had plaatsgevonden.
    """
    plat = " ".join(tekst.replace("\r", " ").replace("\n", " ").split())
    return plat if len(plat) <= maximum else plat[:maximum] + "..."

# Paginering conform .claude/rules/backend-patterns.md par. 5.
DEFAULT_LIMIT = 50
MAX_LIMIT = 1000
MAX_OFFSET = 100_000

# `Role.name` is String(50); een langer filter kan per definitie niets matchen.
MAX_ROLE_NAME_LENGTH = 50

# Filters uit het contract waarvoor geen data bestaat. Expliciet weigeren en nooit stil
# negeren: een genegeerd filter levert meer terug dan gevraagd terwijl de aanroeper denkt dat
# er gefilterd is, en een adviserende skill baseert daar zijn advies op.
_UNSUPPORTED_FILTERS: dict[str, str] = {
    "department": (
        "afdelingen bestaan niet in het datamodel van dit platform, dus er kan niet op "
        "gefilterd worden (ADR-036 OP-26)"
    ),
    "employee_id": (
        "deze tool geeft tellingen per rol terug en geen individuele medewerkers, dus "
        "filteren op een enkele persoon heeft geen betekenis (ADR-036 OP-27)"
    ),
}


@asynccontextmanager
async def _default_session_factory() -> AsyncGenerator[AsyncSession, None]:
    """Standaard sessie via de centrale DB-manager, net als de business-registry."""
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        yield session


class _InvalidArgument(Exception):
    """Interne signalering van een onbruikbaar argument; wordt een nette foutrespons."""


class HRToolRegistry:
    """Voert de HR-tools uit, alle per tenant.

    Twee leestools (rolbezetting, vaardighedenkloof) en sinds 2026-09-21 een SCHRIJFtool
    (`schedule_training`). Dat onderscheid is niet cosmetisch: de schrijftool heeft een eigen
    risiconiveau, gaat langs de HITL-poort, en zijn payloadvalidatie is strenger omdat een
    verkeerd veld hier een rij in de database oplevert in plaats van een leeg antwoord.
    """

    _TOOL_NAMES = {TOOL_NAME, GAP_TOOL_NAME, SCHEDULE_TOOL_NAME}

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self._session_factory = session_factory or _default_session_factory

    @classmethod
    def known_tool_names(cls) -> set[str]:
        """De toolnamen die deze registry afhandelt."""
        return set(cls._TOOL_NAMES)

    @staticmethod
    def _read_bounded_int(payload: dict[str, Any], field: str, default: int, maximum: int) -> int:  # TODO(TYPE): replace Any with concrete type
        """Lees een pagineringsgetal, of gooi `_InvalidArgument` met een leesbare reden.

        Een onleesbare waarde wordt NIET stil vervangen door de default. Deze module weigert
        `department` en een niet-string `role` juist expliciet omdat stil corrigeren de
        aanroeper laat denken dat zijn invoer is opgevolgd; dan mag `limit="abc"` niet
        stilzwijgend 50 worden (Gate 2-review BE-AGT-044, LOW-A).

        Boven het maximum wordt wel afgekapt -- dat is geen stille correctie, want de
        toegepaste waarde komt als `applied_limit`/`applied_offset` terug in de respons.
        """
        # Als `object` gelezen en daarna versmald: `payload` is dict[str, Any], en zonder
        # deze annotatie draagt de waarde zijn Any-heid door tot in het return-type.
        raw: object = payload.get(field, default)
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise _InvalidArgument(f"'{field}' moet een geheel getal zijn")
        if raw < 0:
            raise _InvalidArgument(f"'{field}' mag niet negatief zijn")
        bounded: int = min(raw, maximum)
        return max(1, bounded) if field == "limit" else bounded

    async def execute_hr_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        *,
        tenant_id: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Voer een HR-tool uit. Retourneert altijd een dict, gooit alleen bij onbekend."""
        if tool_name not in self._TOOL_NAMES:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail=f"HR tool '{tool_name}' is not implemented",
            )

        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id must be a positive integer from the execution context",
            )

        if tool_name == SCHEDULE_TOOL_NAME:
            # VOOR de filtercontroles hieronder, en dat is geen optimalisatie. Die controles
            # gaan over `role`, `department` en `employee_id` -- de zoekvelden van de twee
            # LEESTOOLS. Zou de schrijftool er ook langs moeten, dan horen die drie namen bij
            # zijn vocabulaire (zie `ToolPolicy.params`: ook een expliciet GEWEIGERDE naam
            # hoort erbij), terwijl deze tool er niets mee doet. Dan zou
            # `PAYLOAD_POLICY["schedule_training"]` drie velden moeten noemen die de tool niet
            # kent, en dat is precies de fantoomparameter die
            # `tests/architecture/test_tool_policy_matches_the_tools.py` moet vangen.
            #
            # GEEN `except _InvalidArgument` hier: `_schedule_training` roept
            # `_read_bounded_int` niet aan en gooit die uitzondering nergens. Die tak stond er
            # wel en was onbereikbaar -- een vangnet dat een validatiecontract suggereert dat de
            # methode niet heeft. (Gate 2, 2026-09-21, LOW-1 van beide reviewers.)
            return await self._schedule_training(tenant_id, payload)

        for field, reason in _UNSUPPORTED_FILTERS.items():
            if payload.get(field) is not None:
                return {
                    "success": False,
                    "error": f"filter '{field}' wordt niet ondersteund: {reason}",
                }

        role_filter = payload.get("role")
        if role_filter is not None and (
            not isinstance(role_filter, str) or len(role_filter) > MAX_ROLE_NAME_LENGTH
        ):
            # Een niet-string filter zou via str() een repr opleveren die nergens op matcht.
            # De tool zou dan een lege lijst teruggeven en de skill zou concluderen dat die rol
            # niet bestaat -- dezelfde stille onwaarheid die hierboven voor `department` juist
            # wordt geweigerd. (Gate 2-review BE-AGT-044, MEDIUM-3.)
            return {
                "success": False,
                "error": (
                    f"filter 'role' moet een string van maximaal {MAX_ROLE_NAME_LENGTH} tekens zijn"
                ),
            }

        try:
            if tool_name == GAP_TOOL_NAME:
                return await self._skill_gap(tenant_id, payload, role_filter)
            return await self._role_occupancy(tenant_id, payload, role_filter)
        except _InvalidArgument as exc:
            return {"success": False, "error": f"ongeldige parameter: {exc}"}

    def _build_statement(
        self, tenant_id: int, limit: int, offset: int, role_filter: str | None
    ) -> Select[Any]:  # TODO(TYPE): replace Any with concrete type
        """De query. Apart zodat een test de gecompileerde SQL kan inspecteren."""
        from src.core.models.rbac_models import Role, User, user_roles

        statement = (
            select(
                Role.name,
                func.count(func.distinct(User.id)).label("user_count"),
                func.count(func.distinct(case((User.is_active, User.id)))).label("active_count"),
            )
            .join(user_roles, user_roles.c.role_id == Role.id)
            .join(User, User.id == user_roles.c.user_id)
            # De expliciete tenantgrens, op BEIDE tabellen: `user_roles` heeft zelf geen
            # tenantkolom, dus een vervuilde associatierij zou anders gebruikers van een
            # andere tenant meetellen.
            .where(Role.tenant_id == tenant_id, User.tenant_id == tenant_id)
            # Wie op grond van AVG art. 17 is gewist, telt niet meer mee. `dsar_service`
            # implementeert die wissing als soft delete met een respijtperiode; zonder deze
            # regel zou een ex-medewerker die om verwijdering vroeg de telling blijven
            # ophogen, en dat getal belandt in de leeropslag.
            .where(User.deleted_at.is_(None))
            .group_by(Role.name)
            .order_by(Role.name)
            .offset(offset)
            # Een extra rij ophalen om `truncated` te bepalen zonder tweede count-query.
            .limit(limit + 1)
        )

        if role_filter is not None:
            statement = statement.where(Role.name == role_filter)

        return statement

    async def _role_occupancy(
        self, tenant_id: int, payload: dict[str, Any], role_filter: str | None  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Aantal gebruikers per rol binnen deze tenant."""
        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

        limit = self._read_bounded_int(payload, "limit", DEFAULT_LIMIT, MAX_LIMIT)
        offset = self._read_bounded_int(payload, "offset", 0, MAX_OFFSET)
        statement = self._build_statement(tenant_id, limit, offset, role_filter)

        # De ADR-004-hook blijft aan en filtert als tweede laag mee. Bewaren en herstellen,
        # nooit hard op None zetten: dat lekte in BE-AGT-042 terug naar de aanroeper.
        previous_tenant_id = get_tenant_id()
        set_tenant_id(tenant_id)
        try:
            async with self._session_factory() as session:
                result = await session.execute(statement)
                rows = result.all()
        except SQLAlchemyError as exc:
            # Geen exceptietekst teruggeven: SQLAlchemy's StatementError plakt de SQL EN de
            # gebonden parameters aan zijn `str()`. Die string zou in de LLM-context, op de
            # event bus, in de leeropslag en in de auditketen belanden.
            # (Gate 2-review BE-AGT-044, HIGH-3.)
            logger.error(
                "query_hr_database failed for tenant %s: %s: %s",
                tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {"success": False, "error": "HR-query mislukt door een interne fout"}
        finally:
            set_tenant_id(previous_tenant_id)

        truncated = len(rows) > limit
        visible = rows[:limit]

        return {
            "success": True,
            "roles": [
                {
                    "role": row[0],
                    "user_count": int(row[1] or 0),
                    "active_count": int(row[2] or 0),
                }
                for row in visible
            ],
            "role_count": len(visible),
            "truncated": truncated,
            "applied_limit": limit,
            "applied_offset": offset,
        }

    def _build_gap_statement(
        self, tenant_id: int, limit: int, offset: int, role_filter: str | None
    ) -> Select[tuple[str, str, int, int, int, int]]:
        """De kloofquery. Apart zodat een test de gecompileerde SQL kan inspecteren.

        Per (functie, gevraagde vaardigheid) drie tellingen: hoeveel mensen die functie
        bekleden, hoeveel daarvan het gevraagde niveau halen, en hoeveel er nooit beoordeeld
        zijn. Dat laatste staat er los in en telt NIET als "haalt het niet": niet gemeten is
        iets anders dan niet kunnen, en een adviserende skill die dat verschil niet ziet stuurt
        mensen naar een training die ze misschien niet nodig hebben.

        De tenantgrens staat op ELKE tabel afzonderlijk in de join-conditie, niet alleen in de
        WHERE. `user_roles` heeft geen tenantkolom, dus een vervuilde associatierij zou anders
        gebruikers van een andere tenant meetellen -- dezelfde reden als bij `_build_statement`.
        """
        from src.core.models.hr_skills_models import EmployeeSkill, RoleRequiredSkill, Skill
        from src.core.models.rbac_models import Role, User, user_roles

        holders = func.count(func.distinct(User.id))
        meeting = func.count(
            func.distinct(
                case((EmployeeSkill.level >= RoleRequiredSkill.required_level, User.id))
            )
        )
        unassessed = func.count(func.distinct(case((EmployeeSkill.id.is_(None), User.id))))

        statement = (
            select(
                Role.name.label("role"),
                Skill.name.label("skill"),
                RoleRequiredSkill.required_level.cast(Integer).label("required_level"),
                holders.label("holders"),
                meeting.label("meeting"),
                unassessed.label("unassessed"),
            )
            .select_from(RoleRequiredSkill)
            .join(
                Role,
                and_(Role.id == RoleRequiredSkill.role_id, Role.tenant_id == tenant_id),
            )
            .join(
                Skill,
                and_(Skill.id == RoleRequiredSkill.skill_id, Skill.tenant_id == tenant_id),
            )
            # Buitenwaartse joins: een functie waar niemand in zit is een geldige uitkomst
            # (kloof = de hele bezetting ontbreekt), en die mag niet uit het antwoord vallen.
            .outerjoin(user_roles, user_roles.c.role_id == Role.id)
            .outerjoin(
                User,
                and_(
                    User.id == user_roles.c.user_id,
                    User.tenant_id == tenant_id,
                    # Wie op grond van AVG art. 17 is gewist telt niet mee -- zelfde regel als
                    # in `_build_statement`, anders houdt een ex-medewerker een kloof open.
                    User.deleted_at.is_(None),
                ),
            )
            .outerjoin(
                EmployeeSkill,
                and_(
                    EmployeeSkill.user_id == User.id,
                    EmployeeSkill.skill_id == Skill.id,
                    EmployeeSkill.tenant_id == tenant_id,
                ),
            )
            .where(RoleRequiredSkill.tenant_id == tenant_id)
            .group_by(Role.name, Skill.name, RoleRequiredSkill.required_level)
            .order_by(Role.name, Skill.name)
            .offset(offset)
            # Een extra rij om `truncated` te bepalen zonder tweede count-query.
            .limit(limit + 1)
        )

        if role_filter is not None:
            statement = statement.where(Role.name == role_filter)

        return statement

    async def _skill_gap(
        self,
        tenant_id: int,
        payload: dict[str, object],
        role_filter: str | None,
    ) -> dict[str, object]:
        """De vaardighedenkloof per functie, geaggregeerd."""
        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

        limit = self._read_bounded_int(payload, "limit", DEFAULT_LIMIT, MAX_LIMIT)
        offset = self._read_bounded_int(payload, "offset", 0, MAX_OFFSET)
        statement = self._build_gap_statement(tenant_id, limit, offset, role_filter)

        previous_tenant_id = get_tenant_id()
        set_tenant_id(tenant_id)
        try:
            async with self._session_factory() as session:
                result = await session.execute(statement)
                rows = result.all()
        except SQLAlchemyError as exc:
            # Geen exceptietekst teruggeven: die plakt de SQL en de gebonden parameters aan
            # zijn `str()`, en dat beland in de LLM-context, op de event bus en in de
            # leeropslag. Zelfde afweging als bij `_role_occupancy`.
            logger.error(
                "analyze_skill_gap failed for tenant %s: %s: %s",
                tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {"success": False, "error": "HR-query mislukt door een interne fout"}
        finally:
            set_tenant_id(previous_tenant_id)

        truncated = len(rows) > limit
        visible = rows[:limit]

        gaps = []
        for row in visible:
            holders = int(row.holders or 0)
            meeting = int(row.meeting or 0)
            gaps.append(
                {
                    "role": row.role,
                    "skill": row.skill,
                    "required_level": int(row.required_level or 0),
                    "holders": holders,
                    "meeting_requirement": meeting,
                    # De drie categorieen sluiten elkaar uit en tellen op tot `holders`:
                    # haalt het, haalt het niet, en nooit beoordeeld. Wie niet beoordeeld is
                    # telt NIET als "haalt het niet" -- niet gemeten is iets anders dan niet
                    # kunnen, en een skill die dat verschil niet ziet stuurt mensen naar een
                    # training die ze misschien niet nodig hebben.
                    "below_requirement": holders - meeting - int(row.unassessed or 0),
                    "unassessed": int(row.unassessed or 0),
                }
            )

        return {
            "success": True,
            "gaps": gaps,
            "gap_count": len(gaps),
            "truncated": truncated,
            "applied_limit": limit,
            "applied_offset": offset,
        }

    async def _schedule_training(
        self,
        tenant_id: int,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """Wijs een bestaande training toe aan een bestaande medewerker van DEZE tenant.

        **`dict[str, object]` en niet `dict[str, Any]`.** Deze methode doet alleen `.get()` op de
        payload en versmalt elke waarde zelf met `isinstance`, dus `Any` voegt hier geen
        informatie toe en duwt wel de Any-ratel (`scripts/check_any_gate.py`) omhoog -- die is
        blokkerend in CI en telt ook een geboekte `# TODO(TYPE)`-regel mee.

        **Wat deze tool met opzet NIET doet.** Hij maakt geen training aan en geen medewerker.
        `upsert_employee_trainings` zoekt beide op binnen de tenant en meldt per rij een fout als
        een van de twee niet bestaat. Zou de tool ze aanmaken, dan kon een agent met een typefout
        een nieuwe "training" in de catalogus zetten -- en die catalogus is bedrijfsdata, geen
        bijproduct van een agentbesluit.

        **Hij zet ALLEEN `assigned`, en dat is nauwer dan de tabel toestaat.**
        `EMPLOYEE_TRAINING_STATUSES` kent ook `in_progress` en `completed`. Vastleggen dat iemand
        een training heeft AFGEROND is een ander besluit dan hem inplannen: het is een bewering
        over de werkelijkheid waarvoor deze tool geen bewijs heeft, hij is via een tweede aanroep
        weer uit te wissen (`EmployeeTraining` houdt geen historie), en het gaat over Annex III
        punt 4-data. Een HITL-goedkeuring op een ticket dat "schedule_training" heet is daar geen
        verdediging tegen -- de goedkeurder leest de naam, niet de statuswaarde. Afronding
        vastleggen hoort een eigen tool met een eigen risicoregel. (Gate 2, 2026-09-21.)

        **Elke sleutel buiten het vocabulaire wordt GEWEIGERD, niet genegeerd.** Dezelfde regel
        als `_UNSUPPORTED_FILTERS` voor de leestools, en hier zwaarder: de oude evaluatieset
        stuurde letterlijk `{"training": ..., "participants": 3}`. Stil negeren levert EEN
        toegewezen rij op terwijl het model rapporteert dat er drie mensen zijn ingeschreven --
        bij een leestool een te ruim antwoord, hier een besluit dat niemand nam.

        **Geen enkele payloadwaarde komt terug in het antwoord.** Het resultaat van een tool
        wordt door de broker gedigest voor de bewarende sinks (`service.py`, `safe_digest_result`
        / `safe_value_digest`), dus dit is de TWEEDE laag en niet de enige -- die nuance stond er
        eerst onjuist in. De reden om het hier ook te doen: via `act()` komt het resultaat ook in
        de LLM-context terug, en dat pad is niet gedigest.

        **Een foutmelding citeert nooit iets uit de payload.** `upsert_employee_trainings` zet de
        ontvangen naam wel in zijn melding -- terecht, want daar komt hij uit een bestand dat een
        mens heeft geupload. Hier komt hij uit een `TOOL_CALL`-directive, dus uit het model.
        """
        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id
        from src.core.repositories.hr_import_types import EmployeeTrainingImportRow
        from src.core.repositories.hr_trainings_repository import HRTrainingsRepository

        onbekend = _onbekende_velden(payload, _SCHEDULE_FIELDS)
        if onbekend:
            # De namen mogen leesbaar terug: dat zijn SLEUTELS, afgezet tegen een vocabulaire
            # uit onze eigen code. De WAARDEN blijven buiten de melding.
            return {
                "success": False,
                "error": (
                    f"onbekende velden: {', '.join(onbekend)}. Deze tool kent alleen "
                    f"{', '.join(sorted(_SCHEDULE_FIELDS))}"
                ),
            }

        velden: dict[str, object] = {
            "user_email": payload.get("user_email"),
            "training_name": payload.get("training_name"),
            "status": payload.get("status", TOEGESTANE_SCHEDULE_STATUS),
        }
        for veld, waarde in velden.items():
            if not isinstance(waarde, str) or not waarde.strip():
                return {"success": False, "error": f"'{veld}' moet een niet-lege tekst zijn"}
            if len(waarde) > _MAX_VELDLENGTE[veld]:
                # Langer kan per definitie niets matchen (`User.email` is String(320),
                # `Training.name` String(150)), maar zonder grens gaat de hele waarde wel als
                # gebonden parameter naar de database en via de melding naar het logbestand.
                return {
                    "success": False,
                    "error": f"'{veld}' mag maximaal {_MAX_VELDLENGTE[veld]} tekens zijn",
                }

        if str(velden["status"]).strip() != TOEGESTANE_SCHEDULE_STATUS:
            # De toegestane waarde staat WEL in de melding: een constante uit onze eigen code,
            # geen echo van wat het model stuurde.
            return {
                "success": False,
                "error": (
                    f"'status' kan bij deze tool alleen '{TOEGESTANE_SCHEDULE_STATUS}' zijn; "
                    "voortgang of afronding vastleggen is geen inplanning en vraagt een eigen "
                    "tool"
                ),
            }

        rij = EmployeeTrainingImportRow(
            user_email=str(velden["user_email"]).strip(),
            training_name=str(velden["training_name"]).strip(),
            status=TOEGESTANE_SCHEDULE_STATUS,
        )

        # Zelfde bewaren-en-herstellen als bij de leestools, en hier zwaarder van belang: het
        # `begin`-event op de engine leest deze ContextVar en zet daarmee `app.current_tenant`
        # voor Row Level Security. De transactie begint AL in de sessiefabriek (`SELECT 1`), dus
        # zetten moet VOOR het betreden van de `async with` -- erbinnen is te laat.
        previous_tenant_id = get_tenant_id()
        set_tenant_id(tenant_id)
        try:
            async with self._session_factory() as session:
                uitkomst = await HRTrainingsRepository(session).upsert_employee_trainings(
                    tenant_id, [rij]
                )
                if uitkomst.row_errors:
                    # Niets geschreven dat mag blijven staan. De standaardfabriek commit bij het
                    # verlaten van het blok, dus een rij die er per ongeluk toch in staat zou
                    # meeliften op een aanroep die als mislukt wordt gerapporteerd.
                    await session.rollback()
                else:
                    # Expliciet, en niet vertrouwen op de fabriek: `db_manager.get_session()`
                    # commit bij het verlaten van het blok, maar een ingespoten fabriek (tests,
                    # en elke toekomstige aanroeper) hoeft dat niet te doen. Een schrijftool die
                    # afhangt van het gedrag van zijn fabriek schrijft soms niets en meldt succes.
                    await session.commit()
        except SQLAlchemyError as exc:
            # Geen exceptietekst in het antwoord: `StatementError.__str__` plakt de SQL en de
            # gebonden parameters -- hier het e-mailadres -- aan de melding. Getoetst door
            # `test_a_database_failure_leaks_neither_the_email_nor_the_sql`.
            # GEEN `exc` in de boodschap, anders dan bij de leestools hierboven. Gemeten in
            # Gate 2 (2026-09-21) met een echte `OperationalError`: `str(exc)` bevat de SQL EN
            # de gebonden parameters, dus het e-mailadres stond leesbaar in het logbestand --
            # de vierde sink, die de redactielaag niet dekt en die mijn eigen toelichting drie
            # regels hierboven onwaar maakte. Het TYPE blijft (dat onderscheidt een timeout van
            # een constraint), en `exc_info=True` zet de volledige traceback in het
            # traceback-veld in plaats van in de boodschap.
            logger.error(
                "schedule_training mislukt voor tenant %s: %s",
                tenant_id,
                type(exc).__name__,
                exc_info=True,
            )
            raise ToolExecutionException(
                tool_name=SCHEDULE_TOOL_NAME,
                error_detail="de toewijzing kon niet worden opgeslagen",
            ) from exc
        finally:
            set_tenant_id(previous_tenant_id)

        if uitkomst.row_errors:
            # GEEN succes. Een agent die hier `success: True` leest, rapporteert een toewijzing
            # die niet bestaat -- precies de faalvorm die ADR-036 paragraaf 1 beschrijft.
            #
            # De reden gaat naar het logbestand met de repository-melding erbij, op EEN regel en
            # afgekapt. Die melding citeert de ontvangen trainingsnaam, en dat is modeltekst: een
            # regeleinde erin maakt er twee logregels van, waarvan de tweede alles kan beweren
            # (log forging, CWE-117 -- gemeten in Gate 2 op 2026-09-21, met een tweede regel die
            # een succes claimde dat niet had plaatsgevonden). Het antwoord noemt alleen de
            # oorzaak.
            logger.warning(
                "schedule_training niet uitgevoerd voor tenant %s: %s",
                tenant_id,
                _een_logregel("; ".join(fout.message for fout in uitkomst.row_errors)),
            )
            return {
                "success": False,
                "error": (
                    "de toewijzing is niet uitgevoerd: de medewerker of de training bestaat "
                    "niet binnen deze tenant"
                ),
            }

        # De trainingsnaam heeft op dit punt wel een rij in de catalogus gevonden, maar de lookup
        # is hoofdletter-ongevoelig (`func.lower(Training.name)`), dus wat hier terug zou komen is
        # de SPELLING van het model en niet de catalogusnaam. Dat verschil is klein en het is er
        # wel; de aanroeper kent zijn eigen payload en de tellingen zijn wat hij niet weet.
        return {
            "success": True,
            "assigned": uitkomst.inserted,
            "updated": uitkomst.updated,
            "status": rij.status,
        }
