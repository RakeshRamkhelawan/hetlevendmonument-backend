"""
Architecture test: gatekeeper/router.py mag geen directe DB-imports bevatten (ADR-033).
TODO(SP-AUDIT-DB12): gatekeeper router ADR-033 fix.
"""

import ast
from pathlib import Path


def test_gatekeeper_router_no_direct_db_imports() -> None:
    FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}
    router = Path("src/core/api/v1/gatekeeper/router.py")
    assert router.exists(), f"{router} ontbreekt"
    tree = ast.parse(router.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname if alias.asname else alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname if alias.asname else alias.name)
    violations = FORBIDDEN & imported
    assert not violations, (
        f"gatekeeper/router.py importeert verboden DB-symbolen: {violations} -- "
        "verwijder re-export van get_db (ADR-033)"
    )
