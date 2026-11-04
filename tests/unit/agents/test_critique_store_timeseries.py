"""TDD tests voor get_timeseries_stats() -- SP-AGT-006 Dag 3 + SP-AGT-010 Dag 2.

Verifieert: materialized view query, tenant isolatie, hours filter, avg_score,
CritiqueTimeseriesStats TypedDict, _refresh_mv() patroon-3, refresh-guard cooldown.
DB-query wordt gemockt -- geen echte PostgreSQL of materialized view vereist.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.core.agents.critique_store import CritiqueStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_critique_store():
    """Reset CritiqueStore singleton voor elke test."""
    CritiqueStore._instance = None
    yield
    CritiqueStore._instance = None


def _make_row(hour_offset: int, agent_name: str, avg_score: float, count: int) -> MagicMock:
    """Bouw een nep-Row object met .hour, .agent_name, .avg_score, .critique_count."""
    row = MagicMock()
    row.hour = datetime.now(timezone.utc) - timedelta(hours=hour_offset)
    row.agent_name = agent_name
    row.avg_score = avg_score
    row.critique_count = count
    return row


def _make_db_mock(rows: list[MagicMock]) -> tuple[MagicMock, MagicMock]:
    """Bouw mock db_manager + session context voor db_manager.get_session() patroon."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    return mock_db, mock_session_ctx


# ---------------------------------------------------------------------------
# Test 3.1 -- Lege resultatenset als geen data beschikbaar is
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeseries_stats_returns_empty_for_no_data():
    store = CritiqueStore()
    _, mock_session_ctx = _make_db_mock([])

    with (
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch("src.core.database.database.db_manager.get_session", return_value=mock_session_ctx),
    ):
        result = await store.get_timeseries_stats(tenant_id=1, hours=24)

    assert result == []


# ---------------------------------------------------------------------------
# Test 3.2 -- Bucketing per uur (twee uur = twee entries)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeseries_stats_buckets_by_hour():
    store = CritiqueStore()
    row_h1 = _make_row(hour_offset=1, agent_name="AgentA", avg_score=0.8, count=3)
    row_h2 = _make_row(hour_offset=2, agent_name="AgentA", avg_score=0.6, count=2)
    mock_db, mock_session_ctx = _make_db_mock([row_h1, row_h2])

    with (
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch("src.core.database.database.db_manager.get_session", return_value=mock_session_ctx),
    ):
        result = await store.get_timeseries_stats(tenant_id=1, hours=24)

    assert len(result) == 2
    assert result[0]["agent_name"] == "AgentA"
    assert result[0]["avg_score"] == 0.8
    assert result[1]["avg_score"] == 0.6


# ---------------------------------------------------------------------------
# Test 3.3 -- Tenant isolatie (tenant_id doorgegeven in query params)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeseries_stats_tenant_isolation():
    store = CritiqueStore()
    mock_db, mock_session_ctx = _make_db_mock([])

    with (
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch("src.core.database.database.db_manager.get_session", return_value=mock_session_ctx),
    ):
        await store.get_timeseries_stats(tenant_id=99, hours=24)

    call_args = mock_db.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
    assert params.get("tenant_id") == 99


# ---------------------------------------------------------------------------
# Test 3.4 -- Hours filter (cutoff doorgegeven in query params)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeseries_stats_hours_filter():
    store = CritiqueStore()
    mock_db, mock_session_ctx = _make_db_mock([])
    hours = 6
    before_call = datetime.now(timezone.utc)

    with (
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch("src.core.database.database.db_manager.get_session", return_value=mock_session_ctx),
    ):
        await store.get_timeseries_stats(tenant_id=1, hours=hours)

    after_call = datetime.now(timezone.utc)
    call_args = mock_db.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
    cutoff = params.get("cutoff")

    assert cutoff is not None
    expected_min = before_call - timedelta(hours=hours) - timedelta(seconds=2)
    expected_max = after_call - timedelta(hours=hours) + timedelta(seconds=2)
    assert expected_min <= cutoff <= expected_max


