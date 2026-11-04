"""
Slice 6: ComplianceAgent Direct Tests (Standalone Execution)

Run directly: python test_slice6_direct.py

Tests ComplianceAgent compliance checking without pytest fixtures.
"""

import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.agents.capabilities.compliance_agent import ComplianceAgent
from src.core.agents.capabilities.schemas import (
    ComplianceContext,
    ComplianceResult,
    ComplianceStatus,
)


async def test_allows_compliant_action():
    """Test 1: Allowed status for compliant actions."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="read_document",
        target_resource="document_123",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={"doc_id": "123"},
    )

    result = await agent.check_compliance(context)

    assert result.status == ComplianceStatus.ALLOWED, f"Expected ALLOWED, got {result.status}"
    assert len(result.issues) == 0, f"Expected no issues, got {len(result.issues)}"
    assert len(result.passed_checks) > 0, "Expected some passed checks"
    print("✓ Test 1 passed: Allows compliant action")


async def test_blocks_non_compliant_action():
    """Test 2: Blocked status for non-compliant actions."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="disable_encryption",
        target_resource="database",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={},
    )

    result = await agent.check_compliance(context)

    assert result.status == ComplianceStatus.BLOCKED, f"Expected BLOCKED, got {result.status}"
    assert len(result.issues) > 0, "Expected at least one issue"
    assert any(i.severity == "critical" for i in result.issues), "Expected critical issue"
    print("✓ Test 2 passed: Blocks non-compliant action")


async def test_returns_warnings_for_risky_actions():
    """Test 3: Warning status for risky actions."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="approve_invoice",
        target_resource="invoice_456",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={"amount": 15000},  # High amount
    )

    result = await agent.check_compliance(context)

    assert result.status == ComplianceStatus.WARNING, f"Expected WARNING, got {result.status}"
    assert len(result.issues) > 0, "Expected at least one issue"
    assert any(i.severity == "warning" for i in result.issues), "Expected warning issue"
    print("✓ Test 3 passed: Returns warnings for risky actions")


async def test_blocks_insufficient_permissions():
    """Test 4: Blocks actions with insufficient permissions."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="admin_access",
        target_resource="admin_panel",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={},
    )

    result = await agent.check_compliance(context)

    assert result.status == ComplianceStatus.BLOCKED, f"Expected BLOCKED, got {result.status}"
    assert any("RBAC" in i.policy_violated for i in result.issues), "Expected RBAC violation"
    print("✓ Test 4 passed: Blocks insufficient permissions")


async def test_enforces_tenant_boundaries():
    """Test 5: Prevents cross-tenant access."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="read_data",
        target_resource="data_tenant_other-tenant-id",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={"requesting_tenant": "other-tenant-id"},
    )

    result = await agent.check_compliance(context)

    assert result.status == ComplianceStatus.BLOCKED, f"Expected BLOCKED, got {result.status}"
    assert any(
        "tenant" in i.policy_violated.lower() for i in result.issues
    ), "Expected tenant violation"
    print("✓ Test 5 passed: Enforces tenant boundaries")


async def test_allows_same_tenant_access():
    """Test 6: Allows within-tenant operations."""
    agent = ComplianceAgent()

    tenant_id = UUID("550e8400-e29b-41d4-a716-446655440001")
    context = ComplianceContext(
        action="read_data",
        target_resource=f"data_tenant_{tenant_id}",
        tenant_id=tenant_id,
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={"requesting_tenant": str(tenant_id)},
    )

    result = await agent.check_compliance(context)

    assert result.status == ComplianceStatus.ALLOWED, f"Expected ALLOWED, got {result.status}"
    print("✓ Test 6 passed: Allows same-tenant access")


async def test_detects_data_privacy_violations():
    """Test 7: Detects PII sharing violations."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="share_pii",
        target_resource="customer_data",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={"recipient": "external_partner"},
    )

    result = await agent.check_compliance(context)

    assert result.status == ComplianceStatus.BLOCKED, f"Expected BLOCKED, got {result.status}"
    assert any(
        "privacy" in i.policy_violated.lower() for i in result.issues
    ), "Expected privacy violation"
    print("✓ Test 7 passed: Detects data privacy violations")


async def test_provides_remediation_steps():
    """Test 8: Provides remediation guidance."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="disable_encryption",
        target_resource="database",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={},
    )

    result = await agent.check_compliance(context)

    assert len(result.issues) > 0, "Expected at least one issue"
    assert all(i.remediation for i in result.issues), "All issues should have remediation"
    assert any(len(i.remediation) > 20 for i in result.issues), "Remediation should be descriptive"
    print("✓ Test 8 passed: Provides remediation steps")


async def test_handles_empty_parameters():
    """Test 9: Handles empty parameters dict."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="read_document",
        target_resource="doc_123",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={},
    )

    result = await agent.check_compliance(context)

    assert isinstance(
        result, ComplianceResult
    ), f"Should return ComplianceResult, got {type(result)}: {result}"
    assert result.status in [
        ComplianceStatus.ALLOWED,
        ComplianceStatus.WARNING,
        ComplianceStatus.BLOCKED,
    ], f"Invalid status: {result.status}"
    print("✓ Test 9 passed: Handles empty parameters")


async def test_requires_action():
    """Test 10: Requires action field."""
    agent = ComplianceAgent()

    context = ComplianceContext(
        action="",
        target_resource="doc_123",
        tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
        user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
        parameters={},
    )

    try:
        await agent.check_compliance(context)
        assert False, "Should raise ValueError for empty action"
    except ValueError as e:
        assert "action" in str(e).lower(), f"Error message should mention 'action', got: {e}"
        print("✓ Test 10 passed: Requires action")


async def test_requires_tenant_id():
    """Test 11: Requires tenant_id field."""
    agent = ComplianceAgent()

    try:
        context = ComplianceContext(
            action="read_document",
            target_resource="doc_123",
            tenant_id=None,  # This will fail Pydantic validation
            user_id=UUID("550e8400-e29b-41d4-a716-446655440002"),
            parameters={},
        )
        await agent.check_compliance(context)
        assert False, "Should raise validation error for missing tenant_id"
    except (ValueError, TypeError) as e:
        print("✓ Test 11 passed: Requires tenant_id")


async def test_requires_user_id():
    """Test 12: Requires user_id field."""
    agent = ComplianceAgent()

    try:
        context = ComplianceContext(
            action="read_document",
            target_resource="doc_123",
            tenant_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
            user_id=None,  # This will fail Pydantic validation
            parameters={},
        )
        await agent.check_compliance(context)
        assert False, "Should raise validation error for missing user_id"
    except (ValueError, TypeError) as e:
        print("✓ Test 12 passed: Requires user_id")


async def main():
    """Run all direct tests."""
    print("\n" + "=" * 60)
    print("SLICE 6: ComplianceAgent Direct Tests")
    print("=" * 60 + "\n")

    tests = [
        test_allows_compliant_action,
        test_blocks_non_compliant_action,
        test_returns_warnings_for_risky_actions,
        test_blocks_insufficient_permissions,
        test_enforces_tenant_boundaries,
        test_allows_same_tenant_access,
        test_detects_data_privacy_violations,
        test_provides_remediation_steps,
        test_handles_empty_parameters,
        test_requires_action,
        test_requires_tenant_id,
        test_requires_user_id,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            await test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
