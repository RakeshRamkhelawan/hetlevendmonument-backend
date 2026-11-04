"""De modeldeur is pas dicht als de adapter geladen is: elk procesopstartpunt importeert hem.

**Waarom (Gate 2 ronde 2 blokkade P3, optie A).** De noodstopcontrole op de modeldeur zit in twee
delen: de poort (`src/core/shared/model_deur.py`, stdlib-only, in elke modelstack) en de adapter
(`src/core/noodstop/model_deur.py`, de echte controle). De poort laadde de adapter eerst zelf met een
tekenreeks-import, en dat is voor de DSM-meter onzichtbaar. Nu laadt elk procesopstartpunt de adapter
met `from src.core.noodstop import model_deur  # noqa: F401` bovenaan het bestand, en de poort kan
niets meer laden. Alleen deze vorm is toegestaan, omdat de DSM-meter (scripts/dsm_full_analysis.py)
alleen `ast.ImportFrom` telt en `import x` NIET; een kale `import src.core.noodstop.model_deur` zou de
rand dus onzichtbaar laten. (Dat de meter `import x` niet telt is een ander gebrek met een eigen
opdracht: `2026-10-22-sprint-dag-dsm-meter-telt-ook-import-x`; het hoort niet in deze tak.) Zonder registratie blijft de deur dicht
(`ModelDeurNietBeschikbaar`, fail-closed).

Dit maakt een ander risico zichtbaar: een nieuw opstartpunt (een nieuwe worker, een nieuwe
compose-service) dat de adapter vergeet te laden, weigert dan elke modelaanroep. Dat is de bedoelde
fail-closed kant, maar het hoort bij het schrijven van het opstartpunt te falen, niet pas in
productie. Twee controles:

1. Elk procesopstartpunt (uit de Dockerfile, de compose-bestanden en de CD-workflows) importeert de
   adapter op modulenivo, of staat in `GELADEN_DOOR` met de reden en de module die hem wel laadt.
2. De poort gebruikt geen `importlib`, `import_module` of `__import__`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = "src.core.noodstop.model_deur"
POORT = ROOT / "src" / "core" / "shared" / "model_deur.py"

#: De opstartpunten die er minstens zijn. Een ontdekking uit de compose-bestanden kan alleen
#: ONTBREKEN als iemand de regel weghaalt; deze lijst voorkomt dat het afdwingen dan stil leegloopt.
OPSTARTPUNTEN_MINIMAAL = {
    "src.main",
    "src.workers.workflow_worker",
    "src.workers.scheduler",
    "src.core.learning.worker",
    "src.core.als.bonlezer.worker",
}

#: Een opstartpunt dat de adapter niet zelf importeert, met de reden en de module die hem WEL laadt.
GELADEN_DOOR = {
    # `dramatiq src.workers.workflow_worker:redis_broker src.workers.actors`: een proces, twee
    # modules. De broker-module laadt de adapter; `actors` is alleen de lijst van taken erbij.
    "src.workers.actors": "src.workers.workflow_worker",
}

BESTANDEN = [
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "scripts/entrypoint-dev.sh",
    "scripts/entrypoint-prod.sh",
    ".github/workflows/cd-staging.yml",
    ".github/workflows/cd-production.yml",
]
_MODULE = re.compile(r"\b(src(?:\.[A-Za-z_][A-Za-z0-9_]*)+)(?::\w+)?")
_STARTTEKEN = ("dramatiq", "uvicorn", "gunicorn", '"-m"', "-m ", "src.workers.", "CMD", "command")


def _modulepad(module: str) -> Path | None:
    basis = ROOT.joinpath(*module.split("."))
    for kandidaat in (basis.with_suffix(".py"), basis / "__init__.py"):
        if kandidaat.is_file():
            return kandidaat
    return None


def ontdek_opstartpunten(tekst: str) -> set[str]:
    """De modules die een proces starten, uit commando-regels (geen commentaar)."""
    gevonden: set[str] = set()
    for regel in tekst.splitlines():
        kaal = regel.strip()
        if not kaal or kaal.startswith("#"):
            continue
        if not any(teken in kaal for teken in _STARTTEKEN):
            continue
        for module in _MODULE.findall(kaal):
            if _modulepad(module) is not None and not module.endswith(".py"):
                gevonden.add(module)
    return gevonden


def importeert_adapter_op_modulenivo(bron: str) -> bool:
    """Staat er een gewone import van de adapter in de modulebody (dus bij het laden, niet lazy)?"""
    # Alleen deze vorm: `from src.core.noodstop import model_deur`. De DSM-meter telt `ast.ImportFrom`
    # en geen `ast.Import`; een kale `import src.core.noodstop.model_deur` laat de rand onzichtbaar.
    boom = ast.parse(bron)
    for knoop in boom.body:
        if isinstance(knoop, ast.ImportFrom) and knoop.level == 0:
            if knoop.module == "src.core.noodstop" and any(a.name == "model_deur" for a in knoop.names):
                return True
    return False


def tekenreeksimports(bron: str) -> list[str]:
    """`importlib`, `import_module` en `__import__` in de bron (de rand die de DSM niet ziet)."""
    gevonden: list[str] = []
    for knoop in ast.walk(ast.parse(bron)):
        if isinstance(knoop, ast.Import):
            gevonden += [a.name for a in knoop.names if a.name.split(".")[0] == "importlib"]
        elif isinstance(knoop, ast.ImportFrom) and (knoop.module or "").split(".")[0] == "importlib":
            gevonden.append(knoop.module or "importlib")
        elif isinstance(knoop, ast.Name) and knoop.id in {"__import__", "import_module"}:
            gevonden.append(knoop.id)
        elif isinstance(knoop, ast.Attribute) and knoop.attr in {"import_module", "__import__"}:
            gevonden.append(knoop.attr)
    return gevonden


def _ontdekt() -> set[str]:
    gevonden: set[str] = set()
    for naam in BESTANDEN:
        pad = ROOT / naam
        if pad.is_file():
            gevonden |= ontdek_opstartpunten(pad.read_text(encoding="utf-8"))
    return gevonden


def test_de_ontdekking_vindt_de_bekende_opstartpunten() -> None:
    ontdekt = _ontdekt()
    assert OPSTARTPUNTEN_MINIMAAL <= ontdekt, (
        f"de ontdekking uit Dockerfile/compose/CD vindt de bekende opstartpunten niet meer: {sorted(ontdekt)}"
    )


def test_elk_procesopstartpunt_importeert_de_modeldeur_adapter() -> None:
    punten = OPSTARTPUNTEN_MINIMAAL | _ontdekt()
    ontbreekt: list[str] = []
    for module in sorted(punten):
        pad = _modulepad(module)
        assert pad is not None, f"opstartpunt {module} bestaat niet"
        if importeert_adapter_op_modulenivo(pad.read_text(encoding="utf-8")):
            continue
        via = GELADEN_DOOR.get(module)
        if via is not None:
            via_pad = _modulepad(via)
            assert via_pad is not None and importeert_adapter_op_modulenivo(
                via_pad.read_text(encoding="utf-8")
            ), f"{module} staat in GELADEN_DOOR via {via}, maar die laadt de adapter niet"
            continue
        ontbreekt.append(module)
    assert not ontbreekt, (
        "Deze procesopstartpunten laden de modeldeur-adapter niet; een worker of app zonder die "
        "import weigert ELKE modelaanroep (fail-closed). Voeg bovenaan toe:\n"
        "    from src.core.noodstop import model_deur  # noqa: F401\n"
        f"Opstartpunten: {ontbreekt}"
    )


def test_de_poort_laadt_niets_met_een_tekenreeksimport() -> None:
    gevonden = tekenreeksimports(POORT.read_text(encoding="utf-8"))
    assert not gevonden, (
        "src/core/shared/model_deur.py laadt de adapter met een tekenreeks-import, en die is voor de "
        f"DSM-meter onzichtbaar: {gevonden}. Laat het opstartpunt hem gewoon importeren."
    )


# --- zelftests: de controles vangen wat ze moeten vangen ---------------------------------------


def test_zelftest_modulenivo_import_telt_lazy_import_niet() -> None:
    assert importeert_adapter_op_modulenivo("from src.core.noodstop import model_deur  # noqa: F401\n")
    # De kale vorm en de `from ADAPTER import x`-vorm tellen NIET: de eerste ziet de meter niet.
    assert not importeert_adapter_op_modulenivo(f"import {ADAPTER}  # noqa: F401\n")
    assert not importeert_adapter_op_modulenivo(f"from {ADAPTER} import eis_model_actief\n")
    assert not importeert_adapter_op_modulenivo(
        "def start():\n    from src.core.noodstop import model_deur\n"
    )
    assert not importeert_adapter_op_modulenivo(f"def start():\n    import {ADAPTER}\n")
    assert not importeert_adapter_op_modulenivo(f"if False:\n    import {ADAPTER}\n")
    assert not importeert_adapter_op_modulenivo("import os\n")


def test_zelftest_tekenreeksimport_wordt_gezien() -> None:
    assert tekenreeksimports("import importlib\n")
    assert tekenreeksimports("from importlib import import_module\n")
    assert tekenreeksimports("x = __import__('a')\n")
    assert tekenreeksimports("mod.import_module('a')\n")
    assert not tekenreeksimports("import functools\n")


def test_zelftest_ontdekking_leest_commando_regels_en_negeert_commentaar() -> None:
    tekst = (
        '# dramatiq src.workers.nietbestaand_commentaar\n'
        'CMD ["src.workers.workflow_worker:redis_broker", "src.workers.actors"]\n'
        'command: ["dramatiq", "src.core.learning.worker:_broker"]\n'
        '    exec uvicorn src.main:app --port 8000\n'
    )
    assert ontdek_opstartpunten(tekst) >= {
        "src.workers.workflow_worker",
        "src.workers.actors",
        "src.core.learning.worker",
        "src.main",
    }
