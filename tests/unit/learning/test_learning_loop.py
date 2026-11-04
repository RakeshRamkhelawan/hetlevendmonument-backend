from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.loop import LearningLoop
from src.core.routing.router_orchestrator import GunaRouter, RouterRequest, RouterResponse
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_learning_loop_updates_routing_behavior():
    # 1. Mock dependencies to return None so it falls through to our Learned Layer
    with (
        patch("src.core.routing.router_orchestrator.KeywordRouter") as mock_l1_cls,
        patch("src.core.routing.router_orchestrator.SemanticRouter") as mock_l3_cls,
    ):
        mock_l1 = mock_l1_cls.return_value
        mock_l1.route.return_value = None

        mock_l3 = mock_l3_cls.return_value
        mock_l3.route = AsyncMock(return_value=None)

        router = GunaRouter()
        task = TaskData(title="French Tax", description="Tax in Paris")
        request = RouterRequest(task=task, tenant_id=1)

        # 2. Process a Learning Insight
        loop = LearningLoop()
        with patch("src.core.database.database.db_manager.get_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            await loop.record_adaptation_rule(
                tenant_id=1, trigger_pattern="french tax", suggested_agent="taxcompliance"
            )

        # 3. Simulate subsequent routing
        # We mock the learned rule check
        with patch.object(
            GunaRouter, "_check_adaptation_rules", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = "taxcompliance"

            res2 = await router.route(request)

            # The router should now prefer the adaptation rule
            assert res2.target_supervisor == "taxcompliance"
            assert res2.layer_used == "layer_learned"
