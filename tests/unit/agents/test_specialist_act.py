"""Unit tests for BaseSpecialistAgent.act() -- TOOL_CALL parsing and execution."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.types import ExecutionStatusContract


def _make_config(**overrides):
    """Create a minimal valid config dict for BaseSpecialistAgent."""
    defaults = {
        "agent_id": "test-agent-001",
        "technology": "general",
        "name": "Test Agent",
        "description": "A test agent",
        "allowed_tools": [],
    }
    defaults.update(overrides)
    return defaults


class TestParseToolCalls:
    """Test _parse_tool_calls() regex parsing."""

    def test_parse_single_tool_call(self):
        """Single TOOL_CALL line is parsed correctly."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        decision = 'TOOL_CALL: test__echo {"message": "hello"}'
        calls = agent._parse_tool_calls(decision)
        assert len(calls) == 1
        assert calls[0][0] == "test__echo"
        assert calls[0][1] == {"message": "hello"}

    def test_parse_multiple_tool_calls(self):
        """Multiple TOOL_CALL lines are parsed in order."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        decision = (
            "Analysis complete.\n"
            'TOOL_CALL: test__echo {"message": "step1"}\n'
            'TOOL_CALL: test__slow {"delay_seconds": 0.1}\n'
            "Done."
        )
        calls = agent._parse_tool_calls(decision)
        assert len(calls) == 2
        assert calls[0][0] == "test__echo"
        assert calls[1][0] == "test__slow"

    def test_no_tool_calls_returns_empty(self):
        """Decision without TOOL_CALL returns empty list."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        decision = "I analyzed the data. No tools needed."
        calls = agent._parse_tool_calls(decision)
        assert calls == []

    def test_invalid_json_skipped(self):
        """Invalid JSON in TOOL_CALL is skipped with warning, not crash."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        decision = "TOOL_CALL: test__echo {invalid json}"
        calls = agent._parse_tool_calls(decision)
        assert calls == []

    def test_tool_not_in_allowed_list_rejected(self):
        """Tool not in agent's allowed_tools is rejected."""
        config = _make_config(allowed_tools=["test__echo"])
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        decision = 'TOOL_CALL: dangerous__rm_rf {"path": "/"}'
        calls = agent._parse_tool_calls(decision)
        assert calls == []

    def test_allowed_tool_passes(self):
        """Tool in agent's allowed_tools is accepted."""
        config = _make_config(allowed_tools=["test__echo"])
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        decision = 'TOOL_CALL: test__echo {"message": "ok"}'
        calls = agent._parse_tool_calls(decision)
        assert len(calls) == 1
        assert calls[0][0] == "test__echo"

    def test_empty_allowed_tools_allows_all(self):
        """Empty allowed_tools list allows any tool."""
        config = _make_config(allowed_tools=[])
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        decision = 'TOOL_CALL: any__tool {"param": 1}'
        calls = agent._parse_tool_calls(decision)
        assert len(calls) == 1


