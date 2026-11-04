import pytest

from src.core.api.v1.tools.integrations_router import (
    integrations_router,
    list_integration_catalog,
    search_integrations,
)


def test_routes_registered() -> None:
    paths = [r.path for r in integrations_router.routes]
    assert "/integrations/catalog" in paths
    assert "/integrations/search" in paths


@pytest.mark.asyncio
async def test_list_integration_catalog() -> None:
    res = await list_integration_catalog(limit=25, offset=5, _authenticated={"user_id": 1})
    assert res["success"] is True
    assert res["data"]["limit"] == 25
    assert res["data"]["offset"] == 5
    assert isinstance(res["data"]["items"], list)


@pytest.mark.asyncio
async def test_search_integrations() -> None:
    res = await search_integrations(query="slack", limit=10, offset=0, _authenticated={"user_id": 1})
    assert res["success"] is True
    assert res["data"]["query"] == "slack"
    assert res["data"]["limit"] == 10
