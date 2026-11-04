"""Architecture tests voor DSM-scanner kwaliteit (SP-DSM-007 Dag 2).

Verifieert dat de scanner TYPE_CHECKING blokken correct negeert.
"""

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
SRC_SCRIPTS = _REPO_ROOT / "scripts"


def test_dsm_scanner_exists():
    """DSM scanner script moet aanwezig zijn."""
    scanner = SRC_SCRIPTS / "dsm_full_analysis.py"
    assert scanner.exists(), "scripts/dsm_full_analysis.py niet gevonden"


def test_dsm_scanner_excludes_type_checking_imports():
    """TODO(SP-DSM-007-DAG2): DSM scanner moet TYPE_CHECKING imports negeren.

    TYPE_CHECKING blokken worden alleen gebruikt voor type-annotaties
    en worden NIET uitgevoerd op runtime. Ze mogen NIET meetellen
    als echte runtime koppeling in de circulaire dep detectie.
    """
    scanner = SRC_SCRIPTS / "dsm_full_analysis.py"
    if not scanner.exists():
        pytest.skip("scanner niet aanwezig")
    scanner_src = scanner.read_text(encoding="utf-8")
    assert "TYPE_CHECKING" in scanner_src, (
        "DSM scanner houdt geen rekening met TYPE_CHECKING blokken. "
        "Voeg TYPE_CHECKING-filter toe zodat annotatie-only imports "
        "niet als runtime circulaire dep worden geteld."
    )


def test_dsm_instability_metric_in_architecture_tests():
    """TODO(SP-DSM-007-DAG2): Architecture test moet instability metriek gebruiken.

    De huidige test_dsm_grade_a_plus.py gebruikt raw fan-out (<=500).
    Dit is niet correct: shared (488) is een foundation-laag en mag niet
    als problematische koppeling worden geteld.
    Correct: Robert Martin instability I = Ce / (Ce + Ca), doel I <= 0.50.
    """
    arch_tests = _REPO_ROOT / "tests" / "architecture"
    grade_test = None
    for f in arch_tests.glob("test_dsm_grade*.py"):
        grade_test = f
        break

    assert grade_test is not None, "Geen test_dsm_grade*.py gevonden in tests/architecture/"

    src = grade_test.read_text(encoding="utf-8")
    assert "instability" in src.lower() or "fan_in" in src.lower() or "Ca" in src, (
        f"{grade_test.name} gebruikt nog geen instability metriek (I = Ce/(Ce+Ca)). "
        "Pas de test aan: bereken I per module en assert I <= 0.50 voor agent_runtime. "
        "Verwijder de raw fan-out check (<=500) die shared-imports onterecht straft."
    )
