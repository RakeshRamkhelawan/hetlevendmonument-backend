"""AUDIT-009 regression tests: real skill execution in DomainPackOrchestrator.

Bevinding (HIGH/P1): ``DomainPackOrchestrator._execute_step`` was a placeholder
-- it did ``await asyncio.sleep(0.01)`` and always returned
``ExecutionResult(task_id="t1", success=True)``, regardless of agent_id or
params. The whole pack execution flow effectively did nothing but reported
success, including ROI logging. An additional pre-existing issue was found at
``packs.py:177``: ``_execute_single_agent`` silently fell back to
``tenant_id=0`` for non-numeric tenant strings (ADR-005: tenant 0 does not
exist).

These tests pin the fix (ADR-036 D10 pilot harness, K1 option A):

- 1.1  _execute_step really executes the pilot skill (skillsgaptraining):
       the skill class is instantiated and called; the result comes from the
       skill, not from a hardcoded ``task_id="t1"``.
- 1.2  No silent success on failure: a raising skill yields success=False
       with a real error_message -- never the sleep placeholder.
- 1.3  Unknown agent fails explicitly (success=False, clear error).
- 1.4  Tenant is passed through unchanged (int 1, not 0, not a string); the
       legacy ``_execute_single_agent`` path rejects non-numeric tenant
       strings explicitly instead of the silent ``else 0`` fallback.
- 1.5  Behavioral: run_pack for a pilot pack step -- ROI logging sees the
       real result; a failed skill produces no success-ROI row.

Boundary mocking policy: skill instantiation, the LLM call and the broker
dispatch are mocked at the boundary; internal logic is not mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.als.enterprise.packs import (
    DomainPack,
    DomainPackOrchestrator,
    WorkflowStep,
)
from src.core.shared.interfaces import ExecutionResult, ExecutionStatusContract

pytestmark = pytest.mark.unit

PILOT_SKILL_ID = "skillsgaptraining"

# BE-AGT-042: het pack-pad is fail-closed zonder verantwoordelijke mens. In productie
# komt die van de HTTP-ingang; hier expliciet, zodat de test het echte pad volgt.
TEST_INITIATOR = 42
PILOT_CLASS = "src.core.als.agents.skills.skillsgaptraining.SkillsGapTrainingSkill"


def _make_orchestrator() -> DomainPackOrchestrator:
    """Real orchestrator on the real catalog (config/agents + domain_packs)."""
    return DomainPackOrchestrator()


# ---------------------------------------------------------------------------
# Test 1.1 -- _execute_step really executes the pilot skill
# ---------------------------------------------------------------------------


class TestExecuteStepRealExecution:
    """Test 1.1 from the day-5 brief."""

    async def test_execute_step_instantiates_and_calls_pilot_skill(self) -> None:
        """The pilot skill is instantiated with the tenant and called; the
        result comes from the skill, not from a hardcoded placeholder."""
        orchestrator = _make_orchestrator()
        skill_result = ExecutionResult(
            task_id="real-skill-result",
            success=True,
            result_data={"output": "Trainingsadvies"},
            tenant_id=1,
            agent_id=PILOT_SKILL_ID,
        )
        mock_skill = MagicMock()
        mock_skill.execute_with_manifest_prompt = AsyncMock(return_value=skill_result)

        with patch.object(
            orchestrator.catalog, "get_agent_instance", return_value=mock_skill
        ) as mock_factory:
            result = await orchestrator._execute_step(
                PILOT_SKILL_ID, 1, {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
            )

        mock_factory.assert_called_once_with(PILOT_SKILL_ID, 1)
        mock_skill.execute_with_manifest_prompt.assert_awaited_once()
        assert result is skill_result, (
            "_execute_step moet het resultaat van de skill retourneren, niet een "
            "eigen placeholder-resultaat (AUDIT-009)."
        )
        assert result.task_id != "t1", "hardcoded placeholder task_id 't1' gedetecteerd"

    async def test_execute_step_full_chain_with_real_skill_class(self) -> None:
        """Stronger variant: real catalog resolution + real skill class; only
        the LLM call and the broker dispatch are mocked at the boundary."""
        from src.core.als.agents.skill_manifest import SkillManifest
        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

        orchestrator = _make_orchestrator()
        llm_service = MagicMock()
        llm_service.generate = AsyncMock(
            # `query_hr_database` en niet `send_notification`: die laatste is op 2026-09-21
            # uit het manifest van de piloot gehaald (er is geen broker-tool voor), waarna de
            # manifest-filter in `act()` hem weigert VOORDAT de broker hem ziet -- en dan meet
            # deze test niet meer of `_execute_step` de echte skill aanroept. Een leestool is
            # hier bovendien het juiste voorbeeld: `schedule_training` is HIGH en zou zonder
            # goedgekeurd ticket door de HITL-poort worden geweigerd.
            return_value='TOOL_CALL: query_hr_database {"role": "Engineer"}'
        )

        # Sinds ADR-036 D4-002 is de piloot Annex III/HITL: een APPROVED-verdict zou anders een
        # ticket aanmaken in plaats van de tool uit te voeren, en deze test toetst of
        # `_execute_step` de ECHTE skill aanroept, niet de HITL-floor. De orchestrator
        # construeert de skill intern via de catalogus, dus er is geen instantie om `.config`
        # na constructie te overschrijven -- in plaats daarvan `to_config()` zelf tijdelijk
        # patchen, dezelfde "boundary mocking"-aanpak als de LLM- en broker-patches hieronder.
        original_to_config = SkillManifest.to_config

        def _to_config_without_the_floor(self: SkillManifest) -> dict[str, object]:
            config = original_to_config(self)
            config["human_in_the_loop"] = "hotl"
            return config

        with (
            patch.object(SkillsGapTrainingSkill, "_get_llm_service", return_value=llm_service),
            patch.object(SkillManifest, "to_config", _to_config_without_the_floor),
            patch(
                "src.core.tool_broker.service.ToolBrokerService.execute_tool",
                new_callable=AsyncMock,
                return_value={"success": True},
            ) as mock_broker,
        ):
            result = await orchestrator._execute_step(
                PILOT_SKILL_ID, 1, {"task": "gap analyse"}, initiated_by_user_id=TEST_INITIATOR
            )

        assert result.success is True
        assert result.task_id != "t1"
        assert result.result_data is not None and result.result_data["tool_calls"] == 1
        llm_service.generate.assert_awaited_once()
        # K1 option A: the LLM call MUST carry the manifest system_prompt
        # (the one containing the TOOL_CALL contract).
        llm_kwargs = llm_service.generate.await_args.kwargs
        assert "TOOL_CALL" in llm_kwargs["system_prompt"], (
            "De LLM-aanroep bevat de manifest-system_prompt niet -- het TOOL_CALL-"
            "formaat is voor het model onzichtbaar (dag-4 dode-tekst bevinding)."
        )
        broker_kwargs = mock_broker.await_args.kwargs
        assert broker_kwargs["agent_id"] == PILOT_SKILL_ID
        assert broker_kwargs["tool_name"] == "query_hr_database"


# ---------------------------------------------------------------------------
# Test 1.2 -- no silent success on failure
# ---------------------------------------------------------------------------


class TestNoSilentSuccess:
    """Test 1.2 from the day-5 brief."""

    async def test_skill_exception_yields_explicit_failure(self) -> None:
        orchestrator = _make_orchestrator()
        mock_skill = MagicMock()
        mock_skill.execute_with_manifest_prompt = AsyncMock(
            side_effect=RuntimeError("broker dispatch exploded")
        )

        with patch.object(orchestrator.catalog, "get_agent_instance", return_value=mock_skill):
            result = await orchestrator._execute_step(
                PILOT_SKILL_ID, 1, {}, initiated_by_user_id=TEST_INITIATOR
            )

        assert result.success is False, (
            "Een falende skill mag nooit als stil succes worden gerapporteerd -- "
            "dat was precies de AUDIT-009-zonde."
        )
        assert (
            result.error_message is not None and "broker dispatch exploded" in result.error_message
        )
        assert result.task_id != "t1"
        assert result.status == ExecutionStatusContract.MISLUKT

    async def test_instantiation_failure_yields_explicit_failure(self) -> None:
        """If the skill class cannot even be instantiated, that is an explicit
        failure too -- not a sleep-and-succeed."""
        orchestrator = _make_orchestrator()

        with patch.object(
            orchestrator.catalog,
            "get_agent_instance",
            side_effect=ValueError("broken skill module"),
        ):
            result = await orchestrator._execute_step(
                PILOT_SKILL_ID, 1, {}, initiated_by_user_id=TEST_INITIATOR
            )

        assert result.success is False
        assert result.error_message is not None and "broken skill module" in result.error_message
        assert result.status == ExecutionStatusContract.MISLUKT


# ---------------------------------------------------------------------------
# Test 1.3 -- unknown agent fails explicitly
# ---------------------------------------------------------------------------


class TestUnknownAgent:
    """Test 1.3 from the day-5 brief."""

    async def test_unknown_agent_fails_explicitly(self) -> None:
        orchestrator = _make_orchestrator()
        result = await orchestrator._execute_step(
            "bestaat_niet", 1, {}, initiated_by_user_id=TEST_INITIATOR
        )

        assert (
            result.success is False
        ), "Een onbekende agent moet expliciet falen, niet 'succes na 10ms'."
        assert result.error_message is not None and "bestaat_niet" in result.error_message
        assert result.task_id != "t1"
        assert result.status == ExecutionStatusContract.MISLUKT

    async def test_known_but_unwired_skill_fails_explicitly(self) -> None:
        """Skills that exist in the catalog but have no execution wiring yet
        (all skills except the pilot) fail explicitly -- no second silent
        placeholder (scope discipline from the day-5 brief)."""
        orchestrator = _make_orchestrator()
        result = await orchestrator._execute_step(
            "employeesentiment", 1, {}, initiated_by_user_id=TEST_INITIATOR
        )

        assert result.success is False
        assert result.error_message is not None and "employeesentiment" in result.error_message
        assert result.status == ExecutionStatusContract.MISLUKT


# ---------------------------------------------------------------------------
# Test 1.4 -- tenant passthrough + tenant_id=0 fallback removed (ADR-005)
# ---------------------------------------------------------------------------


class TestTenantPassthrough:
    """Test 1.4 from the day-5 brief."""

    async def test_skill_receives_tenant_unchanged(self) -> None:
        orchestrator = _make_orchestrator()
        mock_skill = MagicMock()
        mock_skill.execute_with_manifest_prompt = AsyncMock(
            return_value=ExecutionResult(task_id="x", success=True, tenant_id=1)
        )

        with patch.object(
            orchestrator.catalog, "get_agent_instance", return_value=mock_skill
        ) as mock_factory:
            await orchestrator._execute_step(
                PILOT_SKILL_ID, 1, {}, initiated_by_user_id=TEST_INITIATOR
            )

        _, tenant_arg = mock_factory.call_args.args
        assert tenant_arg == 1 and isinstance(
            tenant_arg, int
        ), "De skill moet tenant_id=1 als int krijgen -- niet 0, niet een string."

    async def test_single_agent_rejects_non_numeric_tenant(self) -> None:
        """Pre-existing fix (packs.py:177, ADR-005): the legacy str-tenant path
        must reject a non-numeric tenant explicitly instead of silently
        executing as tenant 0."""
        orchestrator = _make_orchestrator()

        with patch.object(orchestrator, "_execute_step", new_callable=AsyncMock) as mock_step:
            outcome = await orchestrator._execute_single_agent(PILOT_SKILL_ID, "tenant_abc")

        mock_step.assert_not_awaited(), (
            "_execute_step mag niet worden aangeroepen met de stille tenant_id=0-"
            "fallback -- niet-numerieke tenant = expliciete fout (ADR-005)."
        )
        assert outcome["status"] == "error"
        assert "tenant_abc" in outcome["error"]

    async def test_single_agent_passes_numeric_tenant_as_int(self) -> None:
        orchestrator = _make_orchestrator()

        with patch.object(orchestrator, "_execute_step", new_callable=AsyncMock) as mock_step:
            mock_step.return_value = ExecutionResult(task_id="x", success=True, tenant_id=1)
            outcome = await orchestrator._execute_single_agent(PILOT_SKILL_ID, "1")

        mock_step.assert_awaited_once()
        args = mock_step.await_args.args
        assert args[1] == 1 and isinstance(args[1], int)
        assert outcome["status"] == "success"


# ---------------------------------------------------------------------------
# Test 1.5 (behavioral) -- run_pack end-to-end for the pilot
# ---------------------------------------------------------------------------


class TestRunPackBehavioral:
    """Test 1.5 from the day-5 brief: ROI logging must see the real result,
    and a failed skill must not produce a success-ROI row."""

    def _pilot_pack(self) -> DomainPack:
        return DomainPack(
            pack_id="hr.reskilling_engine",
            name="Employee Reskilling & Mobility",
            steps=[
                WorkflowStep(agent_id=PILOT_SKILL_ID, mode="sequential", sla_seconds=600),
            ],
        )

    @staticmethod
    def _mock_db() -> MagicMock:
        mock_db_session = AsyncMock()
        mock_db_cm = MagicMock()
        mock_db_cm.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_db_cm

    async def test_roi_logging_sees_real_result(self) -> None:
        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

        orchestrator = _make_orchestrator()
        llm_service = MagicMock()
        llm_service.generate = AsyncMock(return_value="Advies zonder tools.")

        with (
            patch.object(SkillsGapTrainingSkill, "_get_llm_service", return_value=llm_service),
            patch("src.core.database.database.db_manager") as mock_db_manager,
            patch("src.core.analytics.roi_service.ROIService") as mock_roi_cls,
        ):
            mock_db_manager.get_session.return_value = self._mock_db()
            mock_roi = mock_roi_cls.return_value
            mock_roi.record_run = AsyncMock()

            results = await orchestrator.run_pack(self._pilot_pack(), tenant_id=1)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].task_id != "t1", (
            "ROI-logging zou hier het placeholder-task_id 't1' hebben vastgelegd -- "
            "bewijs dat de skill niet echt heeft gedraaid."
        )
        mock_roi.record_run.assert_awaited_once()
        roi_kwargs = mock_roi.record_run.await_args.kwargs
        assert roi_kwargs["agent_id"] == PILOT_SKILL_ID
        assert roi_kwargs["tenant_id"] == 1
        assert roi_kwargs["task_id"] == results[0].task_id

    async def test_failed_skill_is_recorded_as_mislukt_and_never_as_success(self) -> None:
        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

        orchestrator = _make_orchestrator()
        llm_service = MagicMock()
        llm_service.generate = AsyncMock(side_effect=RuntimeError("LLM provider down"))

        with (
            patch.object(SkillsGapTrainingSkill, "_get_llm_service", return_value=llm_service),
            patch("src.core.database.database.db_manager") as mock_db_manager,
            patch("src.core.analytics.roi_service.ROIService") as mock_roi_cls,
        ):
            mock_db_manager.get_session.return_value = self._mock_db()
            mock_roi = mock_roi_cls.return_value
            mock_roi.record_run = AsyncMock()

            results = await orchestrator.run_pack(self._pilot_pack(), tenant_id=1)

        assert len(results) == 1
        assert results[0].success is False
        assert (
            results[0].error_message is not None and "LLM provider down" in results[0].error_message
        )
        assert results[0].status == ExecutionStatusContract.MISLUKT
        # Een mislukte stap wordt WEL vastgelegd (aantal pogingen hoort bij een eerlijk beeld),
        # maar nooit als geslaagd: alleen status `klaar` telt later als besparing.
        mock_roi.record_run.assert_awaited_once()
        assert mock_roi.record_run.await_args.kwargs["status"] == "mislukt", (
            "Bij een gefaalde skill mag de run niet als geslaagd worden vastgelegd."
        )
