"""Architecture test: governance -> agent_runtime directe imports = 0.

SP-DSM-006 Dag 1 -- dsar_service.py mag Agent ORM NIET direct importeren.
Fix: raw SQL of geinjected repository zonder import uit src.core.agents.
"""

import ast
from pathlib import Path

import pytest

GOVERNANCE_DIR = Path("src/core/governance")
AGENT_RUNTIME_PREFIXES = (
    "src.core.agents",
    "src.domains.memory",
    "src.domains.flows",
    "src.domains.agentic",
)


def _count_governance_to_ar_imports() -> tuple[list[tuple[str, str, int]], list[str], int]:
    """(treffers, paden die niet parseerden, aantal gescand) voor governance -> agent_runtime."""
    hits = []
    fouten: list[str] = []
    gescand = 0
    for py_file in GOVERNANCE_DIR.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8-sig", errors="ignore"))
        except SyntaxError as exc:
            fouten.append(f"{py_file}: {exc}")
            continue
        gescand += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module.startswith(p) for p in AGENT_RUNTIME_PREFIXES):
                    hits.append((str(py_file), node.module, node.lineno))
    return hits, fouten, gescand


@pytest.mark.unit
def test_governance_has_zero_direct_agent_runtime_imports() -> None:
    """governance -> agent_runtime directe imports MOETEN 0 zijn (ADR-034)."""
    hits, fouten, gescand = _count_governance_to_ar_imports()
    assert gescand >= 30, (
        f"Slechts {gescand} bestanden gescand onder {GOVERNANCE_DIR} -- dat lijkt een "
        "(bijna) lege boom. Deze guard controleert dan vrijwel niets."
    )
    assert not fouten, (
        "Deze bestanden parseren niet en zijn NIET gecontroleerd op agent_runtime-imports:\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )
    assert hits == [], (
        f"governance -> agent_runtime: {len(hits)} import(s) gevonden "
        f"(target = 0):\n" + "\n".join(f"  {f}:{lijn} -> {mod}" for f, mod, lijn in hits)
    )
