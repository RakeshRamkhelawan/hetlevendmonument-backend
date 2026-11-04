"""De DSM-meter telt `import x` en `import x as y` zoals `from x import y`.

Brief 2026-10-22 (dsm-meter-telt-ook-import-x). Tot die datum zag `scan_module` alleen
`ast.ImportFrom`: 100 regels `import src....` onder `src/` telden nooit mee in de laaggrenzen,
terwijl ze dezelfde afhankelijkheid zijn. De noodstop omzeilde dat zelfs bewust door te schrijven
`from src.core.noodstop import model_deur`.

Wat hier bewaakt wordt:
- `import x`, `import x as y` en meerdere namen in een regel leveren een rand op;
- dezelfde uitsluitingen als voor `from`: geen TYPE_CHECKING-blok, geen testmap, geen niet-src-import;
- het registratiebestand `src/core/database/import_all_models.py` is een benoemde, gedateerde
  uitzondering (sleutel `bestand::<module>`), maar ALLEEN voor `import x` op moduleniveau waarvan
  het doel een SQLAlchemy-model definieert; een `from x import y`, een import in een functie of een
  niet-model-import in hetzelfde bestand telt WEL;
- het registratiebestand zelf noemt alleen nog modelmodules: zie `test_import_all_models_noemt_alleen_modellen`.

MUTATIEBEWIJS (zie de resultaten in het feature-doc BE-DSM-METER-001; beide richtingen):
    `isinstance(node, ast.Import)`-tak uit scan_module halen     -> `import_x` en `import_x_as_y` ROOD
    de uitzondering op elk bestand laten gelden (kale sleutel)   -> `ander_bestand` ROOD
    de modelcontrole uit de uitzondering halen                   -> `niet_model_in_registratiebestand` ROOD
    de moduleniveau-eis weghalen                                 -> `import_in_functie` ROOD
    een niet-model-import in import_all_models.py                -> `test_import_all_models_noemt_alleen_modellen` ROOD
    legitiem: een model-import op moduleniveau in het bestand    -> `model_import_telt_niet` GROEN
"""

from __future__ import annotations

