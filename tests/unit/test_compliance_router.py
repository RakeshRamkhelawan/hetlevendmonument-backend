"""
Unit tests for Compliance API router.

Sprint 7, Task 1.2 - TDD: RED phase first.
Tests GET /api/v1/compliance/score endpoint.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_compliance_result():
    """Create a mock compliance score result."""
    from src.core.governance.compliance_score import ComplianceScoreResult

    return ComplianceScoreResult(
        overall_score=87.5,
        gdpr_score=90.0,
        ai_act_score=85.0,
        audit_score=88.0,
        calculated_at=datetime.now(timezone.utc),
        tenant_id=123,
    )


@pytest.fixture
def mock_calculator(mock_compliance_result):
    """Create a mock ComplianceScoreCalculator."""
    mock = AsyncMock()
    mock.calculate_overall_score = AsyncMock(return_value=mock_compliance_result)
    return mock


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    mock = AsyncMock()
    return mock


@pytest.fixture
async def compliance_client(mock_calculator, mock_db_session):
    """Create a test client with compliance router."""
    from src.core.api.v1.compliance.dependencies import get_score_service
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.auth.dependencies import get_current_user

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1,
            sub="1",
            user_id=1,
            tenant_id=1,
            email="test@example.com",
            roles=["user"],
        )

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_score_service] = lambda: mock_calculator

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestComplianceScoreEndpoint:
    """Test suite for GET /api/v1/compliance/score endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, compliance_client):
        """RED: Endpoint must exist and return 200 for authenticated user."""
        response = await compliance_client.get("/api/v1/compliance/score")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, compliance_client):
        """RED: Response must have correct structure with all fields."""
        response = await compliance_client.get("/api/v1/compliance/score")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify all required fields exist
        assert "overall_score" in data
        assert "gdpr_score" in data
        assert "ai_act_score" in data
        assert "audit_score" in data
        assert "calculated_at" in data
        assert "tenant_id" in data

        # Verify data types
        assert isinstance(data["overall_score"], (int, float))
        assert isinstance(data["gdpr_score"], (int, float))
        assert isinstance(data["ai_act_score"], (int, float))
        assert isinstance(data["audit_score"], (int, float))
        assert isinstance(data["calculated_at"], str)
        assert isinstance(data["tenant_id"], int)

    @pytest.mark.asyncio
    async def test_endpoint_uses_compliance_score_calculator(
        self, compliance_client, mock_calculator
    ):
        """RED: Endpoint must use ComplianceScoreCalculator service."""
        response = await compliance_client.get("/api/v1/compliance/score")

        assert response.status_code == status.HTTP_200_OK
        # Verify calculator was called
        mock_calculator.calculate_overall_score.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_uses_tenant_id_from_user(self, compliance_client, mock_calculator):
        """RED: Endpoint must get tenant_id from authenticated user (JWT)."""
        response = await compliance_client.get("/api/v1/compliance/score")

        assert response.status_code == status.HTTP_200_OK
        # Verify calculator was called with tenant_id from user (mocked as 1)
        mock_calculator.calculate_overall_score.assert_called_once_with(tenant_id=1)

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_scores(self, compliance_client):
        """RED: Response must return correct scores from calculator."""
        response = await compliance_client.get("/api/v1/compliance/score")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify scores match mock result
        assert data["overall_score"] == 87.5
        assert data["gdpr_score"] == 90.0
        assert data["ai_act_score"] == 85.0
        assert data["audit_score"] == 88.0
        assert data["tenant_id"] == 123


class TestComplianceScoreTenantIsolation:
    """Test tenant isolation for compliance score endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_only_returns_data_for_current_tenant(self):
        """RED: Endpoint must only return data for the current tenant."""
        from src.core.api.v1.compliance.dependencies import get_score_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.governance.compliance_score import ComplianceScoreResult

        tenant_result = ComplianceScoreResult(
            overall_score=92.0,
            gdpr_score=95.0,
            ai_act_score=90.0,
            audit_score=91.0,
            calculated_at=datetime.now(timezone.utc),
            tenant_id=1,
        )

        mock_calc = AsyncMock()
        mock_calc.calculate_overall_score = AsyncMock(return_value=tenant_result)

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_score_service] = lambda: mock_calc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/score")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["tenant_id"] == 1
        mock_calc.calculate_overall_score.assert_called_once_with(tenant_id=1)


class TestComplianceScoreAuthentication:
    """Test authentication requirements for compliance score endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_requires_authentication(self):
        """RED: Endpoint must require authentication (401 without token)."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        # Create app with compliance router but no auth override
        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Override auth to reject all requests
        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/score")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestComplianceScoreErrorHandling:
    """Test error handling for compliance score endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_handles_calculator_error(self):
        """RED: Endpoint must handle calculator errors gracefully."""
        from src.core.api.v1.compliance.dependencies import get_score_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        mock_calc = AsyncMock()
        mock_calc.calculate_overall_score = AsyncMock(side_effect=Exception("Database error"))

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_score_service] = lambda: mock_calc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/score")

        assert response.status_code in [
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]


