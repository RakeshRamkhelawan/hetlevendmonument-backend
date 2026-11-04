"""De opruiming van bonnen na 30 dagen draait ook echt (bonlezer dag 4).

Een opruimtaak die niet is ingepland, of in een worker staat die het uploadvolume niet ziet, doet niets en
meldt niets: de bonnen blijven dan staan terwijl de klant leest dat ze na 30 dagen weg zijn. Deze guard leest
de STRUCTUUR (AST en YAML), geen tekst.

Bewaakte verzamelingen (benoemd, niet afgeleid):

- de scheduler: een `add_job` met `id="ruim_bonnen_op"` en een trigger met een tijdzone;
- de runner `_run_ruim_bonnen_op` in de scheduler: importeert de actor en roept `.send()` aan;
- `src/workers/actors.py`: laadt de actor, zodat de worker hem kent;
- `docker-compose.yml`: de dienst die de actor draait (`workflow-worker`) ziet het uploadvolume SCHRIJFBAAR
  en kent de uploadmap; de scheduler zelf heeft het volume niet (die zet alleen in de wachtrij);
- de actor importeert de bonlezer-worker NIET (die maakt een eigen broker aan bij het importeren).

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
SCHEDULER = REPO / "src" / "workers" / "scheduler.py"
ACTORS = REPO / "src" / "workers" / "actors.py"
ACTOR_MODULE = REPO / "src" / "core" / "tasks" / "bonnen_opruimen.py"
COMPOSE = REPO / "docker-compose.yml"
JOB_ID = "ruim_bonnen_op"
RUNNER = "_run_ruim_bonnen_op"
UITVOERDER = "workflow-worker"
VOLUME = "bonlezer_uploads:/data/bonnen"


def _boom(pad: Path) -> ast.Module:
    return ast.parse(pad.read_text(encoding="utf-8"))


def _add_job_calls(boom: ast.Module) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(boom)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add_job"
    ]


def _kw(call: ast.Call, naam: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == naam), None)


def _job() -> ast.Call:
    for call in _add_job_calls(_boom(SCHEDULER)):
        waarde = _kw(call, "id")
        if isinstance(waarde, ast.Constant) and waarde.value == JOB_ID:
            return call
    raise AssertionError(f"de scheduler plant geen job met id={JOB_ID!r}")


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]  # type: ignore[no-any-return]


def test_the_scheduler_plans_the_cleanup() -> None:
    assert _job() is not None


def test_the_job_has_a_cron_trigger_with_a_timezone() -> None:
    trigger = _kw(_job(), "trigger")

    assert (
        isinstance(trigger, ast.Call)
        and getattr(trigger.func, "id", "") == "CronTrigger"
        and _kw(trigger, "timezone") is not None
    )


def test_the_job_runs_the_runner_of_the_cleanup() -> None:
    job = _job()
    eerste = job.args[0] if job.args else None

    assert isinstance(eerste, ast.Attribute) and eerste.attr == RUNNER


def test_the_job_replaces_an_existing_one() -> None:
    """Zonder `replace_existing` faalt een herstart van de scheduler op een dubbele id."""
    waarde = _kw(_job(), "replace_existing")

    assert isinstance(waarde, ast.Constant) and waarde.value is True


def test_the_runner_imports_the_actor_and_sends_it() -> None:
    runner = next(
        n
        for n in ast.walk(_boom(SCHEDULER))
        if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == RUNNER
    )
    importeert = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "src.core.tasks.bonnen_opruimen"
        and any(a.name == "ruim_bonnen_op" for a in n.names)
        for n in ast.walk(runner)
    )
    verstuurt = any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "send"
        and getattr(n.func.value, "id", "") == "ruim_bonnen_op"
        for n in ast.walk(runner)
    )

    assert (importeert, verstuurt) == (True, True)


def test_the_worker_loads_the_actor() -> None:
    geladen = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "src.core.tasks.bonnen_opruimen"
        and any(a.name == "ruim_bonnen_op" for a in n.names)
        for n in ast.walk(_boom(ACTORS))
    )

    assert geladen


def test_the_executing_service_sees_the_upload_volume_writable() -> None:
    volumes = [str(v) for v in _compose()[UITVOERDER].get("volumes", [])]

    assert VOLUME in volumes


def test_the_executing_service_knows_the_upload_folder() -> None:
    omgeving = [str(e) for e in _compose()[UITVOERDER].get("environment", [])]

    assert "BONLEZER_UPLOAD_ROOT=/data/bonnen" in omgeving


def test_the_scheduler_service_has_no_upload_volume() -> None:
    """De scheduler zet alleen in de wachtrij; een schrijfbaar volume daar is onnodig bereik."""
    volumes = [str(v) for v in _compose()["scheduler"].get("volumes", [])]

    assert not any("bonlezer_uploads" in v for v in volumes)


def test_the_bonlezer_worker_still_only_reads_the_volume() -> None:
    volumes = [str(v) for v in _compose()["bonlezer-worker"].get("volumes", [])]

    assert volumes != [] and all(v.endswith(":ro") for v in volumes)


def test_the_cleanup_actor_does_not_import_the_bonlezer_worker() -> None:
    """De bonlezer-worker maakt bij het importeren een eigen broker aan; dat hoort niet in deze worker."""
    geimporteerd = {
        n.module
        for n in ast.walk(_boom(ACTOR_MODULE))
        if isinstance(n, ast.ImportFrom) and n.module is not None
    }

    assert "src.core.als.bonlezer.worker" not in geimporteerd