import ast
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.dsm_full_analysis import (
    MODEL_REGISTRATIE_BESTANDEN,
    _definieert_model,
    scan_module,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRATIEBESTAND = "src/core/database/import_all_models.py"
SLEUTEL = f"{REGISTRATIEBESTAND}::<module>"


@pytest.fixture
def wortel() -> Iterator[Path]:
    """Een tijdelijke map ZONDER 'test' in het pad: scan_module slaat elk pad met dat woord over."""
    with tempfile.TemporaryDirectory(prefix="dsm_") as map_:
        yield Path(map_)


def _schrijf(root: Path, relatief: str, tekst: str) -> Path:
    pad = root / relatief
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(tekst, encoding="utf-8", newline="\n")
    return pad


def _rand_naar_auth(wortel: Path, tekst: str) -> int:
    """Het aantal randen core_api -> auth dat een bestand in core_api oplevert."""
    _schrijf(wortel, "src/core/api/x.py", tekst)
    counts, _, _ = scan_module("core_api", [str(wortel / "src/core/api")])
    return counts.get("auth", 0)


def test_import_x_levert_een_rand_op(wortel: Path) -> None:
    assert _rand_naar_auth(wortel, "import src.core.auth.api_deps\n") == 1


def test_import_x_as_y_levert_een_rand_op(wortel: Path) -> None:
    assert _rand_naar_auth(wortel, "import src.core.auth.api_deps as deps\n") == 1


def test_meerdere_namen_in_een_importregel_leveren_elk_een_rand_op(wortel: Path) -> None:
    tekst = "import src.core.auth.api_deps, src.core.auth.scope_validator\n"

    assert _rand_naar_auth(wortel, tekst) == 2


def test_from_import_blijft_een_rand_opleveren(wortel: Path) -> None:
    assert _rand_naar_auth(wortel, "from src.core.auth.api_deps import x\n") == 1


def test_een_import_in_een_functie_telt_mee(wortel: Path) -> None:
    tekst = "def f():\n    import src.core.auth.api_deps\n"

    assert _rand_naar_auth(wortel, tekst) == 1


def test_een_import_binnen_type_checking_telt_niet_mee(wortel: Path) -> None:
    tekst = (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import src.core.auth.api_deps\n"
    )

    assert _rand_naar_auth(wortel, tekst) == 0


def test_een_import_buiten_src_telt_niet_mee(wortel: Path) -> None:
    assert _rand_naar_auth(wortel, "import os\nimport requests.auth\n") == 0


def test_een_import_binnen_de_eigen_bak_telt_niet_mee(wortel: Path) -> None:
    _schrijf(wortel, "src/core/api/x.py", "import src.core.api.y\n")
    counts, _, _ = scan_module("core_api", [str(wortel / "src/core/api")])

    assert sum(counts.values()) == 0


def test_een_testmap_wordt_overgeslagen(wortel: Path) -> None:
    _schrijf(wortel, "src/core/api/tests/x.py", "import src.core.auth.api_deps\n")
    counts, _, _ = scan_module("core_api", [str(wortel / "src/core/api")])

    assert counts.get("auth", 0) == 0


def _registratie(wortel: Path, bestand_tekst: str, naam: str = REGISTRATIEBESTAND) -> int:
    """Een nep-repo: het doel `src.core.auth.mod_model` is een model, `mod_plat` niet."""
    _schrijf(
        wortel,
        "src/core/auth/mod_model.py",
        "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n"
        "class Tabel(Base):\n    __tablename__ = 't'\n",
    )
    _schrijf(wortel, "src/core/auth/mod_plat.py", "class Gewoon:\n    pass\n")
    _schrijf(wortel, naam, bestand_tekst)
    counts, _, _ = scan_module("infra", [str(wortel / Path(naam).parent)])
    return counts.get("auth", 0)


def test_model_import_telt_niet_in_het_registratiebestand(wortel: Path) -> None:
    assert _registratie(wortel, "import src.core.auth.mod_model\n") == 0


def test_niet_model_import_in_het_registratiebestand_telt_wel(wortel: Path) -> None:
    assert _registratie(wortel, "import src.core.auth.mod_plat\n") == 1


def test_from_import_in_het_registratiebestand_telt_wel(wortel: Path) -> None:
    assert _registratie(wortel, "from src.core.auth.mod_model import Tabel\n") == 1


def test_import_in_een_functie_in_het_registratiebestand_telt_wel(wortel: Path) -> None:
    tekst = "def f():\n    import src.core.auth.mod_model\n"

    assert _registratie(wortel, tekst) == 1


def test_dezelfde_model_import_in_een_ander_bestand_telt_wel(wortel: Path) -> None:
    tekst = "import src.core.auth.mod_model\n"

    assert _registratie(wortel, tekst, naam="src/core/database/ander_bestand.py") == 1


def test_de_uitzondering_heeft_een_moduleniveau_sleutel_en_een_reden() -> None:
    assert (
        list(MODEL_REGISTRATIE_BESTANDEN) == [SLEUTEL]
        and MODEL_REGISTRATIE_BESTANDEN[SLEUTEL].strip()
    )


def _moduleniveau_imports() -> set[str]:
    boom = ast.parse((REPO_ROOT / REGISTRATIEBESTAND).read_text(encoding="utf-8"))
    return {
        alias.name
        for node in boom.body
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("src.")
    }


def test_de_uitzondering_is_niet_verouderd() -> None:
    """Het registratiebestand moet nog minstens een `import x` van een echt model hebben."""
    modelimports = [m for m in _moduleniveau_imports() if _definieert_model(m, REPO_ROOT)]

    assert modelimports, (
        "import_all_models.py heeft geen modelimport meer: haal de uitzondering weg"
    )
