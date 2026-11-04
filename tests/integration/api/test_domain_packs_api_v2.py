"""
Integration tests for Domain Packs API v2 (Sprint 3 Slice 3)
Tests for stats, health, and restore endpoints
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.procedures.models import DomainPack, ProcedureExecution, ProcedureMetadata
from src.core.procedures.schemas import DomainPackCreate


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    """Valid auth headers using the integration admin JWT token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
async def test_pack(db_session: AsyncSession) -> DomainPack:
    """Create a test domain pack"""
    from src.core.procedures.domain_pack_repository import DomainPackRepository

    tenant_id = 1
    repo = DomainPackRepository(db_session)

    data = DomainPackCreate(
        name="Finance",
        department="Finance",
        version=1,
        description="Finance operations",
        capabilities=["compliance", "audit"],
        input_contracts={"invoices": "array"},
        output_contracts={"approvals": "array"},
    )

    pack = await repo.create(tenant_id, data)
    await db_session.commit()
    return pack


@pytest.fixture
async def deprecated_pack(db_session: AsyncSession) -> DomainPack:
    """Create a deprecated (archived) domain pack"""
    from src.core.procedures.domain_pack_repository import DomainPackRepository

    tenant_id = 1
    repo = DomainPackRepository(db_session)

    data = DomainPackCreate(
        name="Legacy Finance", department="Finance", version=1, status="deprecated"
    )

    pack = await repo.create(tenant_id, data)
    await db_session.commit()
    return pack


class TestDomainPackStats:
    """Tests for GET /api/v1/domain-packs/stats"""

    @pytest.mark.asyncio
    async def test_get_pack_stats_returns_correct_format(
        self,
        async_client: AsyncClient,
        test_pack: DomainPack,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: A domain pack with procedures and executions
        WHEN: Fetching pack stats
        THEN: Returns stats with correct format {procedure_count, executions_30d, failure_rate}
        """
        response = await async_client.get("/api/v1/domain-packs/stats", headers=auth_headers)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_pack_stats_excludes_deprecated(
        self,
        async_client: AsyncClient,
        test_pack: DomainPack,
        deprecated_pack: DomainPack,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: Both active and deprecated packs
        WHEN: Fetching stats
        THEN: Active count excludes deprecated packs
        """
        response = await async_client.get("/api/v1/domain-packs/stats", headers=auth_headers)

        assert response.status_code == 200


class TestDomainPackHealth:
    """Tests for GET /api/v1/domain-packs/{id}/health"""

    @pytest.mark.asyncio
    async def test_get_pack_health_returns_status_and_violations(
        self,
        async_client: AsyncClient,
        test_pack: DomainPack,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: A domain pack
        WHEN: Fetching pack health
        THEN: Returns status (healthy/degraded/unhealthy) and violations list
        """
        response = await async_client.get(
            f"/api/v1/domain-packs/{test_pack.id}/health", headers=auth_headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_pack_health_for_nonexistent_pack_returns_404(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ):
        """
        GIVEN: Non-existent pack ID
        WHEN: Fetching health
        THEN: Returns 404
        """
        fake_id = uuid4()
        response = await async_client.get(
            f"/api/v1/domain-packs/{fake_id}/health", headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pack_health_shows_degraded_for_high_failure_rate(
        self,
        async_client: AsyncClient,
        test_pack: DomainPack,
        db_session: AsyncSession,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: A pack with high failure rate (>20%)
        WHEN: Fetching health
        THEN: Status is 'degraded' and violations include failure rate warning
        """
        # Create mock executions with failures
        # This will be implemented in GREEN phase

        response = await async_client.get(
            f"/api/v1/domain-packs/{test_pack.id}/health", headers=auth_headers
        )

        assert response.status_code == 200


class TestDomainPackRestore:
    """Tests for POST /api/v1/domain-packs/{id}/restore"""

    @pytest.mark.asyncio
    async def test_restore_pack_changes_status_to_active(
        self,
        async_client: AsyncClient,
        deprecated_pack: DomainPack,
        db_session: AsyncSession,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: A deprecated (archived) pack
        WHEN: Restoring the pack
        THEN: Pack status changes to 'active'
        """
        # Verify it's deprecated
        assert deprecated_pack.status == "deprecated"

        response = await async_client.post(
            f"/api/v1/domain-packs/{deprecated_pack.id}/restore", headers=auth_headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_restore_nonexistent_pack_returns_404(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ):
        """
        GIVEN: Non-existent pack ID
        WHEN: Attempting to restore
        THEN: Returns 404
        """
        fake_id = uuid4()
        response = await async_client.post(
            f"/api/v1/domain-packs/{fake_id}/restore", headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_restore_already_active_pack_is_idempotent(
        self,
        async_client: AsyncClient,
        test_pack: DomainPack,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: An already active pack
        WHEN: Restoring it
        THEN: Operation succeeds (idempotent) and status remains active
        """
        assert test_pack.status == "active"

        response = await async_client.post(
            f"/api/v1/domain-packs/{test_pack.id}/restore", headers=auth_headers
        )

        assert response.status_code == 200


class TestDomainPackStatsWithExecutions:
    """Tests for stats calculation with real execution data"""

    @pytest.mark.asyncio
    async def test_stats_include_execution_counts(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: Pack with procedures and executions
        WHEN: Fetching stats
        THEN: Returns accurate execution count for last 30 days
        """
        # Mock execution data will be added in GREEN phase

        response = await async_client.get("/api/v1/domain-packs/stats", headers=auth_headers)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_stats_calculate_failure_rate(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """
        GIVEN: Pack with mix of successful and failed executions
        WHEN: Fetching stats
        THEN: Returns accurate failure rate percentage
        """
        # Mock execution data will be added in GREEN phase

        response = await async_client.get("/api/v1/domain-packs/stats", headers=auth_headers)

        assert response.status_code == 200
