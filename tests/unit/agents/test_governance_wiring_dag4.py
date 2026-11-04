"""EU-AI-006 / AUDIT-FIX-001 Dag 4: GovernanceContract wired in EnhancedBaseAgent."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.types import AgentType, ExecutionStatusContract


class _ReenterableFakeSessionFactory:
    """Testfake voor `memory_store["session_factory"]` die -- anders dan een eenmalig
    aangeroepen `@asynccontextmanager`-generator -- meerdere onafhankelijke
    `async with instance as db:`-cycli verdraagt.

    Gevonden door de verplichte blinde eindreview (ronde 5): `process_task()` doet
    `async with memory_store["session_factory"] as db:` op TWEE plekken (de
    boot-context-loader, regel ~507, EN de GDPR-opt-out-check, regel ~544) binnen
    EEN aanroep. Een `@asynccontextmanager`-fake die maar eenmaal is aangeroepen
    (`_fake_session_factory()`) levert een eenmalig-bruikbaar object -- de tweede
    `async with` daarop geeft `AttributeError: '_AsyncGeneratorContextManager' object
    has no attribute 'args'` (self-getest, reproduceerbaar met een losstaand script).
    Die AttributeError werd door de GDPR-checks eigen `except Exception`
    (fail-closed) opgevangen, dus BEIDE GDPR-tests slaagden altijd op GEBLOKKEERD --
    onafhankelijk van wat `check_profiling_opt_out()`s mock teruggaf. Bewezen met een
    dubbele mock-inversie (`return_value=True` -> `False`, en
    `side_effect=RuntimeError(...)` -> een schone `return_value=False`): beide keren
    bleef de test slagen, wat aantoont dat de mock nooit werd geraadpleegd.

    OP-172 GESLOTEN: `process_task()` roept de factory nu aan (`async with
    session_factory() as db:`), zoals een echte `async_sessionmaker` vereist. Deze fake
    is daarom zelf aanroepbaar (`__call__`) en geeft zichzelf terug, zodat elke
    `async with fake() as db:`-cyclus onafhankelijk een nieuwe `AsyncMock` oplevert via
    `__aenter__` -- de reentrantie-eigenschap hierboven blijft behouden."""

    def __call__(self) -> "_ReenterableFakeSessionFactory":
        return self

    async def __aenter__(self) -> AsyncMock:
        return AsyncMock()

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def make_agent() -> EnhancedBaseAgent:
    with (
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.agents.base_agent.PromptGuard"),
        patch("src.core.agents.base_agent.OutputValidator"),
        patch("src.core.agents.base_agent.LearningMixin.__init_learning__", return_value=None),
    ):
        return EnhancedBaseAgent(
            agent_id="test-agent",
            agent_type=AgentType.RESEARCH,
            tenant_id=42,
        )


def test_governance_contract_instantiated_on_init() -> None:
    """EnhancedBaseAgent.__init__ instantieert GovernanceContract (EU-AI-006)."""
    agent = make_agent()
    from src.core.governance.governance_contract import GovernanceContract

    assert isinstance(agent._governance_contract, GovernanceContract)
    assert agent._governance_contract.agent_id == "test-agent"
    assert agent._governance_contract.tenant_id == 42


def test_governance_contract_blocks_forbidden_action() -> None:
    """is_action_permitted blokkeert acties buiten de autonomy ladder."""
    agent = make_agent()
    assert agent._governance_contract is not None
    agent._governance_contract.is_action_permitted = MagicMock(return_value=False)

    from src.core.shared.interfaces import TaskData

    task = TaskData(
        id="t1",
        title="blocked",
        description="blocked task",
        code="dangerous_action",
        tenant_id=42,
        agent_id="test-agent",
    )

    import asyncio

    with (
        patch.object(agent, "validate_task", new=AsyncMock(return_value=True)),
        patch.object(agent, "_sanitize_task_payload", side_effect=lambda t: t),
    ):
        result = asyncio.get_event_loop().run_until_complete(agent.process_task(task))

    assert result.success is False
    assert "not permitted" in (result.error_message or "")
    assert result.status == ExecutionStatusContract.GEBLOKKEERD
    assert agent._governance_contract is not None
    agent._governance_contract.is_action_permitted.assert_called_once_with("dangerous_action")


def test_prompt_injection_reports_mislukt() -> None:
    """ADR-036 D7-001: een geweigerde prompt-injectie is een mislukking, geen HTTP-code.

    `status="400"` was de enige bestaande schrijver van dit veld voor dit statuscontract
    bestond -- geverifieerd dat niemand die waarde leest (repo-brede grep, 0 treffers),
    dus de vervanging is zonder gedragsrisico."""
    from src.core.exceptions import PromptInjectionError

    agent = make_agent()

    from src.core.shared.interfaces import TaskData

    task = TaskData(
        id="t2",
        title="injection",
        description="prompt injection attempt",
        tenant_id=42,
        agent_id="test-agent",
    )

    import asyncio

    with patch.object(
        agent,
        "_sanitize_task_payload",
        side_effect=PromptInjectionError("prompt injection detected"),
    ):
        result = asyncio.get_event_loop().run_until_complete(agent.process_task(task))

    assert result.success is False
    assert result.error_message == "Invalid input format"
    assert result.status == ExecutionStatusContract.MISLUKT


def test_task_validation_failure_reports_mislukt() -> None:
    """ADR-036 D7-001 -- gevonden door de verplichte blinde eindreview (ronde 1): deze tak
    kreeg wel `status=MISLUKT` in de code, maar geen enkele test asserteerde het. Bewezen
    ontbrekend met een live mutatie (MISLUKT -> KLAAR gaf 0 gedetecteerde regressies)."""
    agent = make_agent()

    from src.core.shared.interfaces import TaskData

    task = TaskData(
        id="t3",
        title="invalid",
        description="fails validate_task",
        tenant_id=42,
        agent_id="test-agent",
    )

    import asyncio

    with (
        patch.object(agent, "validate_task", new=AsyncMock(return_value=False)),
        patch.object(agent, "_sanitize_task_payload", side_effect=lambda t: t),
    ):
        result = asyncio.get_event_loop().run_until_complete(agent.process_task(task))

    assert result.success is False
    assert "validation failed" in (result.error_message or "").lower()
    assert result.status == ExecutionStatusContract.MISLUKT


def test_gdpr_profiling_opt_out_reports_geblokkeerd() -> None:
    """ADR-036 D7-001 -- zelfde bevinding als hierboven, voor de GDPR-art.-21-tak. Een
    profileringsweigering is een beleidsmatige blokkade (GEBLOKKEERD), geen technische
    mislukking."""
    agent = make_agent()
    agent.memory_store = {"session_factory": _ReenterableFakeSessionFactory()}

    from src.core.shared.interfaces import TaskData

    task = TaskData(
        id="t4",
        title="profiled",
        description="task for an opted-out user",
        tenant_id=42,
        agent_id="test-agent",
        metadata={"user_id": "u-1"},
    )

    import asyncio

    with (
        patch.object(agent, "validate_task", new=AsyncMock(return_value=True)),
        patch.object(agent, "_sanitize_task_payload", side_effect=lambda t: t),
        patch(
            "src.core.governance.ai_transparency_service.AITransparencyService"
        ) as mock_service_cls,
    ):
        mock_service_cls.return_value.check_profiling_opt_out = AsyncMock(return_value=True)
        result = asyncio.get_event_loop().run_until_complete(agent.process_task(task))

    assert result.success is False
    assert "gdpr" in (result.error_message or "").lower()
    assert result.status == ExecutionStatusContract.GEBLOKKEERD


def test_gdpr_profiling_check_failure_fails_closed_and_reports_geblokkeerd() -> None:
    """ADR-036 D7-001 -- gevonden door de verplichte blinde eindreview (ronde 2), pre-existing
    en niet door dag 7 veroorzaakt: het faalveilige `except`-pad van de GDPR-opt-out-check
    (`base_agent.py`, "fail-closed on DB error") had GEEN enkele gedragstest -- de bovenstaande
    test oefent alleen het pad uit waar de check schoon `True` teruggeeft. Zonder deze test zou
    een regressie die `self._profiling_opted_out = True` in de except-tak stilletjes naar
    `False` verandert (het fail-OPEN-gedrag dat de code-comment expliciet uitsluit) door geen
    enkele test worden gevangen."""
    agent = make_agent()
    agent.memory_store = {"session_factory": _ReenterableFakeSessionFactory()}

    from src.core.shared.interfaces import TaskData

    task = TaskData(
        id="t4b",
        title="profiled",
        description="task for a user whose opt-out check itself fails",
        tenant_id=42,
        agent_id="test-agent",
        metadata={"user_id": "u-1"},
    )

    import asyncio

    with (
        patch.object(agent, "validate_task", new=AsyncMock(return_value=True)),
        patch.object(agent, "_sanitize_task_payload", side_effect=lambda t: t),
        patch(
            "src.core.governance.ai_transparency_service.AITransparencyService"
        ) as mock_service_cls,
    ):
        mock_service_cls.return_value.check_profiling_opt_out = AsyncMock(
            side_effect=RuntimeError("database onbereikbaar")
        )
        result = asyncio.get_event_loop().run_until_complete(agent.process_task(task))

    assert agent._profiling_opted_out is True, (
        "Een falende opt-out-check moet fail-closed zijn (opted_out=True), niet fail-open."
    )
    assert result.success is False
    assert "gdpr" in (result.error_message or "").lower()
    assert result.status == ExecutionStatusContract.GEBLOKKEERD


@pytest.mark.asyncio
async def test_the_real_session_factory_wiring_supports_async_with_directly() -> None:
    """Pin voor OP-172 (GESLOTEN). Reproduceert de ECHTE waarde die
    `_setup_memory_store()` in `memory_store["session_factory"]` zet (een echte
    `async_sessionmaker`, via de productiefunctie `create_session_factory()` -- niet de
    test-suite's eigen fake die elders in dit bestand gebruikt wordt) en toetst dat
    base_agent.py's gecorrigeerde gebruikspatroon (`async with session_factory() as db:`,
    de factory eerst aanroepen) daadwerkelijk werkt tegen een echte
    `async_sessionmaker`."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.core.container import create_session_factory

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as db:
            assert db is not None
    finally:
        await engine.dispose()


