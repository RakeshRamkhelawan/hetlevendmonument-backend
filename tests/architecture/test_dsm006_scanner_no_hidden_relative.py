"""Architecture test: dsm_full_analysis scanner mag geen relatieve
cross-module imports missen na sanering (ADR-034, ADR-033)."""

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent

SOURCE_DIRS: dict[str, list[str]] = {}
SCANNER_AVAILABLE = False


def classify(_: str) -> str | None:
    return None


try:
    sys.path.insert(0, str(_REPO_ROOT))
    from scripts.dsm_full_analysis import SOURCE_DIRS, classify  # type: ignore[assignment]

    SCANNER_AVAILABLE = True
except (ImportError, AttributeError):
    pass


def _file_to_module(f: Path) -> str:
    parts = f.with_suffix("").parts
    try:
        return ".".join(parts[list(parts).index("src") :])
    except ValueError:
        return ""


def _resolve_relative(fpath: Path, level: int, module: str) -> str:
    """CPython _resolve_name algoritme."""
    pkg = ".".join(_file_to_module(fpath).rsplit(".", 1)[:-1])
    if not pkg:
        return module
    base = pkg
    for _ in range(level - 1):
        base = base.rpartition(".")[0]
        if not base:
            return module
    return f"{base}.{module}" if module else base


def _is_test_path(f: Path) -> bool:
    """Padsegment-gebaseerde testuitsluiting -- geen substring-zoekactie.

    `"test" in str(f).lower()` sluit ook een productiebestand als attestation.py uit
    (bevat "test" als kale substring). Nu: een exact segment "test"/"tests" in het pad,
    of een bestandsnaam die met test_ begint.
    """
    parts_lower = {p.lower() for p in f.parts}
    if "tests" in parts_lower or "test" in parts_lower:
        return True
    return f.name.lower().startswith("test_")


def _candidate_files(root: Path) -> list[Path]:
    """SOURCE_DIRS['agent_runtime'] bevat zowel mappen als losse bestanden.

    `root.rglob("*.py")` op een BESTANDSpad geeft stil een lege lijst terug -- geen
    fout. Elke losse-bestand-vermelding (bijv. src/core/container.py) werd daardoor
    NOOIT gescand, los van de andere gaten in deze guard.
    """
    if root.is_file():
        return [root]
    return list(root.rglob("*.py"))


def _count_hidden_relative_cross_module() -> tuple[int, list[str], int]:
    """(aantal verborgen imports, paden die niet gelezen/geparsed konden worden, aantal gescand)."""
    ar_dirs = SOURCE_DIRS.get("agent_runtime", [])
    hidden = 0
    fouten: list[str] = []
    gescand = 0
    for dir_path in ar_dirs:
        root = Path(dir_path)
        if not root.exists():
            continue
        for f in _candidate_files(root):
            if _is_test_path(f) or "__pycache__" in str(f):
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8-sig"))
            except (OSError, SyntaxError, UnicodeDecodeError) as exc:
                fouten.append(f"{f}: {exc}")
                continue
            gescand += 1
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.level == 0:
                    continue
                resolved = _resolve_relative(f, node.level, node.module or "")
                if not resolved.startswith("src."):
                    continue
                cat = classify(resolved)
                if cat is not None and cat != "agent_runtime":
                    hidden += 1
    return hidden, fouten, gescand


@pytest.mark.unit
def test_scanner_module_is_available() -> None:
    """Vangnet: een kapotte scanner-import mag deze guard niet stilzwijgend SKIPPEN.

    De vorige vorm gebruikte @pytest.mark.skipif(not SCANNER_AVAILABLE, ...) op de
    enige test in dit bestand. Faalt de import van dsm_full_analysis, dan wordt de
    hele guard geskipt in plaats van rood -- in een CI-samenvatting is een geskipte
    test niet te onderscheiden van een geslaagde, terwijl er dan mogelijk honderden
    verborgen imports ongecontroleerd blijven.
    """
    assert SCANNER_AVAILABLE, (
        "scripts.dsm_full_analysis kon niet geimporteerd worden (SOURCE_DIRS/classify "
        "ontbreken of zijn hernoemd). Zonder deze module controleert "
        "test_scanner_sees_all_cross_module_imports NIETS."
    )


@pytest.mark.unit
def test_scanner_sees_all_cross_module_imports() -> None:
    """Scanner mag geen relatieve cross-module imports missen na sanering.

    ROOD tot Dag 3 Fase 1 (scanner fix) + Fase 2 (365 imports) voltooid zijn.
    TODO(SP-DSM-006): verwijder comment als hidden == 0 en scanner geupdated.
    """
    if not SCANNER_AVAILABLE:
        pytest.skip("dsm_full_analysis niet beschikbaar -- zie test_scanner_module_is_available")
    hidden, fouten, gescand = _count_hidden_relative_cross_module()
    assert gescand >= 200, (
        f"Slechts {gescand} bestanden gescand over alle agent_runtime-paden -- dat lijkt "
        "een (bijna) lege scan. Deze guard controleert dan vrijwel niets."
    )
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd op "
        "verborgen relatieve imports:\n" + "\n".join(f"  - {f}" for f in fouten)
    )
    assert hidden == 0, (
        f"{hidden} relatieve cross-module import(s) onzichtbaar voor scanner. "
        "Fix: (1) voeg resolve_relative toe aan dsm_full_analysis.py, "
        "(2) converteer relative imports naar absoluut (Ruff TID252)."
    )
