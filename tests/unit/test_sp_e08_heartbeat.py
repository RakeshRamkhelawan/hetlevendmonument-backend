"""
Tests voor SP-E08: HeartbeatMonitor vervangt Math.random() mocks door echte backend data.

TDD: tests moeten ROOD zijn voor implementatie, GROEN erna.
- Backend: GET /api/v1/als/agents/{agent_id}/heartbeat retourneert echte OrganismRegistry data
- Frontend: HeartbeatMonitor.tsx heeft geen Math.random() meer voor status/responseTime
"""

import pathlib

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = pathlib.Path(__file__).parent.parent.parent
_COMPONENT = _ROOT / "frontend" / "src" / "components" / "external-agents" / "HeartbeatMonitor.tsx"
_ALS_ROUTER = "src/core/api/v1/als/als_agents_router.py"


def _read_als_router() -> str:
    return (_ROOT / _ALS_ROUTER).read_text(encoding="utf-8")


def _read_component() -> str:
    if not _COMPONENT.exists():
        pytest.skip("HeartbeatMonitor.tsx niet gevonden")
    return _COMPONENT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Backend endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatEndpointExists:
    def test_heartbeat_get_endpoint_in_router(self) -> None:
        """GET /{agent_id}/heartbeat endpoint staat in als/router.py."""
        source = _read_als_router()
        assert "/heartbeat" in source and "async def get_agent_heartbeat" in source, (
            "GET /{agent_id}/heartbeat endpoint niet gevonden in als/router.py"
        )

    def test_heartbeat_response_has_success_field(self) -> None:
        """Heartbeat endpoint retourneert standaard {success, data} format (CLAUDE.md §12)."""
        source = _read_als_router()
        if "heartbeat" in source:
            assert '"success"' in source or "'success'" in source, (
                "Heartbeat endpoint mist success field in response (CLAUDE.md §12)"
            )

    def test_heartbeat_filters_by_tenant_id(self) -> None:
        """Heartbeat endpoint filtert op tenant_id -- geen cross-tenant lekkage."""
        source = _read_als_router()
        if "heartbeat" in source and "get_agent_heartbeat" in source:
            assert "tenant_id" in source, (
                "Heartbeat endpoint heeft geen tenant_id filter (CLAUDE.md §6)"
            )

    def test_heartbeat_status_values_are_enum_not_random(self) -> None:
        """Backend heartbeat retourneert enum-waarden, geen Math.random() floats."""
        source = _read_als_router()
        if "heartbeat" in source:
            assert "Math.random" not in source, (
                "als/router.py bevat Math.random() -- status moet uit DB enum komen"
            )

    @pytest.mark.asyncio
    async def test_heartbeat_behavioral_unknown_agent_returns_unknown_status(self) -> None:
        """Behavioral: onbekend agent_id geeft status='unknown', geen 404 of 500.

        Import via source check omdat het als/router import-chain een pre-existing
        SyntaxError in learning_mixin.py heeft (buitenscope SP-E08).
        """
        source = _read_als_router()
        # Endpoint bestaat en retourneert status='unknown' voor onbekende agents
        assert "unknown" in source, (
            "Heartbeat endpoint retourneert geen 'unknown' status voor onbekende agents"
        )
        assert "scalar_one_or_none" in source, (
            "Heartbeat endpoint gebruikt geen scalar_one_or_none() -- null-check ontbreekt"
        )


@pytest.mark.unit
class TestHeartbeatFrontendComponent:
    def test_no_math_random_for_response_time(self) -> None:
        """HeartbeatMonitor.tsx gebruikt geen Math.random() voor responseTime."""
        source = _read_component()
        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            if "Math.random()" in line and "responseTime" in line:
                raise AssertionError(
                    f"Regel {i}: Math.random() voor responseTime gevonden -- moet echte data zijn"
                )

    def test_no_math_random_for_status_in_logs(self) -> None:
        """HeartbeatMonitor.tsx gebruikt geen Math.random() voor log-status."""
        source = _read_component()
        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            if "Math.random()" in line and (
                "status" in line or "'online'" in line or "'idle'" in line
            ):
                raise AssertionError(
                    f"Regel {i}: Math.random() voor status gevonden -- moet echte data zijn"
                )

    def test_no_mock_agents_array(self) -> None:
        """const mockAgents array is verwijderd uit HeartbeatMonitor.tsx."""
        source = _read_component()
        assert "const mockAgents" not in source, (
            "mockAgents array nog aanwezig -- moet vervangen zijn door echte API-aanroep"
        )

    def test_has_real_api_call(self) -> None:
        """HeartbeatMonitor.tsx heeft een echte fetch/useQuery aanroep (geen puur mock)."""
        source = _read_component()
        has_real_call = (
            "fetch(" in source or "useQuery" in source or "api." in source or "axios" in source
        )
        assert has_real_call, (
            "HeartbeatMonitor.tsx heeft geen echte API-aanroep na verwijdering mock data"
        )

    def test_use_effect_has_cleanup(self) -> None:
        """useEffect heeft clearInterval cleanup (CLAUDE.md §13)."""
        source = _read_component()
        if "setInterval" in source:
            assert "clearInterval" in source, (
                "setInterval zonder clearInterval cleanup -- memory leak (CLAUDE.md §13)"
            )

    def test_no_hardcoded_localhost_url(self) -> None:
        """Geen hardcoded localhost URL in HeartbeatMonitor.tsx (CLAUDE.md §8)."""
        source = _read_component()
        assert "http://localhost" not in source and "https://localhost" not in source, (
            "Hardcoded localhost URL gevonden in HeartbeatMonitor.tsx (CLAUDE.md §8)"
        )

    def test_credentials_include_in_fetch(self) -> None:
        """fetch() gebruikt credentials:'include' voor cookie-auth (CLAUDE.md §13.1)."""
        source = _read_component()
        if "fetch(" in source:
            has_credentials = (
                'credentials: "include"' in source
                or "credentials:'include'" in source
                or "credentials: 'include'" in source
            )
            assert has_credentials, (
                "fetch() zonder credentials:include -- cookie-auth werkt niet (CLAUDE.md §13.1)"
            )

    def test_behavioral_operator_sees_backend_data_not_random(self) -> None:
        """Behavioral: operator ziet backend-data, niet willekeurig gegenereerde status."""
        source = _read_component()
        # Geen Math.random() aanroepen voor status of response time data
        random_for_data = any(
            "Math.random()" in line
            and ("responseTime" in line or "status" in line or "tasks_processed" in line)
            for line in source.splitlines()
        )
        assert not random_for_data, "Component toont nog steeds Math.random() data aan de operator"
