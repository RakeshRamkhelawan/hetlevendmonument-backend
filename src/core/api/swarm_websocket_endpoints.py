# orphan:exempt reason: actief gebruikt door tests/code; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
ACP Protocol: Swarm WebSocket Endpoints

Real-time streaming endpoints for multi-agent swarm collaboration.
"""
# orphan:exempt -- legacy shim, pre-migration flat endpoint

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from src.core.auth.api_deps import UserResponse, get_current_user_dependency, WebSocketAuthenticator
from src.core.services.swarm_stream_service import (
    SwarmEvent,
    SwarmStreamService,
    create_swarm_service,
)

SWARM_EXECUTION_TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/swarm", tags=["swarm"])


# ============================================================================
# Request/Response Models
# ============================================================================


class StartSwarmRequest(BaseModel):
    """Request to start a swarm session."""

    objective: str
    auto_spawn: bool = True


class FeedbackRequest(BaseModel):
    """Feedback submission."""

    feedback_id: str
    response: str


# ============================================================================
# WebSocket Manager
# ============================================================================


class SwarmConnectionManager:
    """Manages WebSocket connections for swarm streaming."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.services: dict[str, SwarmStreamService] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Connect a client to a swarm session."""
        # The endpoint authenticates first and authenticate() already accepts;
        # a second accept raises in Starlette.
        if websocket.client_state == WebSocketState.CONNECTING:
            await websocket.accept()

        if session_id not in self.active_connections:
            self.active_connections[session_id] = []

        self.active_connections[session_id].append(websocket)
        logger.info(f"Client connected to swarm session: {session_id}")

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Disconnect a client from a swarm session."""
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)

            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

        logger.info(f"Client disconnected from swarm session: {session_id}")

    async def broadcast(self, session_id: str, event: SwarmEvent) -> None:
        """Broadcast event to all clients in a session."""
        if session_id in self.active_connections:
            message = json.dumps(event.to_dict())

            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")

    def get_service(self, tenant_id: int) -> SwarmStreamService:
        """Get or create a swarm service for a tenant."""
        key = str(tenant_id)
        if key not in self.services:
            self.services[key] = create_swarm_service(tenant_id)
        return self.services[key]


manager = SwarmConnectionManager()
auth = WebSocketAuthenticator()


# ============================================================================
# REST Endpoints
# ============================================================================


@router.post("/start")
async def start_swarm(
    request: StartSwarmRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Start a new swarm session."""
    from src.core.governance.oversight_gate import OversightGate  # lazy -- ADR-033
    from src.core.governance.governance_helper import PolicyEngineAdapter, AuditServiceAdapter

    # Governance check
    gate = OversightGate(policy_engine=PolicyEngineAdapter(), audit_service=AuditServiceAdapter())
    oversight_result = await gate.check(
        agent_name="SwarmOrchestrator",
        agent_department="SwarmOperations",
        agent_specialisation="MultiAgentCoordination",
        agent_capabilities=["swarm_coordination", "multi_agent_execution"],
        task_action="start_swarm",
        task_params={"objective": request.objective, "auto_spawn": request.auto_spawn},
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )

    if not oversight_result.allowed:
        raise HTTPException(
            status_code=403, detail="Blocked by governance: " + oversight_result.reason
        )

    service = manager.get_service(current_user.tenant_id)
    try:
        session = await asyncio.wait_for(
            service.start_swarm(objective=request.objective, auto_spawn=request.auto_spawn),
            timeout=SWARM_EXECUTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Swarm start timed out")
    return {"success": True, "session": session.to_dict()}


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Submit feedback for a pending request."""
    service = manager.get_service(current_user.tenant_id)
    service.submit_feedback(request.feedback_id, request.response)
    return {"success": True}


@router.get("/sessions")
async def list_sessions(
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List active swarm sessions."""
    service = manager.get_service(current_user.tenant_id)
    sessions = service.get_active_sessions()
    return {"sessions": [s.to_dict() for s in sessions]}


# ============================================================================
# WebSocket Endpoints
# ============================================================================


@router.websocket("/stream/{session_id}")
async def swarm_stream(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time swarm streaming.

    Clients connect to receive live updates from swarm execution.
    """
    user = await auth.authenticate(websocket)
    if not user:
        return

    await manager.connect(websocket, session_id)

    # Find the service with this session
    service: SwarmStreamService | None = None
    event_callback: Any | None = None  # TODO(TYPE): replace Any with concrete type
    for svc in manager.services.values():
        if svc.get_session(session_id):
            service = svc
            break

    if service:
        # Register callback for this session
        async def _event_callback(event: SwarmEvent) -> None:
            await manager.broadcast(session_id, event)

        event_callback = _event_callback
        service.add_event_callback(event_callback)

    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()

            try:
                message = json.loads(data)

                # Handle feedback submissions via WebSocket
                if message.get("type") == "feedback":
                    if service:
                        service.submit_feedback(message.get("feedback_id"), message.get("response"))

                # Handle execute command
                elif message.get("type") == "execute":
                    if service:
                        session = service.get_session(session_id)
                        if session:
                            asyncio.create_task(service.execute_swarm(session, simulate=True))

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        if service and event_callback is not None:
            service.remove_event_callback(event_callback)


@router.websocket("/stream/secure/{session_id}")
async def swarm_stream_secure(websocket: WebSocket, session_id: str) -> None:
    """
    Secure WebSocket endpoint with JWT authentication.

    SEC-AGT-004: de ongebruikte ``token: str | None = Query(None)``-parameter is
    verwijderd (2026-07-31). Authenticatie liep al volledig via
    ``auth.authenticate(websocket)`` (cookie/subprotocol/header); de parameter nodigde
    alleen uit om een token in de URL te zetten, wat in access logs en
    browsergeschiedenis belandt.
    """
    # Authenticate
    user = await auth.authenticate(websocket)
    if not user:
        return

    await manager.connect(websocket, session_id)
    service = manager.get_service(user.tenant_id)

    async def event_callback(event: SwarmEvent) -> None:
        await manager.broadcast(session_id, event)

    service.add_event_callback(event_callback)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "start":
                session = await service.start_swarm(
                    objective=message.get("objective", "Default objective"),
                    auto_spawn=True,
                )
                # Start execution
                asyncio.create_task(service.execute_swarm(session, simulate=True))

            elif message.get("type") == "feedback":
                service.submit_feedback(message.get("feedback_id"), message.get("response"))

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        service.remove_event_callback(event_callback)


# ============================================================================
# Health Check
# ============================================================================


@router.get("/health")
async def health_check() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Health check for swarm service."""
    active_connections = sum(len(c) for c in manager.active_connections.values())

    # Calculate active_sessions from services if available, otherwise from connections
    active_sessions = 0
    for service in manager.services.values():
        active_sessions += len(service.get_active_sessions())

    # If no services have sessions but connections exist, fall back to connection count
    if active_sessions == 0 and active_connections > 0:
        active_sessions = len(manager.active_connections)

    # Determine status based on activity
    if active_connections == 0 and active_sessions == 0:
        status = "idle"
    else:
        status = "healthy"

    return {
        "status": status,
        "service": "swarm-stream",
        "active_connections": active_connections,
        "active_sessions": active_sessions,
    }
