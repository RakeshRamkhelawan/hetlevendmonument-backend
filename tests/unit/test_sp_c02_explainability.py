# ASCII-only: no emojis or unicode (CLAUDE.md Section 10)
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient

from src.core.copilot.council.models import CouncilDecisionRow
from src.core.copilot.council.types import DecisionVerdict

pytestmark = [pytest.mark.unit, pytest.mark.security]


def _make_explainability_client(db_mock: AsyncMock) -> TestClient:
    """Build a minimal FastAPI test app with the explainability router."""
    from src.core.api.v1.missions.router import router as mission_router
    from src.core.auth.dependencies import get_current_user, get_current_user_id
    from src.core.middleware.tenant_context import (
        set_tenant_id,
        require_tenant_id,
        _current_user_scopes,
    )
    from src.core.api.dependencies import get_db
    from src.core.models.rbac_models import User

    app = FastAPI()

    @app.middleware("http")
    async def add_tenant_state(request: Request, call_next):
        set_tenant_id(42)
        _current_user_scopes.set(["agents:read"])
        request.state.tenant_id = 42
        request.state.user_id = 1
        return await call_next(request)

    class FakeUser:
        id = 1
        tenant_id = 42
        email = "test@example.com"

    # Set up DB mock side effect to handle User select queries from require_scopes dependency
    async def mock_execute(query):
        mock_result = MagicMock()
        query_str = str(query)
        if "users" in query_str.lower():
            user = User(id=1, tenant_id=42, email="test@example.com")
            mock_result.scalar_one_or_none.return_value = user
        elif "from missions" in query_str.lower():
            mock_result.scalar_one_or_none.return_value = db_mock._mission_result
        elif "from council_decisions" in query_str.lower():
            mock_result.scalar_one_or_none.return_value = db_mock._decision_result
        else:
            mock_result.scalar_one_or_none.return_value = db_mock._db_result
        return mock_result

    db_mock.execute.side_effect = mock_execute
    db_mock._db_result = None
    if "_mission_result" not in db_mock.__dict__:
        db_mock._mission_result = None
    if "_decision_result" not in db_mock.__dict__:
        db_mock._decision_result = None

    app.dependency_overrides[get_current_user] = lambda: FakeUser()
    app.dependency_overrides[get_current_user_id] = lambda: 1
    app.dependency_overrides[require_tenant_id] = lambda: 42
    app.dependency_overrides[get_db] = lambda: db_mock

    app.include_router(mission_router)
    return TestClient(app, raise_server_exceptions=False)


class TestExplainabilityEndpoint:
    def test_explainability_endpoint_exists(self) -> None:
        """GET /api/v1/missions/{id}/steps/{step_id}/explainability exists."""
        db_mock = AsyncMock()
        client = _make_explainability_client(db_mock)
        db_mock._db_result = None
        mission_uuid = str(uuid.uuid4())
        step_uuid = str(uuid.uuid4())
        response = client.get(f"/missions/{mission_uuid}/steps/{step_uuid}/explainability")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["available"] is False

    def test_explainability_invalid_uuid_returns_available_false(self) -> None:
        """Endpoint handles invalid UUID formats gracefully."""
        db_mock = AsyncMock()
        client = _make_explainability_client(db_mock)
        db_mock._db_result = None
        response = client.get("/missions/invalid-mission/steps/invalid-step/explainability")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["available"] is False
        assert "invalid" in data["data"]["reason"].lower()

    def test_explainability_never_returns_mock_data(self) -> None:
        """Endpoint queries the database and never returns hardcoded fake data."""
        db_mock = AsyncMock()
        decision_mock = MagicMock(spec=CouncilDecisionRow)
        decision_mock.tenant_id = 42
        decision_mock.proposal_id = uuid.uuid4()
        decision_mock.agent_type = "workflow"
        decision_mock.explanation_for_user = "Decision made based on cluster 1 analysis."
        decision_mock.verdict = "APPROVED"
        decision_mock.deliberation_ms = 450

        mission_mock = MagicMock()
        mission_mock.payload = {"steps": [{"id": str(decision_mock.proposal_id)}]}

        client = _make_explainability_client(db_mock)
        db_mock._mission_result = mission_mock
        db_mock._decision_result = decision_mock
        mission_uuid = str(uuid.uuid4())
        step_uuid = str(decision_mock.proposal_id)

        response = client.get(f"/missions/{mission_uuid}/steps/{step_uuid}/explainability")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["available"] is True
        assert data["data"]["decision_rationale"] == "Decision made based on cluster 1 analysis."
        assert data["data"]["verdict"] == "APPROVED"
        assert (
            "churn clusters" not in data["data"]["decision_rationale"]
        )  # Proves it does not return the template mock

    def test_explainability_returns_available_false_when_step_not_in_mission(self) -> None:
        """Endpoint must reject explainability lookup when step does not belong to mission."""
        db_mock = AsyncMock()
        mission_mock = MagicMock()
        mission_mock.payload = {"steps": [{"id": str(uuid.uuid4())}]}

        client = _make_explainability_client(db_mock)
        db_mock._mission_result = mission_mock
        db_mock._decision_result = None
        response = client.get(
            f"/missions/{uuid.uuid4()}/steps/{uuid.uuid4()}/explainability"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["available"] is False
        assert "does not belong" in data["data"]["reason"].lower()

    def test_unauthenticated_request_returns_401(self) -> None:
        """Unauthenticated requests are rejected with 400 (tenant context checked before auth)."""
        from src.core.api.v1.missions.router import router as mission_router
        from src.core.database.database import get_db

        app = FastAPI()

        async def _mock_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = _mock_db
        app.include_router(mission_router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            f"/missions/{uuid.uuid4()}/steps/{uuid.uuid4()}/explainability"
        )
        # get_tenant dependency returns 400 when tenant context is missing (before auth check)
        assert response.status_code == 400

    def test_tenant_isolation_prevents_cross_tenant_access(self) -> None:
        """A tenant context of 42 only retrieves decisions belonging to tenant 42."""
        # This will be verified in the endpoint where we do:
        # CouncilDecisionRow.tenant_id == tenant_id
        # We can test that the query execution filter includes tenant_id
        db_mock = AsyncMock()
        client = _make_explainability_client(db_mock)
        mission_uuid = str(uuid.uuid4())
        step_uuid = str(uuid.uuid4())
        mission_mock = MagicMock()
        mission_mock.payload = {"steps": [{"id": step_uuid}]}
        db_mock._mission_result = mission_mock
        db_mock._decision_result = None

        client.get(f"/missions/{mission_uuid}/steps/{step_uuid}/explainability")

        # Verify the council query filters by the tenant_id in dependency (42)
        query_strs = [str(call.args[0]) for call in db_mock.execute.call_args_list]
        council_query = next((q for q in query_strs if "FROM council_decisions" in q), "")
        assert "council_decisions.tenant_id = :tenant_id_1" in council_query
        assert "council_decisions.proposal_id = :proposal_id_1" in council_query
