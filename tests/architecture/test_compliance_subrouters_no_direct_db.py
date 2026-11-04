"""
Architecture test: compliance sub-routers mogen geen directe DB-imports bevatten (ADR-033).
TODO(SP-AUDIT-DB13): compliance sub-router service-injectie S4.
"""

import ast
from pathlib import Path

SUBROUTER_FILES = [
    "src/core/api/v1/compliance/score_router.py",
    "src/core/api/v1/compliance/gdpr_summary_router.py",
    "src/core/api/v1/compliance/gdpr_dsar_router.py",
    "src/core/api/v1/compliance/ai_act_summary_router.py",
    "src/core/api/v1/compliance/ai_act_decisions_router.py",
    "src/core/api/v1/compliance/integrity_verify_router.py",
    "src/core/api/v1/compliance/integrity_status_router.py",
    "src/core/api/v1/compliance/pdf_router.py",
]

FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}


def _get_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname if alias.asname else alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname if alias.asname else alias.name)
    return imported


def test_compliance_subrouters_no_direct_db_imports() -> None:
    """TODO(SP-AUDIT-DB13): compliance sub-routers injecteren DB via service, niet direct."""
    violations: dict[str, set[str]] = {}
    for path_str in SUBROUTER_FILES:
        path = Path(path_str)
        assert path.exists(), f"{path} ontbreekt"
        found = FORBIDDEN & _get_imports(path)
        if found:
            violations[path_str] = found
    assert not violations, (
        "Compliance sub-routers importeren verboden DB-symbolen (ADR-033):\n"
        + "\n".join(f"  {f}: {v}" for f, v in violations.items())
    )
