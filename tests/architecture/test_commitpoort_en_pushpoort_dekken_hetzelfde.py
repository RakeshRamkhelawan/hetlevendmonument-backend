"""De commitpoort en de pushpoort bewaken hetzelfde testoppervlak; geen uitgesloten paden.

Gemeten 2026-09-28: een wijziging aan validators.py werd geblokkeerd door een
pre-existing e2e-test-failure. De commitpoort trok tests/e2e/ mee via impact_tests.py,
terwijl de pushpoort alleen tests/unit tests/architecture tests/core tests/contracts dekt.
Dat is de slechtste combinatie: streng waar niemand onderhoudt, stil waar het telt.

Opgelost door DOELMAPPEN in scripts/impact_tests.py te beperken tot de vier
pushpoort-mappen. Deze test bewaakt dat die twee niet uit elkaar lopen.

Mutatiebewijs (beide richtingen), 2026-09-28:
- DOELMAPPEN uitbreiden met een extra map (bv. "tests/e2e/") -> ROOD
- een map uit DOELMAPPEN verwijderen (bv. "tests/unit/") -> ROOD
- de correcte vier mappen in DOELMAPPEN -> GROEN
- pushpoort-aanroep in pre-push uitbreiden met een extra map -> ROOD
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import impact_tests  # noqa: E402

IMPACT_TESTS = REPO_ROOT / "scripts" / "impact_tests.py"
PRE_PUSH = REPO_ROOT / "scripts" / "hooks" / "pre-push"


def _doelmappen_uit_impact_tests() -> frozenset[str]:
    """DOELMAPPEN uit scripts/impact_tests.py via AST (rstrip '/' voor vergelijking)."""
    boom = ast.parse(IMPACT_TESTS.read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if (
            isinstance(knoop, ast.Assign)
            and len(knoop.targets) == 1
            and isinstance(knoop.targets[0], ast.Name)
            and knoop.targets[0].id == "DOELMAPPEN"
            and isinstance(knoop.value, ast.Tuple)
        ):
            return frozenset(
                el.value.rstrip("/")
                for el in knoop.value.elts
                if isinstance(el, ast.Constant) and isinstance(el.value, str)
            )
    return frozenset()


def _pushpoort_mappen_uit_pre_push() -> frozenset[str]:
    """De vier testmappen uit de pytest-aanroep in scripts/hooks/pre-push."""
    inhoud = PRE_PUSH.read_text(encoding="utf-8")
    # Zoek: "$PY_EXE" -m pytest tests/unit tests/architecture tests/core tests/contracts
    treffer = re.search(
        r"-m\s+pytest\s+((?:tests/[a-zA-Z]+\s*)+)",
        inhoud,
    )
    if not treffer:
        return frozenset()
    return frozenset(
        deel.rstrip("/") for deel in treffer.group(1).split() if deel.startswith("tests/")
    )


def test_commitpoort_en_pushpoort_bewaken_dezelfde_mappen() -> None:
    doelmappen = _doelmappen_uit_impact_tests()
    assert doelmappen, (
        "DOELMAPPEN niet gevonden in %s -- de commitpoort heeft geen expliciete "
        "doelmappen en scant heel tests/, terwijl de pushpoort maar vier mappen dekt" % IMPACT_TESTS
    )

    pushpoort = _pushpoort_mappen_uit_pre_push()
    assert pushpoort, (
        "pushpoort-mappen niet gevonden in %s -- kon de pytest-aanroep met "
        "'-m pytest tests/...' niet parseren" % PRE_PUSH
    )

    alleen_in_commit = doelmappen - pushpoort
    alleen_in_push = pushpoort - doelmappen

    assert not alleen_in_commit and not alleen_in_push, (
        "commitpoort en pushpoort lopen uit elkaar. "
        "Alleen in DOELMAPPEN (commitpoort): %s. "
        "Alleen in pushpoort: %s. "
        "Fix: synchroniseer DOELMAPPEN in scripts/impact_tests.py met de "
        "pytest-aanroep in scripts/hooks/pre-push"
        % (sorted(alleen_in_commit), sorted(alleen_in_push))
    )


def test_testbestanden_bevat_geen_uitgesloten_paden() -> None:
    """_testbestanden() geeft geen paden die pytest zelf zou overslaan.

    Gemeten 2026-09-30: impact_tests.py gaf tests/unit/temp_disabled/ door aan pytest.
    pyproject.toml heeft --ignore=tests/unit/temp_disabled en norecursedirs = ["temp_disabled"].
    Wie een bestand EXPLICIET noemt overrulet die uitsluiting -- 6 minuten testtijd die
    niemand groen hoeft te hebben blokkeert een commit.

    Mutatiebewijs richting 1 (2026-09-30): zonder _pytest_uitgesloten()-filter bevatte
    _testbestanden() paden als tests/unit/temp_disabled/test_auth_real.py.
    Richting 2: met de filter zijn er geen temp_disabled-paden -- EN de gewone paden
    (tests/unit/) zijn er nog steeds (weiger-alles is geen oplossing).
    """
    paden = impact_tests._testbestanden()

    # Richting 1: geen uitgesloten paden
    uitgesloten = [p for p in paden if "temp_disabled" in p]
    assert not uitgesloten, (
        "testbestanden met uitgesloten pad gevonden: %s\n"
        "pyproject.toml heeft --ignore=tests/unit/temp_disabled, maar impact_tests "
        "geeft deze paden toch door -- dat overrulet de uitsluiting" % uitgesloten
    )

    # Richting 2: gewone paden zijn er nog
    normale = [p for p in paden if p.startswith("tests/unit/") and "temp_disabled" not in p]
    assert normale, (
        "_testbestanden() geeft geen enkel normaal pad uit tests/unit/ -- "
        "de filter sluit te veel uit (weiger-alles-fout)"
    )


def test_geraakte_tests_bevat_geen_uitgesloten_paden_transitief() -> None:
    """geraakte_tests() geeft geen temp_disabled-paden, ook niet via een transitieve import.

    Gemeten 2026-09-30 (org-18): tests/fixtures/tenant.py werd gewijzigd (org-a9).
    De impactset bevatte transitief tests/unit/temp_disabled/test_auth_real.py,
    omdat dat bestand de fixture importeert. Impact_tests filterde die map niet uit.

    Dit is de toets op de UITKOMST (niet de invoer): wat komt er uit geraakte_tests()
    als een fixture-bestand gewijzigd is?

    Mutatiebewijs richting 1 (2026-09-30): zonder _pytest_uitgesloten()-filter bevatte
    de uitkomst temp_disabled-paden. Met de filter zijn ze er niet -- ook niet transitief.
    Richting 2: de uitkomst is niet LEEG als er echte testbestanden de fixture importeren
    (weiger-alles is geen oplossing). Dit wordt bewust NIET hard getoetst omdat de fixture
    niet altijd importeurs heeft; het transitieve gat is het punt, niet de volledigheid.
    """
    paden = impact_tests.geraakte_tests(["tests/fixtures/tenant.py"])

    uitgesloten = [p for p in paden if "temp_disabled" in p]
    assert not uitgesloten, (
        "geraakte_tests() geeft uitgesloten paden terug voor tests/fixtures/tenant.py: %s\n"
        "Dit zijn transitief bereikbare temp_disabled-bestanden -- ze mogen de "
        "commitpoort niet blokkeren" % uitgesloten
    )
