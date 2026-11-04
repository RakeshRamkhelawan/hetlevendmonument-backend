"""Unit tests for Goal API Router (Fase 3.3).

Tests all endpoints in goal_router.py:
- POST   /goals           -> create_goal
- GET    /goals/tree       -> get_goal_tree
- GET    /goals/{goal_id}  -> get_goal
- GET    /goals/{goal_id}/ancestry -> get_goal_ancestry
- PUT    /goals/{goal_id}  -> update_goal
- PUT    /goals/{goal_id}/progress -> update_progress
- DELETE /goals/{goal_id}  -> delete_goal
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.api.v1.company.goal_router import (
    create_goal,
    delete_goal,
    get_goal,
    get_goal_ancestry,
    get_goal_tree,
    update_goal,
    update_progress,
)
from src.core.company.goal_service import GoalService
from src.core.exceptions import ValidatieFout
from src.core.company.schemas import (
    GoalAncestryResponse,
    GoalCreate,
    GoalResponse,
    GoalTreeResponse,
    GoalUpdate,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_goal_service():
    """Create mock GoalService with all async methods."""
    service = MagicMock(spec=GoalService)
    service.create_goal = AsyncMock()
    service.get_goal_tree = AsyncMock()
    service.get_goal = AsyncMock()
    service.get_ancestry = AsyncMock()
    service.update_goal = AsyncMock()
    service.update_progress = AsyncMock()
    service.delete_goal = AsyncMock()
    return service


@pytest.fixture
def sample_goal_response():
    """Create a sample GoalResponse for reuse."""
    return GoalResponse(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        goal_type="strategic",
        title="Revenue Growth",
        description="Increase revenue by 20%",
        status="active",
        progress_pct=25,
        kpis={"revenue_target": 1000000},
        deadline=None,
        parent_goal_id=None,
        children_count=2,
    )


# ============================================================================
# Happy Path Tests
# ============================================================================


class TestCreateGoal:
    """Test POST /goals endpoint."""

    @pytest.mark.asyncio
    async def test_create_goal_success(self, mock_goal_service, sample_goal_response):
        """POST met valide data -> 201 met GoalResponse."""
        mock_goal_service.create_goal.return_value = sample_goal_response

        company_id = uuid.uuid4()
        data = GoalCreate(
            goal_type="strategic",
            title="Revenue Growth",
            description="Increase revenue by 20%",
        )

        result = await create_goal(company_id, data, mock_goal_service)

        assert result.title == "Revenue Growth"
        assert result.goal_type == "strategic"
        mock_goal_service.create_goal.assert_called_once_with(company_id, data)

    @pytest.mark.asyncio
    async def test_create_goal_with_parent(self, mock_goal_service, sample_goal_response):
        """POST met parent_goal_id -> 201."""
        sample_goal_response.parent_goal_id = uuid.uuid4()
        mock_goal_service.create_goal.return_value = sample_goal_response

        company_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        data = GoalCreate(
            goal_type="project",
            title="Q1 Sales Project",
            parent_goal_id=parent_id,
        )

        result = await create_goal(company_id, data, mock_goal_service)

        assert result is not None
        mock_goal_service.create_goal.assert_called_once()


class TestGetGoalTree:
    """Test GET /goals/tree endpoint."""

    @pytest.mark.asyncio
    async def test_get_goal_tree_success(self, mock_goal_service, sample_goal_response):
        """GET tree -> GoalTreeResponse met goals."""
        tree_response = GoalTreeResponse(
            goals=[sample_goal_response],
            tree_structure={"root": str(sample_goal_response.id)},
        )
        mock_goal_service.get_goal_tree.return_value = tree_response

        company_id = uuid.uuid4()
        result = await get_goal_tree(company_id, mock_goal_service)

        assert len(result.goals) == 1
        assert result.tree_structure is not None
        mock_goal_service.get_goal_tree.assert_called_once_with(company_id)


class TestGetGoal:
    """Test GET /goals/{goal_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_goal_by_id(self, mock_goal_service, sample_goal_response):
        """GET goal by ID -> GoalResponse."""
        mock_goal_service.get_goal.return_value = sample_goal_response

        goal_id = uuid.uuid4()
        result = await get_goal(goal_id, mock_goal_service)

        assert result.title == "Revenue Growth"
        mock_goal_service.get_goal.assert_called_once_with(goal_id)

    @pytest.mark.asyncio
    async def test_get_goal_not_found_404(self, mock_goal_service):
        """GET onbekend goal ID -> 404."""
        mock_goal_service.get_goal.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_goal(uuid.uuid4(), mock_goal_service)

        assert exc_info.value.status_code == 404
        assert "Goal not found" in exc_info.value.detail


class TestGetGoalAncestry:
    """Test GET /goals/{goal_id}/ancestry endpoint."""

    @pytest.mark.asyncio
    async def test_get_goal_ancestry(self, mock_goal_service, sample_goal_response):
        """GET ancestry -> GoalAncestryResponse met chain."""
        from src.core.company.context import GoalChain

        ancestry_response = GoalAncestryResponse(
            chain=[sample_goal_response],
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                mission_title="Company Mission",
                strategic_goal_id=sample_goal_response.id,
                strategic_goal_title=sample_goal_response.title,
            ),
        )
        mock_goal_service.get_ancestry.return_value = ancestry_response

        goal_id = uuid.uuid4()
        result = await get_goal_ancestry(goal_id, mock_goal_service)

        assert len(result.chain) == 1
        assert result.goal_chain.mission_title == "Company Mission"
        mock_goal_service.get_ancestry.assert_called_once_with(goal_id)


