"""agent_runtime bereikt de noodstop alleen via `src/core/services/noodstop_toegang.py` (ADR-033, ADR-036 OP-03).

De enkele ingang verlaagt de Ce van agent_runtime (negen importstatements worden een). Dat getal is
alleen iets waard als de directe koppeling er niet ongemerkt weer in sluipt. Deze test leest daarom
ELK bestand dat de DSM-meter tot agent_runtime rekent (`SOURCE_DIRS["agent_runtime"]` uit
`scripts/dsm_full_analysis.py`, zelfde regels als `scan_module`: geen testpaden, geen
TYPE_CHECKING-blokken) en faalt zodra er een `src.core.noodstop`-import staat die niet in
`UITZONDERINGEN` staat. Elke uitzondering heeft een reden; een staleness-test faalt als een
uitzondering niet meer nodig is, zodat de lijst niet kan verouderen.

Wat deze test NIET bewijst: dat een deur de controle ook echt aanroept. Dat doet
`test_elke_deur_controleert_de_noodstop`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.dsm_full_analysis import (
    SOURCE_DIRS,
    _collect_type_checking_nodes,
    scan_module,
)

ROOT = Path(__file__).resolve().parents[2]
DOEL = "src.core.noodstop"
INGANG = "src/core/services/noodstop_toegang.py"

#: "bestand::regel" of "bestand::functie" -> reden. Een functie dekt elke noodstop-import in die functie.
UITZONDERINGEN: dict[str, str] = {
    f"{INGANG}::23": "de ingang zelf: dit is de ene rand van agent_runtime naar de noodstop",
    "src/core/als/bonlezer/worker.py::48": (
        "opstartpunt: laadt de adapter van de modeldeur (`from src.core.noodstop import model_deur`); "
        "dat moet een eigen importstatement zijn (zie test_modeldeur_opstart)"
    ),
    "src/core/learning/worker.py::63": "opstartpunt: laadt de adapter van de modeldeur, zelfde reden",
    "src/workers/scheduler.py::29": "opstartpunt: laadt de adapter van de modeldeur, zelfde reden",
    "src/core/tasks/cva_tasks.py::9": (
        "teller `registreer_weggegooid`: `noodstop.weggegooid` laadt AuditService en de bypass-sessie; "
        "via de ingang geeft dat een importcyclus"
    ),
}


def _is_noodstop(module: str) -> bool:
    return module == DOEL or module.startswith(DOEL + ".")


def _agent_runtime_bestanden() -> list[Path]:
    """Dezelfde bestandskeuze als `scan_module` in de meter."""
    bestanden: list[Path] = []
    for bron in SOURCE_DIRS["agent_runtime"]:
        p = ROOT / bron
        if not p.exists():
            continue
        paden = [p] if p.is_file() else sorted(p.rglob("*.py"))
        for pad in paden:
            if any("test" in deel.lower() for deel in pad.relative_to(ROOT).parts):
                continue
            bestanden.append(pad)
    return bestanden


def _noodstop_imports(pad: Path) -> list[tuple[int, str | None]]:
    """(regel, omsluitende functie of None) van elke noodstop-import die de meter telt."""
    try:
        tree = ast.parse(pad.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    tc_ids = _collect_type_checking_nodes(tree)
    ouders: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for kind in ast.iter_child_nodes(node):
            ouders[id(kind)] = node

    def functie(node: ast.AST) -> str | None:
        huidig = ouders.get(id(node))
        while huidig is not None:
            if isinstance(huidig, ast.FunctionDef | ast.AsyncFunctionDef):
                return huidig.name
            huidig = ouders.get(id(huidig))
        return None

    gevonden: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if id(node) in tc_ids:
            continue
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            hit = _is_noodstop(node.module) or (
                node.module == "src.core" and any(a.name == "noodstop" for a in node.names)
            )
        elif isinstance(node, ast.Import):
            hit = any(_is_noodstop(a.name) for a in node.names)
        else:
            continue
        if hit:
            gevonden.append((node.lineno, functie(node)))
    return gevonden


def _sleutels(rel: str, regel: int, functie: str | None) -> list[str]:
    sleutels = [f"{rel}::{regel}"]
    if functie:
        sleutels.append(f"{rel}::{functie}")
    return sleutels


def _alle_noodstop_imports() -> list[tuple[str, int, str | None]]:
    uit: list[tuple[str, int, str | None]] = []
    for pad in _agent_runtime_bestanden():
        rel = pad.relative_to(ROOT).as_posix()
        uit.extend((rel, regel, fn) for regel, fn in _noodstop_imports(pad))
    return uit


def test_de_bestandskeuze_is_die_van_de_meter() -> None:
    """Geen eigen lijst: het aantal bestanden moet gelijk zijn aan wat `scan_module` zelf telt."""
    _, bestanden_meter, _ = scan_module("agent_runtime", SOURCE_DIRS["agent_runtime"])
    assert len(_agent_runtime_bestanden()) == bestanden_meter


def test_agent_runtime_importeert_de_noodstop_alleen_via_de_ingang() -> None:
    overtredingen = [
        f"{rel}:{regel}"
        for rel, regel, fn in _alle_noodstop_imports()
        if not any(s in UITZONDERINGEN for s in _sleutels(rel, regel, fn))
    ]
    assert not overtredingen, (
        "agent_runtime-bestanden importeren `src.core.noodstop` rechtstreeks: "
        f"{overtredingen}. Importeer uit `src.core.services.noodstop_toegang` (voeg de naam daar toe als hij "
        "ontbreekt), of voeg een uitzondering met reden toe aan UITZONDERINGEN."
    )


def test_elke_uitzondering_is_nog_nodig() -> None:
    gebruikt: set[str] = set()
    for rel, regel, fn in _alle_noodstop_imports():
        gebruikt.update(s for s in _sleutels(rel, regel, fn) if s in UITZONDERINGEN)
    verouderd = sorted(set(UITZONDERINGEN) - gebruikt)
    assert not verouderd, f"deze uitzonderingen dekken geen noodstop-import meer, verwijder ze: {verouderd}"
    assert all(reden.strip() for reden in UITZONDERINGEN.values())
