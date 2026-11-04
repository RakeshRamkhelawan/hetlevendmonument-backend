"""De ene keten die "klaar" definieert: van HR-vraag tot opgeslagen besluit.

Waarom dit bestaat
------------------
Elf weken lang groeide het register van 40 naar 265 punten terwijl er geen enkele
gebruiker iets terugkreeg. De oorzaak is meetbaar: er ging nooit iets op rood.
Code die niets doet en `success=True` teruggeeft, ziet er in elke test, elk log en
elk dashboard uit als code die werkt (11 supervisors, ChiefOrchestrator, de
retentietaak -- zie scripts/codebase_inventory.py --list-hollow).

Dit script is het tegengif. Het legt EEN keten af en zegt hoe ver hij komt. Niet
groen of rood, maar "stap 4 van 7" -- zodat je wekelijks ziet of er beweging is.
Een stap telt pas als hij ONGEMOCKT slaagt: echte manifesten, echte ToolBroker,
echte database. Een stap die alleen met een dubbelganger slaagt, telt niet.

De keten
--------
  1. Het manifest van de HR-specialist is te laden
  2. De specialist is als klasse te construeren uit dat manifest
  3. Elke tool die het manifest noemt, kent de ToolBroker ook echt
  4. De instructietekst staat toe dat de agent tools aanroept
  5. De kloofanalyse levert echte rijen uit de database
  6. De schrijfactie bestaat en staat achter de HITL-poort
  7. Na goedkeuring staat het besluit als rij in de database

Gebruik
-------
    python scripts/acceptance_thread.py

Stappen 5 en 7 hebben een draaiende testdatabase nodig
(`make test-db-up`, PostgreSQL op netwerkpoort 5455). Zonder database meldt het
script dat ze niet te toetsen zijn -- dat is iets anders dan gefaald, en het script
zegt het verschil.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# DIT MOET VOOR ELKE src.*-IMPORT. De configuratie wordt bij de eerste import gebouwd en
# leest DATABASE_URL dan een keer; wie hem later zet, wijst naar een database die de app
# nooit gebruikt. Gemeten 2026-09-15 stond os.environ op poort 5455 terwijl de config naar
# 5435 wees, binnen dezelfde run. Zie tests/conftest.py, dezelfde reden.
import os  # noqa: E402

if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ.get(
        "SANSKRITISETU_TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5455/sanskritisetu",
    )

MANIFEST = REPO / "src/core/als/agents/skills/manifests/skillsgaptraining.yml"

OK = "GEHAALD"
FAIL = "NIET GEHAALD"
SKIP = "NIET TE TOETSEN"

# De zin die 134 van de 135 manifesten hun agent meegeven. Zolang die er staat,
# roept de specialist per instructie geen enkele tool aan -- hoe goed de rest ook
# is aangesloten.
FORBIDDING_SENTENCE = "do not have working tools"

# Stap 5, stap 7 en `--seed` SCHRIJVEN in de database uit DATABASE_URL. Dat mag alleen in een
# herkenbare wegwerpdatabase (scripts/wegwerp_database.py); anders weigeren ze, zonder verbinding.
try:
    # Als script (`python scripts/acceptance_thread.py`) staat `scripts/` zelf op sys.path.
    from wegwerp_database import (  # noqa: E402
        UITLEG,
        GeenWegwerpDatabase,
        controleer_wegwerp_database,
    )
except ModuleNotFoundError:
    # Geladen als module vanuit de repo (zonder `scripts/` op sys.path).
    from scripts.wegwerp_database import (  # type: ignore[no-redef]  # noqa: E402
        UITLEG,
        GeenWegwerpDatabase,
        controleer_wegwerp_database,
    )

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.sql import Executable


class _OpruimFout(RuntimeError):
    """De opruiming van de wegwerprijen is mislukt; er kunnen rijen zijn achtergebleven."""


async def _voer_opruiming_uit(
    fabriek: async_sessionmaker[AsyncSession], opdrachten: Sequence[Executable]
) -> None:
    """Voer de opruimopdrachten uit in een eigen sessie. Mislukt dat, dan een `_OpruimFout`.

    Tot 2026-10-14 stond hier `except Exception: pass`: een opruiming die faalde liet wegwerprijen
    in de database achter terwijl het script GEHAALD meldde.
    """
    try:
        async with fabriek() as sessie:
            for opdracht in opdrachten:
                await sessie.execute(opdracht)
            await sessie.commit()
    except Exception as exc:
        # Loopt dit in een `finally` terwijl er al een fout onderweg was, dan is die fout de
        # oorzaak; die mag niet uit de melding verdwijnen (`__context__`).
        eerder = exc.__context__
        eerder_tekst = (
            "; oorspronkelijke fout: {}: {}".format(type(eerder).__name__, eerder)
            if eerder is not None
            else ""
        )
        raise _OpruimFout(
            "opruimen mislukte ({}: {}); er kunnen wegwerprijen zijn achtergebleven in de "
            "database{}".format(type(exc).__name__, exc, eerder_tekst)
        ) from exc


def _weigering_tekst(stap: int, exc: GeenWegwerpDatabase) -> str:
    return (
        "stap {} schrijft en wist rijen en weigert daarom deze database zonder herkenbare "
        "wegwerpnaam: {} {}".format(stap, exc, UITLEG)
    )


class Stage:
    def __init__(self, number: int, title: str) -> None:
        self.number = number
        self.title = title
        self.status = FAIL
        self.detail = ""

    def ok(self, detail: str = "") -> None:
        self.status = OK
        self.detail = detail

    def fail(self, detail: str) -> None:
        self.status = FAIL
        self.detail = detail

    def skip(self, detail: str) -> None:
        self.status = SKIP
        self.detail = detail


def stage_1_manifest(stage: Stage) -> object | None:
    from src.core.als.agents.skill_manifest import SkillManifest

    if not MANIFEST.exists():
        stage.fail("manifest ontbreekt: {}".format(MANIFEST))
        return None
    manifest = SkillManifest.load(MANIFEST)
    stage.ok(
        "skill_id={} classificatie={} hitl={}".format(
            manifest.skill_id, manifest.annex_iii_classification, manifest.human_in_the_loop
        )
    )
    return manifest


def stage_2_class(stage: Stage) -> None:
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    skill = SkillsGapTrainingSkill(tenant_id=1)
    if not hasattr(skill, "act"):
        stage.fail("de specialist heeft geen act()")
        return
    stage.ok("{} geconstrueerd voor tenant 1".format(type(skill).__name__))


def _uitvoerbare_toolnamen() -> set[str]:
    """De namen die de broker van DEZE SKILL werkelijk kan uitvoeren.

    Twee keer bijgesteld op 2026-09-21, en de tweede keer is de belangrijkste:

    1. De lokale registry stond hier eerst niet bij, wat de meting onjuist maakte in de
       strengere richting -- een bestaande `local__`-tool werd geteld als niet-bestaand.
    2. Toen bleek de omgekeerde fout ernstiger: de klasse-attributen van de drie registries
       zeggen NIETS over wat deze agent kan aanroepen. `BaseSpecialistAgent` bouwt zijn eigen
       `ToolBrokerService` en geeft daar geen `local_registry` aan mee (gemeten: `None`, en de
       `local__`-tak gooit "Local tool registry not initialized"). Een naam in
       `LocalToolRegistry._TOOL_NAMES` is dus geen aangesloten tool voor deze skill. Deze
       functie vraagt het daarom aan het OBJECT dat de skill in handen heeft.

    **Bewust de EXPLICIETE namen en niet `service.is_known_tool()`.** Die functie laat ook een
    prefix passeren (`local__` en drie andere), dus `local__wat_ik_maar_verzin` zou als bestaand
    tellen. Dan kan deze stap groen worden op een tool die niemand heeft gebouwd -- precies de
    faalvorm die dit script moet vangen, in het meetinstrument zelf.
    """
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    broker = SkillsGapTrainingSkill(tenant_id=1).tools
    namen: set[str] = set()
    for attribuut in ("business_registry", "hr_registry", "local_registry"):
        registry = getattr(broker, attribuut, None)
        if registry is not None:
            namen |= set(type(registry).known_tool_names())
    return namen


def stage_3_tools(stage: Stage, manifest: object) -> None:
    known = _uitvoerbare_toolnamen()
    wanted = list(getattr(manifest, "allowed_tools", []))
    missing = [name for name in wanted if name not in known]
    if missing:
        stage.fail(
            "{} van de {} tools bestaan niet: {}".format(
                len(missing), len(wanted), ", ".join(missing)
            )
        )
        return
    stage.ok("alle {} tools bestaan".format(len(wanted)))


def stage_4_prompt(stage: Stage, manifest: object) -> None:
    prompt = str(getattr(manifest, "system_prompt", ""))
    if FORBIDDING_SENTENCE in prompt:
        stage.fail("de instructietekst verbiedt de agent tools te gebruiken")
        return
    if "TOOL_CALL" not in prompt:
        stage.fail("de instructietekst legt niet uit hoe een tool aangeroepen wordt")
        return
    stage.ok("de agent mag en weet hoe hij een tool aanroept")


def stage_5_gap_query(stage: Stage) -> None:
    import asyncio
    import uuid

    # DATABASE_URL staat bovenaan dit bestand gezet, voor elke src-import. De DB-manager
    # zelf wordt normaal door de app-lifespan opgezet; dit script draait daarbuiten.
    from src.core.database.database import initialize_database
    from src.core.tool_broker.hr_registry import GAP_TOOL_NAME, HRToolRegistry
    from src.core.models.rbac_models import Tenant, Role, User, user_roles
    from src.core.models.hr_skills_models import Skill, RoleRequiredSkill, EmployeeSkill
    from src.core.middleware.tenant_context import set_tenant_id, get_tenant_id
    from sqlalchemy import select, and_, delete
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    async def run() -> tuple[dict[str, object], str, str]:
        controleer_wegwerp_database(os.environ["DATABASE_URL"])
        if not await initialize_database():
            raise _GeenDatabase("initialize_database gaf False -- geen verbinding")

        marker = uuid.uuid4().hex[:8]
        role_name = f"AcceptanceRole-{marker}"
        skill_name = f"AcceptanceSkill-{marker}"
        user_email = f"acceptance-{marker}@test.local"
        tenant_id = 1

        engine = create_async_engine(os.environ["DATABASE_URL"])
        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        prev_tenant = get_tenant_id()
        set_tenant_id(tenant_id)
        role_id: int | None = None
        user_id: int | None = None
        skill_id: int | None = None
        req_id: int | None = None
        emp_skill_id: int | None = None

        try:
            # 1. Maak een eigen gemarkeerde wegwerpkloof aan
            async with session_factory() as session:
                t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
                if t_res.scalar_one_or_none() is None:
                    session.add(Tenant(id=tenant_id, name="Acceptance Tenant", is_active=True))
                    await session.flush()

                role = Role(name=role_name, tenant_id=tenant_id, is_active=True)
                session.add(role)
                await session.flush()
                role_id = role.id

                user = User(
                    email=user_email,
                    hashed_password="$2b$12$WqJTQqMXvDHMYndXLTpn6u66lPZfLuWW17se2s2vsD/zpBl7a/0dO",
                    tenant_id=tenant_id,
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                user_id = user.id

                await session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
                await session.flush()

                skill = Skill(name=skill_name, tenant_id=tenant_id)
                session.add(skill)
                await session.flush()
                skill_id = skill.id

                req_skill = RoleRequiredSkill(
                    role_id=role_id,
                    skill_id=skill_id,
                    required_level=4,
                    tenant_id=tenant_id,
                )
                session.add(req_skill)
                await session.flush()
                req_id = req_skill.id

                emp_skill = EmployeeSkill(
                    user_id=user_id,
                    skill_id=skill_id,
                    level=2,
                    tenant_id=tenant_id,
                )
                session.add(emp_skill)
                await session.flush()
                emp_skill_id = emp_skill.id

                await session.commit()

            # 2. Voer de kloofquery uit via de ToolBroker
            registry = HRToolRegistry()
            result = await registry.execute_hr_tool(
                tool_name=GAP_TOOL_NAME,
                payload={"role_filter": role_name},
                tenant_id=tenant_id,
            )
            return result, role_name, skill_name
        finally:
            # 3. Ruim de wegwerpkloof altijd af. Een mislukte opruiming is een FOUT (`_OpruimFout`) en
            # geen stilte: er kunnen dan wegwerprijen in de database zijn achtergebleven.
            opruimen: list[Executable] = []
            if emp_skill_id is not None:
                opruimen.append(delete(EmployeeSkill).where(EmployeeSkill.id == emp_skill_id))
            if req_id is not None:
                opruimen.append(delete(RoleRequiredSkill).where(RoleRequiredSkill.id == req_id))
            if skill_id is not None:
                opruimen.append(delete(Skill).where(Skill.id == skill_id))
            if user_id is not None and role_id is not None:
                opruimen.append(
                    user_roles.delete().where(
                        and_(user_roles.c.user_id == user_id, user_roles.c.role_id == role_id)
                    )
                )
            if user_id is not None:
                opruimen.append(delete(User).where(User.id == user_id))
            if role_id is not None:
                opruimen.append(delete(Role).where(Role.id == role_id))
            try:
                await _voer_opruiming_uit(session_factory, opruimen)
            finally:
                set_tenant_id(prev_tenant)
                await engine.dispose()

    try:
        result_data = asyncio.run(run())
    except Exception as exc:
        _meld_stapfout(stage, exc, 5)
        return

    result, role_name, skill_name = result_data
    gaps = result.get("gaps") if isinstance(result, dict) else None
    if not gaps:
        stage.fail(
            "de tool gaf 0 rijen terug voor de zojuist aangemaakte proefkloof ({})".format(role_name)
        )
        return

    own_gap = next((g for g in gaps if g.get("role") == role_name and g.get("skill") == skill_name), None)
    if not own_gap:
        stage.fail(
            "de tool gaf wel rijen ({}), maar NIET de zojuist zelf aangemaakte kloof ({}, {})".format(
                len(gaps), role_name, skill_name
            )
        )
        return

    if own_gap.get("below_requirement", 0) < 1:
        stage.fail("de aangemaakte kloof heeft below_requirement < 1: {}".format(own_gap))
        return

    stage.ok(
        "stap 5 heeft zijn eigen wegwerpkloof ({}) succesvol aangemaakt, gedetecteerd (below_requirement={}) en afgeruimd".format(
            skill_name, own_gap.get("below_requirement")
        )
    )


def stage_6_write_action(stage: Stage) -> None:
    known = _uitvoerbare_toolnamen()
    if "schedule_training" not in known:
        stage.fail("schedule_training bestaat niet -- er is geen schrijfactie om goed te keuren")
        return
    try:
        from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel

        level = ToolRiskClassifier().classify("schedule_training")
    except Exception as exc:
        stage.fail("risicoklasse niet te bepalen: {}".format(exc))
        return
    # De stap logde de klasse en meldde GEHAALD, wat de uitkomst ook was. Zet iemand
    # `schedule_training: low` in `tool_risk_levels.yml`, dan gaat de HITL-poort niet meer open
    # en zei dit script nog steeds GEHAALD -- een holle stap in het instrument dat holle code
    # moet aanwijzen, dezelfde vorm die stap 5 al eens had. (Gate 2-review 2026-09-21.)
    if level is not ToolRiskLevel.HIGH:
        stage.fail(
            "schedule_training bestaat maar is {} -- alleen HIGH opent de HITL-poort, dus een "
            "mens ziet deze schrijfactie niet".format(level)
        )
        return
    stage.ok("schedule_training bestaat en staat op HIGH, dus achter de HITL-poort")


def actieve_provider() -> str:
    """De provider die een LLM-aanroep NU zou bedienen, zonder er een te doen.

    Bestaat omdat een groene keten niets waard is als een namaakmodel hem groen maakte.
    Gemeten 2026-09-20: `.env` noemde een provider die de fabriek niet kent, waarna alles
    stil op `MockProvider` terugviel -- en een MockProvider geeft plausibele tekst terug.
    Stap 7 telt daarom niet mee zolang dit `mock` zegt.
    """
    try:
        from src.core.services.llm.service import LLMService

        return str(LLMService().provider.provider_name)
    except Exception as exc:  # een kapotte provider is iets anders dan een namaakprovider
        return "ONBEKEND ({})".format(type(exc).__name__)


_BCRYPT_TESTWACHTWOORD = "$2b$12$WqJTQqMXvDHMYndXLTpn6u66lPZfLuWW17se2s2vsD/zpBl7a/0dO"
_STAP7_GEBRUIKERS = ("maker", "besluiter", "goed", "af")


class _GeenDatabase(RuntimeError):
    """Wij stellen zelf vast dat er geen database is; dat hoeft niet uit tekst te blijken."""


def _namen_stap7(marker: str) -> tuple[str, str, str]:
    return (
        "AcceptanceFunctie7-{}".format(marker),
        "AcceptanceVaardigheid7-{}".format(marker),
        "AcceptanceTraining7-{}".format(marker),
    )


async def _zaai_stap7(
    fabriek: async_sessionmaker[AsyncSession],
    ids: dict[str, int],
    tenant_id: int,
    marker: str,
) -> None:
    """Maak de wegwerpfunctie, -gebruikers, -vaardigheid, -training en -eis; vul `ids` onderweg.

    `ids` wordt tijdens het zaaien gevuld: faalt het halverwege, dan weet de opruiming nog wat er
    al stond.
    """
    from sqlalchemy import select

    from src.core.models.hr_skills_models import EmployeeSkill, RoleRequiredSkill, Skill
    from src.core.models.hr_training_models import Training
    from src.core.models.rbac_models import Role, Tenant, User, user_roles

    functie, vaardigheid, training_naam = _namen_stap7(marker)
    async with fabriek() as s:
        bestaat = (
            await s.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if bestaat is None:
            s.add(Tenant(id=tenant_id, name="Acceptance Tenant", is_active=True))
            await s.flush()
        rol = Role(name=functie, tenant_id=tenant_id, is_active=True)
        s.add(rol)
        await s.flush()
        ids["rol"] = rol.id
        for sleutel in _STAP7_GEBRUIKERS:
            gebruiker = User(
                email="acceptance7-{}-{}@test.local".format(sleutel, marker),
                hashed_password=_BCRYPT_TESTWACHTWOORD,
                tenant_id=tenant_id,
                is_active=True,
            )
            s.add(gebruiker)
            await s.flush()
            ids[sleutel] = gebruiker.id
        for sleutel in ("goed", "af"):
            await s.execute(user_roles.insert().values(user_id=ids[sleutel], role_id=ids["rol"]))
        skill = Skill(name=vaardigheid, tenant_id=tenant_id)
        s.add(skill)
        await s.flush()
        ids["skill"] = skill.id
        training = Training(name=training_naam, tenant_id=tenant_id, skill_id=skill.id)
        s.add(training)
        await s.flush()
        ids["training"] = training.id
        s.add(
            RoleRequiredSkill(
                role_id=ids["rol"], skill_id=skill.id, required_level=4, tenant_id=tenant_id
            )
        )
        for sleutel in ("goed", "af"):
            s.add(
                EmployeeSkill(user_id=ids[sleutel], skill_id=skill.id, level=2, tenant_id=tenant_id)
            )
        await s.commit()


async def _maak_voorstellen_stap7(
    fabriek: async_sessionmaker[AsyncSession],
    ids: dict[str, int],
    tenant_id: int,
    marker: str,
) -> int:
    """Het voorstel maken zoals `POST /training-proposals`, in een eigen transactie."""
    from src.core.repositories.hr_training_proposals_repository import HRTrainingProposalsRepository

    functie, vaardigheid, training_naam = _namen_stap7(marker)
    async with fabriek() as s:
        uitkomst = await HRTrainingProposalsRepository(s).create_from_gap(
            tenant_id,
            ids["maker"],
            role_name=functie,
            skill_name=vaardigheid,
            training_name=training_naam,
        )
        await s.commit()
    return uitkomst.created


async def _rij_stap7(
    fabriek: async_sessionmaker[AsyncSession], ids: dict[str, int], tenant_id: int, user_id: int
) -> str | None:
    """De status van de `employee_trainings`-rij, gelezen met een EIGEN sessie."""
    from sqlalchemy import select

    from src.core.models.hr_training_models import EmployeeTraining

    async with fabriek() as lees:
        return (
            await lees.execute(
                select(EmployeeTraining.status).where(
                    EmployeeTraining.tenant_id == tenant_id,
                    EmployeeTraining.user_id == user_id,
                    EmployeeTraining.training_id == ids["training"],
                )
            )
        ).scalar_one_or_none()


async def _voorstel_id_stap7(
    fabriek: async_sessionmaker[AsyncSession], ids: dict[str, int], tenant_id: int, user_id: int
) -> int:
    from sqlalchemy import select

    from src.core.models.hr_training_models import TrainingProposal

    async with fabriek() as lees:
        gevonden = await lees.execute(
            select(TrainingProposal.id).where(
                TrainingProposal.tenant_id == tenant_id,
                TrainingProposal.user_id == user_id,
                TrainingProposal.skill_id == ids["skill"],
            )
        )
        return int(gevonden.scalar_one())


async def _status_stap7(fabriek: async_sessionmaker[AsyncSession], proposal_id: int) -> str:
    from sqlalchemy import select

    from src.core.models.hr_training_models import TrainingProposal

    async with fabriek() as lees:
        gevonden = await lees.execute(
            select(TrainingProposal.status).where(TrainingProposal.id == proposal_id)
        )
        return str(gevonden.scalar_one())


async def _keur_goed_stap7(
    fabriek: async_sessionmaker[AsyncSession], ids: dict[str, int], tenant_id: int, goed_id: int
) -> None:
    """Goedkeuren in de volgorde van de router: status zetten, dan toewijzen, dan committen."""
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from src.core.repositories.hr_training_proposals_repository import (
        STATUS_GOEDGEKEURD,
        HRTrainingProposalsRepository,
    )
    from src.core.tool_broker.hr_registry import SCHEDULE_TOOL_NAME, HRToolRegistry

    async with fabriek() as s:

        @asynccontextmanager
        async def _deze_sessie() -> AsyncIterator[AsyncSession]:
            yield s

        repo = HRTrainingProposalsRepository(s)
        voorstel = await repo.get_to_decide(tenant_id, goed_id)
        if voorstel is None:
            raise RuntimeError("het zojuist gemaakte voorstel is niet te vinden")
        if not await repo.mark_decided(
            tenant_id, goed_id, status=STATUS_GOEDGEKEURD, decided_by=ids["besluiter"]
        ):
            raise RuntimeError("het voorstel was al beslist")
        toewijzing = await HRToolRegistry(session_factory=_deze_sessie).execute_hr_tool(
            SCHEDULE_TOOL_NAME,
            {"user_email": voorstel.employee_email, "training_name": voorstel.training_name},
            tenant_id=tenant_id,
        )
        if toewijzing.get("success") is not True:
            await s.rollback()
            raise RuntimeError("toewijzen mislukte: {}".format(toewijzing))
        await s.commit()


async def _wijs_af_stap7(
    fabriek: async_sessionmaker[AsyncSession], ids: dict[str, int], tenant_id: int, af_id: int
) -> None:
    """Afwijzen: alleen de status, er wordt niets toegewezen."""
    from src.core.repositories.hr_training_proposals_repository import (
        STATUS_AFGEWEZEN,
        HRTrainingProposalsRepository,
    )

    async with fabriek() as s:
        await HRTrainingProposalsRepository(s).mark_decided(
            tenant_id, af_id, status=STATUS_AFGEWEZEN, decided_by=ids["besluiter"]
        )
        await s.commit()


def _opruimopdrachten_stap7(ids: dict[str, int]) -> list[Executable]:
    """Wat er weg moet, op basis van wat er daadwerkelijk is aangemaakt (`ids`)."""
    from sqlalchemy import delete

    from src.core.models.hr_skills_models import EmployeeSkill, RoleRequiredSkill, Skill
    from src.core.models.hr_training_models import EmployeeTraining, Training, TrainingProposal
    from src.core.models.rbac_models import Role, User, user_roles

    opruimen: list[Executable] = []
    if "training" in ids:
        opruimen.append(
            delete(EmployeeTraining).where(EmployeeTraining.training_id == ids["training"])
        )
    if "skill" in ids:
        opruimen.append(delete(TrainingProposal).where(TrainingProposal.skill_id == ids["skill"]))
        opruimen.append(delete(EmployeeSkill).where(EmployeeSkill.skill_id == ids["skill"]))
        opruimen.append(delete(RoleRequiredSkill).where(RoleRequiredSkill.skill_id == ids["skill"]))
    if "rol" in ids:
        opruimen.append(delete(user_roles).where(user_roles.c.role_id == ids["rol"]))
    if "training" in ids:
        opruimen.append(delete(Training).where(Training.id == ids["training"]))
    if "skill" in ids:
        opruimen.append(delete(Skill).where(Skill.id == ids["skill"]))
    for sleutel in _STAP7_GEBRUIKERS:
        if sleutel in ids:
            opruimen.append(delete(User).where(User.id == ids[sleutel]))
    if "rol" in ids:
        opruimen.append(delete(Role).where(Role.id == ids["rol"]))
    return opruimen


async def _stage_7_database_pad() -> dict[str, object]:
    """Van voorstel tot opgeslagen besluit, met echte rijen in de echte database.

    Wat dit bewijst: een voorstel dat een mens goedkeurt, landt als rij in `employee_trainings`
    via hetzelfde pad als de router (`training_proposals_router.approve_training_proposal`:
    `get_to_decide`, `mark_decided`, dan `schedule_training` in DEZELFDE sessie), en een
    afgewezen voorstel laat GEEN rij achter. De uitkomst wordt met een EIGEN, tweede sessie
    teruggelezen, zodat een niet-gecommitte rij niet voor bewijs doorgaat.

    Wat het NIET bewijst: de rechtencontrole (`hr:approve`), vier ogen en het scherm. Die
    staan in `tests/integration/test_hr_pilot_dag2_opleidingsvoorstel.py`.

    De stappen staan in kleine functies (`_zaai_stap7`, `_maak_voorstellen_stap7`,
    `_keur_goed_stap7`, `_wijs_af_stap7`, `_opruimopdrachten_stap7`); dit is alleen de volgorde.
    """
    # EERST de controle, voor elke import en elke verbinding: deze stap schrijft rijen en wist ze.
    controleer_wegwerp_database(os.environ["DATABASE_URL"])

    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.core.database.database import initialize_database
    from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

    if not await initialize_database():
        raise _GeenDatabase("initialize_database gaf False -- geen verbinding")

    tenant_id = 1
    marker = uuid.uuid4().hex[:8]
    engine = create_async_engine(os.environ["DATABASE_URL"])
    fabriek = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    vorig = get_tenant_id()
    set_tenant_id(tenant_id)

    ids: dict[str, int] = {}
    try:
        await _zaai_stap7(fabriek, ids, tenant_id, marker)
        aangemaakt = await _maak_voorstellen_stap7(fabriek, ids, tenant_id, marker)
        voor = [await _rij_stap7(fabriek, ids, tenant_id, ids[k]) for k in ("goed", "af")]
        goed_id = await _voorstel_id_stap7(fabriek, ids, tenant_id, ids["goed"])
        af_id = await _voorstel_id_stap7(fabriek, ids, tenant_id, ids["af"])
        await _keur_goed_stap7(fabriek, ids, tenant_id, goed_id)
        await _wijs_af_stap7(fabriek, ids, tenant_id, af_id)
        return {
            "aangemaakt": aangemaakt,
            "rijen_voor_besluit": sum(1 for r in voor if r is not None),
            "goedgekeurd_status": await _status_stap7(fabriek, goed_id),
            "goedgekeurd_rij": await _rij_stap7(fabriek, ids, tenant_id, ids["goed"]),
            "afgewezen_status": await _status_stap7(fabriek, af_id),
            "afgewezen_rij": await _rij_stap7(fabriek, ids, tenant_id, ids["af"]),
        }
    finally:
        # Een mislukte opruiming is een FOUT (`_OpruimFout`) en geen stilte: er kunnen dan
        # wegwerprijen in de database zijn achtergebleven.
        try:
            await _voer_opruiming_uit(fabriek, _opruimopdrachten_stap7(ids))
        finally:
            set_tenant_id(vorig)
            await engine.dispose()


def _beoordeel_stap7(stage: Stage, uitkomst: dict[str, object]) -> None:
    """Zet de uitslag van stap 7 op basis van wat er uit de database is teruggelezen."""
    if uitkomst["aangemaakt"] != 2:
        stage.fail(
            "verwacht 2 voorstellen voor 2 medewerkers onder de eis, kreeg {}".format(
                uitkomst["aangemaakt"]
            )
        )
    elif uitkomst["rijen_voor_besluit"] != 0:
        stage.fail(
            "er stond al een employee_trainings-rij VOOR het besluit; de meting zegt dan niets"
        )
    elif (
        uitkomst["goedgekeurd_status"] != "goedgekeurd" or uitkomst["goedgekeurd_rij"] != "assigned"
    ):
        stage.fail(
            "na goedkeuring: voorstel={}, employee_trainings-rij={} (verwacht goedgekeurd en assigned)".format(
                uitkomst["goedgekeurd_status"], uitkomst["goedgekeurd_rij"]
            )
        )
    elif uitkomst["afgewezen_status"] != "afgewezen" or uitkomst["afgewezen_rij"] is not None:
        stage.fail(
            "na afwijzing: voorstel={}, employee_trainings-rij={} (verwacht afgewezen en GEEN rij)".format(
                uitkomst["afgewezen_status"], uitkomst["afgewezen_rij"]
            )
        )
    else:
        stage.ok(
            "goedgekeurd voorstel -> employee_trainings-rij 'assigned' (gelezen met een eigen sessie); "
            "afgewezen voorstel -> geen rij; alles afgeruimd"
        )


def _meld_stapfout(stage: Stage, exc: Exception, stap: int) -> None:
    """Zet de uitslag van een stap die met een fout stopte: geweigerd, geen database of kapot."""
    if isinstance(exc, GeenWegwerpDatabase):
        stage.fail(_weigering_tekst(stap, exc))
    elif isinstance(exc, _OpruimFout):
        stage.fail(str(exc))
    elif isinstance(exc, _GeenDatabase):
        stage.skip("geen testdatabase bereikbaar -- {}".format(exc))
    else:
        text = "{}: {}".format(type(exc).__name__, exc)
        lowered = text.lower()
        absent = ("connect", "refused", "does not exist", "not initialized", "geweigerd")
        if any(marker in lowered for marker in absent) and "relation" not in lowered:
            stage.skip("geen testdatabase bereikbaar -- {}".format(text[:120]))
        else:
            stage.fail(text[:200])


def stage_7_persisted(stage: Stage, provider: str) -> None:
    # De volgorde telt: eerst de vraag WIE antwoordt, dan pas of er iets is opgeslagen.
    # Andersom zou deze stap ooit groen kunnen worden op een besluit dat een namaakmodel
    # heeft bedacht -- exact de faalvorm die dit script moet vangen.
    if provider == "mock":
        stage.fail(
            "provider is 'mock' -- een besluit uit een namaakmodel telt niet als bewijs "
            "(zet LLM_PROVIDER op een echte provider, bv. ollama of deepseek)"
        )
        return
    import asyncio

    try:
        uitkomst = asyncio.run(_stage_7_database_pad())
    except Exception as exc:
        _meld_stapfout(stage, exc, 7)
        return
    _beoordeel_stap7(stage, uitkomst)


def _voer_seed_uit() -> bool:
    """Zaai de proefdata. Geeft True terug als dit is geweigerd (geen wegwerpdatabase)."""
    # Zaaien schrijft proefdata die NIET wordt opgeruimd: alleen in een wegwerpdatabase.
    try:
        controleer_wegwerp_database(os.environ["DATABASE_URL"])
    except GeenWegwerpDatabase as exc:
        print("--seed geweigerd: {} {}".format(exc, UITLEG))
        return True
    import asyncio

    from scripts.seed_hr_acceptance_data import seed_hr_acceptance_data
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    async def _do_seed() -> None:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with session_factory() as session:
                await seed_hr_acceptance_data(session, tenant_id=1)
        finally:
            await engine.dispose()

    asyncio.run(_do_seed())
    return False


def main() -> int:
    if "--seed" in sys.argv:
        geweigerd = _voer_seed_uit()
        if geweigerd:
            return 2

    stages = [
        Stage(1, "het manifest van de HR-specialist is te laden"),
        Stage(2, "de specialist is te construeren uit dat manifest"),
        Stage(3, "elke tool die het manifest noemt, kent de ToolBroker ook echt"),
        Stage(4, "de instructietekst staat toe dat de agent tools aanroept"),
        Stage(5, "de kloofanalyse levert echte rijen uit de database"),
        Stage(6, "de schrijfactie bestaat en heeft een risicoklasse"),
        Stage(7, "na goedkeuring staat het besluit als rij in de database"),
    ]

    manifest = None
    try:
        manifest = stage_1_manifest(stages[0])
    except Exception as exc:
        stages[0].fail("{}: {}".format(type(exc).__name__, exc))

    provider = actieve_provider()

    for index, runner in (
        (1, stage_2_class),
        (4, stage_5_gap_query),
        (5, stage_6_write_action),
    ):
        try:
            runner(stages[index])
        except Exception as exc:
            stages[index].fail("{}: {}".format(type(exc).__name__, exc))

    try:
        stage_7_persisted(stages[6], provider)
    except Exception as exc:
        stages[6].fail("{}: {}".format(type(exc).__name__, exc))

    if manifest is not None:
        for index, needs_manifest in ((2, stage_3_tools), (3, stage_4_prompt)):
            try:
                needs_manifest(stages[index], manifest)
            except Exception as exc:
                stages[index].fail("{}: {}".format(type(exc).__name__, exc))
    else:
        for index in (2, 3):
            stages[index].fail("manifest niet geladen, stap niet te toetsen")

    print("")
    print("=== ACCEPTATIEKETEN: HR-VAARDIGHEDENKLOOF ===")
    print(
        "  taalmodel-provider: {}{}".format(
            provider, "   <-- NAMAAK, geen bewijs" if provider == "mock" else ""
        )
    )
    for stage in stages:
        print("  {}  [{:<15}] {}".format(stage.number, stage.status, stage.title))
        if stage.detail:
            print("       {}".format(stage.detail))

    reached = 0
    for stage in stages:
        if stage.status == OK:
            reached += 1
        else:
            break

    passed = sum(1 for s in stages if s.status == OK)
    skipped = sum(1 for s in stages if s.status == SKIP)
    print("")
    print("  Keten komt tot stap {} van {}".format(reached, len(stages)))
    print("  Losse stappen gehaald: {}   niet te toetsen: {}".format(passed, skipped))
    print("")
    return 0 if reached == len(stages) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
