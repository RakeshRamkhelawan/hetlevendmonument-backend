"""
Verify that external_agent_router does NOT import from unittest.mock.
Importing test utilities in production code bypasses real dependency checks.
"""

import ast
import pathlib


def test_no_unittest_mock_import():
    """Parse the router file AST and assert no unittest.mock import exists."""
    router_file = (
        pathlib.Path(__file__).parent.parent.parent
        / "src/core/api/v1/company/external_agent_router.py"
    )
    source = router_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "unittest.mock" in node.module:
                imported_names = [alias.name for alias in node.names]
                raise AssertionError(
                    f"Production code imports test utilities from unittest.mock: "
                    f"{imported_names}. Replace with null-object stubs."
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "unittest" in alias.name:
                    raise AssertionError(f"Production code imports unittest: {alias.name}")


import asyncio


def test_null_stubs_return_correct_types():
    """Verify _NullPolicyEngine and _NullBudgetManager return correct types."""
    import sys

    # Add repo root to path if needed
    repo_root = str(pathlib.Path(__file__).parent.parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from src.core.api.v1.company.external_agent_router import _NullBudgetManager, _NullPolicyEngine

    # Test _NullPolicyEngine
    engine = _NullPolicyEngine()
    result = engine.validate_output({"key": "value"})
    assert result == {"valid": True}, f"Expected {{'valid': True}}, got {result}"

    # Test _NullBudgetManager (async methods)
    manager = _NullBudgetManager()

    budget_result = asyncio.run(manager.check_budget())
    assert budget_result.allowed is True
    assert hasattr(budget_result, "remaining_tokens")

    track_result = asyncio.run(manager.track_usage())
    assert track_result is None
