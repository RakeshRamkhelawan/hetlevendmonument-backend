"""
Unit tests for OrchestratorClient module.

Tests cover:
- Dashboard data fetching
- Performance metrics retrieval
- Task management execution
- System control operations
- Health check

Usage:
    pytest tests/unit/test_orchestrator_client.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.core.agents.ultimate_cva.models import IntentType, ParsedCommand
from src.core.agents.ultimate_cva.orchestrator_client import OrchestratorClient

# =============================================================================
# HELPERS
# =============================================================================


def _mock_http_response(status_code: int = 200, json_data=None):
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


def _make_client_cm(mock_client: AsyncMock):
    """Wrap mock_client so it works as `async with await _get_client()`."""
    # _get_client is async def → returns coroutine whose result is used as `async with`
    # So we need: await _get_client() → object that supports __aenter__/__aexit__
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def orchestrator_client():
    """OrchestratorClient with test API URL."""
    return OrchestratorClient("http://test-api:8000")


@pytest.fixture
def parsed_command():
    """Sample ParsedCommand for testing."""
    return ParsedCommand(
        intent=IntentType.TASK_MANAGEMENT,
        original_text="Create a new task for optimization",
        confidence=0.9,
        parameters={},
    )


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset circuit breaker state between tests."""
    import src.core.agents.ultimate_cva.orchestrator_client as oc_module

    cb = oc_module.get_orchestrator_cb()
    # Reset failure count so circuit stays closed
    cb._failure_count = 0
    cb._state = "closed"  # type: ignore[attr-defined]
    yield
    cb._failure_count = 0
    cb._state = "closed"  # type: ignore[attr-defined]


# =============================================================================
# TEST DASHBOARD DATA
# =============================================================================


@pytest.mark.asyncio
async def test_get_dashboard_data_success(orchestrator_client):
    """Test successful dashboard data retrieval."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_http_response(200, {"cpu": 45, "memory": 60}))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.get_dashboard_data()

    assert result["cpu"] == 45


@pytest.mark.asyncio
async def test_get_dashboard_data_failure(orchestrator_client):
    """Test dashboard data retrieval on HTTP error."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_http_response(500))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.get_dashboard_data()

    assert "error" in result
    assert result["status"] == "connection_failed"


@pytest.mark.asyncio
async def test_get_dashboard_data_connection_error(orchestrator_client):
    """Test dashboard data on connection failure."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=ConnectionError("Connection refused"))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.get_dashboard_data()

    assert "error" in result
    assert result["status"] == "connection_failed"


# =============================================================================
# TEST AGENTS DATA
# =============================================================================


@pytest.mark.asyncio
async def test_get_agents_data(orchestrator_client):
    """Test agents data retrieval."""
    result = await orchestrator_client.get_agents_data()

    assert "total_agents" in result
    assert "agents" in result
    assert isinstance(result["agents"], list)


# =============================================================================
# TEST PERFORMANCE METRICS
# =============================================================================


@pytest.mark.asyncio
async def test_get_performance_metrics_success(orchestrator_client):
    """Test successful performance metrics retrieval."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_http_response(200, {"latency_ms": 50}))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.get_performance_metrics()

    assert result["latency_ms"] == 50


@pytest.mark.asyncio
async def test_get_performance_metrics_failure(orchestrator_client):
    """Test performance metrics on failure."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_http_response(503))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.get_performance_metrics()

    assert "error" in result


# =============================================================================
# TEST TASK MANAGEMENT
# =============================================================================


@pytest.mark.asyncio
async def test_execute_task_management_success(orchestrator_client, parsed_command):
    """Test successful task management execution."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_http_response(200, {"task_id": "123"}))
    _make_client_cm(mock_client)

    context = {"priority": "high"}
    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.execute_task_management(
            parsed_command, "LLM analysis text", context
        )

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_execute_task_management_includes_masterprompt(orchestrator_client, parsed_command):
    """Test that task management includes CEO masterprompt."""
    captured_payload = {}
    mock_client = AsyncMock()

    async def capture_post(url, json=None, **kwargs):
        captured_payload.update(json or {})
        return _mock_http_response(200, {})

    mock_client.post = capture_post
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        await orchestrator_client.execute_task_management(parsed_command, "analysis", {})

    assert "masterprompt" in captured_payload


# =============================================================================
# TEST SYSTEM CONTROL
# =============================================================================


@pytest.mark.asyncio
async def test_execute_system_control_success(orchestrator_client, parsed_command):
    """Test successful system control execution."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_http_response(200, {"action": "completed"}))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.execute_system_control(
            parsed_command, "Safety analysis passed", {}
        )

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_execute_system_control_includes_approval_flag(orchestrator_client, parsed_command):
    """Test that system control requires approval."""
    captured_payload = {}
    mock_client = AsyncMock()

    async def capture_post(url, json=None, **kwargs):
        captured_payload.update(json or {})
        return _mock_http_response(200, {})

    mock_client.post = capture_post
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        await orchestrator_client.execute_system_control(parsed_command, "safe", {})

    assert captured_payload.get("approval_required") is True


# =============================================================================
# TEST HEALTH CHECK
# =============================================================================


@pytest.mark.asyncio
async def test_check_health_success(orchestrator_client):
    """Test health check success."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_http_response(200))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.check_health()

    assert result is True


@pytest.mark.asyncio
async def test_check_health_failure(orchestrator_client):
    """Test health check failure."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=ConnectionError("Refused"))
    _make_client_cm(mock_client)

    with patch.object(orchestrator_client, "_get_client", return_value=mock_client):
        result = await orchestrator_client.check_health()

    assert result is False