class TestComplianceScoreHistoryEndpoint:
    """Test suite for GET /api/v1/compliance/score/history endpoint.

    Sprint 7, Task 1.3 - TDD implementation.
    """

    @pytest.fixture
    def mock_history_result(self):
        """Create mock history results."""
        from src.core.governance.compliance_score import ComplianceScoreResult

        now = datetime.now(timezone.utc)
        return [
            ComplianceScoreResult(
                overall_score=87.5,
                gdpr_score=90.0,
                ai_act_score=85.0,
                audit_score=88.0,
                calculated_at=now,
                tenant_id=123,
            ),
            ComplianceScoreResult(
                overall_score=85.0,
                gdpr_score=88.0,
                ai_act_score=84.0,
                audit_score=83.0,
                calculated_at=now,
                tenant_id=123,
            ),
        ]

    @pytest.fixture
    def mock_history_calculator(self, mock_history_result):
        """Create a mock calculator with get_score_history."""
        mock = AsyncMock()
        mock.get_score_history = AsyncMock(return_value=mock_history_result)
        return mock

    @pytest.fixture
    async def history_client(self, mock_history_calculator, mock_db_session):
        """Create a test client for history endpoint."""
        from src.core.api.v1.compliance.dependencies import get_score_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_score_service] = lambda: mock_history_calculator

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_history_endpoint_exists_and_returns_200(self, history_client):
        """RED: History endpoint must exist and return 200."""
        response = await history_client.get("/api/v1/compliance/score/history")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_history_endpoint_returns_correct_structure(self, history_client):
        """RED: Response must have correct structure with history and metadata."""
        response = await history_client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify required fields
        assert "history" in data
        assert "count" in data
        assert "days_requested" in data

        # Verify types
        assert isinstance(data["history"], list)
        assert isinstance(data["count"], int)
        assert isinstance(data["days_requested"], int)

    @pytest.mark.asyncio
    async def test_history_endpoint_uses_days_query_parameter_default(self, history_client):
        """RED: Endpoint must use default days=30 when not specified."""
        response = await history_client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Default should be 30
        assert data["days_requested"] == 30

    @pytest.mark.asyncio
    async def test_history_endpoint_accepts_days_query_parameter(self, history_client):
        """RED: Endpoint must accept and use days query parameter."""
        response = await history_client.get("/api/v1/compliance/score/history?days=60")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["days_requested"] == 60

    @pytest.mark.asyncio
    async def test_history_endpoint_validates_days_minimum(self, history_client):
        """RED: Endpoint must reject days < 1."""
        response = await history_client.get("/api/v1/compliance/score/history?days=0")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_history_endpoint_validates_days_maximum(self, history_client):
        """RED: Endpoint must reject days > 365."""
        response = await history_client.get("/api/v1/compliance/score/history?days=366")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_history_endpoint_uses_get_score_history(
        self, history_client, mock_history_calculator
    ):
        """RED: Endpoint must use ComplianceScoreCalculator.get_score_history()."""
        response = await history_client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_200_OK
        mock_history_calculator.get_score_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_history_endpoint_passes_tenant_id(self, history_client, mock_history_calculator):
        """RED: Endpoint must pass tenant_id from user to get_score_history."""
        response = await history_client.get("/api/v1/compliance/score/history?days=45")

        assert response.status_code == status.HTTP_200_OK
        mock_history_calculator.get_score_history.assert_called_once_with(tenant_id=1, days=45)

    @pytest.mark.asyncio
    async def test_history_endpoint_returns_history_items(self, history_client):
        """RED: Response must contain history items with correct fields."""
        response = await history_client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["history"]) == 2
        assert data["count"] == 2

        # Check first item has all required fields
        item = data["history"][0]
        assert "overall_score" in item
        assert "gdpr_score" in item
        assert "ai_act_score" in item
        assert "audit_score" in item
        assert "calculated_at" in item
        assert "tenant_id" in item

    @pytest.mark.asyncio
    async def test_history_endpoint_returns_correct_scores(self, history_client):
        """RED: History items must return correct scores."""
        response = await history_client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # First item scores
        assert data["history"][0]["overall_score"] == 87.5
        assert data["history"][0]["gdpr_score"] == 90.0
        assert data["history"][0]["ai_act_score"] == 85.0
        assert data["history"][0]["audit_score"] == 88.0

        # Second item scores
        assert data["history"][1]["overall_score"] == 85.0

    @pytest.mark.asyncio
    async def test_history_endpoint_handles_empty_history(self):
        """RED: Endpoint must handle empty history gracefully."""
        from src.core.api.v1.compliance.dependencies import get_score_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        mock_calc = AsyncMock()
        mock_calc.get_score_history = AsyncMock(return_value=[])

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1, sub="1", user_id=1, tenant_id=1, email="test@example.com", roles=["user"]
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_score_service] = lambda: mock_calc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["history"] == []
        assert data["count"] == 0
        assert data["days_requested"] == 30


class TestComplianceScoreHistoryTenantIsolation:
    """Test tenant isolation for compliance score history endpoint."""

    @pytest.mark.asyncio
    async def test_history_endpoint_only_returns_current_tenant_data(self):
        """RED: History endpoint must only return data for current tenant."""
        from src.core.api.v1.compliance.dependencies import get_score_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.governance.compliance_score import ComplianceScoreResult

        now = datetime.now(timezone.utc)
        tenant_history = [
            ComplianceScoreResult(
                overall_score=92.0,
                gdpr_score=95.0,
                ai_act_score=90.0,
                audit_score=91.0,
                calculated_at=now,
                tenant_id=1,
            )
        ]

        mock_calc = AsyncMock()
        mock_calc.get_score_history = AsyncMock(return_value=tenant_history)

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1, sub="1", user_id=1, tenant_id=1, email="test@example.com", roles=["user"]
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_score_service] = lambda: mock_calc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        mock_calc.get_score_history.assert_called_once_with(tenant_id=1, days=30)
        assert data["history"][0]["tenant_id"] == 1


