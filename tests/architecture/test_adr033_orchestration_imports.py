"""ADR-033 Contract 1: orchestration routers mogen NIET direct uit src.core.agents importeren.

SP-API-009 Dag 2 -- regressietest voor import-linter contract api-no-domain.
"""

import ast
from pathlib import Path


ROUTER_FILES = [
    "src/core/api/v1/orchestration/critic_router.py",
    "src/core/api/v1/orchestration/health_router.py",
    "src/core/api/v1/orchestration/stats_router.py",
    "src/core/api/v1/orchestration/workflow_router.py",
]
FORBIDDEN_PREFIX = "src.core.agents"


def _get_direct_agent_imports(filepath: str) -> list[str]:
    tree = ast.parse(Path(filepath).read_text(encoding="utf-8"))
    return [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(FORBIDDEN_PREFIX)
    ]


def test_critic_router_has_no_direct_agent_imports() -> None:
    violations = _get_direct_agent_imports(ROUTER_FILES[0])
    assert violations == [], f"critic_router.py heeft directe agent-imports: {violations}"


def test_health_router_has_no_direct_agent_imports() -> None:
    violations = _get_direct_agent_imports(ROUTER_FILES[1])
    assert violations == [], f"health_router.py heeft directe agent-imports: {violations}"


def test_stats_router_has_no_direct_agent_imports() -> None:
    violations = _get_direct_agent_imports(ROUTER_FILES[2])
    assert violations == [], f"stats_router.py heeft directe agent-imports: {violations}"


def test_workflow_router_has_no_direct_agent_imports() -> None:
    violations = _get_direct_agent_imports(ROUTER_FILES[3])
    assert violations == [], f"workflow_router.py heeft directe agent-imports: {violations}"
