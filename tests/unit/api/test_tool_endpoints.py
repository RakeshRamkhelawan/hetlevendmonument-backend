import pytest
from unittest.mock import patch
from fastapi import Response

from src.core.api.tool_endpoints import router, get_tool_catalog, search_tools


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/integrations/catalog" in paths
    assert "/integrations/search" in paths


@pytest.mark.asyncio
async def test_get_tool_catalog() -> None:
    resp = Response()
    with patch("src.core.api.tool_endpoints.catalog_syncer.load_catalog", return_value=[{"name": "slack"}]):
        res = await get_tool_catalog(response=resp)
        assert len(res) == 1
        assert res[0]["name"] == "slack"
        assert resp.headers.get("Deprecation") == "true"


@pytest.mark.asyncio
async def test_search_tools() -> None:
    resp = Response()
    res = await search_tools(q="email", response=resp)
    assert res == []
    assert resp.headers.get("Deprecation") == "true"
