"""De HR-termijnactor staat echt ingepland, en een worker laadt hem -- HR-pilot dag 4.

Waarom een eigen guard: `test_debiteuren_actors_are_scheduled.py` en
`test_cleanup_actors_are_scheduled.py` bewaken alleen de actors uit hun eigen module. Een actor in
`src/core/tasks/hr_termijn_tasks.py` valt daar buiten, en `signaleer_hr_termijnen` kon dus bestaan
zonder ooit te draaien: er komt geen foutmelding wanneer iets NIET gebeurt, en HR zou nooit een
melding krijgen.

**Wat bewaakt wordt** (alle controles op BRONTEKST, via `ast`, zodat een naam in een comment of
docstring niet telt):

1. de actor bestaat: een functie met een `@dramatiq.actor`-decorator in `hr_termijn_tasks.py`;
2. de scheduler heeft een `add_job(..., id="signaleer_hr_termijnen")`;
3. de runner die dat `add_job` aanroept doet `signaleer_hr_termijnen.send()` (een `Call`);
4. `src/workers/actors.py` importeert de actor, zodat het gedeployde workercommando hem laadt;
5. de job draait een keer per dag: een `CronTrigger` met een vast uur, zonder `*`, `*/n` of een
   dag-beperking (een meldingstaak die elke minuut draait spamt HR, een wekelijkse laat een termijn
   tot 6 dagen te lang liggen).

**Mutatiebewijs** (op kopieen van de bron, de echte boom blijft ongemoeid; beide richtingen):
de mutaties staan hieronder als testcases met een eigen naam.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_TAKEN = _REPO / "src/core/tasks/hr_termijn_tasks.py"
_SCHEDULER = _REPO / "src/workers/scheduler.py"
_ACTORS = _REPO / "src/workers/actors.py"
ACTOR = "signaleer_hr_termijnen"
RUNNER = "_run_signaleer_hr_termijnen"


def _heeft_actor(bron: str, naam: str) -> bool:
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.FunctionDef) and knoop.name == naam:
            for deco in knoop.decorator_list:
                doel = deco.func if isinstance(deco, ast.Call) else deco
                if isinstance(doel, ast.Attribute) and doel.attr == "actor":
                    return True
                if isinstance(doel, ast.Name) and doel.id == "workflow_actor":
                    return True  # ADR-036 OP-13: de wrapper die aan de workflowbroker bindt
    return False


def _add_job_calls(bron: str) -> list[ast.Call]:
    return [
        k
        for k in ast.walk(ast.parse(bron))
        if isinstance(k, ast.Call)
        and isinstance(k.func, ast.Attribute)
        and k.func.attr == "add_job"
    ]


def _job(bron: str, actor: str) -> ast.Call | None:
    for call in _add_job_calls(bron):
        for kw in call.keywords:
            if kw.arg == "id" and isinstance(kw.value, ast.Constant) and kw.value.value == actor:
                return call
    return None


def _runner_roept_send_aan(bron: str, runner: str, actor: str) -> bool:
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, (ast.AsyncFunctionDef, ast.FunctionDef)) and knoop.name == runner:
            for sub in ast.walk(knoop):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "send"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == actor
                ):
                    return True
    return False


def _job_verwijst_naar_runner(call: ast.Call, runner: str) -> bool:
    if not call.args:
        return False
    eerste = call.args[0]
    return isinstance(eerste, ast.Attribute) and eerste.attr == runner


def _is_dagelijks(call: ast.Call) -> bool:
    """Een `CronTrigger` met een vast uur en zonder dag-beperking."""
    for kw in call.keywords:
        if kw.arg != "trigger" or not isinstance(kw.value, ast.Call):
            continue
        trigger = kw.value
        if not (isinstance(trigger.func, ast.Name) and trigger.func.id == "CronTrigger"):
            return False
        opties = {k.arg: k.value for k in trigger.keywords}
        uur = opties.get("hour")
        beperkt = any(naam in opties for naam in ("day", "day_of_week", "week", "month"))
        return isinstance(uur, ast.Constant) and isinstance(uur.value, int) and not beperkt
    return False


def _importeert(bron: str, naam: str) -> bool:
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.ImportFrom) and any(a.name == naam for a in knoop.names):
            return True
    return False


# --- de echte boom -------------------------------------------------------------------------


def test_de_actor_bestaat() -> None:
    assert _heeft_actor(_TAKEN.read_text(encoding="utf-8"), ACTOR)


def test_de_scheduler_heeft_een_job_voor_de_actor() -> None:
    assert _job(_SCHEDULER.read_text(encoding="utf-8"), ACTOR) is not None


def test_de_job_start_de_juiste_runner() -> None:
    job = _job(_SCHEDULER.read_text(encoding="utf-8"), ACTOR)
    assert job is not None and _job_verwijst_naar_runner(job, RUNNER)


def test_de_runner_stuurt_de_actor_echt_weg() -> None:
    assert _runner_roept_send_aan(_SCHEDULER.read_text(encoding="utf-8"), RUNNER, ACTOR)


def test_de_worker_laadt_de_actor() -> None:
    assert _importeert(_ACTORS.read_text(encoding="utf-8"), ACTOR)


def test_de_job_draait_een_keer_per_dag() -> None:
    job = _job(_SCHEDULER.read_text(encoding="utf-8"), ACTOR)
    assert job is not None and _is_dagelijks(job)


# --- de controles zelf, op gemuteerde kopieen (beide richtingen) --------------------------


_BRON = """
class S:
    def setup(self):
        _sched.add_job(
            self._run_signaleer_hr_termijnen,
            trigger=CronTrigger(hour=7, minute=0, timezone=TZ),
            id="signaleer_hr_termijnen",
        )

    async def _run_signaleer_hr_termijnen(self):
        from src.core.tasks.hr_termijn_tasks import signaleer_hr_termijnen

        signaleer_hr_termijnen.send()
