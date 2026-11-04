"""SP-API-010 Dag 2 -- architecture tests: Batch A flat files (clean groep).

6 bestanden moeten 0 verboden imports hebben na proxy stub migratie.
Test is ROOD voor implementatie (14 violations aanwezig), GROEN daarna.

Verboden domeinen (ADR-033 Contract 1+2):
  src.core.database  |  src.core.governance  |  src.core.learning
  src.core.agents    |  src.core.workflow     |  src.core.llm
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

BATCH_A_CLEAN = [
    "src/core/api/orchestrator_endpoints.py",
    "src/core/api/tool_endpoints.py",
    "src/core/api/agentic_flow_endpoints.py",
    "src/core/api/pack_feedback_endpoints.py",
    "src/core/api/template_endpoints.py",
    "src/core/api/workflow_refinement_endpoints.py",
]


def _collect_forbidden_imports(filepath: str) -> list[str]:
    """Geeft alle verboden ImportFrom-nodes terug (module-level en function-body)."""
    path = Path(filepath)
    if not path.exists():
        return [f"{filepath}: BESTAND ONTBREEKT"]
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in FORBIDDEN_PREFIXES:
                if module.startswith(prefix):
                    names = ", ".join(a.name for a in node.names)
                    found.append(f"{filepath}:{node.lineno} -- from {module} import {names}")
                    break
    return found


def test_batch_a_clean_files_have_zero_forbidden_imports() -> None:
    """SP-API-010 Dag 2: 6 Batch-A bestanden hebben 0 verboden imports na proxy stub.

    Start ROOD (14 violations aanwezig). Wordt GROEN zodra alle stubs klaar zijn.
    Bewaakt ADR-033: flat files delegeren via v1/ dependencies, geen directe domain-imports.
    """
    violations: list[str] = []
    for filepath in BATCH_A_CLEAN:
        violations.extend(_collect_forbidden_imports(filepath))

    assert violations == [], (
        f"SP-API-010 Dag 2: {len(violations)} verboden import(s) in Batch-A bestanden "
        "(fix: proxy stubs aanmaken, imports via v1/<domein>/dependencies.py):\n"
        + "\n".join(violations)
    )