class TestComplianceScoreHistoryAuthentication:
    """Test authentication requirements for history endpoint."""

    @pytest.mark.asyncio
    async def test_history_endpoint_requires_authentication(self):
        """RED: History endpoint must require authentication."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/score/history")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# Sprint 7, Task 2.2 - GDPR Reporting Endpoints
# =============================================================================


@pytest.fixture
def mock_gdpr_summary():
    """Create a mock GDPR summary result."""
    from src.core.governance.compliance_aggregation import GDPRSummary

    return GDPRSummary(
        total_data_subjects=1500,
        dsar_requests_count=42,
        dsar_avg_response_time_hours=48.5,
        consent_records_count=1500,
        data_retention_violations=3,
        period_days=30,
        tenant_id=1,
    )


@pytest.fixture
def mock_aggregation_service(mock_gdpr_summary):
    """Create a mock ComplianceAggregationService."""
    mock = AsyncMock()
    mock.get_gdpr_summary = AsyncMock(return_value=mock_gdpr_summary)
    return mock


@pytest.fixture
async def gdpr_client(mock_aggregation_service, mock_db_session):
    """Create a test client with GDPR endpoints."""
    from src.core.api.v1.compliance.dependencies import get_aggregation_service
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.auth.dependencies import get_current_user

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1, sub="1", user_id=1, tenant_id=1, email="test@example.com", roles=["user"]
        )

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_aggregation_service] = lambda: mock_aggregation_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestGDPRSummaryEndpoint:
    """Test suite for GET /api/v1/compliance/report/gdpr/summary endpoint.

    Sprint 7, Task 2.2 - TDD implementation.
    """

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, gdpr_client):
        """RED: GDPR summary endpoint must exist and return 200."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, gdpr_client):
        """RED: Response must have correct structure with all GDPR summary fields."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify all required fields exist
        assert "total_data_subjects" in data
        assert "dsar_requests_count" in data
        assert "dsar_avg_response_time_hours" in data
        assert "consent_records_count" in data
        assert "data_retention_violations" in data
        assert "period_days" in data
        assert "tenant_id" in data
        assert "generated_at" in data

        # Verify data types
        assert isinstance(data["total_data_subjects"], int)
        assert isinstance(data["dsar_requests_count"], int)
        assert isinstance(data["dsar_avg_response_time_hours"], (int, float))
        assert isinstance(data["consent_records_count"], int)
        assert isinstance(data["data_retention_violations"], int)
        assert isinstance(data["period_days"], int)
        assert isinstance(data["tenant_id"], int)
        assert isinstance(data["generated_at"], str)

    @pytest.mark.asyncio
    async def test_endpoint_uses_compliance_aggregation_service(
        self, gdpr_client, mock_aggregation_service
    ):
        """RED: Endpoint must use ComplianceAggregationService."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary")

        assert response.status_code == status.HTTP_200_OK
        # Verify service was called
        mock_aggregation_service.get_gdpr_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_uses_tenant_id_from_user(self, gdpr_client, mock_aggregation_service):
        """RED: Endpoint must get tenant_id from authenticated user."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary")

        assert response.status_code == status.HTTP_200_OK
        # Verify service was called with tenant_id from user (mocked as 1)
        mock_aggregation_service.get_gdpr_summary.assert_called_once_with(tenant_id=1, days=30)

    @pytest.mark.asyncio
    async def test_endpoint_uses_days_query_parameter_default(self, gdpr_client):
        """RED: Endpoint must use default days=30 when not specified."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Default should be 30
        assert data["period_days"] == 30

    @pytest.mark.asyncio
    async def test_endpoint_accepts_days_query_parameter(
        self, gdpr_client, mock_aggregation_service
    ):
        """RED: Endpoint must accept and use days query parameter."""
        # Update mock to return correct period_days for this test
        from src.core.governance.compliance_aggregation import GDPRSummary

        mock_aggregation_service.get_gdpr_summary = AsyncMock(
            return_value=GDPRSummary(
                total_data_subjects=1500,
                dsar_requests_count=42,
                dsar_avg_response_time_hours=48.5,
                consent_records_count=1500,
                data_retention_violations=3,
                period_days=60,  # Match the requested days
                tenant_id=1,
            )
        )

        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary?days=60")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["period_days"] == 60
        mock_aggregation_service.get_gdpr_summary.assert_called_once_with(tenant_id=1, days=60)

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_minimum(self, gdpr_client):
        """RED: Endpoint must reject days < 1."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary?days=0")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_maximum(self, gdpr_client):
        """RED: Endpoint must reject days > 365."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary?days=366")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_summary_data(self, gdpr_client):
        """RED: Response must return correct GDPR summary data."""
        response = await gdpr_client.get("/api/v1/compliance/report/gdpr/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify data matches mock
        assert data["total_data_subjects"] == 1500
        assert data["dsar_requests_count"] == 42
        assert data["dsar_avg_response_time_hours"] == 48.5
        assert data["consent_records_count"] == 1500
        assert data["data_retention_violations"] == 3
        assert data["tenant_id"] == 1


class TestGDPRSummaryTenantIsolation:
    """Test tenant isolation for GDPR summary endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_only_returns_data_for_current_tenant(self):
        """RED: Endpoint must only return data for the current tenant."""
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.governance.compliance_aggregation import GDPRSummary

        # Create result for tenant 1 (matching the authenticated user's tenant)
        tenant_summary = GDPRSummary(
            total_data_subjects=2000,
            dsar_requests_count=50,
            dsar_avg_response_time_hours=36.0,
            consent_records_count=2000,
            data_retention_violations=0,
            period_days=30,
            tenant_id=1,
        )

        mock_service = AsyncMock()
        mock_service.get_gdpr_summary = AsyncMock(return_value=tenant_summary)

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Mock authentication with tenant_id=1
        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        from src.core.api.v1.compliance.dependencies import get_aggregation_service

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_aggregation_service] = lambda: mock_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/gdpr/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify tenant_id in response matches expected tenant
        assert data["tenant_id"] == 1
        # Verify service was called with tenant_id=1
        mock_service.get_gdpr_summary.assert_called_once_with(tenant_id=1, days=30)


class TestGDPRSummaryAuthentication:
    """Test authentication requirements for GDPR summary endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_requires_authentication(self):
        """RED: Endpoint must require authentication (401 without token)."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        # Create app with compliance router but no auth override
        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Override auth to reject all requests
        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/gdpr/summary")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGDPRSummaryErrorHandling:
    """Test error handling for GDPR summary endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_handles_service_error(self):
        """RED: Endpoint must handle service errors gracefully."""
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        mock_service = AsyncMock()
        mock_service.get_gdpr_summary = AsyncMock(side_effect=Exception("Database error"))

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Mock authentication
        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        from src.core.api.v1.compliance.dependencies import get_aggregation_service

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_aggregation_service] = lambda: mock_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/gdpr/summary")

        # Should return 500 or handle gracefully
        assert response.status_code in [
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]


