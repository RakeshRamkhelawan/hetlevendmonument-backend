"""Architecture test: security_middleware mag GEEN top-level import hebben naar tenancy/middleware.
[SP-DSM-016 Dag 1 -- AUDIT-DSM-004]
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_SECURITY_MIDDLEWARE = _REPO_ROOT / "src/core/security/security_middleware.py"
_SHARED_PUBLIC_REGISTRY = _REPO_ROOT / "src/core/shared/public_registry.py"


def _get_top_level_imports(path: Path) -> list[str]:
    """Return top-level runtime-import module names (not behind TYPE_CHECKING)."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

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

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if node.lineno in type_checking_lines:
                continue
            module = getattr(node, "module", None) or ""
            modules.append(module)
    return modules


def test_dsm016_security_middleware_no_tenancy_import() -> None:
    """security_middleware mag GEEN top-level import hebben naar src.core.middleware.
    [SP-DSM-016 Dag 1 -- AUDIT-DSM-004 FIXED]
    """
    modules = _get_top_level_imports(_SECURITY_MIDDLEWARE)
    violations = [m for m in modules if "src.core.middleware" in m]
    assert not violations, (
        f"AUDIT-DSM-004 [SP-DSM-016 REGRESSION]: security_middleware importeert "
        f"tenancy/middleware: {violations}. "
        f"Fix: verplaats public_registry naar src/core/shared/."
    )


def test_dsm016_public_registry_in_shared() -> None:
    """public_registry MOET in src/core/shared/ staan na AUDIT-DSM-004 fix.
    [SP-DSM-016 Dag 1]
    """
    assert _SHARED_PUBLIC_REGISTRY.exists(), (
        "AUDIT-DSM-004 [SP-DSM-016]: public_registry is nog niet verplaatst naar "
        "src/core/shared/. Huidig pad: src/core/middleware/public_registry.py"
    )
