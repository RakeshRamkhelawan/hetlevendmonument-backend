"""ADR-036 OP-24 (BE-SEC-048, 2026-08-26): initiator-eis + Council-raadpleging op
EnhancedBaseAgent.execute_tool(), achter de `enhanced_base_agent_initiator_check`-
feature-flag (default False).

Kern-regressietest tegen het crash-risico uit BE-SEC-048 SS7.1: `Proposal.__post_init__`
faalt hard (ValueError) bij `user_id<=0` -- de check op `_initiated_by_user_id is None`
moet AL vroeger weigeren, zodat de Proposal-constructie nooit met een ontbrekende
initiator wordt geprobeerd.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.copilot.council.background_gate import AgentCouncilOutcome
from src.core.copilot.council.types import DecisionVerdict
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.types import AgentType


class _ToolAgent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True)


def _make_agent() -> _ToolAgent:
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch("src.core.agents.mixins.learning_mixin.get_feature_flag", return_value=True),
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        agent = _ToolAgent(
            agent_id="tool-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )
    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    agent._tool_broker = mock_broker
    return agent


def _decision(
    verdict: DecisionVerdict, *, hitl_ticket_ref: str | None = None
) -> AgentCouncilOutcome:
    decision = MagicMock()
    decision.verdict = verdict
    decision.explanation_for_user = f"verdict={verdict.value}"
    return AgentCouncilOutcome(decision=decision, hitl_ticket_ref=hitl_ticket_ref)


class TestFlagOff:
    @pytest.mark.asyncio
    async def test_flag_off_skips_the_initiator_check_entirely(self) -> None:
        """Regressie: bestaand gedrag (geen initiator, geen Council) blijft ongewijzigd
        zolang de flag uit staat -- de default."""
        agent = _make_agent()
        with patch("src.core.agents.base_agent.get_feature_flag", return_value=False):
            result = await agent.execute_tool("test__echo", {"value": 1})
        assert result == {"ok": True}
        agent._tool_broker.execute_tool.assert_awaited_once()  # type: ignore[attr-defined]


class TestFlagOnWithoutInitiator:
    @pytest.mark.asyncio
    async def test_missing_initiator_raises_before_any_proposal_is_built(self) -> None:
        """Kern-regressietest tegen BE-SEC-048 SS7.1: geen Proposal-constructie mag ooit
        geprobeerd worden zonder een geldige user_id -- anders crasht
        Proposal.__post_init__ met een ValueError in plaats van een nette weigering."""
        agent = _make_agent()
        assert agent._initiated_by_user_id is None

        with (
            patch("src.core.agents.base_agent.get_feature_flag", return_value=True),
            patch(
                "src.core.copilot.council.background_gate.request_council_decision_for_agent",
                new_callable=AsyncMock,
            ) as mock_council,
        ):
            with pytest.raises(ToolExecutionException, match="geen initiator bekend"):
                await agent.execute_tool("test__echo", {"value": 1})

        mock_council.assert_not_awaited()
        agent._tool_broker.execute_tool.assert_not_awaited()  # type: ignore[attr-defined]


class TestFlagOnWithInitiator:
    @pytest.mark.asyncio
    async def test_approved_verdict_proceeds_to_the_broker(self) -> None:
        agent = _make_agent()
        agent._initiated_by_user_id = 42

        with (
            patch("src.core.agents.base_agent.get_feature_flag", return_value=True),
            patch(
                "src.core.copilot.council.background_gate.request_council_decision_for_agent",
                new_callable=AsyncMock,
                return_value=_decision(DecisionVerdict.APPROVED),
            ) as mock_council,
        ):
            result = await agent.execute_tool("test__echo", {"value": 1})

        assert result == {"ok": True}
        mock_council.assert_awaited_once()
        call_kwargs = mock_council.await_args.kwargs if mock_council.await_args else {}
        assert call_kwargs.get("tenant_id") == 1
        assert call_kwargs.get("user_id") == 42
        assert call_kwargs.get("action_type") == "test__echo"
        agent._tool_broker.execute_tool.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_blocked_verdict_raises_and_never_reaches_the_broker(self) -> None:
        agent = _make_agent()
        agent._initiated_by_user_id = 42

        with (
            patch("src.core.agents.base_agent.get_feature_flag", return_value=True),
            patch(
                "src.core.copilot.council.background_gate.request_council_decision_for_agent",
                new_callable=AsyncMock,
                return_value=_decision(DecisionVerdict.BLOCKED),
            ),
        ):
            with pytest.raises(ToolExecutionException, match="Council-verdict blocked"):
                await agent.execute_tool("test__echo", {"value": 1})

        agent._tool_broker.execute_tool.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_modified_verdict_is_rejected_not_silently_applied(self) -> None:
        """Zelfde patroon als specialist_base.py::_council_rejection() (regel
        411-497, niet _reject_before_council() -- die checkt alleen D5-denylist +
        initiator-null): een MODIFIED-verdict zonder menselijke review van de
        aanpassing wordt geweigerd, niet stilzwijgend uitgevoerd met aangepaste
        parameters."""
        agent = _make_agent()
        agent._initiated_by_user_id = 42

        with (
            patch("src.core.agents.base_agent.get_feature_flag", return_value=True),
            patch(
                "src.core.copilot.council.background_gate.request_council_decision_for_agent",
                new_callable=AsyncMock,
                return_value=_decision(DecisionVerdict.MODIFIED),
            ),
        ):
            with pytest.raises(ToolExecutionException, match="Council-verdict modified"):
                await agent.execute_tool("test__echo", {"value": 1})

        agent._tool_broker.execute_tool.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_hitl_required_verdict_mentions_the_existing_ticket(self) -> None:
        """HITL_REQUIRED heeft al een ticket van de gate zelf (ADR-036 OP-167) -- geen
        eigen ticket-aanmaak hier nodig, alleen de ref doorgeven in de foutmelding."""
        agent = _make_agent()
        agent._initiated_by_user_id = 42

        with (
            patch("src.core.agents.base_agent.get_feature_flag", return_value=True),
            patch(
                "src.core.copilot.council.background_gate.request_council_decision_for_agent",
                new_callable=AsyncMock,
                return_value=_decision(DecisionVerdict.HITL_REQUIRED, hitl_ticket_ref="TICKET-123"),
            ),
        ):
            with pytest.raises(ToolExecutionException, match="TICKET-123"):
                await agent.execute_tool("test__echo", {"value": 1})

        agent._tool_broker.execute_tool.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_action_params_sent_to_council_contain_only_key_names(self) -> None:
        """BE-AGT-043-patroon: alleen sleutelnamen naar de Council, nooit de waarden
        (payload kan modelgegenereerde/gevoelige waarden bevatten)."""
        agent = _make_agent()
        agent._initiated_by_user_id = 42

        with (
            patch("src.core.agents.base_agent.get_feature_flag", return_value=True),
            patch(
                "src.core.copilot.council.background_gate.request_council_decision_for_agent",
                new_callable=AsyncMock,
                return_value=_decision(DecisionVerdict.APPROVED),
            ) as mock_council,
        ):
            await agent.execute_tool("test__echo", {"secret_value": "geheim-123"})

        call_kwargs = mock_council.await_args.kwargs if mock_council.await_args else {}
        assert "geheim-123" not in str(call_kwargs.get("action_params")), (
            "De waarde uit de payload mag niet in de Council-action_params lekken."
        )
        assert call_kwargs.get("ticket_action_params") == {"secret_value": "geheim-123"}, (
            "Het ticket heeft wel de RUWE waarden nodig om de tool later te kunnen "
            "verzilveren -- alleen de Council-action_params zijn geredigeerd."
        )
