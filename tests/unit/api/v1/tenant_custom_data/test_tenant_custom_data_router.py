"""Unit tests for tenant custom data router (src/core/api/v1/tenant_custom_data/router.py).

Covers all 6 endpoints:
- GET  /{namespace}
- GET  /{namespace}/{key}
- PUT  /{namespace}/{key}
- DELETE /{namespace}/{key}
- DELETE /{namespace}
- GET  /
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.api.v1.tenant_custom_data.router import (
    CustomDataValue,
    delete_namespace,
    delete_value,
    get_value,
    list_namespace,
    list_namespaces,
    router,
    set_value,
)


def _mock_user(tenant_id: int = 42, user_id: str = "user-1") -> MagicMock:
    user = MagicMock()
    user.tenant_id = tenant_id
    user.id = user_id
    return user


def test_routes_registered() -> None:
    from fastapi.routing import APIRoute

    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/api/v1/tenant-custom-data/{namespace}" in paths
    assert "/api/v1/tenant-custom-data/{namespace}/{key}" in paths
    assert "/api/v1/tenant-custom-data/" in paths


@pytest.mark.asyncio
async def test_unauthenticated_requests_return_401() -> None:
    service = AsyncMock()

    with pytest.raises(HTTPException) as exc_list_ns:
        await list_namespace(namespace="theme", current_user=None, service=service)
    assert exc_list_ns.value.status_code == 401

    with pytest.raises(HTTPException) as exc_get:
        await get_value(namespace="theme", key="color", current_user=None, service=service)
    assert exc_get.value.status_code == 401

    with pytest.raises(HTTPException) as exc_set:
        await set_value(
            body=CustomDataValue(value="dark"),
            namespace="theme",
            key="color",
            current_user=None,
            service=service,
        )
    assert exc_set.value.status_code == 401

    with pytest.raises(HTTPException) as exc_del_val:
        await delete_value(namespace="theme", key="color", current_user=None, service=service)
    assert exc_del_val.value.status_code == 401

    with pytest.raises(HTTPException) as exc_del_ns:
        await delete_namespace(namespace="theme", current_user=None, service=service)
    assert exc_del_ns.value.status_code == 401

    with pytest.raises(HTTPException) as exc_list_all:
        await list_namespaces(current_user=None, service=service)
    assert exc_list_all.value.status_code == 401


@pytest.mark.asyncio
async def test_list_namespace_enforces_tenant_isolation() -> None:
    service = AsyncMock()
    service.get_namespace.return_value = {"primary_color": "#000", "font": "inter"}
    user = _mock_user(tenant_id=77)

    items = await list_namespace(namespace="settings", current_user=user, service=service)
    service.get_namespace.assert_awaited_once_with(77, "settings")
    assert len(items) == 2
    assert {i.key for i in items} == {"primary_color", "font"}


@pytest.mark.asyncio
async def test_get_value_success_and_not_found() -> None:
    service = AsyncMock()
    user = _mock_user(tenant_id=77)

    service.get_value.return_value = {"enabled": True}
    res = await get_value(namespace="ui", key="darkmode", current_user=user, service=service)
    service.get_value.assert_awaited_once_with(77, "ui", "darkmode")
    assert res.namespace == "ui"
    assert res.key == "darkmode"
    assert res.value == {"enabled": True}

    service.get_value.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await get_value(namespace="ui", key="missing", current_user=user, service=service)
    assert exc_info.value.status_code == 404
    assert "Key not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_set_value_enforces_tenant_isolation() -> None:
    service = AsyncMock()
    user = _mock_user(tenant_id=88)

    body = CustomDataValue(value=[1, 2, 3])
    res = await set_value(body=body, namespace="config", key="numbers", current_user=user, service=service)
    service.set_value.assert_awaited_once_with(88, "config", "numbers", [1, 2, 3])
    assert res.namespace == "config"
    assert res.key == "numbers"
    assert res.value == [1, 2, 3]


@pytest.mark.asyncio
async def test_delete_value_and_namespace_enforce_tenant_isolation() -> None:
    service = AsyncMock()
    user = _mock_user(tenant_id=99)

    await delete_value(namespace="config", key="old_key", current_user=user, service=service)
    service.delete_value.assert_awaited_once_with(99, "config", "old_key")

    await delete_namespace(namespace="config", current_user=user, service=service)
    service.delete_namespace.assert_awaited_once_with(99, "config")


@pytest.mark.asyncio
async def test_list_namespaces_enforces_tenant_isolation() -> None:
    service = AsyncMock()
    service.list_namespaces.return_value = ["theme", "crm", "auth"]
    user = _mock_user(tenant_id=12)

    res = await list_namespaces(current_user=user, service=service)
    service.list_namespaces.assert_awaited_once_with(12)
    assert res.namespaces == ["theme", "crm", "auth"]
