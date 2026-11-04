import sys
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import PromptTemplate
from src.domains.agentic.schemas.experiment_schema import CreateExperimentRequest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Hangs on Windows ProactorEventLoop due to pytest-asyncio 1.3.0 Runner deadlock",
)


@pytest.fixture
def mock_ab_framework():
    """Mock ABTestingFramework to avoid Redis connections during tests"""
    with patch("src.domains.agentic.services.experimentation_service.ab_testing_framework") as mock:
        mock.create_ab_test = AsyncMock(return_value="exp-mock-id")
        mock.start_ab_test = AsyncMock(return_value=True)
        yield mock


@pytest.fixture
async def sample_template(postgres_session: AsyncSession, test_tenant_id: int):
    # `tenant_id` is nullable=False met een expliciete ADR-005-verwijzing op het model
    # (`src/domains/agentic/models.py:60`). Zonder deze waarde faalt de INSERT op een echte
    # Postgres met "null value in column tenant_id violates not-null constraint" -- drie errors in
    # CI-run 31612043571.
    #
    # Dat bleef verborgen doordat dit hele bestand op Windows wordt overgeslagen (zie de
    # `pytestmark` hierboven), dus een lokale suite-run op Windows kan dit per definitie niet
    # betrappen. Alleen CI draait deze tests.
    template = PromptTemplate(
        name="API Test Template",
        system_prompt="System Prompt",
        version="1.0",
        tenant_id=test_tenant_id,
    )
    postgres_session.add(template)
    await postgres_session.flush()
    await postgres_session.refresh(template)
    return template


@pytest.mark.asyncio
async def test_create_experiment_api(
    integration_client: AsyncClient, sample_template, admin_token: str
):
    """Test creating a new experiment via API"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "name": "API Experiment",
        "description": "Testing API creation",
        "prompt_template_id": sample_template.id,
        "variants": [
            {
                "name": "Control",
                "content": "Control Content",
                "traffic": 0.5,
                "is_control": True,
            },
            {
                "name": "Variant B",
                "content": "Variant B Content",
                "traffic": 0.5,
                "is_control": False,
            },
        ],
        # 100 is de ONDERGRENS die de productiecode afdwingt
        # (`production_integration.py:181`: onder de 100 geen statistische validiteit). Hier stond
        # 50, dus deze happy-path-test vroeg om een 201 voor een verzoek dat het systeem terecht
        # weigert. Zichtbaar geworden in CI-run 31615480686; op Windows draait dit bestand niet.
        "min_sample_size": 100,
    }

    response = await integration_client.post(
        "/api/v1/agentic/experiments/", json=payload, headers=headers
    )

    # Expect 201 Created
    assert response.status_code == 201, f"Response: {response.text}"
    data = response.json()
    assert data["name"] == "API Experiment"
    assert "id" in data
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_experiments_api(
    integration_client: AsyncClient, sample_template, admin_token: str
):
    """Test listing experiments"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Create one first (manual injection or via API if order guaranteed, but manual is safer)
    # But since we use db_session rollback, we rely on the implementation logic.
    # We can skip implementation dependency by assuming we can just call the endpoint.

    response = await integration_client.get("/api/v1/agentic/experiments/", headers=headers)
    # Should get empty list or list
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_experiment_details_api(integration_client: AsyncClient, admin_token: str):
    """Test get details (returns 404 for non-existent)"""
    import uuid

    headers = {"Authorization": f"Bearer {admin_token}"}
    non_existent_id = str(uuid.uuid4())
    response = await integration_client.get(
        f"/api/v1/agentic/experiments/{non_existent_id}", headers=headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_experiment_unauthorized(integration_client: AsyncClient):
    """Test creation without token (should fail)"""
    payload = {"name": "Unauthorized"}
    # No headers
    response = await integration_client.post("/api/v1/agentic/experiments/", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_experiment_validation_error(
    integration_client: AsyncClient, admin_token: str
):
    """Test validation error (missing required fields)"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Missing 'prompt_template_id' and 'variants'
    payload = {"name": "Invalid Experiment", "description": "Missing required fields"}

    response = await integration_client.post(
        "/api/v1/agentic/experiments/", json=payload, headers=headers
    )

    # Expect 422 Unprocessable Entity
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_create_experiment_invalid_traffic_split(
    integration_client: AsyncClient, sample_template, admin_token: str
):
    """Test logic validation (traffic split != 1.0)"""
    # Note: This depends on whether the service enforces this validation.
    # If not implemented yet, this test might fail (or pass with 200).
    # Assuming standard A/B framework logic enforces strict 1.0 total.

    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "name": "Bad Traffic Split",
        "prompt_template_id": sample_template.id,
        "variants": [
            {"name": "A", "config": {}, "traffic": 0.8, "is_control": True},
            {
                "name": "B",
                "config": {},
                "traffic": 0.3,
                "is_control": False,
            },  # Sum = 1.1
        ],
    }

    response = await integration_client.post(
        "/api/v1/agentic/experiments/", json=payload, headers=headers
    )

    # If service validation exists, expect 400 or 422. If strict pydantic, 422.
    # If logic check in service, 400.
    # We'll assert >= 400 to be safe, then refine.
    assert response.status_code >= 400, f"Expected error, got {response.status_code}"