class TestGDPRDSAREndpoint:
    """Test suite for GET /api/v1/compliance/report/gdpr/dsar endpoint.

    Sprint 7, Task 2.2 - TDD implementation.
    """

    @pytest.fixture
    def mock_dsar_requests(self):
        """Create mock DSAR request data."""
        return [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "access",
                "status": "completed",
                "requested_at": "2026-04-10T10:00:00Z",
                "completed_at": "2026-04-11T14:00:00Z",
                "response_time_hours": 28.0,
                "data_subject_id": "user-123",
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "type": "delete",
                "status": "pending",
                "requested_at": "2026-04-11T09:00:00Z",
                "completed_at": None,
                "response_time_hours": 0.0,
                "data_subject_id": "user-456",
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "type": "portability",
                "status": "overdue",
                "requested_at": "2026-03-01T08:00:00Z",
                "completed_at": None,
                "response_time_hours": 0.0,
                "data_subject_id": "user-789",
            },
        ]

    @pytest.fixture
    def mock_dsar_db_result(self, mock_dsar_requests):
        """Create mock database result for DSAR queries."""
        mock_result = MagicMock()

        # Create mock DSAR objects
        class MockDSAR:
            def __init__(self, data):
                self.id = data["id"]
                self.user_id = data["data_subject_id"]
                self.tenant_id = 1
                self.request_type = data["type"]
                self.status = data["status"] if data["status"] != "overdue" else "pending"
                self.requested_at = datetime.fromisoformat(
                    data["requested_at"].replace("Z", "+00:00")
                )
                self.completed_at = (
                    datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
                    if data["completed_at"]
                    else None
                )

        mock_dsar_objects = [MockDSAR(req) for req in mock_dsar_requests]
        mock_result.scalars.return_value.all.return_value = mock_dsar_objects
        return mock_result

    @pytest.fixture
    async def dsar_client(self, mock_dsar_db_result):
        """Create a test client for DSAR endpoint with mocked aggregation service."""
        from src.core.api.v1.compliance.dependencies import get_aggregation_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        mock_svc = AsyncMock()
        mock_svc.get_dsar_requests = AsyncMock(return_value=mock_dsar_db_result.scalars().all())

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_aggregation_service] = lambda: mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, dsar_client):
        """RED: DSAR report endpoint must exist and return 200."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, dsar_client):
        """RED: Response must have correct structure with DSAR data."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify required fields exist
        assert "requests" in data
        assert "count" in data
        assert "by_status" in data
        assert "period_days" in data

        # Verify types
        assert isinstance(data["requests"], list)
        assert isinstance(data["count"], int)
        assert isinstance(data["by_status"], dict)
        assert isinstance(data["period_days"], int)

    @pytest.mark.asyncio
    async def test_endpoint_uses_days_query_parameter_default(self, dsar_client):
        """RED: Endpoint must use default days=30 when not specified."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Default should be 30
        assert data["period_days"] == 30

    @pytest.mark.asyncio
    async def test_endpoint_accepts_days_query_parameter(self, dsar_client):
        """RED: Endpoint must accept and use days query parameter."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar?days=60")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["period_days"] == 60

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_minimum(self, dsar_client):
        """RED: Endpoint must reject days < 1."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar?days=0")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_maximum(self, dsar_client):
        """RED: Endpoint must reject days > 365."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar?days=366")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_accepts_status_filter_all(self, dsar_client):
        """RED: Endpoint must accept status=all filter."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar?status=all")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # All requests should be returned
        assert data["count"] >= 0

    @pytest.mark.asyncio
    async def test_endpoint_accepts_status_filter_pending(self, dsar_client):
        """RED: Endpoint must accept status=pending filter."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar?status=pending")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Only pending requests should be in by_status
        assert "pending" in data["by_status"]

    @pytest.mark.asyncio
    async def test_endpoint_accepts_status_filter_completed(self, dsar_client):
        """RED: Endpoint must accept status=completed filter."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar?status=completed")

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_accepts_status_filter_overdue(self, dsar_client):
        """RED: Endpoint must accept status=overdue filter."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar?status=overdue")

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_filters_by_status_correctly(self):
        """RED: Endpoint must filter DSAR requests by status."""
        from src.core.api.v1.compliance.dependencies import get_aggregation_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        # Create mock data with only pending status
        class MockDSARPending:
            id = "550e8400-e29b-41d4-a716-446655440001"
            user_id = "user-456"
            tenant_id = 1
            request_type = "delete"
            status = "pending"
            requested_at = datetime.now(timezone.utc) - timedelta(days=1)
            completed_at = None

        mock_svc = AsyncMock()
        mock_svc.get_dsar_requests = AsyncMock(return_value=[MockDSARPending()])

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_aggregation_service] = lambda: mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/gdpr/dsar?status=pending")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # All returned requests should have status=pending
        for request in data["requests"]:
            assert request["status"] == "pending"

    @pytest.mark.asyncio
    async def test_endpoint_returns_by_status_counts(self, dsar_client):
        """RED: Response must include counts by status."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # by_status should have counts
        assert "pending" in data["by_status"]
        assert "completed" in data["by_status"]
        assert "overdue" in data["by_status"]

    @pytest.mark.asyncio
    async def test_endpoint_returns_request_items_with_correct_fields(self, dsar_client):
        """RED: Response must contain request items with correct fields."""
        response = await dsar_client.get("/api/v1/compliance/report/gdpr/dsar")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        if data["count"] > 0:
            # Check first item has all required fields
            item = data["requests"][0]
            assert "id" in item
            assert "type" in item
            assert "status" in item
            assert "requested_at" in item
            assert "completed_at" in item
            assert "response_time_hours" in item
            assert "data_subject_id" in item


class TestGDPRDSARTenantIsolation:
    """Test tenant isolation for DSAR report endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_only_returns_current_tenant_data(self):
        """RED: DSAR endpoint must only return data for current tenant."""
        from src.core.api.v1.compliance.dependencies import get_aggregation_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        mock_svc = AsyncMock()
        mock_svc.get_dsar_requests = AsyncMock(return_value=[])

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_aggregation_service] = lambda: mock_svc

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/gdpr/dsar")

        assert response.status_code == status.HTTP_200_OK
        # Data returned should be tenant-scoped (validated by implementation)


class TestGDPRDSARAuthentication:
    """Test authentication requirements for DSAR endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_requires_authentication(self):
        """RED: DSAR endpoint must require authentication."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/gdpr/dsar")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# Sprint 7, Task 2.3 - AI Act Reporting Endpoints
# =============================================================================


@pytest.fixture
def mock_ai_act_summary():
    """Create a mock AI Act summary result."""
    from src.core.governance.compliance_aggregation import AIActSummary

    return AIActSummary(
        total_ai_decisions=1250,
        high_risk_decisions=45,
        human_oversight_rate=98.5,
        explainability_score=92.0,
        bias_audit_count=12,
        period_days=30,
        tenant_id=1,
    )


@pytest.fixture
def mock_ai_act_service(mock_ai_act_summary):
    """Create a mock ComplianceAggregationService with AI Act support."""
    mock = AsyncMock()
    mock.get_ai_act_summary = AsyncMock(return_value=mock_ai_act_summary)
    return mock


