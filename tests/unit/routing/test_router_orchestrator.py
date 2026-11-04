from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.routing.router_orchestrator import GunaRouter, RouterRequest, RouterResponse
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_gunarouter_fallback_to_layer3():
    # Mock Layer 1 to return None and Layer 3 to return a result
    with (
        patch("src.core.routing.router_orchestrator.KeywordRouter") as mock_l1_cls,
        patch("src.core.routing.router_orchestrator.SemanticRouter") as mock_l3_cls,
    ):
        mock_l1 = mock_l1_cls.return_value
        mock_l1.route.return_value = None

        mock_l3 = mock_l3_cls.return_value
        mock_l3.route = AsyncMock(return_value="finance_supervisor")

        router = GunaRouter()
        task = TaskData(title="T", description="D")
        request = RouterRequest(task=task, tenant_id=1)

        response = await router.route(request)
        assert response.target_supervisor == "finance_supervisor"
        assert response.layer_used == "layer3"


@pytest.mark.asyncio
async def test_gunarouter_ultimate_fallback_to_cva():
    with (
        patch("src.core.routing.router_orchestrator.KeywordRouter") as mock_l1_cls,
        patch("src.core.routing.router_orchestrator.SemanticRouter") as mock_l3_cls,
        patch.object(GunaRouter, "_check_adaptation_rules", new=AsyncMock(return_value=None)),
    ):
        mock_l1 = mock_l1_cls.return_value
        mock_l1.route.return_value = None

        mock_l3 = mock_l3_cls.return_value
        mock_l3.route = AsyncMock(return_value=None)

        router = GunaRouter()
        task = TaskData(title="T", description="D")
        request = RouterRequest(task=task, tenant_id=1)

        response = await router.route(request)
        assert response.target_supervisor == "cva_supervisor"
        assert response.layer_used == "layer4"
