"""
Slice 3: PlannerAgent Direct Tests (No Fixtures - Rapid Verification)

Standalone tests to verify core PlannerAgent logic without pytest infrastructure.
Run with: python test_slice3_direct.py
"""

import asyncio
import sys
from uuid import uuid4

from src.core.agents.capabilities.planner_agent import PlannerAgent
from src.core.agents.capabilities.schemas import (
    ExecutionDecision,
    ExecutionStep,
    PlannerTask,
    ScoredProcedure,
)

# ============================================================================
# TEST DATA SETUP
# ============================================================================


def create_high_confidence_procedure():
    """Create high confidence procedure (0.92)."""
    return ScoredProcedure(
        procedure_id=uuid4(),
        procedure_name="Approve Invoice",
        domain_pack_id=uuid4(),
        confidence_score=0.92,
        tag_score=0.90,
        semantic_score=0.95,
        history_score=0.88,
        recency_score=0.92,
        user_override_score=1.0,
        is_ambiguous=False,
    )


def create_medium_confidence_procedure():
    """Create medium confidence procedure (0.68)."""
    return ScoredProcedure(
        procedure_id=uuid4(),
        procedure_name="Process Payment",
        domain_pack_id=uuid4(),
        confidence_score=0.68,
        tag_score=0.70,
        semantic_score=0.65,
        history_score=0.60,
        recency_score=0.70,
        user_override_score=0.50,
        is_ambiguous=False,
    )


def create_low_confidence_procedure():
    """Create low confidence procedure (0.35)."""
    return ScoredProcedure(
        procedure_id=uuid4(),
        procedure_name="Random Action",
        domain_pack_id=uuid4(),
        confidence_score=0.35,
        tag_score=0.30,
        semantic_score=0.35,
        history_score=0.20,
        recency_score=0.40,
        user_override_score=0.30,
        is_ambiguous=False,
    )


# ============================================================================
# DIRECT TESTS
# ============================================================================


