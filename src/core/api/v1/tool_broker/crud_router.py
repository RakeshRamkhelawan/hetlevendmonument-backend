# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Tool Broker CRUD endpoints: register + list tools."""

import uuid
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends

from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.shared.production_logging import SafeLogger

from src.core.api.v1.tool_broker_shared import (
    ToolCreate,
    ToolResponse,
    available_tools,
    tool_sleutel,
)

logger = SafeLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["Tool Broker"])


@router.post("/", response_model=ToolResponse, status_code=201)
async def register_tool(
    tool_data: ToolCreate,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> ToolResponse:
    """
    Register a new tool.

    Requires: OAuth2Scope.AGENTS_WRITE
    """
    # Sleutel `(tenant_id, naam)`: een klant overschrijft alleen zijn EIGEN tool met die naam, nooit die van een
    # andere klant of een meegeleverde tool (brief 2026-10-24).
    tool_key = tool_sleutel(current_user.tenant_id, tool_data.name)

    if tool_key in available_tools:
        logger.info("Overwriting/Updating tool: %s", tool_data.name)
        tool_id = available_tools[tool_key].get("id", str(uuid.uuid4()))
    else:
        tool_id = str(uuid.uuid4())

    tool_dict: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "id": tool_id,
        "name": tool_data.name,
        "description": tool_data.description,
        "category": tool_data.category,
        "capabilities": tool_data.capabilities,
        "parameters_schema": tool_data.parameters_schema,
        "tenant_id": current_user.tenant_id,
        "endpoint": tool_data.endpoint,
        "available": True,
        "version": "1.0.0",
        "execution_count": 0,
        "last_used": None,
    }
    # TODO(SP-VOLGENDE): verplaats naar SP-B02 Tool/ToolVersion ORM (service-laag, niet in router)
    available_tools[tool_key] = tool_dict

    return ToolResponse(**available_tools[tool_key])


@router.get("/", response_model=list[ToolResponse])
async def list_tools_filtered(
    category: str | None = None,
    capability: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
) -> list[ToolResponse]:
    """List available tools for the authenticated tenant, optionally filtered."""
    tenant_id = current_user.tenant_id
    results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for _key, tool in available_tools.items():
        # C-2 fix: tenant isolation -- only return tools belonging to this tenant
        if tool.get("tenant_id") != tenant_id:
            continue
        if category and tool.get("category") != category:
            continue
        if capability and capability not in tool.get("capabilities", []):
            continue

        results.append(
            ToolResponse(
                id=cast(str, tool.get("id", str(uuid.uuid4()))),
                name=cast(str, tool["name"]),
                description=cast(Optional[str], tool.get("description")),
                category=cast(str, tool.get("category", "unknown")),
                capabilities=cast(list[str], tool.get("capabilities", [])),
                parameters_schema=cast(dict[str, Any], tool.get("parameters_schema", {})),
                tenant_id=cast(Optional[int], tool.get("tenant_id")),
                endpoint=cast(Optional[str], tool.get("endpoint")),
                available=cast(bool, tool["available"]),
                execution_count=cast(int, tool["execution_count"]),
                last_used=cast(Optional[str], tool["last_used"]),
            )
        )

    return results
