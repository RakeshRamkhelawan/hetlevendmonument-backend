"""CatalogSyncer tegen de echte vorm van GET /api/v1/pieces.

Gemeten 2026-10-06 op ActivePieces 0.81.4 (lokaal): de lijst geeft per piece
`actions` en `triggers` als AANTAL (int), niet als dict. `.keys()` daarop gaf
een AttributeError en daarmee viel de syncer altijd terug op de seed-lijst.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.activepieces.catalog_syncer import CatalogSyncer

LIST_RESPONSE = [
    {"name": "@activepieces/piece-slack", "displayName": "Slack", "actions": 12, "triggers": 3},
    {"name": "@activepieces/piece-gmail", "displayName": "Gmail", "actions": 4, "triggers": 2},
]


@pytest.mark.asyncio
async def test_should_use_live_pieces_when_list_gives_counts(tmp_path: Path) -> None:
    response = MagicMock()
    response.json.return_value = LIST_RESPONSE
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client

    with patch("src.core.activepieces.catalog_syncer.httpx.AsyncClient", return_value=client):
        pieces = await CatalogSyncer(catalog_path=str(tmp_path / "c.json")).sync_all()

    assert [p["name"] for p in pieces] == ["@activepieces/piece-slack", "@activepieces/piece-gmail"]
