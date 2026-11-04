"""De debiteuren-actors staan echt ingepland, en een worker laadt ze -- Keten B dag 2.

Waarom naast `test_cleanup_actors_are_scheduled.py`: die guard bewaakt ALLEEN de actors uit
`governance/retention_cleanup.py` (`_actor_names()` leest dat ene bestand). Een nieuwe actor in
`src/core/tasks/debiteuren_tasks.py` valt er dus buiten, en `verstuur_klare_berichten` zou kunnen
bestaan zonder ooit te draaien: de brief wordt klaargezet, niet verstuurd, en er komt geen
foutmelding wanneer iets NIET gebeurt. De bestaande guard is daarom niet verzwakt maar ook niet
voldoende; deze breidt de bewaking uit naar de nieuwe module.

**Wat bewaakt wordt, per element van `DEBITEUREN_ACTORS`** (dag 3 voegt `volg_debiteuren_op` toe):

1. de actor bestaat in `src/core/tasks/debiteuren_tasks.py` (AST: een functie met een
   `@dramatiq.actor`-decorator, niet een naam in een docstring);
2. de scheduler heeft een `add_job(..., id="<actor>")`;
3. de runner die dat `add_job` aanroept doet `<actor>.send()` (AST: een `Call`), en niet iets
   anders met dezelfde naam in een comment;
4. `src/workers/actors.py` importeert de actor, zodat het gedeployde workercommando
   (`dramatiq ... src.workers.actors`) hem laadt;
5. `verstuur_klare_berichten` draait elke minuut (besluit 1 van de brief);
6. `volg_debiteuren_op` draait een keer per dag (besluit 4 van de brief): een `CronTrigger` met
   een vast uur (geen `*`, geen `*/6`, geen `day`/`day_of_week`-beperking) of een
   `IntervalTrigger` van 1 dag / 24 uur. Een opvolging die elke minuut draait is geen fout in
   de uitkomst (escaleren is eenmalig) maar wel in de bedoeling; een die wekelijks draait laat
   een dossier tot 6 dagen te lang liggen. Dag 3 voegde 5 en 6 toe aan een bestaande guard:
   `verstuur_klare_berichten` blijft op dezelfde manier bewaakt als op dag 2 (de mutatierijen
   hieronder zijn alleen UITGEBREID).
7. Elke actor in `DEBITEUREN_ACTORS` heeft een benoemd ritme (`ELKE_MINUUT` of `ELKE_DAG`): een
   actor zonder ritme is niet bewaakt op frequentie.

**Hoe de guard zelf getoetst is.** De controlefuncties nemen BRONTEKST, zodat de tests onderaan ze
op gemuteerde kopieen kunnen draaien zonder iets in `src/` aan te raken (beide richtingen):

| Mutatie op een kopie van `scheduler.py` | Verwacht |
| --- | --- |
| `add_job` voor de actor weg, naam blijft in de runner | ROOD |
| runner roept `.send()` niet meer aan, naam blijft in een comment | ROOD |
| job loopt op de VERKEERDE actor (`id` anders, send op een andere actor) | ROOD |
| interval wordt dagelijks (`CronTrigger(hour=3)`) | ROOD |
| LEGITIEM: `IntervalTrigger(minutes=1)` in plaats van `CronTrigger(minute="*")` | GROEN |
| LEGITIEM: een ongerelateerde extra job erbij | GROEN |
| dag 3: `volg_debiteuren_op` loopt `CronTrigger(minute="*")` (elke minuut) | ROOD |
| dag 3: `volg_debiteuren_op` loopt `CronTrigger(hour="*/6")` | ROOD |
| dag 3: `volg_debiteuren_op` loopt `CronTrigger(hour=4, day_of_week="mon")` (wekelijks) | ROOD |
| dag 3: `volg_debiteuren_op` loopt `IntervalTrigger(hours=1)` | ROOD |
| dag 3: `volg_debiteuren_op`-job weg, naam blijft in de runner | ROOD |
| dag 3: runner van `volg_debiteuren_op` roept `.send()` niet aan (comment) | ROOD |
| dag 3 LEGITIEM: `CronTrigger(hour=4, minute=15)` | GROEN |
| dag 3 LEGITIEM: `IntervalTrigger(days=1)` en `IntervalTrigger(hours=24)` | GROEN |

En op `actors.py`: import weg -> ROOD; import aanwezig -> GROEN. De echte-boom-tests zijn rood tot
de bouwer de actor, de job en de import heeft.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "src/core/tasks/debiteuren_tasks.py"
SCHEDULER = REPO_ROOT / "src/workers/scheduler.py"
WORKER_ACTORS = REPO_ROOT / "src/workers/actors.py"
TASKS_MODULE = "src.core.tasks.debiteuren_tasks"

#: Expliciet benoemd, geen telling: een actor die uit deze lijst verdwijnt bewaakt niemand meer.
DEBITEUREN_ACTORS: tuple[str, ...] = ("verstuur_klare_berichten", "volg_debiteuren_op")

#: Actors die elke minuut moeten lopen.
ELKE_MINUUT: frozenset[str] = frozenset({"verstuur_klare_berichten"})

#: Actors die een keer per dag moeten lopen.
ELKE_DAG: frozenset[str] = frozenset({"volg_debiteuren_op"})


def _is_actor_decorator(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Call):
        return _is_actor_decorator(decorator.func)
    # `workflow_actor` is de wrapper die de actor aan de workflowbroker bindt (ADR-036 OP-13); hij telt als actor.
    if isinstance(decorator, ast.Attribute):
        return decorator.attr in ("actor", "workflow_actor")
    return isinstance(decorator, ast.Name) and decorator.id in ("actor", "workflow_actor")


def _gedefinieerde_actors(bron: str) -> set[str]:
    tree = ast.parse(bron)
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_actor_decorator(d) for d in node.decorator_list)
    }


def _add_job_voor(tree: ast.AST, actor: str) -> ast.Call | None:
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_job":
            continue
        for kw in node.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant) and kw.value.value == actor:
                return node
    return None


def _methode(tree: ast.AST, naam: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == naam:
            return node
    return None


def _verstuurt(functie: ast.AST, actor: str) -> bool:
    """Doet deze functie `<actor>.send(...)` -- een echte aanroep, geen tekst."""
    for node in ast.walk(functie):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "send"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == actor
        ):
            return True
    return False


def _kw(call: ast.Call, naam: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == naam), None)


def _constante(knoop: ast.expr | None) -> object:
    return knoop.value if isinstance(knoop, ast.Constant) else None


def _loopt_elke_minuut(trigger: ast.expr | None) -> bool:
    if not (isinstance(trigger, ast.Call) and isinstance(trigger.func, ast.Name)):
        return False
    if trigger.func.id == "IntervalTrigger":
        minuten = _constante(_kw(trigger, "minutes"))
        seconden = _constante(_kw(trigger, "seconds"))
        return minuten == 1 or seconden == 60
    if trigger.func.id == "CronTrigger":
        if _kw(trigger, "hour") is not None or _kw(trigger, "day") is not None:
            return False
        minuut = _constante(_kw(trigger, "minute"))
        return minuut in (None, "*", "*/1")
    return False


def _is_vast_getal(knoop: ast.expr | None) -> bool:
    """Een letterlijk getal (`4` of `"4"`), geen `*`, geen `*/6`, geen reeks."""
    waarde = _constante(knoop)
    if isinstance(waarde, bool):
        return False
    return isinstance(waarde, int) or (isinstance(waarde, str) and waarde.isdigit())


def _afwezig_of_vast(call: ast.Call, naam: str) -> bool:
    kw = _kw(call, naam)
    return kw is None or _is_vast_getal(kw)


def _loopt_een_keer_per_dag(trigger: ast.expr | None) -> bool:
    if not (isinstance(trigger, ast.Call) and isinstance(trigger.func, ast.Name)):
        return False
    if trigger.func.id == "IntervalTrigger":
        # Alleen `days=1` of `hours=24`, en geen andere eenheid erbij.
        if any(_kw(trigger, eenheid) is not None for eenheid in ("weeks", "minutes", "seconds")):
            return False
        dagen = _constante(_kw(trigger, "days"))
        uren = _constante(_kw(trigger, "hours"))
        return (dagen == 1 and uren is None) or (uren == 24 and dagen is None)
    if trigger.func.id == "CronTrigger":
        # Een beperking op dag, weekdag, week, maand of jaar maakt het geen dagelijkse job meer.
        if any(
            _kw(trigger, veld) is not None
            for veld in ("day", "day_of_week", "week", "month", "year")
        ):
            return False
        return _is_vast_getal(_kw(trigger, "hour")) and _afwezig_of_vast(trigger, "minute")
    return False


def _scheduler_gebreken(bron: str, actor: str) -> list[str]:
    """Wat ontbreekt er in deze scheduler-bron voor `actor`? Leeg is goed."""
    tree = ast.parse(bron)
    job = _add_job_voor(tree, actor)
    if job is None:
        return [f"geen add_job(id={actor!r}) in de scheduler"]
    gebreken: list[str] = []
    runner = job.args[0] if job.args else None
    if not (isinstance(runner, ast.Attribute) and isinstance(runner.value, ast.Name)):
        gebreken.append("de job krijgt geen `self.<methode>` als eerste argument")
    else:
        functie = _methode(tree, runner.attr)
        if functie is None:
            gebreken.append(f"de runner {runner.attr!r} bestaat niet in de scheduler")
        elif not _verstuurt(functie, actor):
            gebreken.append(f"de runner {runner.attr!r} roept {actor}.send() niet aan")
    if actor in ELKE_MINUUT and not _loopt_elke_minuut(_kw(job, "trigger")):
        gebreken.append("de job loopt niet elke minuut")
    if actor in ELKE_DAG and not _loopt_een_keer_per_dag(_kw(job, "trigger")):
        gebreken.append("de job loopt niet een keer per dag")
    return gebreken


def _worker_laadt(bron: str, actor: str) -> bool:
    for node in ast.walk(ast.parse(bron)):
        if isinstance(node, ast.ImportFrom) and node.module == TASKS_MODULE:
            if any(alias.name == actor for alias in node.names):
                return True
    return False


# --- de echte boom -----------------------------------------------------------------------


def test_the_scan_names_the_actors_it_guards() -> None:
    """Vangnet: de guard bewaakt een benoemde verzameling, en die is niet leeg."""
    assert {"verstuur_klare_berichten", "volg_debiteuren_op"} <= set(DEBITEUREN_ACTORS)


def test_every_guarded_actor_has_a_stated_rhythm() -> None:
    """Een actor zonder ritme wordt niet op frequentie bewaakt (en zou stilletjes elke minuut of
    nooit kunnen lopen)."""
    zonder = [a for a in DEBITEUREN_ACTORS if a not in ELKE_MINUUT | ELKE_DAG]

    assert zonder == [], f"geen ritme benoemd voor: {zonder}"


@pytest.mark.parametrize("actor", DEBITEUREN_ACTORS)
def test_the_actor_is_defined_in_the_tasks_module(actor: str) -> None:
    assert TASKS.exists(), f"{TASKS.relative_to(REPO_ROOT)} bestaat niet"
    assert actor in _gedefinieerde_actors(TASKS.read_text(encoding="utf-8")), (
        f"`{actor}` is geen @dramatiq.actor in {TASKS.name}"
    )


@pytest.mark.parametrize("actor", DEBITEUREN_ACTORS)
def test_the_actor_is_scheduled_and_dispatched(actor: str) -> None:
    gebreken = _scheduler_gebreken(SCHEDULER.read_text(encoding="utf-8"), actor)

    assert not gebreken, f"{SCHEDULER.name}, {actor}: {gebreken}"


@pytest.mark.parametrize("actor", DEBITEUREN_ACTORS)
def test_the_worker_loads_the_actor(actor: str) -> None:
    """Een `.send()` naar een actor die geen worker laadt schrijft in het niets (OP-158)."""
    assert _worker_laadt(WORKER_ACTORS.read_text(encoding="utf-8"), actor), (
        f"{WORKER_ACTORS.name} importeert {actor} niet uit {TASKS_MODULE}; de gedeployde worker "
        "kent hem dan niet en elke geplande opdracht blijft in de wachtrij liggen."
    )


# --- de guard getoetst op gemuteerde kopieen (geen echte bestanden geraakt) --------------

_GOED = """
class Planner:
    def start(self, _sched):
        _sched.add_job(
            self._run_verstuur,
            trigger=CronTrigger(minute="*"),
            id="verstuur_klare_berichten",
            replace_existing=True,
        )
        _sched.add_job(
            self._run_volg,
            trigger=CronTrigger(hour=4, minute=15),
            id="volg_debiteuren_op",
            replace_existing=True,
        )
        _sched.add_job(
            self._run_andere, trigger=CronTrigger(hour=3), id="andere_job", replace_existing=True
        )

    async def _run_verstuur(self):
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten

        verstuur_klare_berichten.send()

    async def _run_volg(self):
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        volg_debiteuren_op.send()

    async def _run_andere(self):
        from src.workers.actors import andere_actor

        andere_actor.send()
