# tests/unit/test_compliance_pdf_endpoint.py
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.core.governance.compliance_score import ComplianceScoreResult


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.execute = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_calculator():
    calc = AsyncMock()
    calc.calculate_overall_score = AsyncMock(
        return_value=ComplianceScoreResult(
            overall_score=82.0,
            gdpr_score=85.0,
            ai_act_score=80.0,
            audit_score=78.0,
            calculated_at=datetime.now(timezone.utc),
            tenant_id=1,
        )
    )
    return calc


@pytest_asyncio.fixture
async def pdf_client(mock_calculator, mock_db_session):
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1, sub="1", user_id=1, tenant_id=1, email="test@example.com", roles=["user"]
        )

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    with patch(
        "src.core.api.v1.compliance.router.ComplianceScoreCalculator",
        return_value=mock_calculator,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_report_returns_200_with_pdf_content_type(pdf_client):
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert "application/pdf" in response.headers["content-type"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_report_returns_non_empty_bytes(pdf_client):
    response = await pdf_client.get(
        "/api/v1/compliance/report/pdf",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert len(response.content) > 100


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pdf_report_without_auth_returns_401(mock_db_session):
    from src.core.api.v1.compliance.router import router as compliance_router
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(compliance_router, prefix="/api/v1")

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/compliance/report/pdf")

    assert response.status_code in (401, 403, 422)
    app.dependency_overrides.clear()
