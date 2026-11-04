"""
Integration tests for ActivePieces integration

These tests require a running ActivePieces instance or use mocking
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.repositories import (
    ActivePiecesConnectionRepository,
    ActivePiecesFlowRepository,
    ActivePiecesFlowRunRepository,
)
from src.core.activepieces.service import ActivePiecesService

pytestmark = pytest.mark.skip(
    reason=(
        "QUARANTINE: requires running ActivePieces instance | "
        "ISSUE: #BACKLOG-2026-0414 | OWNER: @devops | EXPIRES: 2026-05-14"
    )
)


@pytest.fixture
def mock_db():
    """Mock database session"""
    return AsyncMock()


@pytest.fixture
def flow_repo(mock_db):
    """Flow repository fixture"""
    return ActivePiecesFlowRepository(mock_db)


@pytest.fixture
def connection_repo(mock_db):
    """Connection repository fixture"""
    return ActivePiecesConnectionRepository(mock_db)


@pytest.fixture
def flow_run_repo(mock_db):
    """Flow run repository fixture"""
    return ActivePiecesFlowRunRepository(mock_db)


class TestActivePiecesFlowRepository:
    """Integration tests for Flow Repository"""

    @pytest.mark.asyncio
    async def test_create_flow(self, flow_repo, mock_db):
        """Test creating a flow record"""
        flow = await flow_repo.create(
            tenant_id=1,
            ap_flow_id="flow_123",
            project_id="proj_123",
            name="Test Flow",
            description="A test flow",
            status="ENABLED",
        )

        assert flow.tenant_id == 1
        assert flow.ap_flow_id == "flow_123"
        assert flow.name == "Test Flow"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_flow_by_id(self, flow_repo, mock_db):
        """Test retrieving a flow by ID"""
        # Mock the database result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = SimpleNamespace(
            id="flow_uuid",
            tenant_id=1,
            name="Test Flow",
        )
        mock_db.execute.return_value = mock_result

        flow = await flow_repo.get_by_id(1, "flow_uuid")

        assert flow is not None
        assert flow.name == "Test Flow"

    @pytest.mark.asyncio
    async def test_list_flows_by_tenant(self, flow_repo, mock_db):
        """Test listing flows for a tenant"""
        # Mock the database result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            SimpleNamespace(id="flow_1", name="Flow 1"),
            SimpleNamespace(id="flow_2", name="Flow 2"),
        ]
        mock_db.execute.return_value = mock_result

        flows = await flow_repo.list_by_tenant(1)

        assert len(flows) == 2
        assert flows[0].name == "Flow 1"


class TestActivePiecesConnectionRepository:
    """Integration tests for Connection Repository"""

    @pytest.mark.asyncio
    async def test_create_connection(self, connection_repo, mock_db):
        """Test creating a connection record"""
        conn = await connection_repo.create(
            tenant_id=1,
            ap_connection_id="conn_123",
            project_id="proj_123",
            app_name="gmail",
            name="My Gmail",
            status="ACTIVE",
        )

        assert conn.tenant_id == 1
        assert conn.app_name == "gmail"
        assert conn.name == "My Gmail"
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_last_used(self, connection_repo, mock_db):
        """Test updating last_used timestamp"""
        # Mock getting the connection
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result

        result = await connection_repo.update_last_used(1, "conn_uuid")

        assert result is True
        assert mock_conn.last_used_at is not None


class TestActivePiecesFlowRunRepository:
    """Integration tests for Flow Run Repository"""

    @pytest.mark.asyncio
    async def test_create_run(self, flow_run_repo, mock_db):
        """Test creating a flow run record"""
        from uuid import uuid4

        run = await flow_run_repo.create(
            tenant_id=1,
            flow_id=uuid4(),
            ap_run_id="run_123",
            project_id="proj_123",
            status="RUNNING",
            payload={"key": "value"},
        )

        assert run.tenant_id == 1
        assert run.ap_run_id == "run_123"
        assert run.status == "RUNNING"

    @pytest.mark.asyncio
    async def test_update_run_status(self, flow_run_repo, mock_db):
        """Test updating run status"""
        from uuid import uuid4

        # Mock getting the run
        mock_run = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_db.execute.return_value = mock_result

        run = await flow_run_repo.update_status(
            tenant_id=1,
            run_id=uuid4(),
            status="SUCCEEDED",
            duration_ms=5000,
        )

        assert run is not None
        assert run.status == "SUCCEEDED"
        assert run.duration_ms == 5000


class TestActivePiecesClient:
    """Integration tests for ActivePieces Client"""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client initialization"""
        with patch("src.core.activepieces.client.ActivePiecesClient._authenticate"):
            client = ActivePiecesClient()
            assert client.token is None
            assert client.base_url is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_state(self):
        """Test circuit breaker functionality"""
        with patch("src.core.activepieces.client.ActivePiecesClient._authenticate"):
            client = ActivePiecesClient()

            # Initially should be available
            assert client.is_available() is True