def test_agent_at_capacity_reports_meer_budget_nodig() -> None:
    """ADR-036 D7-001 -- zelfde bevinding als hierboven, voor de capaciteitslimiet-tak. Een
    resourcegrens die is bereikt is MEER_BUDGET_NODIG, geen technische mislukking."""
    agent = make_agent()
    agent._max_concurrent_tasks = 1

    from src.core.shared.interfaces import TaskData

    already_running = TaskData(
        id="already-running",
        title="occupies the one slot",
        description="pre-existing task",
        tenant_id=42,
        agent_id="test-agent",
    )
    agent._current_tasks[already_running.id] = already_running

    task = TaskData(
        id="t5",
        title="overloaded",
        description="agent already at capacity",
        tenant_id=42,
        agent_id="test-agent",
    )

    import asyncio

    with (
        patch.object(agent, "validate_task", new=AsyncMock(return_value=True)),
        patch.object(agent, "_sanitize_task_payload", side_effect=lambda t: t),
    ):
        result = asyncio.get_event_loop().run_until_complete(agent.process_task(task))

    assert result.success is False
    assert "capacity" in (result.error_message or "").lower()
    assert result.status == ExecutionStatusContract.MEER_BUDGET_NODIG


def test_unexpected_exception_reports_mislukt() -> None:
    """ADR-036 D7-001 -- zelfde bevinding als hierboven, voor de buitenste `except
    Exception`-afhandeling. `_execute_task()` is op de basisklasse niet geimplementeerd
    (`NotImplementedError`) en dat is precies de onverwachte fout die deze tak moet vangen."""
    agent = make_agent()
    agent._governance_contract = None  # isoleer de buitenste except, niet het governance-pad

    from src.core.shared.interfaces import TaskData

    task = TaskData(
        id="t6",
        title="crash",
        description="triggers the unimplemented _execute_task",
        tenant_id=42,
        agent_id="test-agent",
    )

    import asyncio

    with (
        patch.object(agent, "validate_task", new=AsyncMock(return_value=True)),
        patch.object(agent, "_sanitize_task_payload", side_effect=lambda t: t),
    ):
        result = asyncio.get_event_loop().run_until_complete(agent.process_task(task))

    assert result.success is False
    assert result.status == ExecutionStatusContract.MISLUKT


def test_governance_contract_permits_execute_when_autonomous() -> None:
    """is_action_permitted laat 'execute' door bij HUMAN_OUT_OF_LOOP (autonoom)."""
    from src.core.governance.governance_contract import AutonomyLevel, GovernanceContract

    gc = GovernanceContract(
        agent_id="test-agent",
        tenant_id=42,
        autonomy_level=AutonomyLevel.HUMAN_OUT_OF_LOOP,
    )
    assert gc.is_action_permitted("execute") is True


def test_governance_contract_blocks_execute_when_human_in_loop() -> None:
    """HUMAN_IN_LOOP vereist expliciete goedkeuring -- 'execute' standaard geblokkeerd."""
    from src.core.governance.governance_contract import AutonomyLevel, GovernanceContract

    gc = GovernanceContract(
        agent_id="test-agent",
        tenant_id=42,
        autonomy_level=AutonomyLevel.HUMAN_IN_LOOP,
    )
    assert gc.is_action_permitted("execute") is False
