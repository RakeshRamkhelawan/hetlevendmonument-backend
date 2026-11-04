"""Integration test: R1 is enforced during step execution."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.company.context import AgentExecutionContext, GoalChain
from src.core.procedures.domain_pack_orchestrator import GoalMisalignmentError


@pytest.mark.asyncio
async def test_r1_blocks_misaligned_step_execution():
    """MISALIGNED step should raise GoalMisalignmentError and block execution."""
    from src.core.procedures.multi_pack_assembler import MultiPackAssembler

    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
    )

    mock_step = MagicMock(action="Delete all data")
    mock_procedure = MagicMock(steps=[mock_step])

    assembler = MultiPackAssembler()

    # Patch the validator's validate method on the orchestrator instance
    with patch.object(
        assembler._orchestrator._validator,
        "validate",
        new_callable=AsyncMock,
        return_value=MagicMock(status="MISALIGNED", reason="Destructive action"),
    ):
        with pytest.raises(GoalMisalignmentError):
            await assembler.run_procedure(mock_procedure, ctx)


@pytest.mark.asyncio
async def test_r1_allows_aligned_step_execution():
    """ALIGNED step should execute normally."""
    from src.core.procedures.multi_pack_assembler import MultiPackAssembler

    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
    )

    mock_step = MagicMock(action="Analyze data")
    mock_procedure = MagicMock(steps=[mock_step])

    assembler = MultiPackAssembler()

    with patch.object(
        assembler._orchestrator._validator,
        "validate",
        new_callable=AsyncMock,
        return_value=MagicMock(status="ALIGNED", score=0.85),
    ):
        # Mock the actual execution
        with patch.object(assembler, "_execute_step", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "step_id": "test_step",
                "action": "Analyze data",
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            results = await assembler.run_procedure(mock_procedure, ctx)
            mock_execute.assert_called_once()
            assert len(results) == 1
            assert results[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_r1_checks_each_step_in_procedure():
    """Each step in a procedure should be validated."""
    from src.core.procedures.multi_pack_assembler import MultiPackAssembler

    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
    )

    mock_step1 = MagicMock(action="Step 1 action")
    mock_step2 = MagicMock(action="Step 2 action")
    mock_procedure = MagicMock(steps=[mock_step1, mock_step2])

    assembler = MultiPackAssembler()

    with patch.object(
        assembler._orchestrator._validator,
        "validate",
        new_callable=AsyncMock,
        return_value=MagicMock(status="ALIGNED", score=0.9),
    ) as mock_validate:
        with patch.object(assembler, "_execute_step", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "completed"}
            await assembler.run_procedure(mock_procedure, ctx)

            # Both steps should be executed (both passed validation)
            assert mock_execute.call_count == 2
            # Validator should be called for each step
            assert mock_validate.call_count == 2


@pytest.mark.asyncio
async def test_r1_stops_on_first_misaligned_step():
    """Procedure should stop when first misaligned step is encountered."""
    from src.core.procedures.multi_pack_assembler import MultiPackAssembler

    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
    )

    mock_step1 = MagicMock(action="Aligned step")
    mock_step2 = MagicMock(action="Misaligned step")
    mock_step3 = MagicMock(action="Third step")
    mock_procedure = MagicMock(steps=[mock_step1, mock_step2, mock_step3])

    assembler = MultiPackAssembler()

    with patch.object(
        assembler._orchestrator._validator,
        "validate",
        new_callable=AsyncMock,
        side_effect=[
            MagicMock(status="ALIGNED", score=0.9),
            MagicMock(status="MISALIGNED", reason="Policy violation"),
        ],
    ):
        with patch.object(assembler, "_execute_step", new_callable=AsyncMock) as mock_execute:
            with pytest.raises(GoalMisalignmentError):
                await assembler.run_procedure(mock_procedure, ctx)

            # Only first step executed
            assert mock_execute.call_count == 1


@pytest.mark.asyncio
async def test_r1_passes_context_to_validator():
    """Validator should receive the correct execution context."""
    from src.core.procedures.multi_pack_assembler import MultiPackAssembler

    ctx = AgentExecutionContext(
        tenant_id=42,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
    )

    mock_step = MagicMock(action="Test action")
    mock_procedure = MagicMock(steps=[mock_step])

    assembler = MultiPackAssembler()

    with patch.object(
        assembler._orchestrator._validator,
        "validate",
        new_callable=AsyncMock,
        return_value=MagicMock(status="ALIGNED", score=0.85),
    ) as mock_validate:
        with patch.object(assembler, "_execute_step", new_callable=AsyncMock):
            await assembler.run_procedure(mock_procedure, ctx)

            # Verify validator was called with correct arguments
            mock_validate.assert_called_once_with("Test action", ctx)
