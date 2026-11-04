import pytest
from unittest.mock import MagicMock

from src.core.api.v1.tool_broker.crud_router import (
    router,
    register_tool,
    list_tools_filtered,
)
from src.core.api.v1.tool_broker_shared import ToolCreate, available_tools
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/api/v1/tools/" in paths


@pytest.mark.asyncio
async def test_register_tool_success() -> None:
    user = MagicMock(spec=UserResponse)
    user.tenant_id = 77

    tool_in = ToolCreate(
        name="custom_scanner",
        category="security",
        capabilities=["scanning"],
        description="A security scanner",
    )

    try:
        res = await register_tool(tool_data=tool_in, current_user=user, _=1)
        assert res.name == "custom_scanner"
        assert res.category == "security"
        assert res.tenant_id == 77
        assert (77, "custom_scanner") in available_tools
    finally:
        available_tools.pop((77, "custom_scanner"), None)


@pytest.mark.asyncio
async def test_list_tools_filtered() -> None:
    user = MagicMock(spec=UserResponse)
    user.tenant_id = 88

    tool_in = ToolCreate(
        name="tenant88_tool",
        category="analytics",
        capabilities=["reporting", "charting"],
        description="Analytics tool",
    )

    try:
        await register_tool(tool_data=tool_in, current_user=user, _=1)

        # Matched list
        res = await list_tools_filtered(current_user=user)
        assert len(res) == 1
        assert res[0].name == "tenant88_tool"

        # Filter by category matching
        res_cat = await list_tools_filtered(category="analytics", current_user=user)
        assert len(res_cat) == 1

        # Filter by category non-matching
        res_cat_none = await list_tools_filtered(category="dev", current_user=user)
        assert len(res_cat_none) == 0

        # Filter by capability
        res_cap = await list_tools_filtered(capability="charting", current_user=user)
        assert len(res_cap) == 1

        res_cap_none = await list_tools_filtered(capability="unknown_cap", current_user=user)
        assert len(res_cap_none) == 0

        # Tenant isolation
        other_user = MagicMock(spec=UserResponse)
        other_user.tenant_id = 999
        res_other = await list_tools_filtered(current_user=other_user)
        assert len(res_other) == 0
    finally:
        available_tools.pop((88, "tenant88_tool"), None)