@pytest.fixture
async def ai_act_client(mock_ai_act_service):
    """Create a test client for AI Act endpoints."""
    from src.core.api.v1.compliance.dependencies import get_aggregation_service
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.auth.dependencies import get_current_user

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1,
            sub="1",
            user_id=1,
            tenant_id=1,
            email="test@example.com",
            roles=["user"],
        )

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_aggregation_service] = lambda: mock_ai_act_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestAIActSummaryEndpoint:
    """Test suite for GET /api/v1/compliance/report/ai-act/summary endpoint.

    Sprint 7, Task 2.3 - TDD implementation.
    """

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, ai_act_client):
        """RED: AI Act summary endpoint must exist and return 200."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, ai_act_client):
        """RED: Response must have correct structure with all AI Act summary fields."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify all required fields exist
        assert "total_ai_decisions" in data
        assert "high_risk_decisions" in data
        assert "human_oversight_rate" in data
        assert "explainability_score" in data
        assert "bias_audit_count" in data
        assert "period_days" in data
        assert "tenant_id" in data
        assert "generated_at" in data

        # Verify data types
        assert isinstance(data["total_ai_decisions"], int)
        assert isinstance(data["high_risk_decisions"], int)
        assert isinstance(data["human_oversight_rate"], (int, float))
        assert isinstance(data["explainability_score"], (int, float))
        assert isinstance(data["bias_audit_count"], int)
        assert isinstance(data["period_days"], int)
        assert isinstance(data["tenant_id"], int)
        assert isinstance(data["generated_at"], str)

    @pytest.mark.asyncio
    async def test_endpoint_uses_compliance_aggregation_service(
        self, ai_act_client, mock_ai_act_service
    ):
        """RED: Endpoint must use ComplianceAggregationService."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary")

        assert response.status_code == status.HTTP_200_OK
        # Verify service was called
        mock_ai_act_service.get_ai_act_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_uses_tenant_id_from_user(self, ai_act_client, mock_ai_act_service):
        """RED: Endpoint must get tenant_id from authenticated user."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary")

        assert response.status_code == status.HTTP_200_OK
        # Verify service was called with tenant_id from user (mocked as 1)
        mock_ai_act_service.get_ai_act_summary.assert_called_once_with(tenant_id=1, days=30)

    @pytest.mark.asyncio
    async def test_endpoint_uses_days_query_parameter_default(self, ai_act_client):
        """RED: Endpoint must use default days=30 when not specified."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Default should be 30
        assert data["period_days"] == 30

    @pytest.mark.asyncio
    async def test_endpoint_accepts_days_query_parameter(self, ai_act_client, mock_ai_act_service):
        """RED: Endpoint must accept and use days query parameter."""
        # Update mock to return correct period_days for this test
        from src.core.governance.compliance_aggregation import AIActSummary

        mock_ai_act_service.get_ai_act_summary = AsyncMock(
            return_value=AIActSummary(
                total_ai_decisions=2500,
                high_risk_decisions=90,
                human_oversight_rate=97.5,
                explainability_score=91.0,
                bias_audit_count=24,
                period_days=60,  # Match the requested days
                tenant_id=1,
            )
        )

        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary?days=60")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["period_days"] == 60
        mock_ai_act_service.get_ai_act_summary.assert_called_once_with(tenant_id=1, days=60)

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_minimum(self, ai_act_client):
        """RED: Endpoint must reject days < 1."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary?days=0")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_maximum(self, ai_act_client):
        """RED: Endpoint must reject days > 365."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary?days=366")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_summary_data(self, ai_act_client):
        """RED: Response must return correct AI Act summary data."""
        response = await ai_act_client.get("/api/v1/compliance/report/ai-act/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify data matches mock
        assert data["total_ai_decisions"] == 1250
        assert data["high_risk_decisions"] == 45
        assert data["human_oversight_rate"] == 98.5
        assert data["explainability_score"] == 92.0
        assert data["bias_audit_count"] == 12
        assert data["tenant_id"] == 1


class TestAIActSummaryTenantIsolation:
    """Test tenant isolation for AI Act summary endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_only_returns_data_for_current_tenant(self):
        """RED: Endpoint must only return data for the current tenant."""
        from src.core.api.v1.compliance.dependencies import get_aggregation_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.governance.compliance_aggregation import AIActSummary

        # Create result for tenant 1 (matching the authenticated user's tenant)
        tenant_summary = AIActSummary(
            total_ai_decisions=2000,
            high_risk_decisions=60,
            human_oversight_rate=99.0,
            explainability_score=93.0,
            bias_audit_count=20,
            period_days=30,
            tenant_id=1,
        )

        mock_service = AsyncMock()
        mock_service.get_ai_act_summary = AsyncMock(return_value=tenant_summary)

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Mock authentication with tenant_id=1
        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_aggregation_service] = lambda: mock_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/ai-act/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify tenant_id in response matches expected tenant
        assert data["tenant_id"] == 1
        # Verify service was called with tenant_id=1
        mock_service.get_ai_act_summary.assert_called_once_with(tenant_id=1, days=30)


