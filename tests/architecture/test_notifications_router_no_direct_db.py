"""
Architecture test: notifications router must not import DB symbols directly (ADR-033).
"""

import ast
from pathlib import Path


def test_notifications_router_no_direct_db_imports():
    """ADR-033: notifications router mag get_db/AsyncSession/select/func niet direct importeren."""
    FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}
    router = Path("src/core/api/v1/notifications/router.py")
    tree = ast.parse(router.read_text(encoding="utf-8"))
    imported = {
        alias.name if alias.asname is None else alias.asname
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    violations = FORBIDDEN & imported
    assert not violations, f"notifications/router.py importeert verboden DB-symbolen: {violations}"