# ---------------------------------------------------------------------------
# Test 3.5 -- Gemiddelde score correct in response dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeseries_stats_avg_score_correct():
    store = CritiqueStore()
    row = _make_row(hour_offset=1, agent_name="ScoringAgent", avg_score=0.75, count=4)
    mock_db, mock_session_ctx = _make_db_mock([row])

    with (
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch("src.core.database.database.db_manager.get_session", return_value=mock_session_ctx),
    ):
        result = await store.get_timeseries_stats(tenant_id=1, hours=24)

    assert len(result) == 1
    assert abs(result[0]["avg_score"] - 0.75) < 0.001
    assert result[0]["critique_count"] == 4
    assert "hour" in result[0]


# ---------------------------------------------------------------------------
# Test 3.6 -- Telemetry endpoint retourneert {"success": True, "data": [...]}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telemetry_endpoint_returns_200():
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from src.core.api.v1.orchestration.critic_router import critic_router
    from src.core.api.v1.orchestration.dependencies import get_critic_agent
    from src.core.agents.critic_agent import CriticAgent

    app = FastAPI()
    app.include_router(critic_router, prefix="/critics")

    CriticAgent._instances.pop(999, None)
    mock_agent = MagicMock(spec=CriticAgent)
    mock_agent.tenant_id = 999

    fake_stats = [
        {
            "hour": "2026-06-27T10:00:00+00:00",
            "agent_name": "TestAgent",
            "avg_score": 0.80,
            "critique_count": 5,
        }
    ]

    with patch.object(
        CritiqueStore, "get_timeseries_stats", new_callable=AsyncMock, return_value=fake_stats
    ):
        app.dependency_overrides[get_critic_agent] = lambda: mock_agent

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/critics/telemetry?hours=24")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert body["data"][0]["agent_name"] == "TestAgent"
    assert abs(body["data"][0]["avg_score"] - 0.80) < 0.001


# ---------------------------------------------------------------------------
# SP-AGT-010 Dag 2 -- Tests D, E, F
# ---------------------------------------------------------------------------


# Test D: CritiqueTimeseriesStats TypedDict
def test_critique_timeseries_stats_typeddict_exists() -> None:
    """CritiqueTimeseriesStats TypedDict is exporteerbaar en heeft de juiste velden."""
    from src.core.agents.critique_store import CritiqueTimeseriesStats

    required_keys = {"hour", "agent_name", "avg_score", "critique_count"}
    assert set(CritiqueTimeseriesStats.__annotations__.keys()) == required_keys
    assert CritiqueTimeseriesStats.__annotations__["hour"] is str
    assert CritiqueTimeseriesStats.__annotations__["agent_name"] is str
    assert CritiqueTimeseriesStats.__annotations__["avg_score"] is float
    assert CritiqueTimeseriesStats.__annotations__["critique_count"] is int


@pytest.mark.asyncio
async def test_get_timeseries_stats_annotation_uses_typeddict() -> None:
    """get_timeseries_stats return-annotatie verwijst naar CritiqueTimeseriesStats."""
    import typing
    from src.core.agents.critique_store import CritiqueStore, CritiqueTimeseriesStats

    hints = typing.get_type_hints(CritiqueStore.get_timeseries_stats)
    return_hint = hints.get("return")
    assert return_hint is not None, "get_timeseries_stats heeft geen return-annotatie"
    assert typing.get_origin(return_hint) is list, (
        f"return-annotatie moet list[...] zijn, was: {return_hint}"
    )
    args = typing.get_args(return_hint)
    assert len(args) == 1, f"list[...] moet exact 1 type-argument hebben, was: {args}"
    assert args[0] is CritiqueTimeseriesStats, (
        f"return-annotatie moet list[CritiqueTimeseriesStats] zijn, was: {return_hint}"
    )


