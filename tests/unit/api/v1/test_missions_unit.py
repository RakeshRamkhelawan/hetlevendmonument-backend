"""Unit tests for Mission CRUD and lifecycle endpoints (TC-001 reactivation).

Rewrites the quarantined test_mission_endpoints.py against the current ORM-based
API (MissionORM, no removed in-memory helpers). Uses mocked AsyncSession.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.api.v1.missions.schemas import (
    AgentType,
    CreateMissionRequest,
    Mission,
    MissionListResponse,
    MissionStatus,
    _orm_to_pydantic,
)


def _make_orm_mission(
    tenant_id: int = 1,
    title: str = "Test Mission",
    status: str = MissionStatus.PLANNED.value,
) -> MagicMock:
    """Return a MagicMock shaped like MissionORM."""
    m = MagicMock()
    m.id = uuid4()
    m.tenant_id = tenant_id
    m.created_by = "user_1"
    m.title = title
    m.description = "desc"
    m.agent_type = AgentType.WORKFLOW.value
    m.status = status
    m.payload = {
        "steps": [],
        "impact": {
            "time_saved": None,
            "cost_impact": None,
            "risk_score": 0.0,
            "bias_detected": [],
        },
    }
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = None
    m.estimated_duration_ms = None
    m.total_cost_usd = None
    m.reasoning_chain = None
    m.deleted_at = None
    return m


@pytest.fixture()
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture()
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "agent@tenant1.com"
    user.tenant_id = 1
    user.roles = []
    return user


class TestCreateMission:
    """Happy and unhappy path tests for POST /missions/."""

    @pytest.mark.asyncio
    async def test_create_mission_persists_and_returns_pydantic(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        """Happy path: create_mission persists MissionORM and returns Mission."""
        from src.core.api.v1.missions.crud_router import create_mission

        orm = _make_orm_mission(tenant_id=1)

        request = CreateMissionRequest(
            title="Deploy Agent",
            description="Automate deployment",
            agent_type=AgentType.WORKFLOW,
            steps=[],
        )

        with patch("src.core.api.v1.missions.crud_router.MissionORM", return_value=orm):
            result = await create_mission(
                request=request,
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        assert isinstance(result, Mission)

    @pytest.mark.asyncio
    async def test_create_mission_sets_injected_tenant_id(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        """Mission is created with the injected tenant_id, not from request body."""
        from src.core.api.v1.missions.crud_router import create_mission

        orm = _make_orm_mission(tenant_id=42)

        request = CreateMissionRequest(
            title="Scoped Mission",
            description="",
            agent_type=AgentType.SPECIALIST,
            steps=[],
        )

        mock_orm_cls = MagicMock(return_value=orm)
        with patch("src.core.api.v1.missions.crud_router.MissionORM", mock_orm_cls):
            result = await create_mission(
                request=request,
                db=mock_db,
                tenant_id=42,
                current_user=mock_user,
            )

        call_kwargs = mock_orm_cls.call_args.kwargs
        assert call_kwargs["tenant_id"] == 42, "MissionORM was not called with injected tenant_id"
        assert result.tenant_id == 42


class TestListMissions:
    """Happy path tests for GET /missions/."""

    @pytest.mark.asyncio
    async def test_list_missions_returns_paginated_response(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        """list_missions returns MissionListResponse with missions and total."""
        from src.core.api.v1.missions.crud_router import list_missions

        orm1 = _make_orm_mission(tenant_id=1, title="Mission A")
        orm2 = _make_orm_mission(tenant_id=1, title="Mission B")

        count_result = MagicMock()
        count_result.scalar.return_value = 2
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [orm1, orm2]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await list_missions(
            db=mock_db,
            tenant_id=1,
            current_user=mock_user,
            page=1,
            page_size=10,
            status_filter=None,
            agent_type=None,
            agent_id=None,
        )

        assert isinstance(result, MissionListResponse)
        assert result.total == 2
        assert len(result.missions) == 2

    @pytest.mark.asyncio
    async def test_list_missions_empty_for_tenant_without_missions(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        """list_missions returns empty list when tenant has no missions."""
        from src.core.api.v1.missions.crud_router import list_missions

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await list_missions(
            db=mock_db,
            tenant_id=99,
            current_user=mock_user,
            page=1,
            page_size=10,
            status_filter=None,
            agent_type=None,
            agent_id=None,
        )

        assert result.total == 0
        assert result.missions == []


class TestGetMission:
    """Happy and unhappy path tests for GET /missions/{id}."""

    @pytest.mark.asyncio
    async def test_get_mission_happy_path(self, mock_db: AsyncMock, mock_user: MagicMock) -> None:
        """Happy path: returns Mission for valid id + tenant."""
        from src.core.api.v1.missions.crud_router import get_mission

        orm = _make_orm_mission(tenant_id=1)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm
        mock_db.execute = AsyncMock(return_value=result_mock)

        mission = await get_mission(
            mission_id=str(orm.id),
            db=mock_db,
            tenant_id=1,
            current_user=mock_user,
        )
        assert mission.id == str(orm.id)

    @pytest.mark.asyncio
    async def test_get_mission_not_found_raises_404(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        """Unhappy path: 404 when mission not in tenant scope."""
        from fastapi import HTTPException

        from src.core.api.v1.missions.crud_router import get_mission

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(HTTPException) as exc_info:
            await get_mission(
                mission_id=str(uuid4()),
                db=mock_db,
                tenant_id=1,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 404


class TestOrmToPydantic:
    """Unit tests for the _orm_to_pydantic helper."""

    def test_orm_to_pydantic_maps_basic_fields(self) -> None:
        """_orm_to_pydantic correctly maps id, title, tenant_id, status."""
        orm = _make_orm_mission(tenant_id=5, title="Hello", status=MissionStatus.EXECUTING.value)
        result = _orm_to_pydantic(orm)
        assert result.title == "Hello"
        assert result.tenant_id == 5
        assert result.status == MissionStatus.EXECUTING

    def test_orm_to_pydantic_empty_steps_when_payload_empty(self) -> None:
        """Empty steps payload yields empty steps list."""
        orm = _make_orm_mission()
        orm.payload = {"steps": [], "impact": None}
        result = _orm_to_pydantic(orm)
        assert result.steps == []

    def test_orm_to_pydantic_steps_parsed(self) -> None:
        """Steps in payload are parsed into MissionStep list."""
        orm = _make_orm_mission()
        orm.payload = {
            "steps": [
                {
                    "id": "s1",
                    "order": 1,
                    "description": "init",
                    "action_type": "init",
                    "status": "pending",
                    "requires_approval": True,
                    "approved_by": None,
                    "approved_at": None,
                    "rejected_by": None,
                    "rejected_at": None,
                    "rejection_reason": None,
                    "duration_ms": None,
                    "cost_usd": None,
                    "error": None,
                }
            ],
            "impact": None,
        }
        result = _orm_to_pydantic(orm)
        assert len(result.steps) == 1
        assert result.steps[0].id == "s1"
