"""SP-API-010 Dag 2 -- architecture tests: Batch A gap bestanden.

3 bestanden hebben structurele blockers die proxy stub migratie in Dag 2 verhinderen.
Tests zijn xfail(strict=True): ze MOGEN rood zijn; als ze onverwacht groen worden
is dat een CI-fout (blocker gefixed zonder xfail te verwijderen).

Blockers:
  agent_endpoints.py           -- v1/agents/ importeert module-level FROM agent_endpoints.py (circular)
  admin_learning_endpoints.py  -- GDPR en LLM-budget routes hebben geen v1/ service equivalent
  assistant_endpoints.py       -- POST /ask heeft geen v1/ equivalent (/copilot/turn is ander contract)
"""

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = (
    "src.core.database",
    "src.core.governance",
    "src.core.learning",
    "src.core.agents",
    "src.core.workflow",
    "src.core.llm",
)


def _assert_target_exists(filepath: str) -> None:
    """Vangnet: een verwijderd/hernoemd doelbestand mag deze tests niet stilzwijgend
    trivially laten slagen -- `_collect_forbidden_imports` geeft dan stil `[]` terug."""
    assert Path(filepath).exists(), (
        f"{filepath} bestaat niet meer. Verplaatst of hernoemd (i.p.v. de refactor uit "
        "SP-API-011 voltooid)? Deze test controleert dan niets meer -- werk het pad "
        "hierboven bij."
    )


def _collect_forbidden_imports(filepath: str) -> list[str]:
    path = Path(filepath)
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in FORBIDDEN_PREFIXES:
                if module.startswith(prefix):
                    found.append(f"{filepath}:{node.lineno} -- from {module} import ...")
                    break
    return found


def test_agent_endpoints_has_zero_forbidden_imports() -> None:
    """TODO(SP-API-011): v1/agents/ importeert module-level FROM agent_endpoints.py.

    Oplossing: refactor v1/agents/ (agent_management_router.py, agent_execution_router.py,
    agent_crud_router.py) zodat ze niet meer van de flat file afhangen. Dan proxy stub aanmaken.
    """
    _assert_target_exists("src/core/api/agent_endpoints.py")
    violations = _collect_forbidden_imports("src/core/api/agent_endpoints.py")
    assert violations == [], (
        f"{len(violations)} verboden imports in agent_endpoints.py: {violations}"
    )


def test_admin_learning_endpoints_has_zero_forbidden_imports() -> None:
    """TODO(SP-API-011): admin_learning_endpoints.py -- GDPR en LLM-budget routes.

    POST /gdpr/*, GET+PUT /tenants/{id}/llm-budget hebben geen v1/ service equivalent.
    Oplossing: maak v1/learning/ of v1/admin/ service aan voor deze routes, dan proxy stub.
    """
    _assert_target_exists("src/core/api/admin_learning_endpoints.py")
    violations = _collect_forbidden_imports("src/core/api/admin_learning_endpoints.py")
    assert violations == [], (
        f"{len(violations)} verboden imports in admin_learning_endpoints.py: {violations}"
    )


def test_assistant_endpoints_has_zero_forbidden_imports() -> None:
    """TODO(SP-API-011): assistant_endpoints.py -- POST /ask route.

    /copilot/turn is de opvolger maar heeft een ander contract (session_id, council, etc.).
    Oplossing: maak v1/assistant/ service aan die /ask delegeert, dan proxy stub.
    """
    _assert_target_exists("src/core/api/assistant_endpoints.py")
    violations = _collect_forbidden_imports("src/core/api/assistant_endpoints.py")
    assert violations == [], (
        f"{len(violations)} verboden imports in assistant_endpoints.py: {violations}"
    )