class TestActExecution:
    """Test act() method tool execution."""

    @pytest.mark.asyncio
    async def test_act_no_tools_returns_decision_text(self):
        """act() with no TOOL_CALL returns decision text as output."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        # BE-AGT-042: act() voert niets uit zonder verantwoordelijke mens. Het
        # uitvoerpad zet dit normaal; deze tests roepen act() rechtstreeks aan.
        agent._initiated_by_user_id = 42
        result = await agent.act("Just a plain text decision")
        assert result.success is True
        assert result.result_data["tool_calls"] == 0
        assert result.result_data["output"] == "Just a plain text decision"
        assert result.status == ExecutionStatusContract.KLAAR

    @pytest.mark.asyncio
    async def test_act_executes_parsed_tools(self):
        """act() parses decision and executes tools sequentially."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        # BE-AGT-042: act() voert niets uit zonder verantwoordelijke mens. Het
        # uitvoerpad zet dit normaal; deze tests roepen act() rechtstreeks aan.
        agent._initiated_by_user_id = 42
        agent.tools = AsyncMock()
        agent.tools.execute_tool = AsyncMock(return_value={"message": "hello"})

        decision = 'TOOL_CALL: test__echo {"message": "hello"}'
        result = await agent.act(decision)
        assert result.success is True
        assert len(result.result_data["results"]) == 1
        assert result.result_data["results"][0]["tool"] == "test__echo"
        agent.tools.execute_tool.assert_called_once()
        assert result.status == ExecutionStatusContract.KLAAR

    @pytest.mark.asyncio
    async def test_act_partial_failure(self):
        """One tool failure does not stop the remaining tools -- maar is geen succes.

        De oorspronkelijke versie van deze test bewees de eerste helft met
        `result.success is True`. Dat verwart twee dingen: dat de uitvoering doorgaat
        (bewezen door results==1) en dat de stap gelukt is. Die verwarring had een prijs:
        de OODA-loop rekent op `success` prana af (`specialist_base.py:324-327`), dus een
        tenant betaalde voor werk dat deels niet is uitgevoerd. Zie BE-AGT-039 F3.

        De invariant uit de oorspronkelijke docstring blijft hier volledig getoetst: na de
        eerste fout wordt de tweede tool nog steeds aangeroepen.
        """
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        # BE-AGT-042: act() voert niets uit zonder verantwoordelijke mens. Het
        # uitvoerpad zet dit normaal; deze tests roepen act() rechtstreeks aan.
        agent._initiated_by_user_id = 42
        agent.tools = AsyncMock()
        agent.tools.execute_tool = AsyncMock(side_effect=[Exception("fail"), {"ok": True}])

        decision = (
            'TOOL_CALL: test__fail {"error": "boom"}\n'
            'TOOL_CALL: test__echo {"message": "still runs"}'
        )
        result = await agent.act(decision)
        # De oorspronkelijke bedoeling: de tweede tool draait ondanks de eerste fout.
        assert len(result.result_data["results"]) == 1
        assert len(result.result_data["errors"]) == 1
        assert (
            agent.tools.execute_tool.await_count == 2
        ), "beide tools moeten zijn aangeroepen -- een fout mag de reeks niet afbreken"
        # En de correctie: doorgaan is niet hetzelfde als slagen.
        assert result.success is False
        # ADR-036 D7-001: een geslaagde en een mislukte tool samen is een deeluitvoering,
        # niet een volledige mislukking.
        assert result.status == ExecutionStatusContract.GEDEELTELIJK

    @pytest.mark.asyncio
    async def test_act_all_failures(self):
        """All tool failures result in success=False."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        # BE-AGT-042: act() voert niets uit zonder verantwoordelijke mens. Het
        # uitvoerpad zet dit normaal; deze tests roepen act() rechtstreeks aan.
        agent._initiated_by_user_id = 42
        agent.tools = AsyncMock()
        agent.tools.execute_tool = AsyncMock(side_effect=Exception("fail"))

        decision = 'TOOL_CALL: test__fail {"x": 1}'
        result = await agent.act(decision)
        assert result.success is False
        assert len(result.result_data["errors"]) == 1
        assert len(result.result_data["results"]) == 0
        assert result.status == ExecutionStatusContract.MISLUKT

    @pytest.mark.asyncio
    async def test_agent_id_passed_to_broker(self):
        """agent_id is passed to ToolBroker for permission checks."""
        config = _make_config(agent_id="specialist-007")
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        # BE-AGT-042: act() voert niets uit zonder verantwoordelijke mens. Het
        # uitvoerpad zet dit normaal; deze tests roepen act() rechtstreeks aan.
        agent._initiated_by_user_id = 42
        agent.tools = AsyncMock()
        agent.tools.execute_tool = AsyncMock(return_value={})

        decision = 'TOOL_CALL: test__echo {"message": "hi"}'
        await agent.act(decision)
        agent.tools.execute_tool.assert_called_once_with(
            tool_name="test__echo",
            payload={"message": "hi"},
            agent_id="specialist-007",
            timeout_seconds=30,
            context={"tenant_id": 1},
        )

    @pytest.mark.asyncio
    async def test_act_records_execution_time(self):
        """act() records execution_time in the result."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=1)
        # BE-AGT-042: act() voert niets uit zonder verantwoordelijke mens. Het
        # uitvoerpad zet dit normaal; deze tests roepen act() rechtstreeks aan.
        agent._initiated_by_user_id = 42
        result = await agent.act("no tools here")
        assert result.execution_time >= 0.0

    @pytest.mark.asyncio
    async def test_act_preserves_tenant_id(self):
        """act() includes tenant_id in the result."""
        config = _make_config()
        agent = BaseSpecialistAgent(config=config, tenant_id=42)
        result = await agent.act("no tools")
        assert result.tenant_id == 42
