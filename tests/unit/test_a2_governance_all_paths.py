"""
A2: EU AI Act Governance Tests - All 6 Execution Paths

Tests verify that OversightGate checks are applied (or can be applied) to all 6 execution paths.
This covers the mandatory governance pipeline requirement.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.governance import governance_helper
from src.core.governance.governance_helper import apply_governance_check


@pytest.fixture(autouse=True)
def _clear_shadow_ceo_cache():
    """These tests mock OversightGate but not ShadowCEO -- apply_governance_check's
    ShadowCEO pre-execution veto runs for real here. _shadow_ceo_instances is a
    module-level cache; clear it around every test so accumulated threat_memory
    from one test case can never leak into another."""
    governance_helper._shadow_ceo_instances.clear()
    yield
    governance_helper._shadow_ceo_instances.clear()


class TestA2GovernanceAllPaths:
    """A2: Test governance checkpoint across all 6 execution paths."""

    @pytest.mark.integration
    async def test_path1_agent_registry_governance(self):
        """Path 1: Agent Registry via agent_registry.distribute_task()"""
        # Already has governance (verified in agent_registry.py line 385+)
        # Test that governance helper works with agent metadata
        with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.reason = None
            mock_result.requires_human_approval = False
            mock_instance.check = AsyncMock(return_value=mock_result)
            gate_cls.return_value = mock_instance

            allowed, reason = await apply_governance_check(
                agent_name="test_agent",
                task_action="process_task",
                agent_department="general",
                agent_specialisation="general",
            )
            assert allowed is True

    @pytest.mark.integration
    async def test_path2_orchestrator_governance_pattern(self):
        """Path 2: Orchestrator via orchestrate_task()"""
        # Apply pattern to orchestration/router.py::orchestrate_task()
        with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.reason = None
            mock_result.requires_human_approval = False
            mock_instance.check = AsyncMock(return_value=mock_result)
            gate_cls.return_value = mock_instance

            allowed, reason = await apply_governance_check(
                agent_name="MasterOrchestratorAgent",
                task_action="orchestrate_task",
                agent_department="orchestration",
                agent_specialisation="multi-agent-coordination",
                agent_capabilities=["task_decomposition", "agent_routing"],
            )
            assert allowed is True

    @pytest.mark.integration
    async def test_path3_cva_governance_pattern(self):
        """Path 3: CVA via cva_autonomous_trigger.py"""
        # Apply pattern to CVAAutonomousTrigger._execute_breakthrough_session()
        with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.reason = None
            mock_result.requires_human_approval = False
            mock_instance.check = AsyncMock(return_value=mock_result)
            gate_cls.return_value = mock_instance

            allowed, reason = await apply_governance_check(
                agent_name="CVAAutonomousTrigger",
                task_action="breakthrough_session",
                agent_department="conversational",
                agent_specialisation="autonomous-voice-agent",
            )
            assert allowed is True

    @pytest.mark.integration
    async def test_path4_workflow_governance_pattern(self):
        """Path 4: Workflow Dramatiq Worker via workflow_worker.py::WorkflowWorker.execute()"""
        # Apply pattern to workflow execution
        with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.reason = None
            mock_result.requires_human_approval = False
            mock_instance.check = AsyncMock(return_value=mock_result)
            gate_cls.return_value = mock_instance

            allowed, reason = await apply_governance_check(
                agent_name="WorkflowEngine",
                task_action="execute_workflow",
                agent_department="orchestration",
                agent_specialisation="workflow-automation",
            )
            assert allowed is True

    @pytest.mark.integration
    async def test_path5_subagent_factory_governance_pattern(self):
        """Path 5: Sub-Agent Factory via agent_factory.py::create_agent()"""
        # Apply pattern to agent creation/execution
        with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.reason = None
            mock_result.requires_human_approval = False
            mock_instance.check = AsyncMock(return_value=mock_result)
            gate_cls.return_value = mock_instance

            allowed, reason = await apply_governance_check(
                agent_name="SubAgentFactory",
                task_action="create_and_execute",
                agent_department="orchestration",
                agent_specialisation="agent-factory",
            )
            assert allowed is True

    @pytest.mark.integration
    async def test_path6_websocket_governance_pattern(self):
        """Path 6: WebSocket Stream via swarm_websocket_endpoints.py::stream_agent_execution()"""
        # Apply pattern to WebSocket execution
        with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.allowed = True
            mock_result.reason = None
            mock_result.requires_human_approval = False
            mock_instance.check = AsyncMock(return_value=mock_result)
            gate_cls.return_value = mock_instance

            allowed, reason = await apply_governance_check(
                agent_name="WebSocketStreamAgent",
                task_action="stream_execution",
                agent_department="streaming",
                agent_specialisation="real-time-execution",
            )
            assert allowed is True

    @pytest.mark.integration
    async def test_governance_denial_pattern(self):
        """Test that governance can deny execution when configured."""
        # Mock a denied response
        with patch("src.core.governance.oversight_gate.OversightGate") as mock_gate:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.allowed = False
            mock_result.reason = "Risk classification: CRITICAL"
            mock_instance.check = AsyncMock(return_value=mock_result)
            mock_gate.return_value = mock_instance

            allowed, reason = await apply_governance_check(
                agent_name="HighRiskAgent",
                task_action="dangerous_action",
            )

            # Governance should deny
            assert allowed is False
            assert reason is not None

    @pytest.mark.integration
    async def test_all_paths_governance_checkpoint_callable(self):
        """Verify apply_governance_check is suitable for all 6 paths."""
        test_cases = [
            ("EnhancedBaseAgent", "process_task", "agent_execution"),
            ("MasterOrchestratorAgent", "orchestrate_task", "multi_agent"),
            ("CVAAutonomousTrigger", "breakthrough_session", "conversational"),
            ("WorkflowEngine", "execute_workflow", "workflow"),
            ("SubAgentFactory", "create_and_execute", "factory"),
            ("WebSocketStreamAgent", "stream_execution", "websocket"),
        ]

        for agent_name, task_action, dept in test_cases:
            with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
                mock_instance = AsyncMock()
                mock_result = MagicMock()
                mock_result.allowed = True
                mock_result.reason = None
                mock_result.requires_human_approval = False
                mock_instance.check = AsyncMock(return_value=mock_result)
                gate_cls.return_value = mock_instance

                allowed, reason = await apply_governance_check(
                    agent_name=agent_name,
                    task_action=task_action,
                    agent_department=dept,
                )
                assert allowed is True, f"Path {agent_name} failed governance"


@pytest.mark.integration
async def test_a2_governance_is_mandatory_pattern():
    """
    A2: Governance must be called BEFORE execution in all paths.

    Pattern (same for all 6 paths):

    # In execute method:
    allowed, reason = await apply_governance_check(...)
    if not allowed:
        raise HTTPException(403, reason) or return error
    # Only if allowed: proceed to actual execution
    """
    # Verify the helper function signature matches all paths
    import inspect

    from src.core.governance.governance_helper import apply_governance_check

    sig = inspect.signature(apply_governance_check)
    params = list(sig.parameters.keys())

    # Should have these core parameters for all paths
    assert "agent_name" in params
    assert "task_action" in params

    # Should return (allowed, reason) tuple
    result = await apply_governance_check("test", "test_action")
    assert isinstance(result, tuple)
    assert len(result) == 2
    allowed, reason = result
    assert isinstance(allowed, bool)


@pytest.mark.integration
async def test_a2_governance_import_error_is_fail_closed():
    with (
        patch(
            "src.core.governance.governance_helper.GOVERNANCE_AVAILABLE",
            True,
        ),
        patch("builtins.__import__", side_effect=ImportError("missing oversight gate")),
    ):
        allowed, reason = await apply_governance_check("test", "test_action")
        assert allowed is False
        assert reason is not None
