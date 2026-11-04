"""ADR-034 architecture boundary tests for orchestration/ sub-routers.

Enforces two rules that .importlinter Contract 2 cannot cover (wildcard self-reference):
1. Orchestration sub-routers must not directly import src.core.database.database.
2. ADR-034 core boundary: src.core.agents/ files migrated in SP-AGT-002 must not
   import src.core.database.database directly.

These tests are the automated gate for ADR-034 compliance until Contract 2+3
can be re-enabled (SP-AGT-004, after Strangler Fig migration completes).
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
ORCH_DIR = REPO_ROOT / "src" / "core" / "api" / "v1" / "orchestration"
AGENTS_DIR = REPO_ROOT / "src" / "core" / "agents"

FORBIDDEN_DB_IMPORT = "src.core.database.database"

SP_AGT_002_MIGRATED = [
    "agent_discovery.py",
    "agent_registry.py",
    "agent_router_agent.py",
    "base_agent.py",
]


def _get_direct_imports(path: Path) -> list[str]:
    """Return all `from X import Y` module strings in the file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
    return modules


def test_orchestration_routers_do_not_import_database() -> None:
    """Orchestration sub-routers must not directly import src.core.database.database (ADR-034)."""
    violations: list[str] = []
    for py_file in ORCH_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        for module in _get_direct_imports(py_file):
            if module.startswith(FORBIDDEN_DB_IMPORT):
                violations.append(f"{py_file.relative_to(REPO_ROOT)}")
    assert not violations, (
        f"ADR-034 violation: orchestration/ files import {FORBIDDEN_DB_IMPORT} directly:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\nFix: use IAgentRepository protocol or inject session factory."
    )


def test_sp_agt_002_migrated_agents_do_not_import_database() -> None:
    """SP-AGT-002 migrated agent files must not import src.core.database.database (ADR-034)."""
    violations: list[str] = []
    missing: list[str] = []
    for filename in SP_AGT_002_MIGRATED:
        py_file = AGENTS_DIR / filename
        if not py_file.exists():
            missing.append(filename)
            continue
        for module in _get_direct_imports(py_file):
            if module.startswith(FORBIDDEN_DB_IMPORT):
                violations.append(f"{py_file.relative_to(REPO_ROOT)}: imports {module}")
    assert not missing, (
        "SP_AGT_002_MIGRATED noemt bestanden die niet meer bestaan (hernoemd/verplaatst?): "
        + ", ".join(missing)
        + "\nDeze guard controleert dan NIETS voor die naam -- werk de lijst bij."
    )
    assert not violations, (
        "ADR-034 violation: SP-AGT-002 migrated files still import database directly:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_orchestration_sub_routers_do_not_cross_import() -> None:
    """Orchestration sub-routers must not import from other sub-router files (ADR-033 sec. 3b).

    Allowed imports from the orchestration package:
    - dependencies.py and schemas.py are shared infrastructure -- all files may import them.
    - router.py is the aggregator and is exempt from this check.
    - stats_router.py may import DI factories from workflow_router + health_router (by design).

    Only cross-imports between the actual router files are flagged.
    """
    # Shared infra modules that all routers may import
    SHARED_MODULES = {
        "src.core.api.v1.orchestration.dependencies",
        "src.core.api.v1.orchestration.schemas",
    }
    # router.py is the top-level aggregator -- exempt
    EXEMPT_FILES = {"router.py", "__init__.py"}
    # Explicit allowlist for stats_router (aggregates stats from peer routers by design)
    ALLOWED_CROSS_IMPORTS = {
        "stats_router.py": {
            "src.core.api.v1.orchestration.workflow_router",
            "src.core.api.v1.orchestration.health_router",
        },
    }
    ORCH_PREFIX = "src.core.api.v1.orchestration."
    violations: list[str] = []
    for py_file in ORCH_DIR.glob("*.py"):
        if "__pycache__" in str(py_file) or py_file.name in EXEMPT_FILES:
            continue
        allowed = SHARED_MODULES | ALLOWED_CROSS_IMPORTS.get(py_file.name, set())
        for module in _get_direct_imports(py_file):
            if module.startswith(ORCH_PREFIX) and module not in allowed:
                violations.append(f"{py_file.name} imports {module}")
    assert not violations, (
        "ADR-033 violation: orchestration sub-routers cross-import each other:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\nFix: move shared DI factories to dependencies.py."
    )


def test_providers_py_has_no_database_import_after_dag1_wiring() -> None:
    """providers.py mag na SP-AGT-003 Dag 1 wiring geen src.core.database.database importeren (ADR-034).

    Regressietest: controleert dat de AgentRouterAgent injectie geen database-import
    heeft geintroduceerd in providers.py. Loopt altijd -- ook zonder PostgreSQL en op Windows.
    """
    providers = REPO_ROOT / "src" / "core" / "workflow" / "providers.py"
    tree = ast.parse(providers.read_text(encoding="utf-8"))

    violations = [
        f"L{n.lineno}: from {n.module} import ..."
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module and "src.core.database.database" in n.module
    ]
    assert not violations, (
        "ADR-034 regressie: providers.py importeert database direct na SP-AGT-003 Dag 1 wiring:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\nHerstel: verwijder de database-import en gebruik session factory injectie."
    )
