"""Een opruimactor die niet is ingepland ruimt niets op -- en een planner die niet draait ook niet.

ADR-036 OP-159 (D3): `cleanup_agent_critiques` stond hier met een gedateerde uitzondering
terwijl `agent_critiques` wel op de retentie-allowlist stond -- de belofte was dus onwaar.
Op 2026-08-17 ingepland op 03:05 UTC; KNOWN_UNSCHEDULED is sindsdien leeg.

**Hoe de eerste helft gevonden is.** Bij het bouwen van de HITL-retentie wilde ik
`cleanup_agent_critiques` (`governance/retention_cleanup.py`) als voorbeeld kopieren. De Taak
2-review mat dat die actor nergens in `src/workers/scheduler.py` staat. Kopieren had dus een
retentie opgeleverd die alleen op papier bestaat.

**Hoe de tweede helft gevonden is, en dat is de pijnlijkere.** De eerste versie van deze guard
toetste met een SUBSTRING of de actornaam ergens in `scheduler.py` voorkwam. Een blinde review op
2026-08-06 verwijderde het complete `add_job(...)`-blok voor de HITL-retentie en deze guard bleef
GROEN -- de naam stond immers nog in de runner-methode en in de import. Daarna ook de runner
verwijderd, alleen de dode import over: nog steeds groen. De guard kon precies de toestand die hij
moest betrappen niet zien.

Erger nog een laag hoger: `start_scheduler` had NUL aanroepers buiten zijn eigen `__main__`, en
geen enkele compose-opstelling startte het proces. De guard bewaakte dus de inhoud van een
configuratiebestand dat nergens werd uitgevoerd. Zijn eigen docstring stelde "een ongeplande
opruimactor ruimt niets op"; exact datzelfde argument geldt een laag hoger (ADR-036 OP-64).

**Wat deze guard nu doet, in drie lagen:**

1. Elke dramatiq-actor in `retention_cleanup.py` heeft een `add_job(..., id="<actor>", ...)` in de
   scheduler -- vastgesteld via de AST, niet via een substring.
2. Er bestaat een gedeployed proces dat de scheduler daadwerkelijk start.
3. De uitzonderingslijst rot niet dicht.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.architecture._ci_workflow import (
    ContainerAppCommando,
    containerapp_commandos,
    tokeniseer,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RETENTION = REPO_ROOT / "src/core/governance/retention_cleanup.py"
SCHEDULER = REPO_ROOT / "src/workers/scheduler.py"
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.prod.yml")

#: Actors die BEWUST niet ingepland zijn, met datum en reden per regel.
#:
#: `cleanup_agent_critiques` is op 2026-08-05 gemeten als niet-ingepland en is een bestaande
#: bevinding (ADR-036 OP-60, Fase D/P2), geen regressie van deze sprint. De brongegevens staan ook
#: in `agent_critiques` met een eigen bewaartermijn, dus het gat is niet acuut -- maar de belofte
#: "deze kritieken worden opgeruimd" is vandaag onwaar.
KNOWN_UNSCHEDULED: dict[str, str] = {}


#: De modulenaam die als planner moet draaien. EXACTE gelijkheid, geen substring:
#: `src.workers.scheduler_v2` of `src.workers.scheduler_disabled` telt niet mee.
PLANNER_MODULE = "src.workers.scheduler"


def _start_de_planner(commando: ContainerAppCommando) -> bool:
    """Start dit `containerapp`-commando de planner ECHT? (ADR-036 OP-102, HIGH-3)

    **Drie generaties, en elke opvolger liet iets anders door.** De eerste zocht de modulenaam
    ergens in het bestand; een blinde review liet hem in een shell-comment staan en verving het
    startcommando -- groen, terwijl er in Azure geen planner meer draaide. De tweede strookte
    comments en eiste dat de naam op dezelfde logische regel stond als `containerapp` en
    `create`/`update`. Die liet er drie door, alle drie gemeten op 2026-08-09:

    - de modulenaam als WAARDE van een env-var (`--env-vars "MODULE=src.workers.scheduler"`);
    - een niet-bestaande modulenaam (`src.workers.scheduler_v2`), want het was een substring;
    - `if: false` op de stap, want `step["if"]` werd nergens gelezen.

    Nu: de naam moet het ARGUMENT van `-m` zijn binnen `--command`, met exacte gelijkheid. De
    `if`-conditie wordt gewogen in `_ci_workflow.cd_stappen()`.

    **En de replica-telling hoort erbij.** Een app met `--min-replicas 0` bestaat, heeft het
    juiste startcommando, en draait nooit. Dat is dezelfde klasse als OP-64: een planner die
    nergens draait plant niets.

    **Mutatietest (2026-08-09, beide richtingen, 6/6 zoals verwacht):**

    | Mutatie op `cd-production.yml` | Verwacht | Gemeten |
    | --- | --- | --- |
    | Modulenaam als env-var-WAARDE i.p.v. startcommando | ROOD | ROOD |
    | `src.workers.scheduler_v2` (bestaat niet) | ROOD | ROOD |
    | `if: false` op de stap | ROOD | ROOD |
    | `--min-replicas 0` | ROOD | ROOD |
    | Commando weg, naam in een comment laten staan | ROOD | ROOD |
    | LEGITIEM: een ongerelateerde env-var op dezelfde stap | GROEN | GROEN |

    De eerste drie zijn de omzeilingen die de VORIGE versie van deze guard doorliet; de vierde
    en vijfde kwamen uit de Gate 2-review op het plan van deze dag.
    """
    # `start_argumenten()` leest BEIDE deployvormen: `--command`/`--args` en de
    # `--yaml`-manifestvorm. Die tweede is sinds 2026-08-29 de enige werkende manier om een
    # `-m`-start te deployen (az' argparser weigert een leidende streep als vlagwaarde), en
    # tot 2026-08-30 zag deze guard hem niet -- rood terwijl de planner wel draaide.
    argumenten = commando.start_argumenten()
    heeft_module = any(
        token == "-m" and volgende == PLANNER_MODULE
        for token, volgende in zip(argumenten, argumenten[1:])
    )
    if not heeft_module:
        return False

    replicas = commando.min_replicas()
    if replicas is not None and replicas < 1:
        return False
    return True


def _roept_aan(functie: ast.AST, naam: str) -> bool:
    """Roept deze functie `naam` daadwerkelijk AAN? (ADR-036 OP-101)

    Bewust `ast.Call` en niet `naam in ast.dump(functie)`. Die laatste rendert ook de DOCSTRING,
    dus een functie die de naam alleen in haar toelichting noemt haalt de toets al. Aangetoond
    door een blinde review: de body van `_bind_the_real_broker` vervangen door `return` liet deze
    guard GROEN, omdat de docstring `get_redis_broker()` drie keer noemt.
    """
    for knoop in ast.walk(functie):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        aangeroepen = doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", "")
        if aangeroepen == naam:
            return True
    return False


def _actor_names() -> set[str]:
    """De `actor_name=`-waarden uit `retention_cleanup.py`, uit de bron.

    Bewust de `actor_name`-parameter en niet de functienaam: dramatiq registreert onder die naam,
    en de scheduler verwijst er ook naar. Zouden ze uiteenlopen, dan is dat zelf een bevinding.
    """
    text = RETENTION.read_text(encoding="utf-8")
    return set(re.findall(r'actor_name\s*=\s*["\'](\w+)["\']', text))


def _scheduled_job_ids() -> set[str]:
    """De `id=`-waarden van elke `add_job(...)`-aanroep in de scheduler, via de AST.

    Waarom niet de bestandstekst doorzoeken: een naam komt in dat bestand ook voor in de
    runner-methode, in een logregel en in een import. Een substring-toets blijft daardoor groen
    nadat de PLANNING zelf is verwijderd -- aantoonbaar, want zo is deze guard betrapt.
    """
    tree = ast.parse(SCHEDULER.read_text(encoding="utf-8"))
    job_ids: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_job"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str):
                    job_ids.add(value)
    return job_ids


def _processes_that_start_the_scheduler() -> list[str]:
    """Gedeployde processen die de planner daadwerkelijk starten.

    Een compose-service die `src.workers.scheduler` als entrypoint of command draait telt. Alleen
    de code hebben is niet genoeg: dat was precies de toestand waarin elke bewaartermijn een
    belofte was die niemand nakwam.

    **De YAML wordt GEPARSED, niet doorzocht (ADR-036 OP-77).** De eerste versie zocht de string
    `src.workers.scheduler` ergens in het bestand. Een blinde review verving het entrypoint door
    `sleep infinity` en liet de naam in een comment erboven staan: de guard bleef GROEN terwijl de
    planner niets meer deed. Dat is exact de fout die deze guard een laag lager al had gemaakt --
    een substring-toets op een bestand zegt niets over wat er DRAAIT.
    """
    import yaml

    found: list[str] = []

    # De CD-workflows tellen mee (ADR-036 OP-64). Azure draait geen compose: staat de planner
    # alleen daar, dan draait hij in de cloud nergens. De guard keek eerst uitsluitend naar
    # compose en meldde daarom groen terwijl de gedeployde omgeving geen planner had.
    for commando in containerapp_commandos():
        if _start_de_planner(commando):
            found.append(f"{commando.workflow}:{commando.stap}")

    for name in COMPOSE_FILES:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for service, config in (parsed.get("services") or {}).items():
            if not isinstance(config, dict):
                continue
            # entrypoint EN command: dramatiq-services zetten het commando in de ene, de
            # scheduler in de andere. Beide vormen (lijst of string) komen voor.
            #
            # `deploy.replicas: 0` telt als NIET draaiend -- zelfde reden als `--min-replicas 0`
            # bij de containerapps: een gedefinieerde service die nooit start, plant niets.
            replicas = (config.get("deploy") or {}).get("replicas")
            if replicas is not None and str(replicas).isdigit() and int(replicas) < 1:
                continue
            for key in ("entrypoint", "command"):
                value = config.get(key)
                if value is None:
                    continue
                tokens = list(value) if isinstance(value, list) else tokeniseer(str(value))
                # Exact het argument van `-m`, niet "de naam komt erin voor". Anders telt
                # `src.workers.scheduler_v2` mee, en een naam in een comment ook.
                if any(
                    token == "-m" and volgende == PLANNER_MODULE
                    for token, volgende in zip(tokens, tokens[1:])
                ):
                    found.append(f"{name}:{service}")
    return found


def test_the_scan_finds_actors_at_all() -> None:
    """Vangnet: als de scan leegloopt, zegt de test hieronder niets."""
    found = _actor_names()

    assert len(found) >= 2, (
        f"Slechts {len(found)} actors gevonden in {RETENTION.name}: {sorted(found)}. Is het bestand "
        "hernoemd of de decoratorvorm veranderd? Zolang dit leeg terugkomt, bewaakt deze guard niets."
    )


def test_the_scan_finds_scheduled_jobs_at_all() -> None:
    """Vangnet voor de andere kant: een lege AST-scan zou alles laten slagen."""
    found = _scheduled_job_ids()

    assert len(found) >= 3, (
        f"Slechts {len(found)} `add_job(id=...)`-aanroepen gevonden in {SCHEDULER.name}: "
        f"{sorted(found)}. Is de aanroepvorm veranderd (bijv. een positioneel id of een variabele "
        "in plaats van een letterlijke string)? Dan meet deze guard niets meer."
    )


def test_every_retention_actor_is_scheduled() -> None:
    """Een opruimactor zonder planning is een belofte die niemand nakomt."""
    job_ids = _scheduled_job_ids()
    unscheduled = sorted(
        name for name in _actor_names() if name not in job_ids and name not in KNOWN_UNSCHEDULED
    )

    assert not unscheduled, (
        f"Deze retentie-actors hebben geen `add_job(id=...)` in {SCHEDULER.name}: {unscheduled}. "
        f"Wel ingepland: {sorted(job_ids)}. Voeg een planning toe, of zet de actor met datum en "
        "reden in KNOWN_UNSCHEDULED."
    )


def test_the_scheduler_is_started_by_a_deployed_process() -> None:
    """Een planner die nergens draait plant niets (ADR-036 OP-64).

    Dit is de laag die de vorige versie van deze guard miste. `start_scheduler` had nul aanroepers
    buiten zijn eigen `__main__`, en geen enkele compose-opstelling startte het proces -- terwijl
    de guard eronder vrolijk groen meldde dat alles "ingepland" was.
    """
    processes = _processes_that_start_the_scheduler()

    assert processes, (
        "Geen enkele compose-opstelling start `src.workers.scheduler`. Alle planning in "
        f"{SCHEDULER.name} is dan dode configuratie: de jobs draaien nooit en er komt geen "
        "foutmelding wanneer iets NIET gebeurt. Voeg een scheduler-service toe."
    )


def test_known_unscheduled_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET eruit, anders rot de lijst dicht."""
    job_ids = _scheduled_job_ids()
    resolved = sorted(name for name in KNOWN_UNSCHEDULED if name in job_ids)

    assert not resolved, (
        f"Deze actors staan in KNOWN_UNSCHEDULED maar zijn inmiddels wel ingepland: {resolved}. "
        "Haal ze uit de lijst; anders suggereert die lijst een probleem dat er niet meer is."
    )


