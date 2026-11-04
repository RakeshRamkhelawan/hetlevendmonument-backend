"""Unit tests for GoalService - Fase 3.1

Tests goal CRUD, hierarchy validation, ancestry building, and progress propagation.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.company.goal_service import GoalService
from src.core.company.schemas import GoalCreate, GoalUpdate


@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    manager = AsyncMock()
    return manager


@pytest.fixture
def mock_tenant_context():
    """Create mock tenant context."""
    context = MagicMock()
    context.tenant_id = 1
    context.bypass_filter = False
    return context


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def goal_service(mock_db_manager, mock_tenant_context, mock_redis):
    """Create GoalService with mocked dependencies."""
    service = GoalService(mock_db_manager, mock_tenant_context)
    service._redis = mock_redis
    return service


@pytest.fixture
def company_id():
    """Sample company UUID."""
    return uuid.uuid4()


class TestCreateGoal:
    """Tests for goal creation with hierarchy validation."""

    @pytest.mark.asyncio
    async def test_create_mission_goal(self, goal_service, company_id):
        """Happy path: Create first goal as mission."""
        # Arrange - First query checks for existing mission (returns empty), second creates
        call_count = 0

        async def mock_execute(query, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            # First call: check for existing mission
            if call_count == 1:
                return []  # No existing mission
            # Second call: insert new goal
            return [
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": 1,
                    "company_id": str(company_id),
                    "goal_type": "mission",
                    "title": "Company Mission",
                    "description": "Our mission",
                    "status": "not_started",
                    "progress_pct": 0,
                    "kpis": {},
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            ]

        goal_service._execute = mock_execute

        data = GoalCreate(
            title="Company Mission",
            description="Our mission",
            goal_type="mission",
        )

        # Act
        result = await goal_service.create_goal(company_id, data)

        # Assert
        assert result.goal_type == "mission"
        assert result.title == "Company Mission"

    @pytest.mark.asyncio
    async def test_create_strategic_under_mission(self, goal_service, company_id):
        """Happy path: Create strategic goal under mission."""
        # Arrange
        mission_id = uuid.uuid4()
        call_count = 0

        async def mock_execute(query, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Get parent goal
                return [{"id": str(mission_id), "goal_type": "mission", "title": "Mission"}]
            return [
                {  # Insert strategic
                    "id": str(uuid.uuid4()),
                    "tenant_id": 1,
                    "company_id": str(company_id),
                    "parent_goal_id": str(mission_id),
                    "goal_type": "strategic",
                    "title": "Strategic Goal",
                    "status": "not_started",
                    "progress_pct": 0,
                    "kpis": {},
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            ]

        goal_service._execute = mock_execute

        data = GoalCreate(
            title="Strategic Goal",
            goal_type="strategic",
            parent_goal_id=mission_id,
        )

        # Act
        result = await goal_service.create_goal(company_id, data)

        # Assert
        assert result.goal_type == "strategic"

    @pytest.mark.asyncio
    async def test_create_full_hierarchy(self, goal_service, company_id):
        """Happy path: Mission → Strategic → Project → Task chain."""
        # Arrange
        mission_id = uuid.uuid4()
        call_count = 0

        async def mock_execute(query, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Check existing mission
                return []
            return [
                {
                    "id": str(mission_id),
                    "goal_type": "mission",
                    "title": "Mission",
                    "status": "not_started",
                    "progress_pct": 0,
                    "kpis": {},
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            ]

        goal_service._execute = mock_execute

        data = GoalCreate(title="Mission", goal_type="mission")
        result = await goal_service.create_goal(company_id, data)

        assert result.goal_type == "mission"

    @pytest.mark.asyncio
    async def test_create_second_mission_fails(self, goal_service, company_id):
        """Unhappy path: Cannot create second mission for same company."""
        # Arrange
        existing_mission = uuid.uuid4()
        goal_service._execute = AsyncMock(
            return_value=[
                {
                    "id": str(existing_mission),
                    "goal_type": "mission",
                }
            ]
        )

        data = GoalCreate(title="Second Mission", goal_type="mission")

        # Act & Assert
        with pytest.raises(ValueError, match="Company already has a mission goal"):
            await goal_service.create_goal(company_id, data)

    @pytest.mark.asyncio
    async def test_create_strategic_without_mission_parent_fails(self, goal_service, company_id):
        """Unhappy path: Strategic goal parent must be mission."""
        # Arrange
        wrong_parent = uuid.uuid4()

        async def mock_execute(query, params=None, **kwargs):
            return [
                {
                    "id": str(wrong_parent),
                    "goal_type": "strategic",  # Not mission!
                }
            ]

        goal_service._execute = mock_execute

        data = GoalCreate(
            title="Strategic",
            goal_type="strategic",
            parent_goal_id=wrong_parent,
        )

        # Act & Assert
        with pytest.raises(ValueError, match="strategic goals must have a mission parent"):
            await goal_service.create_goal(company_id, data)

    @pytest.mark.asyncio
    async def test_create_task_under_mission_fails(self, goal_service, company_id):
        """Unhappy path: Task cannot be directly under mission (needs project)."""
        # Arrange
        mission_id = uuid.uuid4()

        async def mock_execute(query, params=None, **kwargs):
            return [
                {
                    "id": str(mission_id),
                    "goal_type": "mission",
                }
            ]

        goal_service._execute = mock_execute

        data = GoalCreate(
            title="Direct Task",
            goal_type="task",
            parent_goal_id=mission_id,
        )

        # Act & Assert
        with pytest.raises(ValueError, match="task goals must have a project parent"):
            await goal_service.create_goal(company_id, data)


class TestGetAncestry:
    """Tests for goal ancestry retrieval with caching."""

    @pytest.mark.asyncio
    async def test_get_ancestry_chain(self, goal_service):
        """Happy path: Get full ancestry from task to mission."""
        # Arrange
        mission_id = uuid.uuid4()
        strategic_id = uuid.uuid4()
        project_id = uuid.uuid4()
        task_id = uuid.uuid4()

        call_count = 0

        async def mock_execute(query, params=None, **kwargs):
            nonlocal call_count
            call_count += 1
            # Each call returns the current goal and we traverse up
            goals = {
                str(task_id): {
                    "id": str(task_id),
                    "goal_type": "task",
                    "title": "Task",
                    "status": "not_started",
                    "progress_pct": 0,
                    "kpis": {},
                    "parent_goal_id": str(project_id),
                },
                str(project_id): {
                    "id": str(project_id),
                    "goal_type": "project",
                    "title": "Project",
                    "status": "not_started",
                    "progress_pct": 0,
                    "kpis": {},
                    "parent_goal_id": str(strategic_id),
                },
                str(strategic_id): {
                    "id": str(strategic_id),
                    "goal_type": "strategic",
                    "title": "Strategic",
                    "status": "not_started",
                    "progress_pct": 0,
                    "kpis": {},
                    "parent_goal_id": str(mission_id),
                },
                str(mission_id): {
                    "id": str(mission_id),
                    "goal_type": "mission",
                    "title": "Mission",
                    "status": "not_started",
                    "progress_pct": 0,
                    "kpis": {},
                    "parent_goal_id": None,
                },
            }
            # Extract goal_id from query params
            goal_id = params.get("goal_id") if params else None
            if goal_id and goal_id in goals:
                return [goals[goal_id]]
            return []

        goal_service._execute = mock_execute

        # Act
        result = await goal_service.get_ancestry(task_id)

        # Assert
        assert len(result.chain) == 4
        assert result.chain[0].goal_type == "task"
        assert result.chain[3].goal_type == "mission"

    @pytest.mark.asyncio
    async def test_ancestry_cached(self, goal_service, mock_redis):
        """Happy path: Second call uses Redis cache."""
        # Arrange
        goal_id = uuid.uuid4()
        cached_data = '[{"id": "12345678-1234-1234-1234-123456789012", "goal_type": "mission", "title": "Cached", "status": "not_started", "progress_pct": 0, "kpis": {}}]'
        mock_redis.get.return_value = cached_data

        # Wrap _execute with a mock to track calls
        original_execute = goal_service._execute
        mock_execute = AsyncMock(wraps=original_execute)
        goal_service._execute = mock_execute

        # Act
        result1 = await goal_service.get_ancestry(goal_id)
        result2 = await goal_service.get_ancestry(goal_id)

        # Assert
        assert mock_redis.get.call_count == 2
        mock_execute.assert_not_called()  # Database not called


class TestBuildGoalChain:
    """Tests for GoalChain building."""

    @pytest.mark.asyncio
    async def test_build_goal_chain(self, goal_service):
        """Happy path: Build GoalChain with all 4 levels."""
        # Arrange
        mission_id = uuid.uuid4()
        strategic_id = uuid.uuid4()
        project_id = uuid.uuid4()
        task_id = uuid.uuid4()

        # Mock that returns goals based on the goal_id in params
        goals_by_id = {
            str(task_id): {
                "id": str(task_id),
                "parent_goal_id": str(project_id),
                "goal_type": "task",
                "title": "Task",
                "status": "not_started",
                "progress_pct": 0,
                "kpis": {},
            },
            str(project_id): {
                "id": str(project_id),
                "parent_goal_id": str(strategic_id),
                "goal_type": "project",
                "title": "Project",
                "status": "not_started",
                "progress_pct": 0,
                "kpis": {},
            },
            str(strategic_id): {
                "id": str(strategic_id),
                "parent_goal_id": str(mission_id),
                "goal_type": "strategic",
                "title": "Strategic",
                "status": "not_started",
                "progress_pct": 0,
                "kpis": {},
            },
            str(mission_id): {
                "id": str(mission_id),
                "parent_goal_id": None,
                "goal_type": "mission",
                "title": "Mission",
                "status": "not_started",
                "progress_pct": 0,
                "kpis": {},
            },
        }

        async def mock_execute(query, params=None, **kwargs):
            goal_id = params.get("goal_id") if params else None
            if goal_id and goal_id in goals_by_id:
                return [goals_by_id[goal_id]]
            return []

        goal_service._execute = mock_execute

        # Act
        result = await goal_service.build_goal_chain(task_id)

        # Assert
        assert result.mission_id == mission_id
        assert result.strategic_goal_id == strategic_id
        assert result.project_goal_id == project_id
        assert result.task_goal_id == task_id


class TestProgressPropagation:
    """Tests for progress updates and parent propagation."""

    @pytest.mark.asyncio
    async def test_progress_propagation(self, goal_service):
        """Happy path: Task 100% updates parent progress."""
        # Arrange
        task_id = uuid.uuid4()
        project_id = uuid.uuid4()

        goal_service._execute = AsyncMock(
            side_effect=[
                # Get task with parent (call 1)
                [
                    {
                        "id": str(task_id),
                        "parent_goal_id": str(project_id),
                        "goal_type": "task",
                        "title": "Task",
                        "status": "not_started",
                        "progress_pct": 0,
                        "kpis": {},
                    }
                ],
                # Update task progress (call 2)
                [
                    {
                        "id": str(task_id),
                        "progress_pct": 100,
                        "goal_type": "task",
                        "title": "Task",
                        "status": "in_progress",
                        "kpis": {},
                    }
                ],
                # Get siblings for average (call 3)
                [{"progress_pct": 100}],  # Only one child
                # Update parent (call 4)
                [
                    {
                        "id": str(project_id),
                        "progress_pct": 100,
                        "goal_type": "project",
                        "title": "Project",
                        "status": "in_progress",
                        "kpis": {},
                    }
                ],
                # Additional calls if needed
                [],
                [],
            ]
        )

        # Act
        result = await goal_service.update_progress(task_id, 100)

        # Assert
        assert result.progress_pct == 100
        assert goal_service._execute.call_count >= 3

    @pytest.mark.asyncio
    async def test_progress_out_of_range(self, goal_service):
        """Unhappy path: Progress must be 0-100."""
        # Arrange
        goal_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(ValueError, match="Progress must be between 0 and 100"):
            await goal_service.update_progress(goal_id, 150)


class TestGoalDeletion:
    """Tests for goal deletion constraints."""

    @pytest.mark.asyncio
    async def test_delete_goal_with_children_fails(self, goal_service):
        """Unhappy path: Cannot delete goal with children."""
        # Arrange
        goal_id = uuid.uuid4()
        goal_service._execute = AsyncMock(
            return_value=[{"id": str(uuid.uuid4()), "parent_goal_id": str(goal_id)}]  # Has child
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot delete goal with children"):
            await goal_service.delete_goal(goal_id)


class TestTenantIsolation:
    """Tests for tenant isolation."""

    @pytest.mark.asyncio
    async def test_goal_wrong_tenant(self, goal_service):
        """Unhappy path: Goal from other tenant returns None."""
        # Arrange
        goal_id = uuid.uuid4()
        goal_service._execute = AsyncMock(return_value=[])  # Not found for this tenant

        # Act
        result = await goal_service.get_goal(goal_id)

        # Assert
        assert result is None
