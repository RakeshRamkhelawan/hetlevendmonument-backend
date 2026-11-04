from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.activepieces.schemas import PieceRead
from src.core.activepieces.service import ActivePiecesService


@pytest.mark.asyncio
async def test_health_check_success():
    mock_client = AsyncMock()
    mock_client.health_check.return_value = {"api_reachable": True}

    service = ActivePiecesService(client=mock_client)
    result = await service.check_health()

    assert result is True
    mock_client.health_check.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_failure():
    mock_client = AsyncMock()
    mock_client.health_check.side_effect = Exception("API Error")

    service = ActivePiecesService(client=mock_client)
    result = await service.check_health()

    assert result is False


@pytest.mark.asyncio
async def test_sync_pieces():
    mock_client = AsyncMock()
    # Use alias for Pydantic v2 compatibility
    mock_client.list_pieces.return_value = [
        PieceRead(name="gmail", displayName="Gmail", version="1.0.0", actions={}, triggers={})
    ]

    service = ActivePiecesService(client=mock_client)
    count = await service.sync_pieces()

    assert count == 1
    # Verify repository calls if I had mocked it
    # mock_repository.upsert.assert_called()
