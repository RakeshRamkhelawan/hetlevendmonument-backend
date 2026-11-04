"""Architecture test: agentic/workflow_router.py must exist and use service injection.

TODO(AUDIT-DB14a): AgenticOrchestrationService + workflow_router.py aanmaken.
"""

import ast
from pathlib import Path


def test_agentic_workflow_router_exists() -> None:
    """AUDIT-DB14a: agentic/workflow_router.py moet aanwezig zijn."""
    router_file = Path("src/core/api/v1/agentic/workflow_router.py")
    assert router_file.exists(), (
        "src/core/api/v1/agentic/workflow_router.py ontbreekt (AUDIT-DB14a). "
        "Maak dit bestand aan met AgenticOrchestrationService via Depends()."
    )


def test_agentic_workflow_router_no_direct_db_imports() -> None:
    """AUDIT-DB14a: workflow_router.py mag geen directe DB-imports bevatten."""
    FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}
    router_file = Path("src/core/api/v1/agentic/workflow_router.py")
    assert router_file.exists(), "src/core/api/v1/agentic/workflow_router.py ontbreekt"

    tree = ast.parse(router_file.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add(alias.name)
                if alias.asname:
                    imported.add(alias.asname)

    violations = FORBIDDEN & imported
    assert not violations, (
        f"workflow_router.py importeert verboden DB-symbolen: {violations}. "
        "Gebruik Depends(get_agentic_orchestration_service) in plaats van Depends(get_db)."
    )


def test_agentic_workflow_router_included_in_composite() -> None:
    """AUDIT-DB14a: workflow_router moet geincludeerd zijn in de composite router."""
    composite = Path("src/core/api/v1/agentic/router.py")
    assert composite.exists(), "src/core/api/v1/agentic/router.py ontbreekt"
    content = composite.read_text(encoding="utf-8")
    assert "workflow_router" in content, (
        "workflow_router is niet geincludeerd in src/core/api/v1/agentic/router.py"
    )