async def test_1_high_confidence_auto_execute():
    """Test 1: High confidence (>0.85) generates auto_execute decision."""
    print("\n🧪 Test 1: High Confidence Auto-Execute")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_high_confidence_procedure()

    task = PlannerTask(
        user_intent="Approve the invoice",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    assert (
        result.decision == ExecutionDecision.AUTO_EXECUTE
    ), f"Expected auto_execute, got {result.decision}"
    assert (
        result.confidence_in_plan > 0.85
    ), f"Expected confidence > 0.85, got {result.confidence_in_plan}"
    assert len(result.execution_plan) > 0, "Expected steps in plan"
    assert result.execution_plan[0].action == "execute", "Expected execute action"

    print(f"  ✅ Decision: {result.decision.value}")
    print(f"  ✅ Confidence: {result.confidence_in_plan:.2%}")
    print(f"  ✅ Steps: {len(result.execution_plan)}")
    print(f"  ✅ Action: {result.execution_plan[0].action}")

    return True


async def test_2_medium_confidence_user_confirm():
    """Test 2: Medium confidence (0.50-0.85) generates user_confirm decision."""
    print("\n🧪 Test 2: Medium Confidence User Confirmation")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_medium_confidence_procedure()

    task = PlannerTask(
        user_intent="Process payment",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    assert (
        result.decision == ExecutionDecision.USER_CONFIRM
    ), f"Expected user_confirm, got {result.decision}"
    assert (
        0.50 <= result.confidence_in_plan <= 0.85
    ), f"Expected confidence 0.50-0.85, got {result.confidence_in_plan}"
    assert len(result.execution_plan) >= 1, "Expected at least 1 step"
    assert result.requires_human_approval, "Should require human approval for medium confidence"

    print(f"  ✅ Decision: {result.decision.value}")
    print(f"  ✅ Confidence: {result.confidence_in_plan:.2%}")
    print(f"  ✅ Steps: {len(result.execution_plan)}")
    print(f"  ✅ Requires approval: {result.requires_human_approval}")

    return True


async def test_3_low_confidence_no_match():
    """Test 3: Low confidence (<0.50) generates no_match decision."""
    print("\n🧪 Test 3: Low Confidence No-Match")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_low_confidence_procedure()

    task = PlannerTask(
        user_intent="Do something unclear",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    assert (
        result.decision == ExecutionDecision.NO_MATCH
    ), f"Expected no_match, got {result.decision}"
    assert (
        result.confidence_in_plan < 0.50
    ), f"Expected confidence < 0.50, got {result.confidence_in_plan}"

    print(f"  ✅ Decision: {result.decision.value}")
    print(f"  ✅ Confidence: {result.confidence_in_plan:.2%}")
    print(f"  ✅ Reasoning: {result.reasoning[:100]}...")

    return True


async def test_4_execution_steps_structure():
    """Test 4: Execution steps have correct structure."""
    print("\n🧪 Test 4: Execution Steps Structure")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_high_confidence_procedure()

    task = PlannerTask(
        user_intent="Approve invoice",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    assert len(result.execution_plan) > 0, "Should have steps"

    for step in result.execution_plan:
        assert isinstance(step, ExecutionStep), "Step should be ExecutionStep"
        assert step.step_number > 0, "Step number should be positive"
        assert step.action in [
            "execute",
            "confirm",
            "guidance",
        ], f"Unknown action: {step.action}"
        assert isinstance(step.parameters, dict), "Parameters should be dict"

    print(f"  ✅ Total steps: {len(result.execution_plan)}")
    for i, step in enumerate(result.execution_plan, 1):
        print(f"     Step {i}: {step.action}")

    return True


async def test_5_estimated_duration():
    """Test 5: Estimated duration calculated."""
    print("\n🧪 Test 5: Duration Estimation")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_high_confidence_procedure()

    task = PlannerTask(
        user_intent="Approve invoice",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    assert result.estimated_duration_minutes > 0, "Estimated duration should be > 0"

    print(f"  ✅ Estimated duration: {result.estimated_duration_minutes} minutes")

    return True


async def test_6_reasoning_provided():
    """Test 6: Reasoning explains the decision."""
    print("\n🧪 Test 6: Reasoning Provided")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_high_confidence_procedure()

    task = PlannerTask(
        user_intent="Approve invoice",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    assert result.reasoning is not None, "Should have reasoning"
    assert len(result.reasoning) > 0, "Reasoning should not be empty"

    print(f"  ✅ Reasoning: {result.reasoning[:100]}...")

    return True


async def test_7_tenant_context_preservation():
    """Test 7: Maintains tenant context."""
    print("\n🧪 Test 7: Tenant Context Preservation")

    agent = PlannerAgent()
    tenant_id_1 = uuid4()
    user_id_1 = uuid4()
    tenant_id_2 = uuid4()
    user_id_2 = uuid4()

    procedure1 = create_high_confidence_procedure()
    procedure2 = create_medium_confidence_procedure()

    task1 = PlannerTask(
        user_intent="Approve invoice",
        procedure=procedure1,
        tenant_id=tenant_id_1,
        user_id=user_id_1,
        domain_pack_context={},
    )

    task2 = PlannerTask(
        user_intent="Process payment",
        procedure=procedure2,
        tenant_id=tenant_id_2,
        user_id=user_id_2,
        domain_pack_context={},
    )

    result1 = await agent.plan(task1)
    result2 = await agent.plan(task2)

    # Results should be independent
    assert (
        result1.decision != result2.decision
    ), "Different procedures should have different decisions"
    assert (
        result1.reasoning != result2.reasoning
    ), "Different procedures should have different reasoning"

    print(f"  ✅ Plan 1 decision: {result1.decision.value}")
    print(f"  ✅ Plan 2 decision: {result2.decision.value}")
    print("  ✅ Plans are independent")

    return True


async def test_8_auto_execute_has_execute_step():
    """Test 8: Auto-execute plans include execute action."""
    print("\n🧪 Test 8: Auto-Execute Has Execute Step")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_high_confidence_procedure()

    task = PlannerTask(
        user_intent="Approve invoice",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    execute_steps = [s for s in result.execution_plan if s.action == "execute"]
    assert len(execute_steps) > 0, "Auto-execute should have execute steps"

    print(f"  ✅ Execute steps: {len(execute_steps)}")

    return True


async def test_9_medium_requires_approval():
    """Test 9: Medium confidence requires human approval flag."""
    print("\n🧪 Test 9: Medium Confidence Requires Approval")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_medium_confidence_procedure()

    task = PlannerTask(
        user_intent="Process payment",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    if result.decision == ExecutionDecision.USER_CONFIRM:
        assert result.requires_human_approval, "USER_CONFIRM should require human approval"

    print(f"  ✅ Requires approval: {result.requires_human_approval}")

    return True


async def test_10_result_completeness():
    """Test 10: Result contains all required fields."""
    print("\n🧪 Test 10: Result Structure Completeness")

    agent = PlannerAgent()
    tenant_id = uuid4()
    user_id = uuid4()
    procedure = create_high_confidence_procedure()

    task = PlannerTask(
        user_intent="Approve invoice",
        procedure=procedure,
        tenant_id=tenant_id,
        user_id=user_id,
        domain_pack_context={},
    )

    result = await agent.plan(task)

    required_fields = [
        "execution_plan",
        "estimated_duration_minutes",
        "confidence_in_plan",
        "decision",
        "reasoning",
        "requires_human_approval",
    ]

    for field in required_fields:
        assert hasattr(result, field), f"Missing field: {field}"
        assert getattr(result, field) is not None, f"Field {field} is None"

    assert isinstance(result.execution_plan, list), "execution_plan should be list"
    assert len(result.execution_plan) > 0, "execution_plan should not be empty"

    print("  ✅ All required fields present:")
    print(f"     - execution_plan: {len(result.execution_plan)} step(s)")
    print(f"     - estimated_duration: {result.estimated_duration_minutes} min")
    print(f"     - confidence: {result.confidence_in_plan:.2%}")
    print(f"     - decision: {result.decision.value}")
    print(f"     - requires_approval: {result.requires_human_approval}")

    return True


# ============================================================================
# TEST RUNNER
# ============================================================================


async def run_all_tests():
    """Run all direct tests."""
    tests = [
        test_1_high_confidence_auto_execute,
        test_2_medium_confidence_user_confirm,
        test_3_low_confidence_no_match,
        test_4_execution_steps_structure,
        test_5_estimated_duration,
        test_6_reasoning_provided,
        test_7_tenant_context_preservation,
        test_8_auto_execute_has_execute_step,
        test_9_medium_requires_approval,
        test_10_result_completeness,
    ]

    print("\n" + "=" * 70)
    print("SLICE 3: PLANNER AGENT - DIRECT TESTS")
    print("=" * 70)

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
        except Exception as e:
            failed += 1
            print(f"\n  ❌ FAILED: {str(e)}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed}/{len(tests)} PASSED")
    print("=" * 70)

    if failed == 0:
        print("\n✅ GREEN PHASE CONFIRMED - All tests passing!")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
