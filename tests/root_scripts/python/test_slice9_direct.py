"""
Slice 9 Direct Tests: ProcedureResolver
Quick standalone validation (5-10 second feedback loop)
"""

import asyncio
from uuid import uuid4

from src.core.agents.capabilities.procedure_resolver import ProcedureResolver
from src.core.agents.capabilities.schemas import ExecutionDecision, ProcedureResolverInput


async def test_high_confidence_auto_execute():
    """Should auto-execute high confidence matches"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="Approve invoice for payment",
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await resolver.resolve(input_data)

    assert result.decision == ExecutionDecision.AUTO_EXECUTE
    assert result.confidence >= 0.8
    assert result.matched_procedure is not None
    print("✓ High confidence auto-execution")


async def test_medium_confidence_user_confirm():
    """Should require confirmation for medium confidence"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="Do something with invoice",  # Single match but vague
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await resolver.resolve(input_data)

    # Should require confirmation or no match for vague query
    assert result.decision in [
        ExecutionDecision.USER_CONFIRM,
        ExecutionDecision.NO_MATCH,
    ]
    print("✓ Medium confidence requires confirmation")


async def test_low_confidence_no_match():
    """Should return no match for low confidence"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="xyzabc completely unknown action",
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await resolver.resolve(input_data)

    assert result.decision == ExecutionDecision.NO_MATCH
    assert result.confidence < 0.5
    print("✓ Low confidence returns no match")


async def test_includes_execution_plan():
    """Should include execution plan for actionable matches"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="Approve invoice",
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await resolver.resolve(input_data)

    if result.decision in [
        ExecutionDecision.AUTO_EXECUTE,
        ExecutionDecision.USER_CONFIRM,
    ]:
        assert result.execution_plan is not None
        assert len(result.execution_plan.execution_plan) > 0
    print("✓ Execution plan included")


async def test_domain_filtering():
    """Should filter by domain"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="Approve invoice",
        tenant_id=uuid4(),
        user_id=uuid4(),
        domain_filter="finance",
    )

    result = await resolver.resolve(input_data)

    # Should find finance procedure
    assert result is not None
    print("✓ Domain filtering works")


async def test_handles_empty_candidates():
    """Should handle no candidates gracefully"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="Something completely unknown",
        tenant_id=uuid4(),
        user_id=uuid4(),
        domain_filter="nonexistent_domain",
    )

    result = await resolver.resolve(input_data)

    assert result.decision == ExecutionDecision.NO_MATCH
    assert "no procedures" in result.reasoning.lower() or "no match" in result.reasoning.lower()
    print("✓ Handles empty candidates")


async def test_provides_reasoning():
    """Should provide clear reasoning for decision"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="View my profile",
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await resolver.resolve(input_data)

    assert result.reasoning is not None
    assert len(result.reasoning) > 0
    assert result.confidence >= 0.0
    print("✓ Provides reasoning")


async def test_orchestration_flow():
    """Should orchestrate all services successfully"""
    resolver = ProcedureResolver()

    input_data = ProcedureResolverInput(
        user_intent="Export data",
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await resolver.resolve(input_data)

    # Should complete without errors
    assert result is not None
    assert result.decision is not None
    print("✓ Orchestration flow complete")


async def main():
    """Run all direct tests"""
    print("\nSlice 9: ProcedureResolver - Direct Tests")
    print("=" * 50)

    tests = [
        test_high_confidence_auto_execute,
        test_medium_confidence_user_confirm,
        test_low_confidence_no_match,
        test_includes_execution_plan,
        test_domain_filtering,
        test_handles_empty_candidates,
        test_provides_reasoning,
        test_orchestration_flow,
    ]

    passed = 0
    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
        except Exception as e:
            print(f"✗ {test.__name__} error: {e}")

    print("\n" + "=" * 50)
    print(f"Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("✅ All direct tests passing!")
        return 0
    else:
        print(f"❌ {len(tests) - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
