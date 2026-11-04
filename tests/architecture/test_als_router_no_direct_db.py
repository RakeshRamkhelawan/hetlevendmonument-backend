"""
Architecture test: als/router.py mag geen directe DB-imports bevatten (ADR-033).
Rood voor S2 implementatie -- groen na fix.
TODO(SP-AUDIT-DB08): als router ADR-033 fix.
"""

import ast
from pathlib import Path


def test_als_router_no_direct_db_imports() -> None:
    FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}
    router = Path("src/core/api/v1/als/router.py")
    assert router.exists(), f"{router} ontbreekt"
    tree = ast.parse(router.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                imported.add(name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                imported.add(name)
    violations = FORBIDDEN & imported
    assert not violations, (
        f"als/router.py importeert verboden DB-symbolen: {violations} -- "
        "verwijder re-export van get_db, patch src.core.api.dependencies direct in tests (ADR-033)"
    )
