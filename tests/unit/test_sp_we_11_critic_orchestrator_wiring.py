"""SP-WE-11: CriticAgent Injecteren in MasterOrchestratorAgent (CG-006).

TDD tests -- RED first, GREEN after fix.
Verifies that _delegate_sub_task() calls post_process_task() via CriticMixin.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent, SubTask
from src.core.shared.interfaces import ExecutionResult


@pytest.mark.unit
class TestCG006CriticOrchestratorWiring:
    """Tests voor CG-006: CriticAgent wiring via CriticMixin in MasterOrchestratorAgent."""

    def _make_orchestrator(self, tenant_id: int = 1) -> MasterOrchestratorAgent:
        return MasterOrchestratorAgent(agent_id="test_orchestrator", tenant_id=tenant_id)

    def _make_sub_task(self, sub_task_id: str = "wf_123_st_0") -> SubTask:
        return SubTask(
            sub_task_id=sub_task_id,
            parent_workflow_id="wf_123",
            title="Analyseer contract",
            description="Extraheer clausules",
            required_capabilities=["legal_analysis"],
            priority=5,
        )

    def _make_result(self, success: bool = True, task_id: str = "wf_123_st_0") -> ExecutionResult:
        return ExecutionResult(
            task_id=task_id,
            success=success,
            result_data={"output": "analysed"},
            execution_time=0.5,
        )

    async def test_post_process_task_called_on_success(self) -> None:
        """RED: post_process_task() must be called once after route_and_execute()."""
        orch = self._make_orchestrator()
        sub_task = self._make_sub_task()
        mock_result = self._make_result(success=True)

        with (
            patch.object(orch, "_get_router") as mock_get_router,
            patch.object(orch, "post_process_task", new_callable=AsyncMock) as mock_ppt,
        ):
            mock_get_router.return_value.route_and_execute = AsyncMock(return_value=mock_result)
            mock_ppt.return_value = mock_result

            await orch._delegate_sub_task(sub_task)

            assert mock_ppt.call_count == 1, (
                "post_process_task() moet 1x worden aangeroepen na route_and_execute(). "
                "Voeg 'result = await self.post_process_task(result, task_id=sub_task.sub_task_id)' "
                "toe in _delegate_sub_task() na 'sub_task.status = ...'."
            )

    async def test_post_process_task_called_with_correct_task_id(self) -> None:
        """post_process_task ontvangt de sub_task_id als task_id keyword argument."""
        orch = self._make_orchestrator()
        sub_task = self._make_sub_task(sub_task_id="wf_456_st_2")
        mock_result = self._make_result(task_id="wf_456_st_2")

        with (
            patch.object(orch, "_get_router") as mock_get_router,
            patch.object(orch, "post_process_task", new_callable=AsyncMock) as mock_ppt,
        ):
            mock_get_router.return_value.route_and_execute = AsyncMock(return_value=mock_result)
            mock_ppt.return_value = mock_result

            await orch._delegate_sub_task(sub_task)

            mock_ppt.assert_called_once_with(mock_result, task_id="wf_456_st_2")

    async def test_post_process_task_not_called_on_delegation_exception(self) -> None:
        """Als route_and_execute() een exception gooit, wordt post_process_task() NIET aangeroepen."""
        orch = self._make_orchestrator()
        sub_task = self._make_sub_task()

        with (
            patch.object(orch, "_get_router") as mock_get_router,
            patch.object(orch, "post_process_task", new_callable=AsyncMock) as mock_ppt,
        ):
            mock_get_router.return_value.route_and_execute = AsyncMock(
                side_effect=RuntimeError("Router onbeschikbaar")
            )

            result = await orch._delegate_sub_task(sub_task)

            assert not result.success
            assert mock_ppt.call_count == 0, (
                "post_process_task() mag NIET worden aangeroepen in het except-pad"
            )

    async def test_critic_failure_does_not_destroy_primary_result(self) -> None:
        """Als post_process_task() een exception gooit, mag de caller dat NIET zien."""
        orch = self._make_orchestrator()
        sub_task = self._make_sub_task()
        mock_result = self._make_result(success=True)

        with (
            patch.object(orch, "_get_router") as mock_get_router,
            patch.object(orch, "post_process_task", new_callable=AsyncMock) as mock_ppt,
        ):
            mock_get_router.return_value.route_and_execute = AsyncMock(return_value=mock_result)
            mock_ppt.side_effect = Exception("CritiqueStore onbeschikbaar")

            try:
                result = await orch._delegate_sub_task(sub_task)
                assert result is not None
            except Exception:
                pytest.fail(
                    "post_process_task() fout mag NIET naar de caller van _delegate_sub_task() bubbelen."
                )

    async def test_no_constructor_critic_parameter(self) -> None:
        """MasterOrchestratorAgent accepteert geen critic= constructor-parameter meer.
        CriticMixin haalt CriticAgent zelf op via get_critic_agent().
        """
        import inspect

        sig = inspect.signature(MasterOrchestratorAgent.__init__)
        assert "critic" not in sig.parameters, (
            "critic= constructor-parameter moet zijn verwijderd. "
            "Gebruik CriticMixin.post_process_task() in plaats van directe injectie."
        )

    async def test_failed_subtask_also_goes_through_post_process(self) -> None:
        """Ook gefaalde subtaak-resultaten (success=False) gaan door post_process_task.
        Telemetrie van mislukte taken is waardevol voor het leereffect.
        """
        orch = self._make_orchestrator()
        sub_task = self._make_sub_task()
        failed_result = self._make_result(success=False)

        with (
            patch.object(orch, "_get_router") as mock_get_router,
            patch.object(orch, "post_process_task", new_callable=AsyncMock) as mock_ppt,
        ):
            mock_get_router.return_value.route_and_execute = AsyncMock(return_value=failed_result)
            mock_ppt.return_value = failed_result

            result = await orch._delegate_sub_task(sub_task)

            assert not result.success
            assert mock_ppt.call_count == 1, (
                "post_process_task() moet ook worden aangeroepen voor gefaalde subtaken"
            )

    async def test_tenant_isolation_separate_critics(self) -> None:
        """Tenant A en Tenant B krijgen aparte CriticAgent instanties via CriticMixin."""
        orch_1 = self._make_orchestrator(tenant_id=1)
        orch_2 = self._make_orchestrator(tenant_id=2)

        sub_task_1 = self._make_sub_task("wf_1_st_0")
        sub_task_2 = self._make_sub_task("wf_2_st_0")
        result_1 = self._make_result(task_id="wf_1_st_0")
        result_2 = self._make_result(task_id="wf_2_st_0")

        captured_tenant_ids: list[int] = []

        def mock_get_critic(tenant_id: int) -> MagicMock:
            captured_tenant_ids.append(tenant_id)
            mock = AsyncMock()
            mock.critique_task = AsyncMock(return_value=MagicMock(score=0.9))
            return mock

        with (
            patch("src.core.agents.critic_agent.CriticAgent", side_effect=mock_get_critic),
            patch.object(orch_1, "_get_router") as mock_r1,
            patch.object(orch_2, "_get_router") as mock_r2,
        ):
            mock_r1.return_value.route_and_execute = AsyncMock(return_value=result_1)
            mock_r2.return_value.route_and_execute = AsyncMock(return_value=result_2)

            await orch_1._delegate_sub_task(sub_task_1)
            await orch_2._delegate_sub_task(sub_task_2)

        assert 1 in captured_tenant_ids, "Tenant 1 CriticAgent niet aangevraagd"
        assert 2 in captured_tenant_ids, "Tenant 2 CriticAgent niet aangevraagd"
        assert captured_tenant_ids.count(1) == 1
        assert captured_tenant_ids.count(2) == 1

    async def test_existing_process_task_flow_unbroken(self) -> None:
        """Regressietest: process_task() werkt nog steeds van begin tot eind."""
        orch = self._make_orchestrator()

        from src.core.shared.interfaces import TaskData

        task = TaskData(
            id="regression_task_001",
            title="Test regressie",
            description="Verifieer dat process_task nog werkt na de fix",
            metadata={"capabilities": ["test"]},
        )
        mock_result = self._make_result(success=True)

        from src.core.agents.master_orchestrator_agent import WorkflowPlan

        with (
            patch.object(orch, "_plan_workflow", new_callable=AsyncMock) as mock_plan,
            patch.object(orch, "_execute_plan", new_callable=AsyncMock) as mock_exec,
            patch.object(orch, "_synthesise_results") as mock_synth,
        ):
            mock_plan.return_value = WorkflowPlan(
                workflow_id="test_wf",
                goal="Test",
                sub_tasks=[],
            )
            mock_exec.return_value = [mock_result]
            mock_synth.return_value = {"goal": "Test", "succeeded": 1, "failed": 0}

            result = await orch.process_task(task)

            assert result.success
            assert result.result_data is not None
