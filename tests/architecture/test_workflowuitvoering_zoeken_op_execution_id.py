"""Een workflowuitvoering zoek je op `execution_id`, nooit op `.id` met een tekst-id (ADR-036 OP-13, brief 2026-10-21).

**Wat er mis was.** `src/workers/workflow_worker.py::neem_de_klant_van_de_opdracht_aan` zocht met de tekst-id van de
opdracht (`exec_...`) op `WorkflowExecution.id`. Dat model (`src.core.models.workflow_models`, tabel
`workflow_executions`) heeft een GEHEEL GETAL als `id`, en het is bovendien niet de tabel waar de API en de engine
mee werken (`c7_workflow_executions`, `C7WorkflowExecution`, tekst-id in `execution_id`). Elke echte worker faalde
daardoor direct met `operator does not exist: integer = character varying`; geen enkele test had het gezien.

**Twee regels, voor alle bestanden onder `src/`:**
1. Een vergelijking `<...WorkflowExecution>.id == <naam met "execution_id">` is verboden: zoek op `.execution_id`.
2. Een module onder `src/workers/` importeert niets uit `src.core.models.workflow_models` (het oude model van een
   andere tabel); een worker leest uitvoeringen uit `src.core.workflow.models`.

Wat dit NIET dekt: een tekst-id die onder een andere naam dan `...execution_id...` met `.id` wordt vergeleken.
Daarvoor is `tests/integration/test_workflow_loopt_echt_tot_het_eind.py` (echte Postgres) het vangnet.

**Mutatiebewijs:** `TestDeMeting` voert `vind_overtredingen` uit op losse bronteksten, per regel in beide richtingen:
`WorkflowExecution.id == execution_id` en `C7WorkflowExecution.id == exec_id` -> gevonden; `.execution_id ==` en
`ProcedureExecution.id == execution_id` (ander model, tekst-id) en een vergelijking met een getal -> NIET gevonden.
De test op de echte boom was ROOD op d054a114 (`src/workers/workflow_worker.py`, drie plekken).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path("src")
WORKERS = SRC_ROOT / "workers"

#: `bestand` -> reden. Leeg: geen enkele plek heeft een goede reden om een tekst-id met `.id` te vergelijken.
KNOWN_UITZONDERINGEN: dict[str, str] = {}

_OUD_MODEL = "src.core.models.workflow_models"


def _naam_bevat_execution_id(knoop: ast.expr) -> bool:
    if isinstance(knoop, ast.Name):
        return "execution_id" in knoop.id or "exec_id" in knoop.id
    if isinstance(knoop, ast.Attribute):
        return "execution_id" in knoop.attr or "exec_id" in knoop.attr
    return False


def _is_workflowuitvoering_id(knoop: ast.expr) -> bool:
    """`WorkflowExecution.id` of `C7WorkflowExecution.id` (ook als `workflow_models.WorkflowExecution.id`)."""
    if not (isinstance(knoop, ast.Attribute) and knoop.attr == "id"):
        return False
    basis = knoop.value
    naam = basis.id if isinstance(basis, ast.Name) else getattr(basis, "attr", "")
    return naam in ("WorkflowExecution", "C7WorkflowExecution")


def vind_overtredingen(bron: str, *, is_worker: bool = False) -> list[tuple[int, str]]:
    """(regel, wat) voor elke overtreding in deze brontekst."""
    boom = ast.parse(bron)
    gevonden: list[tuple[int, str]] = []
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.Compare):
            kanten = [knoop.left, *knoop.comparators]
            if any(_is_workflowuitvoering_id(k) for k in kanten) and any(
                _naam_bevat_execution_id(k) for k in kanten
            ):
                gevonden.append(
                    (knoop.lineno, "WorkflowExecution.id met een execution_id vergeleken")
                )
        if is_worker and isinstance(knoop, ast.ImportFrom) and knoop.module == _OUD_MODEL:
            gevonden.append((knoop.lineno, f"worker importeert uit {_OUD_MODEL}"))
    return gevonden


def _scan_src() -> tuple[dict[str, list[tuple[int, str]]], list[str]]:
    gevonden: dict[str, list[tuple[int, str]]] = {}
    fouten: list[str] = []
    for pad in sorted(SRC_ROOT.rglob("*.py")):
        try:
            hits = vind_overtredingen(
                pad.read_text(encoding="utf-8-sig"), is_worker=WORKERS in pad.parents
            )
        except (OSError, SyntaxError, UnicodeDecodeError) as fout:
            fouten.append(f"{pad.as_posix()}: {fout}")
            continue
        if hits:
            gevonden[pad.as_posix()] = hits
    return gevonden, fouten


class TestDeBoom:
    def test_de_scan_ziet_alle_bestanden_en_slaat_er_geen_over(self) -> None:
        aantal = len(list(SRC_ROOT.rglob("*.py")))
        _, fouten = _scan_src()

        assert (aantal >= 1500, fouten) == (True, [])

    def test_een_workflowuitvoering_wordt_nergens_op_id_met_een_execution_id_gezocht(self) -> None:
        gevonden, _ = _scan_src()
        nieuw = {pad: hits for pad, hits in gevonden.items() if pad not in KNOWN_UITZONDERINGEN}

        regels = [f"  - {pad}:{n} {wat}" for pad, hits in sorted(nieuw.items()) for n, wat in hits]
        assert regels == [], (
            "Een tekst-id (`exec_...`) met `WorkflowExecution.id` vergelijken geeft in PostgreSQL "
            "`operator does not exist: integer = character varying` (ADR-036 OP-13):\n"
            + "\n".join(regels)
            + "\n\nZoek op `.execution_id`, en lees in een worker uit `src.core.workflow.models`."
        )

    def test_de_uitzonderingslijst_is_niet_verouderd(self) -> None:
        gevonden, _ = _scan_src()

        assert sorted(pad for pad in KNOWN_UITZONDERINGEN if pad not in gevonden) == []

    def test_elke_uitzondering_heeft_een_reden(self) -> None:
        # Geen `parametrize` over de lijst: is die leeg, dan maakt pytest er een overgeslagen item `[NOTSET]` van en telt de
        # ratel op tests die nooit draaien (CI-run 39852524654) die als een uitgezette test. Een gewone test draait altijd.
        zonder_reden = sorted(
            pad for pad, reden in KNOWN_UITZONDERINGEN.items() if len(reden.strip()) < 25
        )

        assert zonder_reden == []


class TestDeMeting:
    """De meetfunctie op losse bronteksten: per regel, beide richtingen."""

    @pytest.mark.parametrize(
        "bron",
        [
            "q = select(X).where(WorkflowExecution.id == execution_id)\n",
            "q = select(X).where(execution_id == WorkflowExecution.id)\n",
            "q = select(X).where(C7WorkflowExecution.id == exec_id)\n",
            "q = select(X).where(m.WorkflowExecution.id == uitvoering.execution_id)\n",
        ],
    )
    def test_een_tekst_id_tegen_id_wordt_gevonden(self, bron: str) -> None:
        assert [w for _, w in vind_overtredingen(bron)] == [
            "WorkflowExecution.id met een execution_id vergeleken"
        ]

    @pytest.mark.parametrize(
        "bron",
        [
            "q = select(X).where(WorkflowExecution.execution_id == execution_id)\n",
            "q = select(X).where(C7WorkflowExecution.execution_id == execution_id)\n",
            "q = select(X).where(ProcedureExecution.id == execution_id)\n",
            "q = select(X).where(WorkflowExecution.id == 5)\n",
            "q = select(X).where(WorkflowExecution.tenant_id == tenant_id)\n",
            "# WorkflowExecution.id == execution_id staat hier alleen als commentaar\nx = 1\n",
        ],
    )
    def test_een_legitiem_geval_wordt_niet_gevonden(self, bron: str) -> None:
        assert vind_overtredingen(bron) == []

    def test_een_worker_die_uit_het_oude_model_importeert_wordt_gevonden(self) -> None:
        bron = "from src.core.models.workflow_models import WorkflowExecution\n"

        assert [w for _, w in vind_overtredingen(bron, is_worker=True)] == [
            f"worker importeert uit {_OUD_MODEL}"
        ]

    def test_dezelfde_import_buiten_een_worker_is_toegestaan(self) -> None:
        bron = "from src.core.models.workflow_models import WorkflowExecution\n"

        assert vind_overtredingen(bron, is_worker=False) == []

    def test_een_worker_die_uit_het_c7_model_importeert_wordt_niet_gevonden(self) -> None:
        bron = "from src.core.workflow.models import C7WorkflowExecution\n"

        assert vind_overtredingen(bron, is_worker=True) == []
