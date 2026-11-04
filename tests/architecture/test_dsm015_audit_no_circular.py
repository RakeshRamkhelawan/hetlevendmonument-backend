"""Architecture test: governance/audit_service mag geen runtime-import naar security/auth hebben.
[SP-DSM-015 Dag 2 -- AUDIT-DSM-002]
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_AUDIT_SERVICE = _REPO_ROOT / "src/core/governance/services/audit_service.py"


def _get_runtime_imports(path: Path) -> list[str]:
    """Return module names imported at runtime (not behind TYPE_CHECKING)."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Collect line numbers inside `if TYPE_CHECKING:` blocks
    type_checking_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if is_tc:
                for child in ast.walk(node):
                    line = getattr(child, "lineno", None)
                    if line is not None:
                        type_checking_lines.add(line)

    runtime_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if node.lineno in type_checking_lines:
                continue
            module = getattr(node, "module", None) or ""
            runtime_modules.append(module)

    return runtime_modules


def test_dsm015_governance_no_auth_backward_import() -> None:
    """governance/audit_service mag GEEN runtime-import hebben naar security_manager of auth.
    [SP-DSM-015 Dag 2 -- AUDIT-DSM-002 FIXED]
    """
    runtime_modules = _get_runtime_imports(_AUDIT_SERVICE)
    violations = [m for m in runtime_modules if "security_manager" in m or "src.core.auth" in m]
    assert not violations, (
        f"AUDIT-DSM-002 [SP-DSM-015 REGRESSION]: governance/audit_service heeft runtime-import "
        f"naar security/auth: {violations}. "
        f"Fix: vervang ThreatLevel-enum import door string-literal in log_security_event()."
    )