# Test E: _refresh_mv() sessie binnen best_effort (patroon-3 invariant)
@pytest.mark.asyncio
async def test_refresh_mv_session_is_inside_best_effort() -> None:
    """_refresh_mv() opent de DB-sessie BINNEN de best_effort context manager (patroon-3)."""
    store = CritiqueStore()
    call_order: list[str] = []

    class MockBestEffort:
        def __init__(self, _label: str = "") -> None:
            pass

        async def __aenter__(self) -> "MockBestEffort":
            call_order.append("best_effort_enter")
            return self

        async def __aexit__(
            self,
            _exc_type: object,
            _exc_val: object,
            _exc_tb: object,
        ) -> bool:
            call_order.append("best_effort_exit")
            return False

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    def track_session(*_args: object, **_kwargs: object) -> MagicMock:
        call_order.append("session_open")
        return mock_session_ctx

    with (
        patch("src.core.utils.best_effort.best_effort", MockBestEffort),
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch("src.core.database.database.db_manager.get_session", side_effect=track_session),
    ):
        await store._refresh_mv()

    # session_open moet TUSSEN best_effort_enter en best_effort_exit voorkomen
    assert "best_effort_enter" in call_order, "_refresh_mv() gebruikte best_effort niet"
    assert "session_open" in call_order, "_refresh_mv() opende geen sessie"
    be_enter = call_order.index("best_effort_enter")
    session_open = call_order.index("session_open")
    be_exit = call_order.index("best_effort_exit")
    assert be_enter < session_open < be_exit, (
        f"Sessie niet binnen best_effort: volgorde={call_order}"
    )


# Test F: Refresh-guard cooldown
@pytest.mark.asyncio
async def test_refresh_guard_skips_refresh_within_cooldown() -> None:
    """store() roept _refresh_mv() NIET aan als _last_mv_refresh < cooldown geleden was."""
    from src.core.agents.critique_store import Critique

    store = CritiqueStore()
    # Stel _last_mv_refresh in op net nu -- ruim binnen de 5-min cooldown
    store._last_mv_refresh = datetime.now(timezone.utc)

    critique = Critique(
        critique_id="test-id",
        agent_name="TestAgent",
        task_id="task-1",
        tenant_id=1,
        score=0.9,
        issues=[],
        suggestions=[],
        mode="advisory",
    )

    refresh_called = False

    async def mock_refresh_mv() -> None:
        nonlocal refresh_called
        refresh_called = True

    with patch.object(store, "_refresh_mv", side_effect=mock_refresh_mv):
        with patch.object(store, "_persist_to_db", new_callable=AsyncMock):
            with patch.object(store, "_create_hitl_ticket", new_callable=AsyncMock):
                await store.store(critique)

    assert not refresh_called, (
        "_refresh_mv() werd aangeroepen binnen de cooldown -- guard werkt niet"
    )


# Test G: _persist_to_db() sessie binnen best_effort (patroon-3 invariant)
@pytest.mark.asyncio
async def test_persist_to_db_session_is_inside_best_effort() -> None:
    """_persist_to_db() opent de DB-sessie BINNEN de best_effort context manager (patroon-3)."""
    import sys
    from src.core.agents.critique_store import Critique

    store = CritiqueStore()
    call_order: list[str] = []

    class MockBestEffort:
        def __init__(self, _label: str = "") -> None:
            pass

        async def __aenter__(self) -> "MockBestEffort":
            call_order.append("best_effort_enter")
            return self

        async def __aexit__(self, _exc_type: object, _exc_val: object, _exc_tb: object) -> bool:
            call_order.append("best_effort_exit")
            return False

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    def track_session(*_args: object, **_kwargs: object) -> MagicMock:
        call_order.append("session_open")
        return mock_session_ctx

    critique = Critique(
        critique_id="test-persist-id",
        agent_name="TestAgent",
        task_id="task-persist",
        tenant_id=1,
        score=0.9,
        issues=[],
        suggestions=[],
        mode="advisory",
    )

    mock_critique_models = MagicMock()

    with (
        patch("src.core.utils.best_effort.best_effort", MockBestEffort),
        patch("src.core.database.database.db_manager.initialize", new_callable=AsyncMock),
        patch("src.core.database.database.db_manager.get_session", side_effect=track_session),
        patch.dict(sys.modules, {"src.core.models.critique_models": mock_critique_models}),
    ):
        await store._persist_to_db(critique)

    assert "best_effort_enter" in call_order, "_persist_to_db() gebruikte best_effort niet"
    assert "session_open" in call_order, "_persist_to_db() opende geen sessie"
    be_enter = call_order.index("best_effort_enter")
    session_open = call_order.index("session_open")
    be_exit = call_order.index("best_effort_exit")
    assert be_enter < session_open < be_exit, (
        f"Sessie niet binnen best_effort: volgorde={call_order}"
    )
