"""WebSocket dependency helpers for Focus Builder.

This module restores the import path used by the Focus Builder V1 router.
It keeps the websocket-specific concerns isolated for DI and testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import verify_token
from src.domains.flows.models import Flow


@dataclass
class WSUser:
    """Minimal authenticated websocket user context."""

    id: int
    tenant_id: int


class WebSocketAuthHandler:
    """JWT validator for Focus Builder websocket endpoints."""

    async def validate_token(self, token: str) -> WSUser:
        payload = verify_token(token)
        if payload is None:
            raise ValueError("Invalid token payload")

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        if user_id is None or tenant_id is None:
            raise ValueError("Missing websocket auth claims")

        from src.core.api.dependencies import token_mag_op_een_websocket

        # Geen portaaltoken, account ingeschakeld, tenantclaim een echt geheel getal (een `true`
        # of `1.9` werd door `int(...)` tenant 1; nu geweigerd).
        if not await token_mag_op_een_websocket(payload):
            raise ValueError("Token not allowed on a websocket")

        return WSUser(id=int(user_id), tenant_id=int(tenant_id))


class WebSocketManager:
    """Tracks flow-scoped websocket connections."""

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, flow_id: int) -> None:
        await websocket.accept()
        self._connections.setdefault(flow_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, flow_id: int) -> None:
        connections = self._connections.get(flow_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._connections.pop(flow_id, None)


class FlowVerifier:
    """Verifies that a flow exists for the tenant."""

    async def flow_exists(self, flow_id: int, db: AsyncSession, tenant_id: int) -> bool:
        result = await db.execute(
            select(Flow.id).where(Flow.id == flow_id, Flow.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none() is not None


# Lazy singletons -- not instantiated at import time
_WS_MANAGER: WebSocketManager | None = None
_WS_AUTH: WebSocketAuthHandler | None = None
_FLOW_VERIFIER: FlowVerifier | None = None


def get_ws_manager() -> WebSocketManager:
    global _WS_MANAGER
    if _WS_MANAGER is None:
        _WS_MANAGER = WebSocketManager()
    return _WS_MANAGER


def get_ws_auth() -> WebSocketAuthHandler:
    global _WS_AUTH
    if _WS_AUTH is None:
        _WS_AUTH = WebSocketAuthHandler()
    return _WS_AUTH


def get_flow_verifier() -> FlowVerifier:
    global _FLOW_VERIFIER
    if _FLOW_VERIFIER is None:
        _FLOW_VERIFIER = FlowVerifier()
    return _FLOW_VERIFIER


def __getattr__(name: str) -> Any:  # TODO(TYPE): replace with concrete type
    """Backwards compatibility for module-level singleton access."""
    if name == "_WS_MANAGER":
        return get_ws_manager()
    if name == "_WS_AUTH":
        return get_ws_auth()
    if name == "_FLOW_VERIFIER":
        return get_flow_verifier()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