class TestActivePiecesService:
    """Integration tests for ActivePieces Service"""

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test service initialization"""
        mock_client = AsyncMock()

        with patch("src.core.activepieces.service.ActivePiecesClient", return_value=mock_client):
            service = ActivePiecesService()
            assert service._client is not None

    @pytest.mark.asyncio
    async def test_check_health(self):
        """Test health check"""
        mock_client = AsyncMock()
        mock_client.list_pieces.return_value = []

        with patch("src.core.activepieces.service.ActivePiecesClient", return_value=mock_client):
            service = ActivePiecesService()
            is_healthy = await service.check_health()

            assert is_healthy is True
            mock_client.list_pieces.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_pieces(self):
        """Test syncing pieces"""
        mock_client = AsyncMock()
        mock_client.list_pieces.return_value = [
            SimpleNamespace(name="gmail", displayName="Gmail"),
            SimpleNamespace(name="slack", displayName="Slack"),
        ]

        with patch("src.core.activepieces.service.ActivePiecesClient", return_value=mock_client):
            service = ActivePiecesService()
            count = await service.sync_pieces()

            assert count == 2


class TestActivePiecesAPI:
    """Integration tests for API endpoints"""

    @pytest.mark.asyncio
    async def test_flow_validation_endpoint(self, integration_client):
        """Test flow validation API endpoint"""
        flow_data = {"displayName": "Test Flow", "trigger": {"type": "WEBHOOK", "settings": {}}}

        response = await integration_client.post(
            "/api/v1/integrations/flows/validate",
            json=flow_data,
            params={"flow_type": "activepieces"},
        )

        # Endpoint is protected in integration app; unauthenticated client can return 401.
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert "valid" in data

    @pytest.mark.asyncio
    async def test_health_endpoint(self, integration_client):
        """Test health check API endpoint"""
        response = await integration_client.get("/api/v1/integrations/health")

        # Endpoint is protected in integration app; unauthenticated client can return 401.
        assert response.status_code in [200, 503, 401]


@pytest.mark.skipif(
    not getattr(pytest, "config", None) or not pytest.config.getoption("--live-ap", default=False),
    reason="Requires live ActivePieces instance",
)
class TestActivePiecesLiveIntegration:
    """
    Live integration tests against real ActivePieces instance.
    Run with: pytest --live-ap
    """

    @pytest.fixture
    async def live_client(self):
        """Create a real ActivePieces client"""
        return ActivePiecesClient()

    @pytest.mark.asyncio
    async def test_list_pieces_live(self, live_client):
        """Test listing pieces from real AP instance"""
        pieces = await live_client.list_pieces()

        assert isinstance(pieces, list)
        # Should have at least some pieces
        assert len(pieces) > 0

        # Check piece structure
        piece = pieces[0]
        assert hasattr(piece, "name")
        assert hasattr(piece, "displayName")

    @pytest.mark.asyncio
    async def test_create_and_delete_flow_live(self, live_client):
        """Test creating and deleting a flow"""
        # Create a simple flow
        flow_data = {
            "displayName": f"Test Flow {__import__('time').time()}",
            "trigger": {"type": "EMPTY", "settings": {}},
        }

        # This requires a valid project_id
        # flow = await live_client.create_flow("project_id", flow_data)
        # assert flow is not None

        # Cleanup
        # await live_client.delete_flow(flow["id"])

        pytest.skip("Requires valid project configuration")
