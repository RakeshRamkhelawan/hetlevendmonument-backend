"""De workflow-engine zet en leest alleen attributen die het model echt heeft (ADR-036 OP-13, brief 2026-10-22).

**Wat er mis was.** `src/core/workflow/engine.py` schreef `execution.completed_at`, `task.completed_at` en
`task_record.error_message`, terwijl het model `finished_at` en `error_json` heet. Een SQLAlchemy-model laat een
onbekend attribuut gewoon toe: het wordt een Python-attribuut op het object en NIET opgeslagen. Gevolg (gemeten met een
echte worker): na een run waren start- en eindtijd leeg, stond de taakteller op 0 en was bij een mislukking de reden
niet te lezen. `get_execution_status` en `list_executions` lazen dezelfde niet-bestaande namen terug en gaven een
`AttributeError`. Geen test zag het, omdat geen test na een run de kolommen las.

**De regel.** In `engine.py` heeft elke `<naam>.<attribuut>` waarbij `<naam>` een modelobject is (`execution`, `exec`,
`task`, `task_record`) een attribuut dat het model kent (kolom, relatie of eigenschap). Lezen telt ook mee: een
verkeerde naam teruglezen is dezelfde fout.

**Wat dit NIET dekt:** objecten onder een andere variabelenaam, en andere bestanden. De verzameling namen is
`MODELLEN` hieronder; een nieuwe naam voegt de ontwikkelaar daar toe.

**Mutatiebewijs:** `TestDeMeting` voert `vind_overtredingen` uit op losse bronteksten, in beide richtingen: een
onbekend attribuut zetten of lezen -> gevonden; een bestaande kolom, een relatie en een eigenschap -> NIET gevonden.
De test op de echte boom was ROOD op f86091fd (`completed_at`, `error_message`).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect

from src.core.workflow.models import C7ExecutionTask, C7WorkflowExecution

ENGINE = Path("src/core/workflow/engine.py")

#: variabelenaam in de engine -> het model waar hij naar verwijst
MODELLEN: dict[str, type] = {
    "execution": C7WorkflowExecution,
    "exec": C7WorkflowExecution,
    "task": C7ExecutionTask,
    "task_record": C7ExecutionTask,
}


def _bekende_attributen(model: type) -> set[str]:
    kolommen = set(sa_inspect(model).attrs.keys())
    eigenschappen = {n for n in dir(model) if not n.startswith("_")}
    return kolommen | eigenschappen


def vind_overtredingen(bron: str, modellen: dict[str, type] | None = None) -> list[tuple[int, str]]:
    """(regel, wat) voor elk attribuut op een modelobject dat het model niet kent."""
    modellen = MODELLEN if modellen is None else modellen
    bekend = {naam: _bekende_attributen(model) for naam, model in modellen.items()}
    gevonden: list[tuple[int, str]] = []
    for knoop in ast.walk(ast.parse(bron)):
        if (
            isinstance(knoop, ast.Attribute)
            and isinstance(knoop.value, ast.Name)
            and knoop.value.id in bekend
            and knoop.attr not in bekend[knoop.value.id]
        ):
            richting = "gezet" if isinstance(knoop.ctx, ast.Store) else "gelezen"
            gevonden.append(
                (
                    knoop.lineno,
                    f"{knoop.value.id}.{knoop.attr} ({richting}) bestaat niet op het model",
                )
            )
    return gevonden


class TestDeBoom:
    def test_de_engine_bestaat_en_heeft_modelgebruik(self) -> None:
        bron = ENGINE.read_text(encoding="utf-8")

        assert (ENGINE.exists(), "execution.status" in bron, "task_record." in bron) == (
            True,
            True,
            True,
        )

    def test_de_engine_kent_alleen_bestaande_attributen(self) -> None:
        gevonden = vind_overtredingen(ENGINE.read_text(encoding="utf-8"))

        assert [f"{ENGINE.as_posix()}:{n} {wat}" for n, wat in gevonden] == [], (
            "De engine zet of leest een attribuut dat het model niet heeft. Het wordt dan stil een gewoon "
            "Python-attribuut en niet opgeslagen (ADR-036 OP-13): de statuspagina blijft leeg."
        )


class TestDeMeting:
    @pytest.mark.parametrize(
        ("bron", "verwacht"),
        [
            (
                "execution.completed_at = 1\n",
                "execution.completed_at (gezet) bestaat niet op het model",
            ),
            ("x = task.completed_at\n", "task.completed_at (gelezen) bestaat niet op het model"),
            (
                "task_record.error_message = 'x'\n",
                "task_record.error_message (gezet) bestaat niet op het model",
            ),
            ("y = exec.completed_at\n", "exec.completed_at (gelezen) bestaat niet op het model"),
        ],
    )
    def test_een_onbekend_attribuut_wordt_gevonden(self, bron: str, verwacht: str) -> None:
        assert [w for _, w in vind_overtredingen(bron)] == [verwacht]

    @pytest.mark.parametrize(
        "bron",
        [
            "execution.finished_at = 1\n",
            "execution.error_message = 'x'\n",
            "task.error_json = {}\n",
            "task_record.finished_at = 1\n",
            "x = execution.workflow\n",
            "x = execution.tasks\n",
            "x = task.status\n",
            "andere.completed_at = 1\n",
        ],
    )
    def test_een_bestaand_attribuut_of_een_andere_naam_wordt_niet_gevonden(self, bron: str) -> None:
        assert vind_overtredingen(bron) == []
