"""Geen enkele `_run_*`-methode van `TaskScheduler` mag een verboden stille-fout-vorm hebben.

Verboden vormen:
  1. `except`-tak zonder `raise` -- APScheduler ziet de methode als geslaagd.
  2. `contextlib.suppress(...)` -- onderdrukt de uitzondering volledig.
  3. `async with best_effort(...)` -- best_effort vangt en logt, maar gooit niet door.

Achtergrond (BE-WRK-001, 2026-09-26). De 16 `_run_*`-methodes hadden allemaal een
`try/except Exception` die de fout weglogde en niets teruggaf. APScheduler registreerde
de job dan als geslaagd, en de planner logde vrolijk "enqueued successfully" terwijl de
actor op een StubBroker stond of de import falend was. De listener (`_op_job_probleem`)
krijgt het foutgebeurtenis alleen als de methode UITGOOIT -- bij een swallowed exception
meldt APScheduler succes en geeft de listener nooit een signaal.

Wat deze bewaker doet: hij loopt via AST door de klasse, vindt elke directe methode
waarvan de naam met `_run_` begint, en kijkt of die methode een verboden stille-fout-vorm
bevat. De methode-selectie gebruikt `knoop.body` (niet `ast.walk`) zodat geneste
klassen of hulpfuncties met `_run_`-prefix er niet in vallen.

`_heeft_raise()` gebruikt expliciete recursie (niet `ast.walk`) om geneste
FunctionDef/AsyncFunctionDef-bodies te overslaan. `ast.walk()` respecteert `continue`
niet: hij levert ook de kinderen van een overgeslagen knoop (valkuil_ast_walk_duikt_functiebodies_in).

Mutatiebewijs (2026-09-26, scripts/mutation_harness.py, alle drie UITGEVOERD):
  P1 voorwaarts  -- `try: ... except Exception: pass` in _run_pack_health_job: ROOD.
  P2 tegenrichting -- `try: ... except Exception: raise` in _run_pack_health_job: GROEN
                      (hergooien is toegestaan -- "weiger alles" is geen geldige implementatie).
  P3 tegenrichting -- `try: ... except Exception: pass` in een vrije module-level functie
                      (niet in een _run_*-methode): GROEN (scope-selectie werkt).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEDULER = REPO_ROOT / "src" / "workers" / "scheduler.py"


def _sub_bodies(stmt: ast.stmt) -> list[list[ast.stmt]]:
    """Geeft alle statement-lijsten van een samengesteld statement, zonder functies."""
    if isinstance(stmt, (ast.If, ast.While, ast.For, ast.AsyncFor)):
        result: list[list[ast.stmt]] = [stmt.body]
        if stmt.orelse:
            result.append(stmt.orelse)
        return result
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return [stmt.body]
    if isinstance(stmt, ast.Try):
        result = [stmt.body]
        for h in stmt.handlers:
            result.append(h.body)
        if stmt.orelse:
            result.append(stmt.orelse)
        if stmt.finalbody:
            result.append(stmt.finalbody)
        return result
    return []


def _bevat_raise(stmts: Sequence[ast.stmt]) -> bool:
    """True als `stmts` een Raise bevat, maar daalt NIET af in geneste functies."""
    for stmt in stmts:
        if isinstance(stmt, ast.Raise):
            return True
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue  # Geneste functies overslaan
        for sub_body in _sub_bodies(stmt):
            if _bevat_raise(sub_body):
                return True
    return False


def _heeft_raise(handler: ast.ExceptHandler) -> bool:
    """True als de handler een Raise bevat buiten geneste functiedefinities."""
    return _bevat_raise(handler.body)


def _bevat_context_suppress(stmts: Sequence[ast.stmt]) -> bool:
    """True als `stmts` een `contextlib.suppress(...)` als contextmanager gebruikt."""
    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call):
                    func = ctx.func
                    if (isinstance(func, ast.Attribute) and func.attr == "suppress") or (
                        isinstance(func, ast.Name) and func.id == "suppress"
                    ):
                        return True
        for sub_body in _sub_bodies(stmt):
            if _bevat_context_suppress(sub_body):
                return True
    return False


def _bevat_best_effort(stmts: Sequence[ast.stmt]) -> bool:
    """True als `stmts` een `async with best_effort(...)` gebruikt."""
    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(stmt, ast.AsyncWith):
            for item in stmt.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call):
                    func = ctx.func
                    if (isinstance(func, ast.Name) and func.id == "best_effort") or (
                        isinstance(func, ast.Attribute) and func.attr == "best_effort"
                    ):
                        return True
        for sub_body in _sub_bodies(stmt):
            if _bevat_best_effort(sub_body):
                return True
    return False


def _vind_overtreders() -> list[str]:
    """Methode-namen die een verboden stille-fout-vorm bevatten."""
    bron = SCHEDULER.read_text(encoding="utf-8")
    boom = ast.parse(bron, filename=str(SCHEDULER))

    methodes_gescand: list[str] = []
    overtreders: list[str] = []

    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.ClassDef) or knoop.name != "TaskScheduler":
            continue
        # Gebruik knoop.body (niet ast.walk) zodat alleen DIRECTE methodes worden geselecteerd.
        # Als _run_*-methodes naar module-niveau verhuizen, vindt deze guard 0 methodes --
        # dan faalt de count-assertie hieronder en is de guard niet ongemerkt hol.
        for methode in knoop.body:
            if not isinstance(methode, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not methode.name.startswith("_run_"):
                continue
            methodes_gescand.append(methode.name)

            # Verboden vorm 1: except zonder raise
            for try_knoop in ast.walk(methode):
                if not isinstance(try_knoop, ast.Try):
                    continue
                for handler in try_knoop.handlers:
                    if not _heeft_raise(handler):
                        overtreders.append(methode.name)
                        break

            # Verboden vorm 2: contextlib.suppress
            if _bevat_context_suppress(methode.body):
                overtreders.append(methode.name)

            # Verboden vorm 3: async with best_effort
            if _bevat_best_effort(methode.body):
                overtreders.append(methode.name)

    assert len(methodes_gescand) >= 16, (
        f"De scan vond maar {len(methodes_gescand)} `_run_*`-methodes in TaskScheduler. "
        f"Gemeten 2026-09-26: 16. Minder betekent dat methodes zijn hernoemd, naar "
        f"module-niveau zijn verplaatst, of dat de klasse-selectie kapot is -- "
        f"deze bewaker toetst dan minder dan verwacht."
    )
    return sorted(set(overtreders))


@pytest.mark.architecture
def test_geen_run_methode_heeft_stille_except() -> None:
    """Elke `_run_*`-methode van TaskScheduler mag fouten alleen opvangen als hij ze hergooit.

    Een stille except (geen raise, contextlib.suppress, of best_effort) maakt APScheduler
    blind voor de fout: de job lijkt geslaagd terwijl de actor niets deed.
    De listener `_op_job_probleem` krijgt het signaal alleen als de methode *uitgooit*.
    """
    overtreders = _vind_overtreders()
    assert not overtreders, (
        "Deze `_run_*`-methodes hebben een verboden stille-fout-vorm (except zonder raise, "
        "contextlib.suppress of async with best_effort). "
        "Verwijder de try/except volledig of voeg `raise` toe:\n  " + "\n  ".join(overtreders)
    )
