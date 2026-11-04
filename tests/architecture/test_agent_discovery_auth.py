"""FA-SEC-001: agent_discovery tenant isolation security tests.

Both tests are RED before the fix and GREEN after.
"""

import ast
from pathlib import Path


def test_agent_discovery_not_in_public_prefixes() -> None:
    """FA-SEC-001: /api/v1/agentic/discovery must NOT be in PUBLIC_PREFIXES.

    When present, TenantMiddleware skips JWT extraction and get_tenant_id()
    returns None, causing an unfiltered cross-tenant SELECT on RegisteredAgent.
    """
    from src.core.shared.public_registry import PublicEndpointRegistry

    assert "/api/v1/agentic/discovery" not in PublicEndpointRegistry.PUBLIC_PREFIXES, (
        "SECURITY P0: /api/v1/agentic/discovery is publicly accessible -- "
        "any unauthenticated caller receives all agents from all tenants. "
        "Remove the entry from PUBLIC_PREFIXES and enforce JWT auth."
    )


def test_agent_discovery_no_unfiltered_tenant_none_branch() -> None:
    """FA-SEC-001: _get_all_agents must NOT contain an unfiltered 'if tenant_id is None' branch.

    That branch issues select(RegisteredAgent) without a WHERE clause,
    returning cross-tenant data to unauthenticated callers.
    """
    source = Path("src/core/api/v1/agentic/agent_discovery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if not (isinstance(test.left, ast.Name) and test.left.id == "tenant_id"):
            continue
        if any(isinstance(c, ast.Constant) and c.value is None for c in test.comparators):
            raise AssertionError(
                f"SECURITY P0: 'if tenant_id is None' found at line {node.lineno} "
                f"in agent_discovery.py -- unfiltered SELECT returns cross-tenant data. "
                f"Remove the None branch and use require_tenant_id() exclusively."
            )
