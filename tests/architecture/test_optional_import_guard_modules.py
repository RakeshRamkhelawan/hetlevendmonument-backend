"""Bewaakt de `warn_unused_ignores = false`-uitzonderingslijst in pyproject.toml.

Achtergrond: modules die een optionele afhankelijkheid achter `try/except ImportError`
zetten, hebben een `# type: ignore` nodig als de library geinstalleerd is en niet als hij
ontbreekt. CI installeert geen ML-extras, een Docker-build wel. Dezelfde regel is dus in de
ene omgeving correct en in de andere "overbodig". Daarom staat `warn_unused_ignores` voor
precies die modules uit.

Zonder bewaking wordt zo'n lijst een stortplaats: elke module waar mypy over klaagt kan er
stilletjes bij. Deze tests dwingen af dat elke regel verdiend is, en dat een module die
z'n optional-import-guard verliest ook weer uit de lijst gaat (staleness).

Zie .claude/rules/quality-gates.md, paragraaf "guard-met-gedateerde-uitzondering".
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - CI en lokaal draaien beide >= 3.11
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _override_modules() -> list[str]:
    """De modulelijst uit de override die warn_unused_ignores uitzet."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    overrides = data["tool"]["mypy"]["overrides"]
    hits = [o for o in overrides if o.get("warn_unused_ignores") is False]
    assert len(hits) == 1, (
        "Verwacht precies een override met warn_unused_ignores=false; "
        f"gevonden: {len(hits)}. Meerdere lijsten maken de uitzondering onvindbaar."
    )
    return list(hits[0]["module"])


def _module_to_path(module: str) -> Path:
    return REPO_ROOT / (module.replace(".", "/") + ".py")


_GUARD_EXCEPTIONS = {"ImportError", "ModuleNotFoundError", "Exception"}


def _has_optional_import_guard(path: Path) -> bool:
    """True als het bestand een `try: import ... except <fout>` bevat.

    Bewust AST i.p.v. regex: een `except (ImportError, ModuleNotFoundError)`-tuple en
    `except ImportError as exc` moeten allebei tellen, en een string met de tekst
    "ImportError" erin mag juist niet meetellen.

    `except Exception` telt ook mee. Dat is ruimer dan mooi is, maar het is het patroon
    dat decision_engine.py gebruikt voor `stable_baselines3`, en met reden: die import
    trekt torch mee, dat op een kapotte CUDA-installatie een OSError geeft in plaats van
    een ImportError. De test controleert de vorm (try rond een import), niet de precieze
    exception -- dat is voldoende om te voorkomen dat de uitzonderingslijst een
    stortplaats wordt.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        imports_something = any(
            isinstance(stmt, (ast.Import, ast.ImportFrom))
            for stmt in ast.walk(node)
            if stmt is not node
        )
        if not imports_something:
            continue
        for handler in node.handlers:
            names: list[ast.expr] = []
            if isinstance(handler.type, ast.Tuple):
                names.extend(handler.type.elts)
            elif handler.type is not None:
                names.append(handler.type)
            for name in names:
                if isinstance(name, ast.Name) and name.id in _GUARD_EXCEPTIONS:
                    return True
    return False


def test_override_modules_exist() -> None:
    """Een module die niet meer bestaat MOET uit de lijst -- anders rot hij dicht."""
    missing = [m for m in _override_modules() if not _module_to_path(m).is_file()]
    assert not missing, (
        "Deze modules staan in de warn_unused_ignores-uitzondering maar bestaan niet "
        f"(meer): {missing}. Verwijder ze uit pyproject.toml."
    )


def test_override_modules_actually_guard_an_optional_import() -> None:
    """Elke uitzondering moet verdiend zijn met een echte try/except ImportError."""
    offenders = [
        m
        for m in _override_modules()
        if _module_to_path(m).is_file() and not _has_optional_import_guard(_module_to_path(m))
    ]
    assert not offenders, (
        "Deze modules staan in de warn_unused_ignores-uitzondering maar hebben geen "
        f"optional-import-guard (try/except ImportError): {offenders}. "
        "De uitzondering is bedoeld voor optionele afhankelijkheden, niet als "
        "algemene ontsnapping voor stale ignores -- fix de ignore of haal de module "
        "uit de lijst."
    )