"""


def test_guard_accepts_a_correct_scheduler() -> None:
    assert _scheduler_gebreken(_GOED, "verstuur_klare_berichten") == []


def test_guard_catches_a_missing_add_job_even_if_the_name_stays_in_the_runner() -> None:
    kapot = _GOED.replace('id="verstuur_klare_berichten"', 'id="iets_anders"')

    assert _scheduler_gebreken(kapot, "verstuur_klare_berichten")


def test_guard_catches_a_runner_that_no_longer_sends_even_if_the_name_is_in_a_comment() -> None:
    kapot = _GOED.replace(
        "verstuur_klare_berichten.send()", "pass  # verstuur_klare_berichten.send()"
    )

    assert _scheduler_gebreken(kapot, "verstuur_klare_berichten")


def test_guard_catches_a_job_that_sends_the_wrong_actor() -> None:
    kapot = _GOED.replace("verstuur_klare_berichten.send()", "andere_actor.send()")

    assert _scheduler_gebreken(kapot, "verstuur_klare_berichten")


def test_guard_catches_a_daily_instead_of_a_per_minute_job() -> None:
    kapot = _GOED.replace('CronTrigger(minute="*")', "CronTrigger(hour=3)", 1)

    assert _scheduler_gebreken(kapot, "verstuur_klare_berichten")


def test_guard_accepts_an_interval_trigger_of_one_minute() -> None:
    """Andere kant op: een gelijkwaardige vorm mag niet worden afgewezen."""
    anders = _GOED.replace('CronTrigger(minute="*")', "IntervalTrigger(minutes=1)", 1)

    assert _scheduler_gebreken(anders, "verstuur_klare_berichten") == []


def test_guard_rejects_an_interval_of_five_minutes() -> None:
    kapot = _GOED.replace('CronTrigger(minute="*")', "IntervalTrigger(minutes=5)", 1)

    assert _scheduler_gebreken(kapot, "verstuur_klare_berichten")


_VOLG = "volg_debiteuren_op"
_DAGELIJKS = "CronTrigger(hour=4, minute=15)"


def test_guard_accepts_a_correct_daily_job() -> None:
    assert _scheduler_gebreken(_GOED, _VOLG) == []


@pytest.mark.parametrize(
    "trigger",
    [
        'CronTrigger(minute="*")',
        'CronTrigger(hour="*/6")',
        'CronTrigger(hour="*")',
        'CronTrigger(hour=4, day_of_week="mon")',
        "CronTrigger(hour=4, day=1)",
        "CronTrigger(minute=15)",
        "IntervalTrigger(hours=1)",
        "IntervalTrigger(minutes=1)",
        "IntervalTrigger(days=7)",
        "IntervalTrigger(weeks=1)",
    ],
    ids=[
        "elke_minuut",
        "elke_zes_uur",
        "elk_uur",
        "wekelijks_via_weekdag",
        "maandelijks_via_dag",
        "elk_uur_via_alleen_minuut",
        "interval_een_uur",
        "interval_een_minuut",
        "interval_zeven_dagen",
        "interval_een_week",
    ],
)
def test_guard_catches_a_followup_job_that_does_not_run_once_a_day(trigger: str) -> None:
    kapot = _GOED.replace(_DAGELIJKS, trigger, 1)

    assert _scheduler_gebreken(kapot, _VOLG), f"niet gevangen: {trigger}"


@pytest.mark.parametrize(
    "trigger",
    [
        "CronTrigger(hour=4, minute=15)",
        "CronTrigger(hour=4)",
        'CronTrigger(hour="4", minute="0")',
        "IntervalTrigger(days=1)",
        "IntervalTrigger(hours=24)",
    ],
    ids=["uur_en_minuut", "alleen_uur", "uur_als_tekst", "interval_een_dag", "interval_24_uur"],
)
def test_guard_accepts_every_legitimate_daily_form(trigger: str) -> None:
    """Andere kant op: gelijkwaardige dagelijkse vormen mogen niet worden afgewezen."""
    anders = _GOED.replace(_DAGELIJKS, trigger, 1)

    assert _scheduler_gebreken(anders, _VOLG) == []


def test_guard_catches_a_missing_followup_job_even_if_the_name_stays_in_the_runner() -> None:
    kapot = _GOED.replace(f'id="{_VOLG}"', 'id="iets_anders"')

    assert _scheduler_gebreken(kapot, _VOLG)


def test_guard_catches_a_followup_runner_that_no_longer_sends() -> None:
    kapot = _GOED.replace(f"{_VOLG}.send()", f"pass  # {_VOLG}.send()")

    assert _scheduler_gebreken(kapot, _VOLG)


def test_the_daily_rule_does_not_change_the_per_minute_verdict_for_the_sender() -> None:
    """Andere kant op: een dagelijkse job voor de VERZENDER blijft fout, een per-minuut-job voor
    de opvolger ook; beide regels gelden per actor, niet voor allebei."""
    verzender_dagelijks = _GOED.replace('CronTrigger(minute="*")', _DAGELIJKS, 1)
    opvolger_per_minuut = _GOED.replace(_DAGELIJKS, 'CronTrigger(minute="*")', 1)

    assert _scheduler_gebreken(verzender_dagelijks, "verstuur_klare_berichten")
    assert _scheduler_gebreken(opvolger_per_minuut, _VOLG)


def test_guard_sees_an_actor_only_when_it_is_decorated() -> None:
    bron = (
        "import dramatiq\n\n"
        '@dramatiq.actor(queue_name="x")\nasync def echt(): ...\n\n'
        'def nep():\n    """@dramatiq.actor verstuur_klare_berichten"""\n'
    )

    assert _gedefinieerde_actors(bron) == {"echt"}


def test_guard_sees_the_worker_import_only_as_a_real_import() -> None:
    goed = f"from {TASKS_MODULE} import verstuur_klare_berichten  # noqa: F401\n"
    commentaar = f"# from {TASKS_MODULE} import verstuur_klare_berichten\n"

    assert _worker_laadt(goed, "verstuur_klare_berichten")
    assert not _worker_laadt(commentaar, "verstuur_klare_berichten")
