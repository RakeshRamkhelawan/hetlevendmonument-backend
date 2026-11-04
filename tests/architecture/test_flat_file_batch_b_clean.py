"""SP-API-010 Dag 3 -- Batch B flat files: 0 module-level forbidden imports.

Lazy imports (col_offset > 0) zijn toegestaan -- ADR-033 Contract 1 geldt
alleen voor module-level imports (col_offset == 0).
"""

import ast
from pathlib import Path

FORBIDDEN_DOMAINS = [
    "src.core.database",
    "src.core.governance",
    "src.core.learning",
    "src.core.agents",
    "src.core.workflow",
    "src.core.llm",
]

BATCH_B_TARGET = [
    "src/core/api/knowledge_endpoints.py",
    "src/core/api/workflow_builder_endpoints.py",
    "src/core/api/billing_endpoints.py",
    "src/core/api/crag_endpoints.py",
    "src/core/api/swarm_websocket_endpoints.py",
    "src/core/api/nlp_endpoints.py",
    "src/core/api/workflow_suggestions_endpoints.py",
]


def test_batch_b_clean_files_have_zero_module_level_forbidden_imports() -> None:
    """Batch B flat files mogen geen module-level forbidden imports hebben (ADR-033 Contract 1).

    Lazy imports (col_offset > 0) zijn toegestaan: die vallen buiten module-level DSM scope.
    Health_endpoints.py en llm_endpoints.py zijn al schoon -- niet opgenomen in Batch B targets.
    """
    violations: list[str] = []
    for filepath in BATCH_B_TARGET:
        path = Path(filepath)
        if not path.exists():
            violations.append(f"{filepath}: FILE NOT FOUND")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node.col_offset != 0:
                continue  # lazy import -- toegestaan
            m = getattr(node, "module", "") or ""
            for dom in FORBIDDEN_DOMAINS:
                if m == dom or m.startswith(dom + "."):
                    violations.append(f"{filepath}:{node.lineno}: {m}")
                    break
    assert not violations, (
        "ADR-033 Contract 1 violations (module-level) in Batch B:\n" + "\n".join(violations)
    )
