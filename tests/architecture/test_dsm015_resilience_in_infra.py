"""
SP-DSM-015 Dag 1: circuit-breaker implementatie hoort in src/core/shared/,
niet in tool_broker.

RODE tests: falen VOOR de code-fix, slagen NA de fix.
TODO(SP-DSM-015): tests worden groen na verplaatsing naar src/core/shared/tool_broker_resilience.py.

Bewijs baseline (rood): arch-suite 225 passed, 19 pre-existing failed (test_tenant_context_workers),
13 xfailed -- deze 3 tests zijn aanvullend ROOD.
"""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.architecture


def _direct_imports_in_file(path: Path) -> list[str]:
    """Geeft de module-strings van alle ImportFrom-statements terug."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except SyntaxError:
        return []
    return [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ]


def test_dsm015_tool_broker_resilience_canonical_file_exists_in_shared():
    """Canonical circuit-breaker implementatie moet in src/core/shared/ zitten -- SP-DSM-015 dag 1."""
    target = REPO / "src" / "core" / "shared" / "tool_broker_resilience.py"
    assert target.exists(), (
        "src/core/shared/tool_broker_resilience.py bestaat nog niet. "
        "Verplaats de implementatie uit tool_broker/resilience.py -- SP-DSM-015 dag 1."
    )


def test_dsm015_auth_no_direct_tool_broker_resilience_import():
    """hardening/resilience.py mag niet rechtstreeks importeren uit tool_broker.resilience -- SP-DSM-015 dag 1."""
    hardening = REPO / "src" / "core" / "hardening" / "resilience.py"
    assert hardening.exists(), f"Bestand niet gevonden: {hardening}"
    imports = _direct_imports_in_file(hardening)
    violations = [i for i in imports if i == "src.core.tool_broker.resilience"]
    assert len(violations) == 0, (
        f"hardening/resilience.py importeert nog rechtstreeks uit tool_broker.resilience: {violations}. "
        "Wijzig naar src.core.shared.tool_broker_resilience -- SP-DSM-015 dag 1."
    )


def test_dsm015_integrations_no_direct_tool_broker_resilience_import():
    """activepieces/client.py mag niet rechtstreeks importeren uit tool_broker.resilience -- SP-DSM-015 dag 1."""
    client = REPO / "src" / "core" / "activepieces" / "client.py"
    assert client.exists(), f"Bestand niet gevonden: {client}"
    imports = _direct_imports_in_file(client)
    violations = [i for i in imports if i == "src.core.tool_broker.resilience"]
    assert len(violations) == 0, (
        f"activepieces/client.py importeert nog rechtstreeks uit tool_broker.resilience: {violations}. "
        "Wijzig naar src.core.shared.tool_broker_resilience -- SP-DSM-015 dag 1."
    )