"""

_TRIGGER = "CronTrigger(hour=7, minute=0, timezone=TZ)"


@pytest.mark.parametrize(
    ("naam", "vervang", "verwacht_job", "verwacht_send", "verwacht_dagelijks"),
    [
        ("ongewijzigd", ("", ""), True, True, True),
        ("job weg", ('id="signaleer_hr_termijnen"', 'id="iets_anders"'), False, True, False),
        (
            "send weg, naam blijft in een comment",
            ("signaleer_hr_termijnen.send()", "# signaleer_hr_termijnen.send()"),
            True,
            False,
            True,
        ),
        ("elke minuut", (_TRIGGER, 'CronTrigger(minute="*")'), True, True, False),
        ("elke zes uur", (_TRIGGER, 'CronTrigger(hour="*/6")'), True, True, False),
        (
            "alleen op maandag",
            (_TRIGGER, 'CronTrigger(hour=7, day_of_week="mon")'),
            True,
            True,
            False,
        ),
        ("LEGITIEM: ander uur", ("hour=7", "hour=9"), True, True, True),
    ],
)
def test_de_controles_zien_elke_mutatie(
    naam: str,
    vervang: tuple[str, str],
    verwacht_job: bool,
    verwacht_send: bool,
    verwacht_dagelijks: bool,
) -> None:
    oud, nieuw = vervang
    bron = _BRON.replace(oud, nieuw) if oud else _BRON

    job = _job(bron, ACTOR)

    assert (job is not None) == verwacht_job, naam
    assert _runner_roept_send_aan(bron, RUNNER, ACTOR) == verwacht_send, naam
    assert (job is not None and _is_dagelijks(job)) == verwacht_dagelijks, naam


@pytest.mark.parametrize(
    ("bron", "verwacht"),
    [
        ("from src.core.tasks.hr_termijn_tasks import signaleer_hr_termijnen\n", True),
        ("# from src.core.tasks.hr_termijn_tasks import signaleer_hr_termijnen\n", False),
        ("from src.core.tasks.hr_termijn_tasks import iets_anders\n", False),
    ],
)
def test_de_importcontrole_zoekt_een_echte_import(bron: str, verwacht: bool) -> None:
    assert _importeert(bron, ACTOR) is verwacht
