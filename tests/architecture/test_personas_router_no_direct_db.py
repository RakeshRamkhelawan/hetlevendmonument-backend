"""
Architecture test: personas/router.py mag geen directe DB-imports bevatten (ADR-033).
Rood voor S2 implementatie -- groen na fix.
TODO(SP-AUDIT-DB06): personas router ADR-033 fix.
"""

import ast
from pathlib import Path


def test_personas_router_no_direct_db_imports() -> None:
    FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}
    router = Path("src/core/api/v1/personas/router.py")
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
        f"personas/router.py importeert verboden DB-symbolen: {violations} -- "
        "verplaats naar personas/dependencies.py (ADR-033)"
    )
