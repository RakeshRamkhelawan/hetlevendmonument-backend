from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Deze tests raken de `tool_broker`-property, die een echte `LocalToolRegistry` bouwt, en die
# opent in zijn constructor een ECHTE verbinding naar de Docker-daemon (ADR-036 OP-214).
from tests.fixtures.docker_sandbox import geen_echte_docker_daemon  # noqa: F401

from src.core.agents.base_agent import EnhancedBaseAgent
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
        return _ToolAgent(
            agent_id="tool-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )


def test_tool_broker_initially_none() -> None:
    agent = _make_agent()
    assert agent._tool_broker is None


def test_tool_broker_created_on_first_access() -> None:
    agent = _make_agent()
    broker = agent.tool_broker
    assert broker is not None
    assert agent._tool_broker is broker


def test_tool_broker_cached_after_first_access() -> None:
    agent = _make_agent()
    first = agent.tool_broker
    second = agent.tool_broker
    assert first is second


@pytest.mark.asyncio
async def test_execute_tool_delegates_to_broker() -> None:
    agent = _make_agent()
    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    agent._tool_broker = mock_broker
    result = await agent.execute_tool("test__echo", {"value": 1})
    assert result == {"ok": True}
    mock_broker.execute_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_tool_without_broker_raises() -> None:
    agent = _make_agent()
    agent._create_tool_broker = MagicMock(return_value=None)
    with pytest.raises(RuntimeError, match="ToolBroker not available"):
        await agent.execute_tool("test__echo", {})


@pytest.mark.asyncio
async def test_execute_tool_emits_event() -> None:
    agent = _make_agent()
    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    agent._tool_broker = mock_broker
    agent.emit_event = AsyncMock()
    await agent.execute_tool("test__echo", {"value": 1})
    agent.emit_event.assert_awaited_once()
    assert agent.emit_event.await_args.args[0] == "tool_executed"


@pytest.mark.asyncio
async def test_execute_tool_denylist_precheck_short_circuits_before_broker() -> None:
    """ADR036-ADR015-001/OP-24: een agent-laag-denylistcheck (analoog aan
    specialist_base.py::_reject_before_council()) moet de broker-aanroep NOOIT bereiken voor
    een geweigerde tool. Dit is de daadwerkelijke, betekenisvolle gedragsverandering van deze
    fix -- niet het voorkomen van uitvoering (broker.execute_tool() blokkeert een
    denylist-tool via is_tool_allowed() toch al, zie
    tests/unit/tool_broker/test_denied_actions_hard_denylist.py), maar een vroegere afwijzing
    zonder de broker-round-trip."""
    agent = _make_agent()
    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    agent._tool_broker = mock_broker

    mock_manager = MagicMock()
    mock_manager.is_denied = MagicMock(return_value=True)
    agent._get_execute_tool_permission_manager = MagicMock(return_value=mock_manager)

    with pytest.raises(ToolExecutionException, match="Denylist-geweigerd"):
        await agent.execute_tool("dangerous_tool", {})

    mock_broker.execute_tool.assert_not_awaited()
    mock_manager.is_denied.assert_called_once_with("tool-agent", "dangerous_tool")


@pytest.mark.asyncio
async def test_execute_tool_denies_a_real_denylisted_tool_end_to_end() -> None:
    """ADR036-ADR015-001/OP-24 -- gevonden door de verplichte blinde eindreview (ronde 4):
    geen enkele test liet de ECHTE `is_denied()`-beslissing door de ECHTE `execute_tool()`
    -weg lopen. De twee precheck-tests hierboven mocken `_get_execute_tool_permission_manager`
    zelf weg, en de cache-test (verderop) roept `is_denied()` nooit aan. Bewezen met een live
    mutatie: `is_denied()` altijd `False` laten teruggeven liet alle 24 op dat moment
    relevante tests groen. Geen actieve bypass (de broker blokkeert de denylist onafhankelijk
    ook al via `is_tool_allowed()`), maar de precheck's EIGEN, meetbare belofte (vroegere
    afwijzing, geen broker-round-trip) had nul end-to-end gedragsdekking.

    Deze test gebruikt een ECHTE `ToolPermissionManager` met een handmatig geinjecteerd
    denylist-profiel (geen YAML-bestand nodig) en laat `execute_tool()` volledig ongemockt
    -- alleen de broker zelf is een dubbel, om de round-trip-telling te kunnen bevestigen."""
    from src.core.tool_broker.permission_manager import AgentToolProfile, ToolPermissionManager

    agent = _make_agent()
    real_manager = ToolPermissionManager()
    real_manager._agent_profiles["tool-agent"] = AgentToolProfile(
        agent_id="tool-agent",
        denied_actions=["dangerous_tool"],
    )

    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    mock_broker.permission_manager = real_manager
    agent._tool_broker = mock_broker

    with pytest.raises(ToolExecutionException, match="Denylist-geweigerd"):
        await agent.execute_tool("dangerous_tool", {})

    mock_broker.execute_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_tool_denies_a_tool_on_the_legacy_denied_tools_alias_end_to_end() -> None:
    """ADR036-ADR015-001/OP-24 -- gevonden door de verplichte blinde eindreview (ronde 8):
    `is_denied()` (`permission_manager.py`) weigert op `denied_actions` OF de legacy-alias
    `denied_tools`, maar geen enkele test in de repo oefende de `denied_tools`-tak uit --
    bewezen met een live mutatie: de `or tool_name in profile.denied_tools`-clausule uit
    `is_denied()` verwijderen liet alle 663 op dat moment relevante tests
    (`tests/unit/agents/`, `tests/unit/tool_broker/`) groen. Deze fix (dag 8) voegt een
    TWEEDE productie-aanroeper toe die op deze functie leunt (naast de bestaande
    `_reject_before_council()`-check in `specialist_base.py`), dus het coverage-gat wordt
    door deze diff zelf relevanter, ook al is `permission_manager.py` niet gewijzigd.

    Spiegelbeeld van `test_execute_tool_denies_a_real_denylisted_tool_end_to_end` hierboven,
    maar met `denied_tools=[...]` in plaats van `denied_actions=[...]`."""
    from src.core.tool_broker.permission_manager import AgentToolProfile, ToolPermissionManager

    agent = _make_agent()
    real_manager = ToolPermissionManager()
    real_manager._agent_profiles["tool-agent"] = AgentToolProfile(
        agent_id="tool-agent",
        denied_tools=["legacy_dangerous_tool"],
    )

    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    mock_broker.permission_manager = real_manager
    agent._tool_broker = mock_broker

    with pytest.raises(ToolExecutionException, match="Denylist-geweigerd"):
        await agent.execute_tool("legacy_dangerous_tool", {})

    mock_broker.execute_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_tool_allows_a_different_tool_on_the_same_real_profile_end_to_end() -> None:
    """ADR036-ADR015-001/OP-24 -- gevonden door de verplichte blinde eindreview (ronde 5),
    het spiegelbeeld van ronde 4's eigen bevinding: geen enkele test bewees dat een NIET-
    geweigerde tool nog steeds doorgaat naar de broker wanneer de echte
    `ToolPermissionManager` een ECHT, NIET-LEEG profiel heeft (i.e. het profiel bestaat en
    heeft een denylist, maar die denylist bevat deze specifieke tool niet). Zonder deze test
    zou een regressie die `is_denied()` verwart "heeft dit agent-profiel OVERHAUPT een
    denylist" met "staat DEZE tool op de denylist" (bv. `return bool(profile.denied_actions)`
    i.p.v. `return tool_name in profile.denied_actions or ...`) volledig ongedetecteerd
    blijven -- bewezen met een live mutatie van `is_denied()` naar exact die vorm: alle 10
    toen-bestaande tests in dit bestand bleven groen, want de enige test met een echt
    profiel (`test_execute_tool_denies_a_real_denylisted_tool_end_to_end`, hierboven) vraagt
    toevallig alleen de WEL-geweigerde tool op, en `test_execute_tool_allows_non_denied_tool_
    through_to_broker` (hieronder) mockt de manager zelf weg."""
    from src.core.tool_broker.permission_manager import AgentToolProfile, ToolPermissionManager

    agent = _make_agent()
    real_manager = ToolPermissionManager()
    real_manager._agent_profiles["tool-agent"] = AgentToolProfile(
        agent_id="tool-agent",
        denied_actions=["dangerous_tool"],
    )

    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    mock_broker.permission_manager = real_manager
    agent._tool_broker = mock_broker

    result = await agent.execute_tool("safe_tool", {"value": 1})

    assert result == {"ok": True}
    mock_broker.execute_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_tool_allows_non_denied_tool_through_to_broker() -> None:
    """Regressietest voor de OP-24-precheck: een niet-geweigerde tool moet nog steeds
    normaal doorgaan naar de broker -- de precheck mag alleen een echte denylist-hit
    blokkeren, geen enkele andere aanroep."""
    agent = _make_agent()
    mock_broker = AsyncMock()
    mock_broker.execute_tool = AsyncMock(return_value={"ok": True})
    agent._tool_broker = mock_broker

    mock_manager = MagicMock()
    mock_manager.is_denied = MagicMock(return_value=False)
    agent._get_execute_tool_permission_manager = MagicMock(return_value=mock_manager)

    result = await agent.execute_tool("test__echo", {"value": 1})

    assert result == {"ok": True}
    mock_broker.execute_tool.assert_awaited_once()


def test_get_execute_tool_permission_manager_reuses_and_caches_the_real_manager() -> None:
    """ADR036-ADR015-001/OP-24 -- gevonden door de verplichte blinde eindreview (ronde 2):
    de manager-hergebruik- en cache-logica van `_get_execute_tool_permission_manager()` werd
    door geen enkele test daadwerkelijk uitgeoefend. De twee tests hierboven mocken de
    helper zelf weg, en de twee oudere broker-delegatietests gebruiken een `AsyncMock`-
    broker -- die valt altijd op de fallback-constructietak (de `isinstance`-toets faalt op
    een auto-mock-attribuut), nooit op het ECHTE hergebruikpad, en geen enkele test riep de
    helper tweemaal aan om de cache-hit-tak te raken. Bewezen met een live mutatie: de hele
    hergebruik-en-cache-mechaniek verwijderen (altijd een verse `ToolPermissionManager()`
    bouwen) liet alle 232 op dat moment relevante tests groen.

    Deze test dwingt drie takken af: (1) een broker met een ECHTE `ToolPermissionManager`
    op `.permission_manager` moet DAT exemplaar teruggeven (identiteit, niet een nieuw
    gebouwd exemplaar); (2) een tweede aanroep -- met een ANDER, eigen echt exemplaar op een
    andere broker -- moet nog steeds het EERSTE (gecachte) exemplaar teruggeven, wat bewijst
    dat de cache daadwerkelijk geraadpleegd wordt in plaats van de broker opnieuw te lezen;
    (3) de cache moet PER AGENT-INSTANTIE zijn, niet gedeeld over alle agenten.

    **Correctie na ronde 3 van de verplichte blinde eindreview**: de oorspronkelijke versie
    van deze test (alleen takken 1-2) bewees de cache-SCOPE niet op zichzelf -- een mutatie
    naar een KLASSE-brede cache (`type(self)._execute_tool_permission_manager = manager`
    i.p.v. `self.`) werd in het volledige testbestand toevallig ook gevangen, maar uitsluitend
    doordat een ANDERE, eerder in het bestand gedefinieerde test
    (`test_execute_tool_delegates_to_broker`) de klasse-brede cache al had gevuld voordat deze
    test zelfs maar draaide -- in isolatie gedraaid (`pytest ...::test_get_execute_tool_
    permission_manager_reuses_and_caches_the_real_manager`) bleef die mutatie ONGEVANGEN. Tak
    3 hieronder maakt de test zelfstandig bewijsvoerend: een TWEEDE, onafhankelijke agent mag
    de EERSTE agent's gecachte manager nooit terugkrijgen."""
    from src.core.tool_broker.permission_manager import ToolPermissionManager

    agent = _make_agent()

    first_manager = ToolPermissionManager()
    first_broker = MagicMock()
    first_broker.permission_manager = first_manager

    result_one = agent._get_execute_tool_permission_manager(first_broker)
    assert result_one is first_manager, (
        "De broker's ECHTE manager moet hergebruikt worden, niet een nieuw exemplaar."
    )

    second_manager = ToolPermissionManager()
    second_broker = MagicMock()
    second_broker.permission_manager = second_manager

    result_two = agent._get_execute_tool_permission_manager(second_broker)
    assert result_two is first_manager, (
        "Een tweede aanroep moet de GECACHTE manager teruggeven (identiek aan de eerste), "
        "niet opnieuw uit de (andere) broker lezen -- anders zou dit de tweede broker's "
        "manager teruggeven."
    )

    other_agent = _make_agent()
    third_manager = ToolPermissionManager()
    third_broker = MagicMock()
    third_broker.permission_manager = third_manager

    result_three = other_agent._get_execute_tool_permission_manager(third_broker)
    assert result_three is not first_manager, (
        "De cache moet PER AGENT-INSTANTIE zijn -- een andere agent mag nooit de gecachte "
        "manager van de eerste agent terugkrijgen, alleen zijn eigen (derde) broker's manager."
    )
    assert result_three is third_manager
