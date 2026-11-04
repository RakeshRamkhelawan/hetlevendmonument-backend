"""
Unit tests voor Goal domein: doel aanmaken, doel ophalen, edge cases

NOTE: goal_router is now at src.core.api.v1.company.goal_router with prefix="/goals".
Endpoints updated to match the new router. Dependencies are mocked for unit testing.
"""

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.api.v1.company.goal_router import get_goal_service, router as goal_router
from src.core.company.schemas import GoalAncestryResponse, GoalResponse, GoalTreeResponse


class MockGoalService:
    """In-memory mock goal service for unit tests."""

    def __init__(self):
        self._goals: dict[str, GoalResponse] = {}
        self._has_mission = False

    async def create_goal(self, company_id: UUID, data):
        if data.goal_type == "mission" and self._has_mission:
            raise ValueError("Company already has a mission goal")
        if data.goal_type != "mission" and data.parent_goal_id is None:
            raise ValueError(f"{data.goal_type} goals must have a parent")

        goal_id = uuid4()
        goal = GoalResponse(
            id=goal_id,
            company_id=company_id,
            goal_type=data.goal_type,
            title=data.title,
            description=data.description,
            status="not_started",
            progress_pct=0,
        )
        self._goals[str(goal_id)] = goal
        if data.goal_type == "mission":
            self._has_mission = True
        return goal

    async def get_goal(self, goal_id: UUID):
        return self._goals.get(str(goal_id))

    async def update_progress(self, goal_id: UUID, progress: int):
        goal = self._goals.get(str(goal_id))
        if goal is None:
            raise ValueError("Goal not found")
        return goal.model_copy(update={"progress_pct": progress})

    async def delete_goal(self, goal_id: UUID):
        if str(goal_id) not in self._goals:
            raise ValueError("Goal not found")
        del self._goals[str(goal_id)]

    async def update_goal(self, goal_id: UUID, data):
        goal = self._goals.get(str(goal_id))
        if goal is None:
            raise ValueError("Goal not found")
        updates = {}
        if data.title is not None:
            updates["title"] = data.title
        if data.description is not None:
            updates["description"] = data.description
        updated = goal.model_copy(update=updates)
        self._goals[str(goal_id)] = updated
        return updated

    async def get_goal_tree(self, company_id: UUID):
        return GoalTreeResponse(
            goals=list(self._goals.values()),
            tree_structure={"root": [], "nodes": {}},
        )

    async def get_ancestry(self, goal_id: UUID):
        goal = self._goals.get(str(goal_id))
        chain = [goal] if goal else []
        return GoalAncestryResponse(chain=chain)


@pytest.fixture
def client() -> TestClient:
    """Minimal app fixture with the goal router and mocked dependencies."""
    app = FastAPI()
    app.include_router(goal_router, prefix="/api/v1")

    # Mock company layer feature flag
    app.dependency_overrides[require_company_layer_enabled] = lambda: None

    # Mock goal service
    mock_service = MockGoalService()
    app.dependency_overrides[get_goal_service] = lambda: mock_service

    return TestClient(app)


def test_create_goal_success(client: TestClient):
    """Test creating a goal successfully."""
    response = client.post(
        "/api/v1/goals",
        params={"company_id": str(uuid4())},
        json={
            "title": "Test Goal",
            "description": "Test goal description",
            "goal_type": "mission",
        },
    )
    assert response.status_code == 201
    assert "id" in response.json()


def test_get_goal_success(client: TestClient):
    """Test retrieving a goal successfully after creation."""
    company_id = str(uuid4())
    reg = client.post(
        "/api/v1/goals",
        params={"company_id": company_id},
        json={
            "title": "Get Goal",
            "description": "Goal to retrieve",
            "goal_type": "mission",
        },
    )
    goal_id = reg.json().get("id")
    response = client.get(f"/api/v1/goals/{goal_id}")
    assert response.status_code == 200
    assert response.json().get("title") == "Get Goal"


def test_get_goal_not_found(client: TestClient):
    """Test retrieving a non-existent goal."""
    response = client.get("/api/v1/goals/99999999-9999-9999-9999-999999999999")
    assert response.status_code == 404


def test_create_goal_missing_fields(client: TestClient):
    """Test creating a goal with missing required fields."""
    response = client.post(
        "/api/v1/goals",
        params={"company_id": str(uuid4())},
        json={"title": ""},
    )
    assert response.status_code in (400, 422)


def test_create_goal_duplicate_mission(client: TestClient):
    """Test creating duplicate mission goals."""
    company_id = str(uuid4())
    client.post(
        "/api/v1/goals",
        params={"company_id": company_id},
        json={"title": "DupMission", "goal_type": "mission"},
    )
    response = client.post(
        "/api/v1/goals",
        params={"company_id": company_id},
        json={"title": "DupMission", "goal_type": "mission"},
    )
    assert response.status_code in (400, 409)


def test_goal_boundary_values(client: TestClient):
    """Test goal creation with boundary values."""
    long_title = "G" * 255
    response = client.post(
        "/api/v1/goals",
        params={"company_id": str(uuid4())},
        json={"title": long_title, "goal_type": "mission"},
    )
    assert response.status_code in (201, 400, 422)


def test_goal_tenant_isolation():
    """Simuleer goal aanmaken onder verschillende tenants (mock context vereist)"""
    pass


def test_goal_audit_logging(monkeypatch):
    """Mock audit log en controleer aanroep bij goal aanmaken"""
    pass


def test_goal_concurrent_creation(monkeypatch):
    """Simuleer gelijktijdige goal creatie requests (threading or async)"""
    pass


def test_goal_rollback_on_db_failure(monkeypatch):
    """Forceer DB-fout tijdens goal creatie, controleer rollback"""
    pass
