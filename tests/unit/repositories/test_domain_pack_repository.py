"""
Unit tests for DomainPackRepository
Tests for CRUD operations and tenant-scoping
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.procedures.domain_pack_repository import DomainPackRepository
from src.core.procedures.models import DomainPack
from src.core.procedures.schemas import DomainPackCreate, DomainPackUpdate


@pytest.fixture
def tenant_id():
    """Fixed tenant ID for tests"""
    return 1


@pytest.fixture
def other_tenant_id():
    """Different tenant for cross-tenant tests"""
    return 2


class TestDomainPackRepositoryCreate:
    """Tests for creating domain packs"""

    @pytest.mark.asyncio
    async def test_create_domain_pack_success(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Valid DomainPackCreate data
        WHEN: Creating a domain pack
        THEN: Domain pack is created with correct attributes
        """
        repo = DomainPackRepository(db_session)

        data = DomainPackCreate(
            name="Finance",
            department="Finance",
            version=1,
            description="Finance domain procedures",
            capabilities=["compliance", "risk_analysis"],
            input_contracts={"invoices": "array"},
            output_contracts={"approvals": "array"},
        )

        result = await repo.create(tenant_id, data)

        assert result.id is not None
        assert result.tenant_id == tenant_id
        assert result.name == "Finance"
        assert result.department == "Finance"
        assert result.version == 1
        assert result.status == "active"
        assert result.created_at is not None
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_domain_pack_with_minimal_data(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Minimal required fields
        WHEN: Creating a domain pack
        THEN: Domain pack is created with defaults
        """
        repo = DomainPackRepository(db_session)

        data = DomainPackCreate(name="Legal", department="Legal")

        result = await repo.create(tenant_id, data)

        assert result.name == "Legal"
        assert result.version == 1
        assert result.capabilities == []
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_create_domain_pack_missing_required_field_fails(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: Missing required field (name)
        WHEN: Creating domain pack
        THEN: Validation fails
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DomainPackCreate(department="Finance")  # Missing 'name'


class TestDomainPackRepositoryRead:
    """Tests for reading domain packs"""

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Existing domain pack
        WHEN: Getting by ID and tenant
        THEN: Returns the domain pack
        """
        repo = DomainPackRepository(db_session)

        # Create first
        data = DomainPackCreate(name="Finance", department="Finance")
        created = await repo.create(tenant_id, data)

        # Get
        result = await repo.get_by_id(tenant_id, created.id)

        assert result is not None
        assert result.id == created.id
        assert result.name == "Finance"

    @pytest.mark.asyncio
    async def test_get_by_id_wrong_tenant_raises_not_found(
        self, db_session: AsyncSession, tenant_id, other_tenant_id
    ):
        """
        GIVEN: Domain pack for tenant A
        WHEN: Requesting with tenant B's ID
        THEN: Returns None or raises NotFound
        """
        repo = DomainPackRepository(db_session)

        # Create for tenant_id
        data = DomainPackCreate(name="Finance", department="Finance")
        created = await repo.create(tenant_id, data)

        # Try to get with different tenant
        result = await repo.get_by_id(other_tenant_id, created.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_nonexistent_returns_none(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Random UUID that doesn't exist
        WHEN: Getting by ID
        THEN: Returns None
        """
        repo = DomainPackRepository(db_session)

        result = await repo.get_by_id(tenant_id, uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_list_domain_packs_by_tenant_returns_only_that_tenant(
        self, db_session: AsyncSession, tenant_id, other_tenant_id
    ):
        """
        GIVEN: Multiple domain packs for different tenants
        WHEN: Listing for specific tenant
        THEN: Returns only that tenant's domain packs
        """
        repo = DomainPackRepository(db_session)

        # Create for tenant_id
        data1 = DomainPackCreate(name="Finance", department="Finance")
        await repo.create(tenant_id, data1)

        # Create for other_tenant_id
        data2 = DomainPackCreate(name="Legal", department="Legal")
        await repo.create(other_tenant_id, data2)

        # List for tenant_id
        results = await repo.list_by_tenant(tenant_id)

        assert len(results) == 1
        assert results[0].name == "Finance"


class TestDomainPackRepositoryUpdate:
    """Tests for updating domain packs"""

    @pytest.mark.asyncio
    async def test_update_domain_pack_success(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Existing domain pack
        WHEN: Updating fields
        THEN: Updates are applied and updated_at changes
        """
        repo = DomainPackRepository(db_session)

        # Create
        data = DomainPackCreate(name="Finance", department="Finance")
        created = await repo.create(tenant_id, data)
        original_updated_at = created.updated_at

        # Update
        update_data = DomainPackUpdate(description="Updated description", status="deprecated")
        result = await repo.update(tenant_id, created.id, update_data)

        assert result is not None
        assert result.description == "Updated description"
        assert result.status == "deprecated"
        assert result.updated_at > original_updated_at

    @pytest.mark.asyncio
    async def test_update_nonexistent_domain_pack_raises(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Nonexistent domain pack ID
        WHEN: Updating
        THEN: Raises error or returns None
        """
        repo = DomainPackRepository(db_session)

        update_data = DomainPackUpdate(description="Test")
        result = await repo.update(tenant_id, uuid4(), update_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_other_tenant_pack_raises(
        self, db_session: AsyncSession, tenant_id, other_tenant_id
    ):
        """
        GIVEN: Domain pack for tenant A
        WHEN: Trying to update with tenant B
        THEN: Returns None or raises error
        """
        repo = DomainPackRepository(db_session)

        # Create for tenant_id
        data = DomainPackCreate(name="Finance", department="Finance")
        created = await repo.create(tenant_id, data)

        # Try to update with other_tenant_id
        update_data = DomainPackUpdate(description="Updated")
        result = await repo.update(other_tenant_id, created.id, update_data)

        assert result is None


class TestDomainPackRepositoryArchive:
    """Tests for archiving domain packs"""

    @pytest.mark.asyncio
    async def test_archive_domain_pack_sets_status_deprecated(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: Active domain pack
        WHEN: Archiving
        THEN: Status becomes 'deprecated'
        """
        repo = DomainPackRepository(db_session)

        # Create
        data = DomainPackCreate(name="Finance", department="Finance")
        created = await repo.create(tenant_id, data)

        # Archive
        result = await repo.archive(tenant_id, created.id)

        assert result is not None
        assert result.status == "deprecated"

    @pytest.mark.asyncio
    async def test_archive_nonexistent_returns_none(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Nonexistent domain pack ID
        WHEN: Archiving
        THEN: Returns None
        """
        repo = DomainPackRepository(db_session)

        result = await repo.archive(tenant_id, uuid4())

        assert result is None


class TestDomainPackRepositorySearch:
    """Tests for searching domain packs"""

    @pytest.mark.asyncio
    async def test_search_by_name_returns_matching_packs(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Multiple domain packs with different names
        WHEN: Searching by name
        THEN: Returns matching packs
        """
        repo = DomainPackRepository(db_session)

        # Create packs
        data1 = DomainPackCreate(name="Finance", department="Finance")
        data2 = DomainPackCreate(name="Legal", department="Legal")
        await repo.create(tenant_id, data1)
        await repo.create(tenant_id, data2)

        # Search
        results = await repo.search(tenant_id, "Finance")

        assert len(results) >= 1
        assert any(pack.name == "Finance" for pack in results)

    @pytest.mark.asyncio
    async def test_search_with_no_matches_returns_empty_list(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: No matching domain packs
        WHEN: Searching
        THEN: Returns empty list
        """
        repo = DomainPackRepository(db_session)

        results = await repo.search(tenant_id, "NonexistentPack")

        assert results == []
