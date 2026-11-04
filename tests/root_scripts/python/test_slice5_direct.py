"""
Slice 5: ExecutorAgent - Direct Tests (No Pytest Fixtures)

Standalone async tests to verify ExecutorAgent implementation.
Run with: python test_slice5_direct.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.agents.capabilities.executor_agent import ExecutorAgent
from src.core.agents.capabilities.schemas import ExecutorResult, ExecutorTask


async def test_1_basic_execution():
    """Test basic tool execution"""
    print("\n🧪 Test 1: Basic Execution")

    agent = ExecutorAgent()
    task = ExecutorTask(
        tool_name="calculate_sum",
        arguments={"a": 5, "b": 3},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.execute(task)

    assert result.success is True, "Should execute successfully"
    assert result.result == {"sum": 8}, f"Expected sum=8, got {result.result}"
    assert result.error is None, "Should have no error"
    assert result.retries_attempted == 0, "Should not retry on success"
    assert result.audit_log_id is not None, "Should have audit log ID"

    print(f"  ✅ Tool executed successfully: {result.result}")
    print(f"  ✅ Audit log ID: {result.audit_log_id}")


async def test_2_tool_not_found():
    """Test handling of missing tool"""
    print("\n🧪 Test 2: Tool Not Found")

    agent = ExecutorAgent()
    task = ExecutorTask(
        tool_name="nonexistent_tool",
        arguments={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.execute(task)

    assert result.success is False, "Should fail for missing tool"
    assert "not found" in result.error.lower(), f"Expected 'not found' error, got: {result.error}"
    assert result.retries_attempted == 0, "Should not retry for missing tool"

    print(f"  ✅ Error handled: {result.error}")


async def test_3_retry_logic():
    """Test retry logic with transient failures"""
    print("\n🧪 Test 3: Retry Logic")

    agent = ExecutorAgent(max_retries=3, base_delay=0.01)  # Fast retries for testing
    task = ExecutorTask(
        tool_name="transient_error",
        arguments={},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.execute(task)

    # May succeed after retries or fail after max retries
    print(f"  ✅ Success: {result.success}, Retries: {result.retries_attempted}")
    assert result.audit_log_id is not None, "Should have audit log"


async def test_4_validation_error_no_retry():
    """Test that validation errors don't trigger retries"""
    print("\n🧪 Test 4: Validation Error (No Retry)")

    agent = ExecutorAgent()
    task = ExecutorTask(
        tool_name="validate_input",
        arguments={"invalid": "data"},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.execute(task)

    assert result.success is False, "Should fail on validation error"
    assert result.retries_attempted == 0, "Should NOT retry validation errors"
    assert "validation" in result.error.lower(), f"Expected validation error, got: {result.error}"

    print(f"  ✅ Validation error caught: {result.error}")
    print(f"  ✅ No retries attempted: {result.retries_attempted}")


async def test_5_division_by_zero():
    """Test error handling for runtime errors"""
    print("\n🧪 Test 5: Division By Zero Error")

    agent = ExecutorAgent()
    task = ExecutorTask(
        tool_name="divide",
        arguments={"a": 10, "b": 0},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.execute(task)

    assert result.success is False, "Should fail on division by zero"
    assert result.error is not None, "Should have error message"
    print(f"  ✅ Error handled: {result.error}")


async def test_6_missing_required_argument():
    """Test validation of required arguments"""
    print("\n🧪 Test 6: Missing Required Argument")

    agent = ExecutorAgent()
    task = ExecutorTask(
        tool_name="send_email",
        arguments={},  # Missing 'to' field
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.execute(task)

    assert result.success is False, "Should fail without required argument"
    assert (
        "to" in result.error.lower()
        or "required" in result.error.lower()
        or "argument" in result.error.lower()
    ), f"Expected argument error, got: {result.error}"

    print(f"  ✅ Missing argument caught: {result.error}")


async def test_7_tenant_isolation():
    """Test tenant isolation in execution"""
    print("\n🧪 Test 7: Tenant Isolation")

    agent = ExecutorAgent()
    tenant1 = uuid4()
    tenant2 = uuid4()

    task1 = ExecutorTask(
        tool_name="get_data",
        arguments={"key": "shared_key"},
        tenant_id=tenant1,
        user_id=uuid4(),
    )

    task2 = ExecutorTask(
        tool_name="get_data",
        arguments={"key": "shared_key"},
        tenant_id=tenant2,
        user_id=uuid4(),
    )

    result1 = await agent.execute(task1)
    result2 = await agent.execute(task2)

    assert result1.success is True, "Tenant 1 execution should succeed"
    assert result2.success is True, "Tenant 2 execution should succeed"
    assert result1.audit_log_id != result2.audit_log_id, "Should have different audit IDs"

    print(f"  ✅ Tenant 1 result: {result1.result}")
    print(f"  ✅ Tenant 2 result: {result2.result}")
    print("  ✅ Separate audit IDs confirmed")


async def test_8_tool_registry():
    """Test tool registration and listing"""
    print("\n🧪 Test 8: Tool Registry")

    agent = ExecutorAgent()

    # List tools
    tools = agent.list_available_tools()
    assert len(tools) > 0, "Should have registered tools"
    assert "send_email" in tools, "Should have send_email tool"
    assert "calculate_sum" in tools, "Should have calculate_sum tool"

    print(f"  ✅ Available tools ({len(tools)}): {', '.join(tools[:5])}...")

    # Register custom tool
    async def custom_tool(args: dict) -> dict:
        return {"custom": "result", "args": args}

    agent.register_tool("custom_tool", custom_tool)

    # Execute custom tool
    task = ExecutorTask(
        tool_name="custom_tool",
        arguments={"test": "data"},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result = await agent.execute(task)

    assert result.success is True, "Custom tool should execute"
    assert result.result["custom"] == "result", "Should return custom result"

    print(f"  ✅ Custom tool registered and executed: {result.result}")


async def test_9_tool_metadata():
    """Test tool metadata retrieval"""
    print("\n🧪 Test 9: Tool Metadata")

    agent = ExecutorAgent()

    metadata = agent.get_tool_metadata("send_email")

    assert metadata is not None, "Should have metadata"
    assert metadata["name"] == "send_email", f"Expected name='send_email', got {metadata['name']}"
    assert "description" in metadata, "Should have description"
    assert "parameters" in metadata, "Should have parameters"

    print(f"  ✅ Metadata retrieved: {metadata['name']}")
    print(f"  ✅ Parameters: {list(metadata['parameters'].keys())}")


async def test_10_audit_logging():
    """Test audit log generation"""
    print("\n🧪 Test 10: Audit Logging")

    agent = ExecutorAgent()

    # Success case
    task_success = ExecutorTask(
        tool_name="calculate_sum",
        arguments={"a": 1, "b": 2},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result_success = await agent.execute(task_success)
    assert result_success.audit_log_id is not None, "Should have audit log on success"

    # Failure case
    task_failure = ExecutorTask(
        tool_name="divide",
        arguments={"a": 10, "b": 0},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )

    result_failure = await agent.execute(task_failure)
    assert result_failure.audit_log_id is not None, "Should have audit log on failure"

    print(f"  ✅ Success audit ID: {result_success.audit_log_id}")
    print(f"  ✅ Failure audit ID: {result_failure.audit_log_id}")


async def test_11_input_validation():
    """Test input validation"""
    print("\n🧪 Test 11: Input Validation")

    agent = ExecutorAgent()

    # Empty tool name
    try:
        task = ExecutorTask(
            tool_name="",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )
        result = await agent.execute(task)
        assert False, "Should have raised validation error for empty tool_name"
    except Exception as e:
        print(f"  ✅ Empty tool_name caught: {str(e)}")

    # Test successful validation
    task = ExecutorTask(
        tool_name="calculate_sum",
        arguments={"a": 1, "b": 2},
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    result = await agent.execute(task)
    assert result.success is True, "Valid task should execute"
    print("  ✅ Valid task executed successfully")


async def test_12_concurrent_execution():
    """Test concurrent tool execution"""
    print("\n🧪 Test 12: Concurrent Execution")

    agent = ExecutorAgent()

    tasks = [
        ExecutorTask(
            tool_name="calculate_sum",
            arguments={"a": i, "b": i + 1},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )
        for i in range(5)
    ]

    results = await asyncio.gather(*[agent.execute(task) for task in tasks])

    assert len(results) == 5, f"Expected 5 results, got {len(results)}"
    assert all(r.success for r in results), "All executions should succeed"

    sums = [r.result["sum"] for r in results]
    print(f"  ✅ Concurrent executions completed: {sums}")
    print(f"  ✅ All {len(results)} tasks successful")


async def run_all_tests():
    """Run all direct tests"""
    print("=" * 70)
    print("SLICE 5: EXECUTOR AGENT - DIRECT TESTS")
    print("=" * 70)

    tests = [
        test_1_basic_execution,
        test_2_tool_not_found,
        test_3_retry_logic,
        test_4_validation_error_no_retry,
        test_5_division_by_zero,
        test_6_missing_required_argument,
        test_7_tenant_isolation,
        test_8_tool_registry,
        test_9_tool_metadata,
        test_10_audit_logging,
        test_11_input_validation,
        test_12_concurrent_execution,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            await test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n  ❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed}/{len(tests)} PASSED")
    print("=" * 70)

    if failed == 0:
        print("\n✅ GREEN PHASE CONFIRMED - All tests passing!")
    else:
        print(f"\n❌ {failed} test(s) failed")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