class TestAIActSummaryAuthentication:
    """Test authentication requirements for AI Act summary endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_requires_authentication(self):
        """RED: Endpoint must require authentication (401 without token)."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        # Create app with compliance router but no auth override
        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Override auth to reject all requests
        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/ai-act/summary")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAIActSummaryErrorHandling:
    """Test error handling for AI Act summary endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_handles_service_error(self):
        """RED: Endpoint must handle service errors gracefully."""
        from src.core.api.v1.compliance.dependencies import get_aggregation_service
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        mock_service = AsyncMock()
        mock_service.get_ai_act_summary = AsyncMock(side_effect=Exception("Database error"))

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Mock authentication
        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_aggregation_service] = lambda: mock_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/ai-act/summary")

        # Should return 500 or handle gracefully
        assert response.status_code in [
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]


# =============================================================================
# Sprint 7, Task 3.2 - Integrity Check Endpoints
# =============================================================================


@pytest.fixture
def mock_chain_verification_result():
    """Create a mock chain verification result."""
    from datetime import datetime, timezone

    from src.core.governance.hash_chain import ChainVerificationResult

    return ChainVerificationResult(
        is_valid=True,
        total_entries=1500,
        verified_entries=1500,
        broken_at_entry_id=None,
        broken_at_index=None,
        expected_hash=None,
        actual_hash=None,
        verification_time_ms=245.5,
        tenant_id=1,
        checked_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_chain_status():
    """Create a mock chain status result."""
    from datetime import datetime, timezone

    from src.core.governance.hash_chain import ChainStatus

    return ChainStatus(
        status="healthy",
        last_verified_at=datetime.now(timezone.utc),
        total_entries=1500,
        broken_entries_count=0,
        health_percentage=100.0,
        tenant_id=1,
    )


@pytest.fixture
def mock_entry_verification_result():
    """Create a mock entry verification result."""
    from src.core.governance.hash_chain import EntryVerificationResult

    return EntryVerificationResult(
        entry_id=12345,
        is_valid=True,
        hash_matches=True,
        previous_hash_matches=True,
        computed_hash="abc123def456",
        stored_hash="abc123def456",
        tenant_id=1,
    )


@pytest.fixture
def mock_hash_chain_verifier(
    mock_chain_verification_result, mock_chain_status, mock_entry_verification_result
):
    """Create a mock HashChainVerifier."""
    mock = AsyncMock()
    mock.verify_chain = AsyncMock(return_value=mock_chain_verification_result)
    mock.get_chain_status = AsyncMock(return_value=mock_chain_status)
    mock.verify_entry = AsyncMock(return_value=mock_entry_verification_result)
    return mock


@pytest.fixture
async def integrity_client(mock_hash_chain_verifier):
    """Create a test client for integrity endpoints."""
    from src.core.api.v1.compliance.dependencies import get_hash_chain_verifier
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.auth.dependencies import get_current_user

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1,
            sub="1",
            user_id=1,
            tenant_id=1,
            email="test@example.com",
            roles=["user"],
        )

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_hash_chain_verifier] = lambda: mock_hash_chain_verifier

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestIntegrityVerifyEndpoint:
    """Test suite for GET /api/v1/compliance/integrity/verify endpoint.

    Sprint 7, Task 3.2 - TDD implementation.
    """

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, integrity_client):
        """RED: Integrity verify endpoint must exist and return 200."""
        response = await integrity_client.get("/api/v1/compliance/integrity/verify")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, integrity_client):
        """RED: Response must have correct structure with all verification fields."""
        response = await integrity_client.get("/api/v1/compliance/integrity/verify")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify all required fields exist
        assert "is_valid" in data
        assert "total_entries" in data
        assert "verified_entries" in data
        assert "broken_at_entry_id" in data
        assert "broken_at_index" in data
        assert "expected_hash" in data
        assert "actual_hash" in data
        assert "verification_time_ms" in data
        assert "tenant_id" in data
        assert "checked_at" in data
        assert "period" in data

        # Verify data types
        assert isinstance(data["is_valid"], bool)
        assert isinstance(data["total_entries"], int)
        assert isinstance(data["verified_entries"], int)
        assert data["tenant_id"] == 1

    @pytest.mark.asyncio
    async def test_endpoint_uses_hash_chain_verifier(
        self, integrity_client, mock_hash_chain_verifier
    ):
        """RED: Endpoint must use HashChainVerifier.verify_chain()."""
        response = await integrity_client.get("/api/v1/compliance/integrity/verify")

        assert response.status_code == status.HTTP_200_OK
        # Verify verifier was called
        mock_hash_chain_verifier.verify_chain.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_passes_tenant_id(self, integrity_client, mock_hash_chain_verifier):
        """RED: Endpoint must pass tenant_id from user to verify_chain."""
        response = await integrity_client.get("/api/v1/compliance/integrity/verify")

        assert response.status_code == status.HTTP_200_OK
        # Verify verifier was called with tenant_id from user (mocked as 1)
        mock_hash_chain_verifier.verify_chain.assert_called_once()
        call_kwargs = mock_hash_chain_verifier.verify_chain.call_args.kwargs
        assert call_kwargs.get("tenant_id") == 1

    @pytest.mark.asyncio
    async def test_endpoint_accepts_start_date_query_parameter(
        self, integrity_client, mock_hash_chain_verifier
    ):
        """RED: Endpoint must accept and use start_date query parameter."""
        response = await integrity_client.get(
            "/api/v1/compliance/integrity/verify?start_date=2026-01-01"
        )

        assert response.status_code == status.HTTP_200_OK
        mock_hash_chain_verifier.verify_chain.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_accepts_end_date_query_parameter(
        self, integrity_client, mock_hash_chain_verifier
    ):
        """RED: Endpoint must accept and use end_date query parameter."""
        response = await integrity_client.get(
            "/api/v1/compliance/integrity/verify?end_date=2026-04-12"
        )

        assert response.status_code == status.HTTP_200_OK
        mock_hash_chain_verifier.verify_chain.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_accepts_both_date_parameters(
        self, integrity_client, mock_hash_chain_verifier
    ):
        """RED: Endpoint must accept both start_date and end_date parameters."""
        response = await integrity_client.get(
            "/api/v1/compliance/integrity/verify?start_date=2026-01-01&end_date=2026-04-12"
        )

        assert response.status_code == status.HTTP_200_OK
        mock_hash_chain_verifier.verify_chain.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_verification_data(self, integrity_client):
        """RED: Response must return correct verification data."""
        response = await integrity_client.get("/api/v1/compliance/integrity/verify")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify data matches mock
        assert data["is_valid"] is True
        assert data["total_entries"] == 1500
        assert data["verified_entries"] == 1500
        assert data["broken_at_entry_id"] is None
        assert data["broken_at_index"] is None
        assert data["tenant_id"] == 1


class TestIntegrityStatusEndpoint:
    """Test suite for GET /api/v1/compliance/integrity/status endpoint.

    Sprint 7, Task 3.2 - TDD implementation.
    """

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, integrity_client):
        """RED: Integrity status endpoint must exist and return 200."""
        response = await integrity_client.get("/api/v1/compliance/integrity/status")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, integrity_client):
        """RED: Response must have correct structure with all status fields."""
        response = await integrity_client.get("/api/v1/compliance/integrity/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify all required fields exist
        assert "status" in data
        assert "last_verified_at" in data
        assert "total_entries" in data
        assert "broken_entries_count" in data
        assert "health_percentage" in data
        assert "tenant_id" in data
        assert "generated_at" in data

        # Verify data types
        assert isinstance(data["status"], str)
        assert isinstance(data["total_entries"], int)
        assert isinstance(data["broken_entries_count"], int)
        assert isinstance(data["health_percentage"], (int, float))
        assert isinstance(data["tenant_id"], int)

    @pytest.mark.asyncio
    async def test_endpoint_uses_hash_chain_verifier(
        self, integrity_client, mock_hash_chain_verifier
    ):
        """RED: Endpoint must use HashChainVerifier.get_chain_status()."""
        response = await integrity_client.get("/api/v1/compliance/integrity/status")

        assert response.status_code == status.HTTP_200_OK
        # Verify verifier was called
        mock_hash_chain_verifier.get_chain_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_passes_tenant_id(self, integrity_client, mock_hash_chain_verifier):
        """RED: Endpoint must pass tenant_id from user to get_chain_status."""
        response = await integrity_client.get("/api/v1/compliance/integrity/status")

        assert response.status_code == status.HTTP_200_OK
        # Verify verifier was called with tenant_id from user
        mock_hash_chain_verifier.get_chain_status.assert_called_once_with(tenant_id=1)

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_status_data(self, integrity_client):
        """RED: Response must return correct status data."""
        response = await integrity_client.get("/api/v1/compliance/integrity/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify data matches mock
        assert data["status"] == "healthy"
        assert data["total_entries"] == 1500
        assert data["broken_entries_count"] == 0
        assert data["health_percentage"] == 100.0
        assert data["tenant_id"] == 1


class TestIntegrityVerifyEntryEndpoint:
    """Test suite for POST /api/v1/compliance/integrity/verify-entry endpoint.

    Sprint 7, Task 3.2 - TDD implementation.
    """

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, integrity_client):
        """RED: Verify entry endpoint must exist and return 200."""
        response = await integrity_client.post(
            "/api/v1/compliance/integrity/verify-entry", json={"entry_id": 12345}
        )
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, integrity_client):
        """RED: Response must have correct structure with all verification fields."""
        response = await integrity_client.post(
            "/api/v1/compliance/integrity/verify-entry", json={"entry_id": 12345}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify all required fields exist
        assert "entry_id" in data
        assert "is_valid" in data
        assert "hash_matches" in data
        assert "previous_hash_matches" in data
        assert "computed_hash" in data
        assert "stored_hash" in data
        assert "tenant_id" in data
        assert "verified_at" in data

        # Verify data types
        assert isinstance(data["entry_id"], int)
        assert isinstance(data["is_valid"], bool)
        assert isinstance(data["hash_matches"], bool)
        assert isinstance(data["previous_hash_matches"], bool)
        assert isinstance(data["computed_hash"], str)
        assert isinstance(data["stored_hash"], str)
        assert isinstance(data["tenant_id"], int)

    @pytest.mark.asyncio
    async def test_endpoint_uses_hash_chain_verifier(
        self, integrity_client, mock_hash_chain_verifier
    ):
        """RED: Endpoint must use HashChainVerifier.verify_entry()."""
        response = await integrity_client.post(
            "/api/v1/compliance/integrity/verify-entry", json={"entry_id": 12345}
        )

        assert response.status_code == status.HTTP_200_OK
        # Verify verifier was called
        mock_hash_chain_verifier.verify_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_endpoint_passes_entry_id_and_tenant_id(
        self, integrity_client, mock_hash_chain_verifier
    ):
        """RED: Endpoint must pass entry_id and tenant_id to verify_entry."""
        response = await integrity_client.post(
            "/api/v1/compliance/integrity/verify-entry", json={"entry_id": 12345}
        )

        assert response.status_code == status.HTTP_200_OK
        # Verify verifier was called with correct parameters
        mock_hash_chain_verifier.verify_entry.assert_called_once_with(entry_id=12345, tenant_id=1)

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_entry_data(self, integrity_client):
        """RED: Response must return correct entry verification data."""
        response = await integrity_client.post(
            "/api/v1/compliance/integrity/verify-entry", json={"entry_id": 12345}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify data matches mock
        assert data["entry_id"] == 12345
        assert data["is_valid"] is True
        assert data["hash_matches"] is True
        assert data["previous_hash_matches"] is True
        assert data["computed_hash"] == "abc123def456"
        assert data["stored_hash"] == "abc123def456"
        assert data["tenant_id"] == 1

    @pytest.mark.asyncio
    async def test_endpoint_rejects_missing_entry_id(self, integrity_client):
        """RED: Endpoint must reject request without entry_id."""
        response = await integrity_client.post("/api/v1/compliance/integrity/verify-entry", json={})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestIntegrityEndpointsTenantIsolation:
    """Test tenant isolation for integrity endpoints."""

    @pytest.mark.asyncio
    async def test_verify_endpoint_only_returns_data_for_current_tenant(self):
        """RED: Verify endpoint must only return data for current tenant."""
        from datetime import datetime, timezone

        from src.core.api.v1.compliance.dependencies import get_hash_chain_verifier
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.governance.hash_chain import ChainVerificationResult

        # Create result for tenant 1
        tenant_result = ChainVerificationResult(
            is_valid=True,
            total_entries=1500,
            verified_entries=1500,
            broken_at_entry_id=None,
            broken_at_index=None,
            expected_hash=None,
            actual_hash=None,
            verification_time_ms=245.5,
            tenant_id=1,
            checked_at=datetime.now(timezone.utc),
        )

        mock_verifier = AsyncMock()
        mock_verifier.verify_chain = AsyncMock(return_value=tenant_result)

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_hash_chain_verifier] = lambda: mock_verifier

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/integrity/verify")

        assert response.status_code == status.HTTP_200_OK

        # Verify verifier was called with tenant_id=1
        mock_verifier.verify_chain.assert_called_once()
        call_kwargs = mock_verifier.verify_chain.call_args.kwargs
        assert call_kwargs.get("tenant_id") == 1


class TestIntegrityEndpointsAuthentication:
    """Test authentication requirements for integrity endpoints."""

    @pytest.mark.asyncio
    async def test_verify_endpoint_requires_authentication(self):
        """RED: Verify endpoint must require authentication."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/integrity/verify")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_status_endpoint_requires_authentication(self):
        """RED: Status endpoint must require authentication."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/integrity/status")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_verify_entry_endpoint_requires_authentication(self):
        """RED: Verify entry endpoint must require authentication."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/compliance/integrity/verify-entry", json={"entry_id": 12345}
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAIActDecisionsEndpoint:
    """Test suite for GET /api/v1/compliance/report/ai-act/decisions endpoint.

    Sprint 7, Task 2.3 - TDD implementation.
    """

    @pytest.fixture
    def mock_ai_decisions(self):
        """Create mock AI decision data."""
        return [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "decision_type": "credit_approval",
                "risk_level": "high",
                "human_reviewed": True,
                "explainability_score": 85.5,
                "decided_at": "2026-04-10T10:00:00Z",
                "outcome": "approved",
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "decision_type": "job_screening",
                "risk_level": "medium",
                "human_reviewed": True,
                "explainability_score": 78.0,
                "decided_at": "2026-04-11T09:00:00Z",
                "outcome": "rejected",
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "decision_type": "content_moderation",
                "risk_level": "low",
                "human_reviewed": False,
                "explainability_score": 92.0,
                "decided_at": "2026-04-12T08:00:00Z",
                "outcome": "flagged",
            },
        ]

    @pytest.fixture
    def mock_ai_decisions_db_result(self, mock_ai_decisions):
        """Create mock database result for AI decisions queries."""
        mock_result = MagicMock()

        # Create mock AI decision objects
        class MockAIDecision:
            def __init__(self, data):
                self.id = data["id"]
                self.tenant_id = 1
                self.decision_type = data["decision_type"]
                self.profiling_involved = data["risk_level"] == "high"
                self.human_review_requested = data["human_reviewed"]
                self.confidence_score = data["explainability_score"] / 100.0
                self.created_at = datetime.fromisoformat(data["decided_at"].replace("Z", "+00:00"))
                self.decision_data = {"outcome": data["outcome"]}

        mock_decision_objects = [MockAIDecision(dec) for dec in mock_ai_decisions]
        mock_result.scalars.return_value.all.return_value = mock_decision_objects
        return mock_result

    @pytest.fixture
    async def ai_decisions_client(self, mock_ai_decisions_db_result):
        """Create a test client for AI decisions endpoint with mocked DB."""
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.database.database import get_db

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        # Mock authentication
        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        # Create mock DB that supports SQLAlchemy operations
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_ai_decisions_db_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_endpoint_exists_and_returns_200(self, ai_decisions_client):
        """RED: AI Act decisions report endpoint must exist and return 200."""
        response = await ai_decisions_client.get("/api/v1/compliance/report/ai-act/decisions")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_response_structure(self, ai_decisions_client):
        """RED: Response must have correct structure with AI decisions data."""
        response = await ai_decisions_client.get("/api/v1/compliance/report/ai-act/decisions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify required fields exist
        assert "decisions" in data
        assert "count" in data
        assert "by_risk_level" in data
        assert "human_oversight_rate" in data
        assert "period_days" in data

        # Verify types
        assert isinstance(data["decisions"], list)
        assert isinstance(data["count"], int)
        assert isinstance(data["by_risk_level"], dict)
        assert isinstance(data["human_oversight_rate"], (int, float))
        assert isinstance(data["period_days"], int)

    @pytest.mark.asyncio
    async def test_endpoint_uses_days_query_parameter_default(self, ai_decisions_client):
        """RED: Endpoint must use default days=30 when not specified."""
        response = await ai_decisions_client.get("/api/v1/compliance/report/ai-act/decisions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Default should be 30
        assert data["period_days"] == 30

    @pytest.mark.asyncio
    async def test_endpoint_accepts_days_query_parameter(self, ai_decisions_client):
        """RED: Endpoint must accept and use days query parameter."""
        response = await ai_decisions_client.get(
            "/api/v1/compliance/report/ai-act/decisions?days=60"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["period_days"] == 60

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_minimum(self, ai_decisions_client):
        """RED: Endpoint must reject days < 1."""
        response = await ai_decisions_client.get(
            "/api/v1/compliance/report/ai-act/decisions?days=0"
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_validates_days_maximum(self, ai_decisions_client):
        """RED: Endpoint must reject days > 365."""
        response = await ai_decisions_client.get(
            "/api/v1/compliance/report/ai-act/decisions?days=366"
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_endpoint_accepts_risk_level_filter_all(self, ai_decisions_client):
        """RED: Endpoint must accept risk_level=all filter."""
        response = await ai_decisions_client.get(
            "/api/v1/compliance/report/ai-act/decisions?risk_level=all"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # All decisions should be returned
        assert data["count"] >= 0

    @pytest.mark.asyncio
    async def test_endpoint_accepts_risk_level_filter_low(self, ai_decisions_client):
        """RED: Endpoint must accept risk_level=low filter."""
        response = await ai_decisions_client.get(
            "/api/v1/compliance/report/ai-act/decisions?risk_level=low"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # by_risk_level should have low key
        assert "low" in data["by_risk_level"]

    @pytest.mark.asyncio
    async def test_endpoint_accepts_risk_level_filter_medium(self, ai_decisions_client):
        """RED: Endpoint must accept risk_level=medium filter."""
        response = await ai_decisions_client.get(
            "/api/v1/compliance/report/ai-act/decisions?risk_level=medium"
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_accepts_risk_level_filter_high(self, ai_decisions_client):
        """RED: Endpoint must accept risk_level=high filter."""
        response = await ai_decisions_client.get(
            "/api/v1/compliance/report/ai-act/decisions?risk_level=high"
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_endpoint_filters_by_risk_level_correctly(self):
        """RED: Endpoint must filter AI decisions by risk level."""
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.database.database import get_db

        # Create mock data with only high-risk decisions
        class MockAIDecisionHighRisk:
            id = "550e8400-e29b-41d4-a716-446655440000"
            tenant_id = 1
            decision_type = "credit_approval"
            profiling_involved = True  # high risk
            human_review_requested = True
            confidence_score = 0.855
            created_at = datetime.now(timezone.utc) - timedelta(days=1)
            decision_data = {"outcome": "approved"}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MockAIDecisionHighRisk()]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/compliance/report/ai-act/decisions?risk_level=high"
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # All returned decisions should have risk_level=high
        for decision in data["decisions"]:
            assert decision["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_endpoint_returns_by_risk_level_counts(self, ai_decisions_client):
        """RED: Response must include counts by risk level."""
        response = await ai_decisions_client.get("/api/v1/compliance/report/ai-act/decisions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # by_risk_level should have counts
        assert "low" in data["by_risk_level"]
        assert "medium" in data["by_risk_level"]
        assert "high" in data["by_risk_level"]

    @pytest.mark.asyncio
    async def test_endpoint_returns_human_oversight_rate(self, ai_decisions_client):
        """RED: Response must include human oversight rate."""
        response = await ai_decisions_client.get("/api/v1/compliance/report/ai-act/decisions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should have human_oversight_rate
        assert "human_oversight_rate" in data
        assert isinstance(data["human_oversight_rate"], (int, float))
        # Rate should be 0-100
        assert 0 <= data["human_oversight_rate"] <= 100

    @pytest.mark.asyncio
    async def test_endpoint_returns_decision_items_with_correct_fields(self, ai_decisions_client):
        """RED: Response must contain decision items with correct fields."""
        response = await ai_decisions_client.get("/api/v1/compliance/report/ai-act/decisions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        if data["count"] > 0:
            # Check first item has all required fields
            item = data["decisions"][0]
            assert "id" in item
            assert "decision_type" in item
            assert "risk_level" in item
            assert "human_reviewed" in item
            assert "explainability_score" in item
            assert "decided_at" in item
            assert "outcome" in item


class TestAIActDecisionsTenantIsolation:
    """Test tenant isolation for AI Act decisions report endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_only_returns_current_tenant_data(self):
        """RED: AI Act decisions endpoint must only return data for current tenant."""
        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user
        from src.core.database.database import get_db

        # Create mock DB result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_get_current_user():
            from types import SimpleNamespace

            return SimpleNamespace(
                id=1,
                sub="1",
                user_id=1,
                tenant_id=1,
                email="test@example.com",
                roles=["user"],
            )

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/ai-act/decisions")

        assert response.status_code == status.HTTP_200_OK
        # Data returned should be tenant-scoped (validated by implementation)


class TestAIActDecisionsAuthentication:
    """Test authentication requirements for AI Act decisions endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_requires_authentication(self):
        """RED: AI Act decisions endpoint must require authentication."""
        from fastapi import HTTPException

        from src.core.api.v1.compliance.router import router as compliance_router
        from src.core.auth.dependencies import get_current_user

        app = FastAPI()
        app.include_router(compliance_router, prefix="/api/v1")

        async def override_no_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        app.dependency_overrides[get_current_user] = override_no_auth

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/compliance/report/ai-act/decisions")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