def test_the_hitl_retention_actor_exists_and_is_scheduled() -> None:
    """De HITL-retentie zelf (ADR-036 OP-47).

    `cleanup_expired_hitl_tickets` MARKEERT tickets als verlopen maar VERWIJDERT niets -- gemeten:
    `git grep "delete(HITLTicket)"` over `src/` was leeg, en geen enkele art.-17-route raakt deze
    tabel. Zonder verwijderpad blijft elk ticket eeuwig staan, ook nadat de inhoud is opgeruimd.
    """
    actors = _actor_names()

    assert "cleanup_resolved_hitl_tickets" in actors, (
        f"Er is geen retentie-actor voor afgehandelde HITL-tickets. Gevonden: {sorted(actors)}. "
        "Markeren als verlopen is geen retentie -- de rij blijft staan."
    )
    assert "cleanup_resolved_hitl_tickets" in _scheduled_job_ids(), (
        "De HITL-retentie-actor bestaat maar heeft geen `add_job(id=...)` in de scheduler. Dat is "
        "exact de fout die deze guard moet voorkomen -- en die de vorige, substring-gebaseerde "
        "versie niet kon zien."
    )


def test_the_scheduler_binds_the_real_broker_before_enqueuing() -> None:
    """Een planner die naar een geheugenwachtrij stuurt, ruimt niets op (ADR-036 OP-76).

    **Hoe dit gevonden is.** De blinde securityreview van 2026-08-06 mat in een echt proces:

        globale broker               : StubBroker
        cleanup_expired_hitl_tickets : StubBroker   <- de enige handhaving van de SLA van 4 uur
        cleanup_resolved_hitl_tickets: RedisBroker

    `workflow_worker.py` zet bij het importeren een `StubBroker` en wisselt hem pas om zodra
    `get_redis_broker()` wordt aangeroepen. Het scheduler-proces deed dat niet, dus elke `.send()`
    verdween in een wachtrij binnen datzelfde proces -- met de logregel "enqueued successfully"
    erachteraan. Precies het patroon van OP-64, een laag dieper.

    Deze test leest de bron in plaats van de broker te instantieren: dat laatste vraagt een echte
    Redis en een DATABASE_URL, en een architectuurtest hoort geen infrastructuur nodig te hebben.
    Het GEDRAG is met de hand geverifieerd (StubBroker -> RedisBroker na de aanroep).
    """
    source = SCHEDULER.read_text(encoding="utf-8")

    assert "get_redis_broker" in source, (
        f"{SCHEDULER.name} haalt de echte broker nergens op. Zonder die aanroep blijft de globale "
        "broker de StubBroker die `workflow_worker` bij het importeren zet, en verdwijnt elke "
        "geplande opdracht in een geheugenwachtrij binnen het scheduler-proces zelf -- inclusief "
        "de enige handhaving van de SLA op openstaande tickets."
    )

    tree = ast.parse(source)
    called_in_start = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
            "start_scheduler",
            "_bind_the_real_broker",
        ):
            if _roept_aan(node, "get_redis_broker"):
                called_in_start = True

    assert called_in_start, (
        "`get_redis_broker` staat wel in het bestand maar wordt niet aangeroepen vanuit "
        "`start_scheduler` of `_bind_the_real_broker`. Een import zonder aanroep wisselt de broker "
        "niet om."
    )


