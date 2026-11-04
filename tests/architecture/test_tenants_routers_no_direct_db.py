"""AUDIT-DB-01: tenants routers must not directly import database primitives.

This architecture test is scoped to the tenants domain so it turns green
within the pilot iteration and does not block CI for remaining domains.
"""

import ast
from pathlib import Path

import pytest

_ROUTER_FILES = [
    "src/core/api/v1/tenants/router.py",
    "src/core/api/v1/tenants/tenants_list_router.py",
    "src/core/api/v1/tenants/tenants_detail_router.py",
    "src/core/api/v1/tenants/tenants_stats_router.py",
]

_FORBIDDEN_NAMES = {
    "get_db",
    "AsyncSession",
    "select",
    "func",
    "Tenant",
    "Agent",
    "AuditLog",
    "Document",
}


@pytest.mark.architecture
def test_tenants_routers_no_direct_db() -> None:
    """TODO(SP-DB-01): tenants routers must not contain direct database imports."""
    offenders: list[str] = []
    repo_root = Path(__file__).parents[2]

    for rel_path in _ROUTER_FILES:
        path = repo_root / rel_path
        assert path.exists(), f"Expected router file to exist: {rel_path}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name in _FORBIDDEN_NAMES:
                        found.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _FORBIDDEN_NAMES:
                        found.add(alias.name)

        if found:
            offenders.append(f"{rel_path}: {sorted(found)}")

    assert not offenders, "Direct database imports found in tenants routers:\n" + "\n".join(
        f"  - {item}" for item in offenders
    )
