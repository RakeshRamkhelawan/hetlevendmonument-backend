"""Fixtures for Focus Builder tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.testclient import TestClient as StarletteTestClient

from src.core.api.focus_builder_endpoints import router as focus_builder_router
from src.core.api.setup.exception_handlers import setup_exception_handlers


class MockWebSocketManager:
    """Mock WebSocket manager for unit tests."""

    def __init__(self):
        self.connections = {}

    async def connect(self, websocket, canvas_id: str):
        await websocket.accept()
        if canvas_id not in self.connections:
            self.connections[canvas_id] = []
        self.connections[canvas_id].append(websocket)

        # Send connection established
        await websocket.send_json({"type": "connection_established", "canvas_id": canvas_id})

    async def disconnect(self, websocket, canvas_id: str):
        if canvas_id in self.connections:
            if websocket in self.connections[canvas_id]:
                self.connections[canvas_id].remove(websocket)

    async def broadcast(self, canvas_id: str, message: dict):
        if canvas_id in self.connections:
            for conn in self.connections[canvas_id]:
                await conn.send_json(message)


@pytest.fixture
def app_with_limiter():
    """Create app with properly initialized limiter."""
    app = FastAPI()

    # Initialize limiter in app state
    app.state.limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100/minute"],
        storage_uri="memory://",
        headers_enabled=True,
    )

    # Mock other state
    app.state.ws_manager = MockWebSocketManager()

    # Register exception handlers
    setup_exception_handlers(app)

    # Mock database dependency
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.auth.dependencies import require_permission
    from src.core.auth.rbac import Permission
    from src.core.database.database import get_db

    mock_db = AsyncMock(spec=AsyncSession)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Mock auth dependency - always return user_id 1
    def override_require_permission(permission: Permission):
        def checker():
            return 1  # Return user_id

        return checker

    app.dependency_overrides[require_permission] = override_require_permission

    # Mock FocusBuilderService
    from src.core.api.focus_builder_endpoints import get_focus_builder_service
    from src.core.focus_builder.service import FocusBuilderService

    mock_service = MagicMock(spec=FocusBuilderService)
    mock_service.create_flow = AsyncMock(
        return_value={"id": 1, "name": "Test Flow", "tenant_id": 1, "active": True}
    )
    mock_service.list_flows = AsyncMock(return_value=[])
    mock_service.get_flow = AsyncMock(
        return_value={"id": 1, "name": "Test Flow", "tenant_id": 1, "active": True}
    )
    mock_service.update_flow = AsyncMock(
        return_value={"id": 1, "name": "Updated Flow", "tenant_id": 1, "active": True}
    )
    mock_service.delete_flow = AsyncMock(return_value=True)
    mock_service.ap_client = MagicMock()
    mock_service.ap_client.trigger_flow = AsyncMock(return_value={"status": "triggered"})
    mock_service.get_latest_run_status = AsyncMock(return_value={"status": "completed"})
    mock_service.get_run_logs = AsyncMock(return_value={"logs": []})
    mock_service.piece_repo = MagicMock()
    mock_service.piece_repo.get_pieces = AsyncMock(return_value=[])
    mock_service.sync_pieces_catalog = AsyncMock(return_value=5)
    mock_service.generate_flow_from_prompt = AsyncMock(
        return_value={"flow": {"name": "AI Generated Flow"}, "explanation": "Generated from prompt"}
    )

    def override_get_focus_builder_service():
        return mock_service

    app.dependency_overrides[get_focus_builder_service] = override_get_focus_builder_service

    # Include routes
    app.include_router(focus_builder_router, prefix="/api/v1")

    return app


@pytest.fixture
def client_with_limiter(app_with_limiter):
    """Create test client with rate limiter."""
    return TestClient(app_with_limiter)


@pytest.fixture
def ws_client(app_with_limiter):
    """Create synchronous WebSocket test client."""
    with StarletteTestClient(app_with_limiter) as client:
        yield client


@pytest.fixture
def auth_token():
    """Generate valid JWT token for tests."""
    from jose import jwt

    token = jwt.encode(
        {"sub": "1", "tenant_id": "1", "exp": 9999999999}, "test-secret-key", algorithm="HS256"
    )
    return token


@pytest.fixture
def mock_focus_builder_service():
    """Mock FocusBuilderService for unit tests."""
    service = MagicMock()
    service.create_flow = AsyncMock(
        return_value={"id": 1, "name": "Test Flow", "tenant_id": 1, "active": True}
    )
    service.list_flows = AsyncMock(return_value=[])
    service.get_flow = AsyncMock(
        return_value={
            "id": 1,
            "name": "Test Flow",
            "tenant_id": 1,
            "active": True,
            "activepieces_flow_id": "ap-flow-123",
        }
    )
    service.update_flow = AsyncMock(
        return_value={"id": 1, "name": "Updated Flow", "tenant_id": 1, "active": True}
    )
    service.delete_flow = AsyncMock(return_value=True)
    service.ap_client = MagicMock()
    service.ap_client.trigger_flow = AsyncMock(return_value={"status": "triggered"})
    service.get_latest_run_status = AsyncMock(return_value={"status": "completed"})
    service.get_run_logs = AsyncMock(return_value={"logs": []})
    service.piece_repo = MagicMock()
    service.piece_repo.get_pieces = AsyncMock(return_value=[])
    service.sync_pieces_catalog = AsyncMock(return_value=5)
    service.generate_flow_from_prompt = AsyncMock(
        return_value={"flow": {"name": "AI Generated Flow"}, "explanation": "Generated from prompt"}
    )
    return service
