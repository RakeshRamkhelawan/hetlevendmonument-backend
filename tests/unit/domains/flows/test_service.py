"""
Unit tests for src.domains.flows.service.FocusBuilderService.

TDD: tests were RED before implementation and GREEN after.
Covers the critical fixes from FocusBuilder audit 2026-06-18:
- C-1: ActivePiecesClient must be lazy (not instantiated in __init__)
- H-1: create_flow must save to DB before calling ActivePieces
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.verbinding import ApVerbindingOntbreektError
from src.domains.flows.models import FlowUpdate, ReactFlowGraph, ReactFlowNode
from src.domains.flows.service import FocusBuilderService


@pytest.fixture
def mock_db() -> Any:
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def tenant_id() -> int:
    return 42


@pytest.fixture
def minimal_graph() -> ReactFlowGraph:
    return ReactFlowGraph(
        nodes=[
            ReactFlowNode(
                id="trigger-1",
                type="webhook_trigger",
                position={"x": 0, "y": 0},
                # Met naam: een knoop zonder naam wordt een code-stap en die weigert de
                # stappencontrole sinds wfb-dag1 stap 1.
                data={"label": "Trigger", "name": "webhook_trigger"},
            )
        ],
        edges=[],
    )


@pytest.mark.unit
class TestLazyActivePiecesClient:
    """C-1: ActivePiecesClient must not be instantiated in __init__."""

    def test_init_does_not_instantiate_ap_client(
        self, mock_db: AsyncSession, tenant_id: int
    ) -> None:
        with patch("src.domains.flows.service.ActivePiecesClient") as mock_ap_cls:
            service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)

        assert service._ap_client is None
        mock_ap_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_ap_client_property_creates_client_lazily(
        self, mock_db: AsyncSession, tenant_id: int
    ) -> None:
        mock_ap_instance = MagicMock()

        with patch(
            "src.domains.flows.service.ap_client_voor", new=AsyncMock(return_value=mock_ap_instance)
        ) as mock_ap_voor:
            service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)
            client = await service.ap_client()

        mock_ap_voor.assert_awaited_once_with(tenant_id, mock_db)
        assert client is mock_ap_instance
        assert service._ap_client is mock_ap_instance

    @pytest.mark.asyncio
    async def test_ap_client_property_reuses_instance(
        self, mock_db: AsyncSession, tenant_id: int
    ) -> None:
        mock_ap_instance = MagicMock()

        with patch(
            "src.domains.flows.service.ap_client_voor", new=AsyncMock(return_value=mock_ap_instance)
        ) as mock_ap_voor:
            service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)
            _ = await service.ap_client()
            _ = await service.ap_client()

        mock_ap_voor.assert_awaited_once_with(tenant_id, mock_db)

    @pytest.mark.asyncio
    async def test_ap_client_property_raises_when_the_tenant_has_no_connection(
        self, mock_db: AsyncSession, tenant_id: int
    ) -> None:
        with patch(
            "src.domains.flows.service.ap_client_voor",
            new=AsyncMock(side_effect=ApVerbindingOntbreektError("er is nog geen verbinding.")),
        ):
            service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)
            with pytest.raises(ApVerbindingOntbreektError):
                _ = await service.ap_client()


@pytest.mark.unit
class TestCreateFlowDbFirst:
    """H-1: create_flow must persist in DB before calling ActivePieces."""

    @pytest.mark.asyncio
    async def test_create_flow_saves_to_db_before_ap(
        self, mock_db: AsyncSession, tenant_id: int, minimal_graph: ReactFlowGraph
    ) -> None:
        service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)

        mock_record = MagicMock()
        mock_record.id = 123
        mock_record.activepieces_flow_id = None

        # Track order of calls
        call_order: list[str] = []

        async def mock_create(data: dict[str, Any]) -> MagicMock:
            call_order.append("db_create")
            return mock_record

        async def mock_update(flow_id: int, data: dict[str, Any]) -> MagicMock:
            call_order.append("db_update")
            return mock_record

        create_mock = AsyncMock(side_effect=mock_create)
        update_mock = AsyncMock(side_effect=mock_update)
        object.__setattr__(service.repository, "create", create_mock)
        object.__setattr__(service.repository, "update", update_mock)

        mock_ap_client = MagicMock()
        mock_ap_client.create_flow = AsyncMock(side_effect=Exception("AP is down"))
        service._ap_client = mock_ap_client

        with patch.object(service, "_get_tenant_ap_project_id", return_value="project-1"):
            result = await service.create_flow(
                name="test-flow",
                description="A test flow",
                graph=minimal_graph,
                created_by=7,
            )

        assert "db_create" in call_order
        assert "db_update" not in call_order  # AP failed before update
        assert result is mock_record
        create_mock.assert_called_once()
        create_kwargs = create_mock.call_args[0][0]
        assert create_kwargs["activepieces_flow_id"] is None
        assert create_kwargs["description"] == "A test flow"

    @pytest.mark.asyncio
    async def test_create_flow_updates_ap_flow_id_on_success(
        self, mock_db: AsyncSession, tenant_id: int, minimal_graph: ReactFlowGraph
    ) -> None:
        service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)

        mock_record = MagicMock()
        mock_record.id = 456
        mock_record.activepieces_flow_id = None

        create_mock = AsyncMock(return_value=mock_record)
        update_mock = AsyncMock(return_value=mock_record)
        object.__setattr__(service.repository, "create", create_mock)
        object.__setattr__(service.repository, "update", update_mock)

        mock_ap_client = MagicMock()
        mock_ap_client.create_flow = AsyncMock(return_value={"id": "ap-flow-789"})
        mock_ap_client.update_flow = AsyncMock(return_value={"id": "ap-flow-789"})
        service._ap_client = mock_ap_client

        with patch.object(service, "_get_tenant_ap_project_id", return_value="project-1"):
            result = await service.create_flow(
                name="test-flow",
                description=None,
                graph=minimal_graph,
                created_by=7,
            )

        create_mock.assert_called_once()
        update_mock.assert_called_once()
        update_kwargs = update_mock.call_args[0][1]
        assert update_kwargs["activepieces_flow_id"] == "ap-flow-789"
        assert result.activepieces_flow_id == "ap-flow-789"


@pytest.mark.unit
class TestUpdateFlow:
    """Update flow must persist all supplied fields and degrade gracefully on AP failure."""

    @pytest.mark.asyncio
    async def test_update_flow_persists_scalar_and_graph_fields(
        self, mock_db: AsyncSession, tenant_id: int, minimal_graph: ReactFlowGraph
    ) -> None:
        service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)

        mock_flow = MagicMock()
        mock_flow.id = 1
        mock_flow.activepieces_flow_id = "ap-flow-1"
        mock_flow.activepieces_version = 2
        mock_flow.name = "new-name"

        updated_flow = MagicMock()
        updated_flow.activepieces_flow_id = "ap-flow-1"
        updated_flow.name = "new-name"

        get_mock = AsyncMock(return_value=mock_flow)
        update_mock = AsyncMock(return_value=updated_flow)
        object.__setattr__(service.repository, "get", get_mock)
        object.__setattr__(service.repository, "update", update_mock)

        mock_ap_client = MagicMock()
        mock_ap_client.update_flow = AsyncMock(return_value={"id": "ap-flow-1"})
        service._ap_client = mock_ap_client

        update = FlowUpdate(name="new-name", react_flow_graph=minimal_graph)
        result = await service.update_flow(1, update)

        assert result is updated_flow
        update_mock.assert_called_once()
        update_kwargs = update_mock.call_args[0][1]
        assert update_kwargs["name"] == "new-name"
        assert "react_flow_graph" in update_kwargs
        assert "activepieces_flow_json" in update_kwargs
        mock_ap_client.update_flow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_flow_degrades_when_ap_unavailable(
        self, mock_db: AsyncSession, tenant_id: int
    ) -> None:
        service = FocusBuilderService(db=mock_db, tenant_id=tenant_id)

        mock_flow = MagicMock()
        mock_flow.id = 1
        mock_flow.activepieces_flow_id = "ap-flow-1"
        mock_flow.activepieces_version = 1
        mock_flow.name = "old-name"

        updated_flow = MagicMock()
        updated_flow.name = "old-name"

        get_mock = AsyncMock(return_value=mock_flow)
        update_mock = AsyncMock(return_value=updated_flow)
        object.__setattr__(service.repository, "get", get_mock)
        object.__setattr__(service.repository, "update", update_mock)

        mock_ap_client = MagicMock()
        mock_ap_client.update_flow = AsyncMock(side_effect=ConnectionError("AP down"))
        service._ap_client = mock_ap_client

        update = FlowUpdate(is_published=True)
        result = await service.update_flow(1, update)

        assert result is updated_flow
        update_mock.assert_called_once()
        update_kwargs = cast(dict[str, Any], update_mock.call_args[0][1])
        assert update_kwargs["is_published"] is True
