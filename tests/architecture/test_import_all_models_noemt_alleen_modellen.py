"""`import_all_models.py` noemt alleen modules die een SQLAlchemy-model definieren.

Brief 2026-10-23 (import_all_models registreert alleen modellen). Het registratiebestand bestaat om
`Base.metadata` te vullen (Alembic, `create_all`). Een import van een module zonder model registreert
niets en maakt van de database-laag een afhankelijkheid van pydantic-, Enum- of her-exporterende
modules uit hogere lagen: de DSM-meter telde die acht imports sinds 2026-10-22 als randen
infra -> agent_runtime (5), infra -> domain_pack (1) en twee niet-ingedeelde modules.

**Per import gemeten (2026-10-23), met een verse interpreter per meting**: `Base.metadata` had met alle
91 imports 201 tabellen, zonder elk van de acht afzonderlijk 201, en zonder alle acht samen ook 201,
zonder een enkele importfout. Geen van de acht laadde dus (transitief) een tabel die anders
ontbrak, en ze zijn weggehaald. Een model verandert niet, een migratie is er niet.

**Wat deze test bewaakt:** elke import in het bestand (ook in een functie, ook `from x import y`)
is `import src....` van een module die een klasse met basis `Base` of een `__tablename__` definieert.

MUTATIEBEWIJS (2026-10-23, beide richtingen):
    een pydantic-module (`import src.core.learning.gdpr_models`) terugzetten  -> ROOD
    een `from src.core.auth.models import X` erbij                            -> ROOD
    een import in een functie erbij                                           -> ROOD
    een echte modelmodule erbij (`import src.core.agents.models`, dubbel)     -> alleen `geen_dubbele_imports` ROOD
    legitiem: een modelmodule op moduleniveau (tijdelijke repo, `een_modelmodule_..._is_goed`)  -> GROEN
    NB: de regel `import src.core.database.models` (her-exporterend pakket, de submodules staan er al apart)
    is als negende gevonden en ook weggehaald; 201 tabellen zonder die regel.
"""

from __future__ import annotations

import ast
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.dsm_full_analysis import _definieert_model

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRATIEBESTAND = REPO_ROOT / "src/core/database/import_all_models.py"


def _imports(bron: str) -> list[tuple[int, str]]:
    """(regel, gevonden naam) van elke import in de bron; `from x import y` levert `from x`."""
    gevonden: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(bron)):
        if isinstance(node, ast.Import):
            gevonden.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            gevonden.append((node.lineno, f"from {node.module or ''}"))
    return sorted(gevonden)


def niet_modelimports(bron: str, wortel: Path) -> list[str]:
    """De imports in `bron` die GEEN `import src.<module met een SQLAlchemy-model>` zijn."""
    slecht: list[str] = []
    for regel, naam in _imports(bron):
        if naam.startswith("from ") or not naam.startswith("src."):
            slecht.append(f"{regel}: {naam}")
        elif not _definieert_model(naam, wortel):
            slecht.append(f"{regel}: {naam}")
    return slecht


@pytest.fixture
def wortel() -> Iterator[Path]:
    """Een tijdelijke repo ZONDER 'test' in het pad, met een modelmodule en een gewone module."""
    with tempfile.TemporaryDirectory(prefix="dsm_") as map_:
        basis = Path(map_)
        (basis / "src/core/x").mkdir(parents=True)
        (basis / "src/core/x/model.py").write_text(
            "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\n"
            "class T(Base):\n    __tablename__ = 't'\n",
            encoding="utf-8",
        )
        (basis / "src/core/x/plat.py").write_text(
            "from pydantic import BaseModel\nclass P(BaseModel):\n    x: int = 1\n",
            encoding="utf-8",
        )
        yield basis


def test_het_registratiebestand_noemt_alleen_modules_met_een_model() -> None:
    slecht = niet_modelimports(REGISTRATIEBESTAND.read_text(encoding="utf-8"), REPO_ROOT)

    assert not slecht, (
        "import_all_models.py importeert modules zonder SQLAlchemy-model (dat registreert niets): "
        + "; ".join(slecht)
    )


def test_het_registratiebestand_heeft_geen_dubbele_imports() -> None:
    namen = [n for _, n in _imports(REGISTRATIEBESTAND.read_text(encoding="utf-8"))]
    dubbel = sorted({n for n in namen if namen.count(n) > 1})

    assert not dubbel, f"dubbel geimporteerd: {dubbel}"


def test_het_registratiebestand_importeert_modellen_op_moduleniveau() -> None:
    boom = ast.parse(REGISTRATIEBESTAND.read_text(encoding="utf-8"))
    in_functie = [
        node.lineno
        for stap in ast.walk(boom)
        if isinstance(stap, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(stap)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]

    assert not in_functie, f"imports in een functie op regel {in_functie}"


def test_een_pydantic_module_wordt_betrapt(wortel: Path) -> None:
    assert niet_modelimports("import src.core.x.plat\n", wortel) == ["1: src.core.x.plat"]


def test_een_from_import_wordt_betrapt(wortel: Path) -> None:
    assert niet_modelimports("from src.core.x.model import T\n", wortel) == [
        "1: from src.core.x.model"
    ]


def test_een_import_in_een_functie_wordt_betrapt_als_hij_geen_model_is(wortel: Path) -> None:
    bron = "def f():\n    import src.core.x.plat\n"

    assert niet_modelimports(bron, wortel) == ["2: src.core.x.plat"]


def test_een_modelmodule_op_moduleniveau_is_goed(wortel: Path) -> None:
    assert niet_modelimports("import src.core.x.model\n", wortel) == []


def test_een_module_die_niet_bestaat_wordt_betrapt(wortel: Path) -> None:
    assert niet_modelimports("import src.core.x.bestaat_niet\n", wortel) == [
        "1: src.core.x.bestaat_niet"
    ]
