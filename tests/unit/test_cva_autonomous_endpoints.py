from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.fixture
def mock_current_user():
    user = Mock()
    user.id = 123
    return user


def _make_mock_system(status="healthy"):
    sys = AsyncMock()
    sys.get_system_status.return_value = {"status": status}
    return sys


class TestCvaAutonomousHealth:
    @pytest.mark.asyncio
    async def test_health_reports_healthy_when_all_systems_up(self, mock_current_user):
        from src.core.api.v1.autonomous.agents_router import autonomous_health_check

        with (
            patch(
                "src.core.api.v1.autonomous.agents_router.get_agent_factory",
                return_value=_make_mock_system("healthy"),
            ),
            patch(
                "src.core.api.v1.autonomous.agents_router.get_self_healing_system",
                return_value=_make_mock_system("healthy"),
            ),
            patch(
                "src.core.api.v1.autonomous.agents_router.get_code_generator",
                return_value=_make_mock_system("healthy"),
            ),
            patch(
                "src.core.api.v1.autonomous.agents_router.get_emergent_intelligence",
                return_value=_make_mock_system("healthy"),
            ),
        ):
            response = await autonomous_health_check(
                current_user=mock_current_user,
                _=1,
            )

        assert response["status"] == "healthy"
        assert "components" in response

    @pytest.mark.asyncio
    async def test_health_returns_degraded_when_factory_missing(self, mock_current_user):
        from src.core.api.v1.autonomous.agents_router import autonomous_health_check

        with (
            patch(
                "src.core.api.v1.autonomous.agents_router.get_agent_factory",
                return_value=None,
            ),
            patch(
                "src.core.api.v1.autonomous.agents_router.get_self_healing_system",
                return_value=_make_mock_system("healthy"),
            ),
            patch(
                "src.core.api.v1.autonomous.agents_router.get_code_generator",
                return_value=_make_mock_system("healthy"),
            ),
            patch(
                "src.core.api.v1.autonomous.agents_router.get_emergent_intelligence",
                return_value=_make_mock_system("healthy"),
            ),
        ):
            response = await autonomous_health_check(
                current_user=mock_current_user,
                _=1,
            )

        assert response["status"] == "degraded"
