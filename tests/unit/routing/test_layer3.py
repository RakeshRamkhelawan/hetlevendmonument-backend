from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.routing.layer3_semantic import SemanticRouter
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_layer3_semantic_match():
    # 1. Mock DB Result
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = MagicMock(return_value="finance_supervisor")

    # 2. Mock LLMService and DB Session
    with (
        patch("src.core.routing.layer3_semantic.LLMService") as mock_llm_cls,
        patch("src.core.database.database.db_manager.get_session") as mock_session,
    ):
        # Setup LLM mock
        mock_llm = mock_llm_cls.return_value
        mock_llm.get_embeddings = AsyncMock(return_value=[0.1] * 1536)
        mock_llm_cls.for_tenant = AsyncMock(return_value=mock_llm)

        # Setup DB mock
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_session.return_value.__aenter__.return_value = mock_db

        router = SemanticRouter()
        task = TaskData(
            title="Money issue", description="Where is my cash?", metadata={"tenant_id": 1}
        )

        target = await router.route(task)
        assert target == "finance_supervisor"


@pytest.mark.asyncio
async def test_layer3_no_match():
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)

    with (
        patch("src.core.routing.layer3_semantic.LLMService") as mock_llm_cls,
        patch("src.core.database.database.db_manager.get_session") as mock_session,
    ):
        mock_llm = mock_llm_cls.return_value
        mock_llm.get_embeddings = AsyncMock(return_value=[0.1] * 1536)
        mock_llm_cls.for_tenant = AsyncMock(return_value=mock_llm)

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_session.return_value.__aenter__.return_value = mock_db

        router = SemanticRouter()
        task = TaskData(title="???", description="Blabla", metadata={"tenant_id": 1})

        target = await router.route(task)
        assert target is None