#: CD-workflows die een worker-image deployen maar (nog) geen planner starten, met datum en reden.
#:
#: Productie heeft geen planner-app. Dat is geen omissie maar een openstaand KOSTENBESLUIT van
#: Rakesh: het is een tweede altijd-draaiende Container App. Zolang dat besluit niet is genomen
#: draait in productie GEEN enkele retentie-actor -- tickets blijven `pending` en houden dus hun
#: rauwe modelparameters, en niets wordt ooit verwijderd. Dat mag niet stil blijven, en dus staat
#: het hier met een staleness-test eronder in plaats van dat de guard er blind voor is.
#: Leeg sinds 2026-08-08: Rakesh heeft het kostenbesluit genomen en productie heeft nu ook een
#: planner. De staleness-test hieronder zou deze regel toch hebben laten omvallen -- dat is precies
#: waarvoor die bestaat, zodat een uitzondering niet stil kan blijven staan nadat hij is opgelost.
KNOWN_WORKFLOWS_WITHOUT_SCHEDULER: dict[str, str] = {}


def _workflows_deploying_a_worker() -> dict[str, bool]:
    """Per CD-workflow: deployt hij een worker-image, en start hij ook de planner?

    **Waarom per WORKFLOW en niet globaal (ADR-036 OP-91).** De eerste versie voegde de
    compose-bestanden en de CD-workflows samen tot een enkele lijst en eiste dat die niet leeg was.
    Een blinde review verwijderde daarop de complete `Deploy scheduler`-stap uit `cd-staging.yml` en
    de guard bleef GROEN -- `docker-compose.prod.yml` hield hem overeind. Dat is het eigen argument
    van deze guard omgekeerd toegepast: Azure draait geen compose, dus een planner in een
    compose-bestand zegt niets over de cloud.
    """
    resultaat: dict[str, bool] = {}
    for commando in containerapp_commandos():
        if "/worker:" not in commando.image():
            continue
        resultaat.setdefault(commando.workflow, False)
        if _start_de_planner(commando):
            resultaat[commando.workflow] = True
    return resultaat


