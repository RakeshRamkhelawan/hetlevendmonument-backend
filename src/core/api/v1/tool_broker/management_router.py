# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Tool Broker management endpoints: list/status/enable/disable."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.shared.production_logging import SafeLogger
from src.core.tool_broker.resilience import get_circuit_breaker_registry

from src.core.api.v1.tool_broker.dependencies import get_db, is_platformbeheerder
from src.core.api.v1.tool_broker_shared import (
    ToolListResponse,
    ToolRegel,
    ToolStatusResponse,
    available_tools,
    gebruik_van,
    zoek_tool,
)

logger = SafeLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["Tool Broker"])


async def _eis_platformbeheerder_voor_meegeleverde_tool(
    tool_info: ToolRegel,
    current_user: UserResponse,
    db: AsyncSession,
) -> None:
    """Een meegeleverde tool (`tenant_id` `None`) staat voor ELKE klant aan of uit: schakelen is dus een platformzaak.

    Gemeten 2026-10-27: een klantbeheerder (rol `admin`, `*:*`, geen platformrol) haalde `admin:*` via de
    databasefallback en kon `serena` voor alle klanten uitzetten. Fail-secure: wie geen platformbeheerder is krijgt
    403 en er verandert niets. Per klant aan- of uitzetten komt later via het inrichtscherm van de koppelingen.
    """
    if tool_info.get("tenant_id") is not None:
        return
    if not await is_platformbeheerder(current_user.id, current_user.tenant_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alleen een platformbeheerder kan een meegeleverde tool aan- of uitzetten.",
        )


@router.get("/list", response_model=ToolListResponse)
async def list_tools_all(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> ToolListResponse:
    """
    List all available tools and their status.

    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info("User %s listing available tools", current_user.id)

        registry = get_circuit_breaker_registry()
        client_map = {
            "serena": "serena_client",
            "sequential_thinking": "sequential_thinking_client",
        }

        tools: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for (tool_tenant, tool_name), tool_info in available_tools.items():
            # Eigen tools en meegeleverde tools; nooit de tool van een andere klant (brief 2026-10-24).
            if tool_tenant not in (None, current_user.tenant_id):
                continue
            circuit_status = "closed"
            client_name = client_map.get(tool_name) if tool_tenant is None else None
            if client_name:
                breaker = registry.get(client_name)
                if breaker:
                    circuit_status = breaker.state.value

            gebruik = gebruik_van(current_user.tenant_id, tool_name, tool_info)
            tools.append(
                ToolStatusResponse(
                    tool_name=tool_name,
                    available=tool_info["available"],
                    version=tool_info["version"],
                    last_used=gebruik.get("last_used"),
                    execution_count=gebruik["execution_count"],
                    circuit_status=circuit_status,
                    success_rate=1.0,
                    avg_latency_ms=0.0,
                )
            )

        return ToolListResponse(tools=tools, total_count=len(tools))

    except Exception as e:
        logger.error("Failed to list tools: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tools",
        )


@router.get("/{tool_name}/status", response_model=ToolStatusResponse)
async def get_tool_status(
    tool_name: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> ToolStatusResponse:
    """
    Get status of a specific tool.

    Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        tool_info = zoek_tool(current_user.tenant_id, tool_name)
        if tool_info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tool '{}' not found".format(tool_name),
            )

        logger.info("User %s checking status of tool: %s", current_user.id, tool_name)

        gebruik = gebruik_van(current_user.tenant_id, tool_name, tool_info)
        return ToolStatusResponse(
            tool_name=tool_name,
            available=tool_info["available"],
            version=tool_info["version"],
            last_used=gebruik.get("last_used"),
            execution_count=gebruik["execution_count"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get tool status: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tool status",
        )


@router.post("/{tool_name}/enable", response_model=dict[str, str])
async def enable_tool(
    tool_name: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Enable a tool.

    Requires: OAuth2Scope.ADMIN_ALL. Een MEEGELEVERDE tool (voor elke klant zichtbaar) alleen voor een
    platformbeheerder; een klantbeheerder schakelt alleen zijn eigen tool.
    """
    try:
        tool_info = zoek_tool(current_user.tenant_id, tool_name)
        if tool_info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tool '{}' not found".format(tool_name),
            )

        await _eis_platformbeheerder_voor_meegeleverde_tool(tool_info, current_user, db)
        logger.info("User %s enabling tool: %s", current_user.id, tool_name)
        tool_info["available"] = True
        return {"message": "Tool '{}' has been enabled".format(tool_name)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to enable tool: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable tool",
        )


@router.post("/{tool_name}/disable", response_model=dict[str, str])
async def disable_tool(
    tool_name: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Disable a tool.

    Requires: OAuth2Scope.ADMIN_ALL. Een MEEGELEVERDE tool (voor elke klant zichtbaar) alleen voor een
    platformbeheerder; een klantbeheerder schakelt alleen zijn eigen tool.
    """
    try:
        tool_info = zoek_tool(current_user.tenant_id, tool_name)
        if tool_info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tool '{}' not found".format(tool_name),
            )

        await _eis_platformbeheerder_voor_meegeleverde_tool(tool_info, current_user, db)
        logger.info("User %s disabling tool: %s", current_user.id, tool_name)
        tool_info["available"] = False
        return {"message": "Tool '{}' has been disabled".format(tool_name)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to disable tool: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable tool",
        )
