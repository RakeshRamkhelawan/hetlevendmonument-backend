"""De testomgeving heeft een vaste, alleen-voor-test `MASTER_ENCRYPTION_KEY` (brief 2026-10-23).

Gemeten 2026-10-22 en opnieuw 2026-10-24: `tests/conftest.py` zette wel `TESTING` en een test-JWT-
geheim, maar geen hoofdsleutel. `tests/unit/test_focus_builder_observer.py` faalt los gedraaid met
`HoofdsleutelOntbreekt` (1 failed, 4 passed) en blokkeert zo een commit die het bestand raakt; in de
vaste testronde viel het niet op omdat een andere test de omgeving eerder vulde.

De sleutel is met `setdefault` gezet: een echte sleutel uit de shell van een ontwikkelaar wint, en
"de suite is groen" blijft een uitspraak over de code. Hij is GEEN echte sleutel (alleen in de
repo, alleen in tests) en voldoet aan de sterkte-eisen van `TenantSecretEncryption`, zodat tests die
hem gebruiken niet op `HoofdsleutelTeZwak` stuklopen.

MUTATIEBEWIJS (2026-10-24):
    de regel uit tests/conftest.py halen                          -> beide tests ROOD
    `setdefault` vervangen door een harde toewijzing              -> `..._wint_een_sleutel_uit_de_shell_niet_af` ROOD
    een te zwakke waarde ("a" * 43)                               -> `..._los_gedraaid_is_groen` ROOD
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFTEST = REPO_ROOT / "tests/conftest.py"
BEWEZEN_TESTBESTAND = "tests/unit/test_focus_builder_observer.py"


def _sleutel_aanroepen() -> list[ast.Call]:
    boom = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(boom)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setdefault"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "MASTER_ENCRYPTION_KEY"
    ]


def test_de_conftest_zet_de_hoofdsleutel_met_setdefault() -> None:
    assert len(_sleutel_aanroepen()) == 1


def _andere_manieren_om_de_sleutel_te_zetten(boom: ast.AST) -> list[ast.Call]:
    """`os.putenv("MASTER_ENCRYPTION_KEY", ...)` en `os.environ.update({...: ...})`."""
    gevonden: list[ast.Call] = []
    for node in ast.walk(boom):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr == "putenv" and node.args:
            eerste = node.args[0]
            if isinstance(eerste, ast.Constant) and eerste.value == "MASTER_ENCRYPTION_KEY":
                gevonden.append(node)
        if node.func.attr == "update" and node.args and isinstance(node.args[0], ast.Dict):
            sleutels = [k.value for k in node.args[0].keys if isinstance(k, ast.Constant)]
            if "MASTER_ENCRYPTION_KEY" in sleutels:
                gevonden.append(node)
    return gevonden


def test_de_conftest_zet_de_sleutel_niet_op_een_andere_harde_manier() -> None:
    boom = ast.parse(CONFTEST.read_text(encoding="utf-8"))

    assert _andere_manieren_om_de_sleutel_te_zetten(boom) == []


def test_de_conftest_wint_een_sleutel_uit_de_shell_niet_af() -> None:
    boom = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    harde_toewijzingen = [
        node
        for node in ast.walk(boom)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Subscript)
            and isinstance(t.slice, ast.Constant)
            and t.slice.value == "MASTER_ENCRYPTION_KEY"
            for t in node.targets
        )
    ]

    assert harde_toewijzingen == []


#: Een vers pytest-proces importeert de hele applicatie: gemeten 24 s op een rustige en 49 s op een drukke
#: machine, tegen de 60 s van `--timeout=60` in de testpoort. Onder belasting doodde die limiet de xdist-werker
#: ("worker crashed", 2026-10-24). Een eigen, ruimere grens voor deze ene test.
SUBPROCES_TIMEOUT = 240


@pytest.mark.timeout(SUBPROCES_TIMEOUT)
def test_een_test_die_de_hoofdsleutel_nodig_heeft_is_los_gedraaid_groen() -> None:
    omgeving = {
        k: v
        for k, v in os.environ.items()
        if k != "MASTER_ENCRYPTION_KEY" and not k.startswith("PYTEST_")
    }

    uitslag = subprocess.run(
        [sys.executable, "-m", "pytest", BEWEZEN_TESTBESTAND, "-n", "0", "-q", "--tb=line"]
        + ["-p", "no:cacheprovider", "--timeout=100"],
        cwd=REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )

    assert uitslag.returncode == 0, uitslag.stdout[-600:]
