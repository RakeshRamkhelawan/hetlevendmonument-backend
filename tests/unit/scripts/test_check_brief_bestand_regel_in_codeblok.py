"""De toets op `bestand:regel` in scripts/check_brief.py en zijn omgang met codeblokken.

Aanleiding: een stackdump met een verwijzing naar een bestand uit de standaardbibliotheek
werd geweigerd, omdat de toets ook over regels binnen een omheind blok liep. Brief (map
docs/agent-briefs/generated/): 2026-10-01-sprint-dag-check-brief-weigert-een-stackdump-in-
een-codeblok.md

Techniek: beslissingstabel over (plek van de verwijzing) x (bestand bestaat / regel te hoog).
Er is bewust geen mock: de toets draait over de echte `controleer()` met echte briefbestanden
in tmp_path, tegen het echte repobestand scripts/check_brief.py.

Deze module heeft geen autouse-fixture, en tests/unit/scripts heeft geen conftest die iets
in check_brief patcht.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_SPEC = importlib.util.spec_from_file_location(
    "check_brief_onder_test", REPO_ROOT / "scripts" / "check_brief.py"
)
assert _SPEC is not None and _SPEC.loader is not None
check_brief = importlib.util.module_from_spec(_SPEC)
# dataclasses zoekt de module op in sys.modules tijdens het laden.
sys.modules[_SPEC.name] = check_brief
_SPEC.loader.exec_module(check_brief)

# Drie backticks, samengesteld zodat dit testbestand zelf geen omheind blok bevat.
HEK = "`" * 3
# Een bestand dat in de repo bestaat en veel minder dan 99999 regels heeft.
BESTAAND = "scripts/check_brief.py"


def _schrijf_brief(tmp_path: Path, tekst: str) -> Path:
    pad = tmp_path / "2026-10-01-sprint-dag-testbrief.md"
    pad.write_text(tekst, encoding="utf-8")
    return pad


def _meldingen_over(bestand_regel: str, meldingen: list[str]) -> list[str]:
    return [m for m in meldingen if bestand_regel in m]


def test_verwijzing_naar_onbekend_bestand_in_omheind_codeblok_blokkeert_niet(tmp_path):
    """Een stackdump in een omheind blok mag een brief niet weigeren."""
    tekst = f"# Brief\n\nEen py-spy-dump:\n\n{HEK}\n  File threading.py:1000 in run\n{HEK}\n"
    uitslag = check_brief.controleer(_schrijf_brief(tmp_path, tekst))
    assert _meldingen_over("threading.py:1000", uitslag.blokkerend) == []


def test_verwijzing_naar_onbekend_bestand_in_gewone_tekst_blokkeert(tmp_path):
    """Buiten een blok blijft een onbekend bestand blokkerend."""
    tekst = "# Brief\n\nZie `threading.py:1000` voor de wachtende thread.\n"
    uitslag = check_brief.controleer(_schrijf_brief(tmp_path, tekst))
    assert _meldingen_over("threading.py:1000", uitslag.blokkerend) != []


def test_ingesprongen_citaat_met_te_hoog_regelnummer_blokkeert(tmp_path):
    """Een ingesprongen citaat heeft geen hekken en wordt dus getoetst."""
    tekst = f"# Brief\n\nGelezen citaat:\n\n    {BESTAAND}:99999\n"
    uitslag = check_brief.controleer(_schrijf_brief(tmp_path, tekst))
    assert _meldingen_over(f"{BESTAAND}:99999", uitslag.blokkerend) != []


def test_hekken_in_gewone_tekst_verbergen_een_verwijzing_ertussen_niet(tmp_path):
    """Hekken midden in proza knippen geen tekst weg voor de toets."""
    # Risico 1 uit de brief: drie backticks MIDDEN in een zin zijn geen omheind blok.
    tekst = (
        f"# Brief\n\nHet teken {HEK} opent een blok.\n"
        "Zie `nietbestaand_xyz.py:7` hier.\n"
        f"Het teken {HEK} sluit het weer.\n"
    )
    uitslag = check_brief.controleer(_schrijf_brief(tmp_path, tekst))
    assert _meldingen_over("nietbestaand_xyz.py:7", uitslag.blokkerend) != []


def test_verwijzing_na_een_codeblok_houdt_de_hash_van_erboven(tmp_path):
    """Na een blok blijft de commit-hash van erboven in beeld."""
    # Risico 2 uit de brief: weghalen van een blok mag de hash-context niet verschuiven.
    tekst = (
        "# Brief\n\nGelezen op commit 5a1aef5b.\n\n"
        f"{HEK}\nvoorbeelduitvoer\nnog een regel\n{HEK}\n\n"
        f"Zie `{BESTAAND}:10` voor de lus.\n"
    )
    uitslag = check_brief.controleer(_schrijf_brief(tmp_path, tekst))
    assert _meldingen_over(f"`{BESTAAND}:10` heeft geen commit-hash", uitslag.waarschuwing) == []
