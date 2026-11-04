"""Het mutatieharnas weigert te draaien zolang de volledige testronde bezig is.

**De bevinding, in de volgorde waarin hij ontstond.** CLAUDE.md verbiedt sinds 2026-09-20 een
reviewagent of een mutatietest naast de volledige testronde, met de meting erbij: exit 124,
terwijl die ronde normaal 17-18 minuten duurt. Op 2026-09-25 liep een sessie er alsnog in --
dezelfde sessie die die regel die dag nog aan iemand anders had uitgelegd. Gemeten gevolg: twee
workercrashes (`node down: Not properly terminated`) en 28m17 tegenover 17m12 bij een schone
herhaling. Geen defect, wel een verloren half uur.

**Waarom hier gereedschap hoort en geen extra regel.** De regel bestond en was bekend. Het slot
bestond ook, was machinebreed en leesbaar vanuit elke worktree -- alleen bemiddelde het
uitsluitend tussen POORTRUNS onderling (zie de moduledocstring van `scripts/testpoort_slot.py`:
"er draait er nooit meer dan een"). Niemand buiten de ronde raadpleegde het ooit. Dat is
dezelfde vorm als de impact-analyse die bestond maar nergens werd aangeroepen: het gereedschap
lag er, de bedrading ontbrak. De staande les in dit project is dat een terugkerende fout
ONTBREKEND GEREEDSCHAP is, geen ontbrekend proza.

**Wat dit NIET dekt, expliciet.** Alleen mutaties. De niet-meting van 2026-09-25 kwam mede door
losse `python -c`-aanroepen die de hele applicatie laadden, en die komen hier nooit langs. De
bredere formulering -- een meting is pas een meting als je kunt zeggen wat er naast draaide --
blijft mensenwerk en staat in CLAUDE.md. Dit dekt het geval dat aantoonbaar tweemaal is misgegaan.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import mutation_harness  # noqa: E402
import testpoort_slot  # noqa: E402


@pytest.fixture
def eigen_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Leid het slot om naar tmp_path.

    Het echte slot is gedeeld met elke andere sessie op deze machine; een test raakt het niet
    aan -- dat zou precies de schade aanrichten die deze bewaker moet voorkomen.
    """
    pad = tmp_path / "poort-slot.json"
    monkeypatch.setattr(testpoort_slot, "_slotpad", lambda: pad)
    return pad


def _zet_slot(pad: Path, *, minuten_oud: int = 0) -> None:
    sinds = datetime.now(timezone.utc) - timedelta(minutes=minuten_oud)
    pad.write_text(
        json.dumps(
            {
                "sessie": "een-andere-sessie",
                "werkmap": "C:/tmp/ergens",
                "sinds": sinds.isoformat(),
                "reden": "volledige testronde",
            }
        ),
        encoding="utf-8",
    )


def test_muteren_wordt_GEWEIGERD_terwijl_de_ronde_draait(eigen_slot: Path, tmp_path: Path) -> None:
    """Zonder dit is de regel uit CLAUDE.md afhankelijk van onthouden op het slechtste moment."""
    _zet_slot(eigen_slot)
    doelwit = tmp_path / "doelwit.py"
    doelwit.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(mutation_harness.MutationError) as fout:
        with mutation_harness.Mutation(doelwit):
            pass

    melding = str(fout.value)
    assert "een-andere-sessie" in melding, (
        "de melding noemt niet WIE de ronde draait; dan weet de lezer niet of hij moet "
        "wachten of dat er een slot is blijven hangen"
    )
    assert "C:/tmp/ergens" in melding, "de werkmap van de houder ontbreekt in de melding"


def test_muteren_gaat_gewoon_door_als_het_slot_VRIJ_is(eigen_slot: Path, tmp_path: Path) -> None:
    """De tegenrichting, en de belangrijkste helft.

    Zonder deze test is "weiger altijd" een geldige implementatie, en dan is het mutatiebewijs
    -- de zwaarste bewijsvorm die dit project kent -- helemaal niet meer te leveren.
    """
    doelwit = tmp_path / "doelwit.py"
    doelwit.write_text("x = 1\n", encoding="utf-8")

    with mutation_harness.Mutation(doelwit) as m:
        m.write("x = 2\n")
        assert doelwit.read_text(encoding="utf-8") == "x = 2\n"

    assert doelwit.read_text(encoding="utf-8") == "x = 1\n", "de mutatie is niet teruggezet"


def test_een_VEROUDERD_slot_blokkeert_niets(eigen_slot: Path, tmp_path: Path) -> None:
    """Een gecrashte ronde mag niet al het andere werk stilleggen.

    Dat is precies de faalvorm die de MCP-orchestrator deze week liet zien: een proces liep
    vast, liet zijn slot achter, en daarmee lag elke schrijvende aanroep van elke sessie stil
    tot iemand handmatig een bestand weghaalde. Het slot hanteert daarvoor een overnamegrens;
    deze bewaker volgt die.
    """
    _zet_slot(eigen_slot, minuten_oud=120)
    doelwit = tmp_path / "doelwit.py"
    doelwit.write_text("x = 1\n", encoding="utf-8")

    with mutation_harness.Mutation(doelwit) as m:
        m.write("x = 2\n")

    assert doelwit.read_text(encoding="utf-8") == "x = 1\n"


def test_de_bedrading_zit_in_de_contextmanager() -> None:
    """De les van 2026-09-24/25: toets de BEDRADING, niet alleen de hulpfunctie.

    Een controle die bestaat maar nergens wordt aangeroepen, is precies het gat dat deze hele
    bevinding heeft veroorzaakt. Daarom hier op de broncode van `Mutation.__enter__` zelf, en
    niet op het bestand als geheel: een vermelding in een docstring telt niet.
    """
    import ast
    import inspect

    boom = ast.parse(inspect.getsource(mutation_harness.Mutation))
    enter = next(
        knoop
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.FunctionDef) and knoop.name == "__enter__"
    )
    aangeroepen = {
        knoop.func.id
        for knoop in ast.walk(enter)
        if isinstance(knoop, ast.Call) and isinstance(knoop.func, ast.Name)
    }

    assert "eis_vrije_testronde" in aangeroepen, (
        "Mutation.__enter__ raadpleegt het testronde-slot niet meer; dan kan een mutatie weer "
        "naast een lopende ronde draaien en is die ronde een NIET-meting"
    )
