"""Test dat dependencies.py geen module-level agent_runtime imports bevat.

SP-DSM-COMPLETE Dag 3: lazy imports breken infra <-> agent_runtime circular.
"""

import ast
from pathlib import Path


def _get_toplevel_imports() -> list[str]:
    """Lees module-level ImportFrom nodes uit dependencies.py (niet TYPE_CHECKING)."""
    path = Path("src/core/dependencies.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.If):
            # Skip TYPE_CHECKING blocks
            pass
    return modules


def test_dependencies_has_no_toplevel_agent_runtime_imports() -> None:
    """dependencies.py mag geen module-level imports hebben van agent_runtime modules."""
    toplevel = _get_toplevel_imports()
    forbidden_prefixes = (
        "src.core.agents",
        "src.core.autonomy",
        "src.core.collaboration",
        "src.core.ai",
        "src.core.learning",
        "src.core.workflow",
    )
    bad = [m for m in toplevel if any(m.startswith(p) for p in forbidden_prefixes)]
    assert bad == [], f"Module-level agent_runtime imports in dependencies.py: {bad}"


def test_dependencies_is_importable() -> None:
    """dependencies.py moet importeerbaar zijn zonder ImportError."""
    import importlib

    mod = importlib.import_module("src.core.dependencies")
    assert hasattr(mod, "get_autonomous_agent_dependency")
    assert hasattr(mod, "get_task_distributor")
    assert hasattr(mod, "get_agent_registry")