def test_the_scan_finds_worker_deploying_workflows() -> None:
    """Vangnet op een EXPLICIETE verzameling, niet op "de lijst is niet leeg" (ADR-036 HIGH-3).

    "Niet leeg" is hier aantoonbaar te zwak. Hernoem `cd-production.yml` naar `.yaml`, of naar
    iets dat niet met `cd-` begint, en die workflow verdwijnt STIL uit de scan terwijl
    `cd-staging.yml` het vangnet groen houdt. Dat is dezelfde faalvorm als OP-91 zelf, een laag
    hoger: er werd geteld in plaats van benoemd.
    """
    gevonden = _workflows_deploying_a_worker()

    ontbreekt = sorted({"cd-production.yml", "cd-staging.yml"} - set(gevonden))
    assert not ontbreekt, (
        f"Deze CD-workflows deployen geen worker-image meer: {ontbreekt}. Gevonden: "
        f"{sorted(gevonden)}. Is het bestand hernoemd (let op: `.yaml` en namen zonder "
        "`cd-`-voorvoegsel vallen buiten de scan), of is de image-naam veranderd? Zolang een "
        "workflow hier ontbreekt bewaakt de test hieronder daar niets."
    )


def test_every_deployed_environment_starts_a_scheduler() -> None:
    """Elke omgeving met een worker heeft ook een planner nodig."""
    zonder = sorted(
        naam
        for naam, heeft_planner in _workflows_deploying_a_worker().items()
        if not heeft_planner and naam not in KNOWN_WORKFLOWS_WITHOUT_SCHEDULER
    )

    assert not zonder, (
        f"Deze omgevingen deployen wel een worker maar starten geen planner: {zonder}.\n\n"
        "Daar draait dan GEEN enkele retentie-actor: HITL-tickets blijven `pending` en houden hun "
        "rauwe modelparameters, en niets wordt ooit verwijderd. Er komt geen foutmelding wanneer "
        "iets NIET gebeurt. Voeg een scheduler-stap toe, of zet de workflow met datum en reden in "
        "KNOWN_WORKFLOWS_WITHOUT_SCHEDULER."
    )


def test_known_workflows_without_scheduler_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET eruit."""
    opgelost = sorted(
        naam
        for naam, heeft_planner in _workflows_deploying_a_worker().items()
        if heeft_planner and naam in KNOWN_WORKFLOWS_WITHOUT_SCHEDULER
    )

    assert not opgelost, (
        f"Deze workflows staan in KNOWN_WORKFLOWS_WITHOUT_SCHEDULER maar starten inmiddels wel een "
        f"planner: {opgelost}. Haal ze uit de lijst; anders suggereert die lijst een openstaand "
        "kostenbesluit dat allang genomen is."
    )
