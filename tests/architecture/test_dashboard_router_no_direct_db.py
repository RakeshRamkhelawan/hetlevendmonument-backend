"""
Architecture test: dashboard router must not import DB symbols directly (ADR-033).
"""

import ast
from pathlib import Path


def test_dashboard_router_no_direct_db_imports():
    """ADR-033: dashboard router mag get_db/AsyncSession/select/func niet direct importeren."""
    FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}
    router = Path("src/core/api/v1/dashboard/router.py")
    tree = ast.parse(router.read_text(encoding="utf-8"))
    imported = {
        alias.name if alias.asname is None else alias.asname
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    violations = FORBIDDEN & imported
    assert not violations, f"dashboard/router.py importeert verboden DB-symbolen: {violations}"
