from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.activepieces.schemas import PieceRead
from src.core.focus_builder.models import FocusBuilderFlow
from src.core.focus_builder.schemas import FlowCreate
from src.core.focus_builder.service import FocusBuilderService

TEST_TENANT_ID = 1


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    # De client wordt lazy per tenant gemaakt (`ap_client_voor`); hier zetten we hem vooraf.
    svc = FocusBuilderService(db=mock_session, tenant_id=TEST_TENANT_ID)
    svc._ap_client = AsyncMock()
    # Mock internal dependencies to isolate Service logic
    svc.flow_repo = AsyncMock()
    svc.piece_repo = AsyncMock()
    return svc


def create_valid_graph():
    """Helper to create a valid graph with trigger for testing."""
    return {
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "data": {"label": "Start"},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "2",
                "type": "action",
                "data": {"label": "Action"},
                "position": {"x": 0, "y": 100},
            },
        ],
        "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
    }


@pytest.mark.asyncio
async def test_create_flow_orchestration(service):
    """Test that create_flow calls DB, Transformer (implicit), and Client"""
    # Setup - use a valid graph that passes validation
    flow_data = FlowCreate(name="Test Flow", react_flow_graph=create_valid_graph(), tenant_id=1)

    # DB Mock return
    db_flow = FocusBuilderFlow(id=1, name="Test Flow", tenant_id=1, react_flow_graph={})
    service.flow_repo.create.return_value = db_flow

    # Client Mock return
    service._ap_client.execute_workflow.return_value = {
        "success": True,
        "flow_id": "ap_123",
    }

    # Execute
    result = await service.create_flow(flow_data)

    # Verify
    service.flow_repo.create.assert_called_once()
    service._ap_client.execute_workflow.assert_called_once()
    # Verify DB update was called with AP ID
    service.flow_repo.update.assert_called_with(1, {"activepieces_flow_id": "ap_123"})
    assert result == db_flow


@pytest.mark.asyncio
async def test_sync_pieces_catalog(service):
    """Test sync logic"""
    # Setup - Client returns 1 piece
    piece = PieceRead(
        name="gmail",
        displayName="Gmail",  # Pydantic alias handling in test might need care
        version="0.0.1",
        actions={},
        triggers={},
    )
    # PieceRead alias 'displayName' -> 'display_name' if configured, checking schema:
    # Schema defines aliases 'displayName' for 'display_name'.
    # Constructor needs aliased names usually if populating by name?
    # Let's use kwargs matching the model fields directly to be safe in test or rely on standard init

    service._ap_client.list_pieces.return_value = [piece]

    # Execute
    count = await service.sync_pieces_catalog()

    # Verify
    assert count == 1
    service.piece_repo.upsert_piece.assert_called_once()
    service.session.commit.assert_called_once()