class TestUpdateGoal:
    """Test PUT /goals/{goal_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_goal_success(self, mock_goal_service, sample_goal_response):
        """PUT met valide data -> GoalResponse."""
        sample_goal_response.title = "Updated Goal"
        mock_goal_service.update_goal.return_value = sample_goal_response

        goal_id = uuid.uuid4()
        data = GoalUpdate(title="Updated Goal")

        result = await update_goal(goal_id, data, mock_goal_service)

        assert result.title == "Updated Goal"
        mock_goal_service.update_goal.assert_called_once_with(goal_id, data)

    @pytest.mark.asyncio
    async def test_update_goal_not_found(self, mock_goal_service):
        """PUT onbekend goal -> 404."""
        mock_goal_service.update_goal.side_effect = ValueError("Goal not found")

        with pytest.raises(HTTPException) as exc_info:
            await update_goal(
                uuid.uuid4(),
                GoalUpdate(title="X"),
                mock_goal_service,
            )

        assert exc_info.value.status_code == 404


class TestUpdateProgress:
    """Test PUT /goals/{goal_id}/progress endpoint."""

    @pytest.mark.asyncio
    async def test_update_progress_success(self, mock_goal_service, sample_goal_response):
        """PUT progress=75 -> GoalResponse met progress_pct=75."""
        sample_goal_response.progress_pct = 75
        mock_goal_service.update_progress.return_value = sample_goal_response

        goal_id = uuid.uuid4()
        result = await update_progress(goal_id, progress=75, service=mock_goal_service)

        assert result.progress_pct == 75
        mock_goal_service.update_progress.assert_called_once_with(goal_id, 75)

    @pytest.mark.asyncio
    async def test_update_progress_error(self, mock_goal_service):
        """PUT progress met error -> 400."""
        mock_goal_service.update_progress.side_effect = ValueError("Invalid progress")

        with pytest.raises(HTTPException) as exc_info:
            await update_progress(uuid.uuid4(), progress=50, service=mock_goal_service)

        assert exc_info.value.status_code == 400


class TestDeleteGoal:
    """Test DELETE /goals/{goal_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_goal_success(self, mock_goal_service):
        """DELETE zonder children -> 204 (None)."""
        mock_goal_service.delete_goal.return_value = None

        goal_id = uuid.uuid4()
        result = await delete_goal(goal_id, mock_goal_service)

        assert result is None
        mock_goal_service.delete_goal.assert_called_once_with(goal_id)

    @pytest.mark.asyncio
    async def test_delete_goal_with_children_blocked(self, mock_goal_service):
        """DELETE met children -> 400."""
        mock_goal_service.delete_goal.side_effect = ValidatieFout("Cannot delete goal with children")

        with pytest.raises(HTTPException) as exc_info:
            await delete_goal(uuid.uuid4(), mock_goal_service)

        assert exc_info.value.status_code == 400
        assert "children" in exc_info.value.detail


# ============================================================================
# Unhappy Path Tests - Create Goal
# ============================================================================


class TestCreateGoalErrors:
    """Test create_goal error handling."""

    @pytest.mark.asyncio
    async def test_create_goal_mission_conflict_409(self, mock_goal_service):
        """Duplicate mission goal -> 409 Conflict."""
        mock_goal_service.create_goal.side_effect = ValueError("Company already has a mission goal")

        data = GoalCreate(goal_type="mission", title="Duplicate Mission")

        with pytest.raises(HTTPException) as exc_info:
            await create_goal(uuid.uuid4(), data, mock_goal_service)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_goal_invalid_hierarchy_422(self, mock_goal_service):
        """Verkeerde parent type -> 422."""
        mock_goal_service.create_goal.side_effect = ValueError(
            "Strategic goal must have a mission parent"
        )

        data = GoalCreate(
            goal_type="strategic",
            title="Orphan Strategic",
            parent_goal_id=uuid.uuid4(),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_goal(uuid.uuid4(), data, mock_goal_service)

        assert exc_info.value.status_code == 422
