"""Architecture test: generated agents mogen geen relatieve imports buiten
agent_runtime hebben. Geen uitzonderingen (ADR-034)."""

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
GENERATED_DIR = _REPO_ROOT / "src" / "core" / "agents" / "generated"


def _relative_imports_in_generated() -> tuple[list[tuple[str, int, str]], list[str], int]:
    """(treffers, bestanden die niet gelezen/geparsed konden worden, aantal gescand)."""
    hits = []
    fouten: list[str] = []
    gescand = 0
    for py_file in sorted(GENERATED_DIR.glob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{py_file.name}: {exc}")
            continue
        gescand += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                mod_or_names = node.module or ",".join(a.name for a in node.names)
                hits.append((py_file.name, node.lineno, mod_or_names))
    return hits, fouten, gescand


@pytest.mark.unit
def test_generated_agents_have_zero_relative_imports() -> None:
    """Alle generated agents gebruiken absolute imports (ADR-034, TID252 gate).

    ROOD tot Dag 3 Fase 2 is voltooid.
    TODO(SP-DSM-006): verwijder comment als Fase 2 groen is.
    """
    assert GENERATED_DIR.is_dir(), f"generated/ not found at {GENERATED_DIR}"
    hits, fouten, gescand = _relative_imports_in_generated()
    assert gescand >= 5, (
        f"Slechts {gescand} bestanden gescand in {GENERATED_DIR} -- dat lijkt een "
        "(bijna) lege map. Deze guard controleert dan vrijwel niets."
    )
    assert not fouten, (
        "Deze bestanden in generated/ konden niet gelezen/geparsed worden en zijn NIET "
        "gecontroleerd op relatieve imports:\n" + "\n".join(f"  - {f}" for f in fouten)
    )
    assert hits == [], (
        f"{len(hits)} relatieve import(s) gevonden in generated/ (verwacht: 0):\n"
        + "\n".join(f"  {f}:{ln} -> {mod}" for f, ln, mod in hits[:10])
        + (f"\n  ... en {len(hits) - 10} meer" if len(hits) > 10 else "")
    )
