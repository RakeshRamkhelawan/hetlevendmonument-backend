"""
Unit tests for ProcedureMetadataRepository
Tests for creation, search by intent tags, and filtering by domain pack
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.procedures.models import DomainPack, ProcedureMetadata
from src.core.procedures.procedures_repository import ProcedureMetadataRepository
from src.core.procedures.schemas import ProcedureMetadataCreate


@pytest.fixture
def tenant_id():
    """Fixed tenant ID for tests"""
    return 1


@pytest.fixture
def other_tenant_id():
    """different tenant for cross-tenant tests"""
    return 2


async def create_domain_pack(db_session: AsyncSession, tenant_id: str, name: str = "Finance"):
    """Helper to create a domain pack for tests"""
    from src.core.procedures.domain_pack_repository import DomainPackRepository
    from src.core.procedures.schemas import DomainPackCreate

    repo = DomainPackRepository(db_session)
    data = DomainPackCreate(name=name, department=name)
    pack = await repo.create(tenant_id, data)
    await db_session.flush()
    return pack


class TestProcedureMetadataRepositoryCreate:
    """Tests for creating procedure metadata"""

    @pytest.mark.asyncio
    async def test_create_procedure_metadata_links_flow_and_domain_pack(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: Valid ProcedureMetadataCreate data with flow_id and domain_pack_id
        WHEN: Creating procedure metadata
        THEN: Metadata is created and links are established
        """
        pack = await create_domain_pack(db_session, tenant_id)
        flow_id = uuid4()

        repo = ProcedureMetadataRepository(db_session)
        data = ProcedureMetadataCreate(
            flow_id=flow_id,
            domain_pack_id=pack.id,
            category="invoice_approval",
            intent_tags=["finance", "approval"],
            prerequisites=["budget_approval"],
        )

        result = await repo.create(tenant_id, data)

        assert result.id is not None
        assert result.tenant_id == tenant_id
        assert result.flow_id == flow_id
        assert result.domain_pack_id == pack.id
        assert result.category == "invoice_approval"
        assert result.intent_tags == ["finance", "approval"]
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_create_procedure_metadata_with_minimal_data(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: Minimal required fields
        WHEN: Creating procedure metadata
        THEN: Created with defaults
        """
        pack = await create_domain_pack(db_session, tenant_id)
        flow_id = uuid4()

        repo = ProcedureMetadataRepository(db_session)
        data = ProcedureMetadataCreate(
            flow_id=flow_id, domain_pack_id=pack.id, category="test_procedure"
        )

        result = await repo.create(tenant_id, data)

        assert result.category == "test_procedure"
        assert result.intent_tags == []
        assert result.is_platform_template is False


class TestProcedureMetadataRepositorySearch:
    """Tests for searching procedures by intent tags"""

    @pytest.mark.asyncio
    async def test_search_by_intent_tags_returns_matching_procedures(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: Multiple procedures with different tags
        WHEN: Searching by specific tag
        THEN: Returns only procedures with that tag
        """
        pack = await create_domain_pack(db_session, tenant_id)
        repo = ProcedureMetadataRepository(db_session)

        # Create procedures with different tags
        data1 = ProcedureMetadataCreate(
            flow_id=uuid4(),
            domain_pack_id=pack.id,
            category="invoice_approval",
            intent_tags=["finance", "approval"],
        )
        data2 = ProcedureMetadataCreate(
            flow_id=uuid4(),
            domain_pack_id=pack.id,
            category="payment_request",
            intent_tags=["finance", "payment"],
        )
        data3 = ProcedureMetadataCreate(
            flow_id=uuid4(),
            domain_pack_id=pack.id,
            category="hr_request",
            intent_tags=["hr", "request"],
        )

        await repo.create(tenant_id, data1)
        await repo.create(tenant_id, data2)
        await repo.create(tenant_id, data3)

        # Search for "approval" tag
        results = await repo.search_by_intent_tags(tenant_id, ["approval"])

        assert len(results) >= 1
        assert any(p.category == "invoice_approval" for p in results)

    @pytest.mark.asyncio
    async def test_search_by_intent_tags_empty_result_returns_empty_list(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: No procedures with requested tag
        WHEN: Searching
        THEN: Returns empty list (no exception)
        """
        repo = ProcedureMetadataRepository(db_session)

        results = await repo.search_by_intent_tags(tenant_id, ["nonexistent_tag"])

        assert results == []

    @pytest.mark.asyncio
    async def test_search_by_multiple_tags_returns_union(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Multiple procedures with various tags
        WHEN: Searching with multiple tags
        THEN: Returns procedures matching ANY of the tags (union)
        """
        pack = await create_domain_pack(db_session, tenant_id)
        repo = ProcedureMetadataRepository(db_session)

        # Create procedures
        data1 = ProcedureMetadataCreate(
            flow_id=uuid4(),
            domain_pack_id=pack.id,
            category="proc1",
            intent_tags=["finance"],
        )
        data2 = ProcedureMetadataCreate(
            flow_id=uuid4(),
            domain_pack_id=pack.id,
            category="proc2",
            intent_tags=["hr"],
        )

        await repo.create(tenant_id, data1)
        await repo.create(tenant_id, data2)

        # Search for either finance or hr
        results = await repo.search_by_intent_tags(tenant_id, ["finance", "hr"])

        assert len(results) >= 2


class TestProcedureMetadataRepositoryFilter:
    """Tests for filtering by domain pack"""

    @pytest.mark.asyncio
    async def test_list_by_domain_pack_filters_correctly(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Multiple procedures in different domain packs
        WHEN: Listing by specific domain pack
        THEN: Returns only procedures from that pack
        """
        repo = ProcedureMetadataRepository(db_session)

        # Create two domain packs
        pack1 = await create_domain_pack(db_session, tenant_id, "Finance")
        pack2 = await create_domain_pack(db_session, tenant_id, "Legal")

        # Create procedures for each pack
        data1 = ProcedureMetadataCreate(
            flow_id=uuid4(), domain_pack_id=pack1.id, category="invoice"
        )
        data2 = ProcedureMetadataCreate(
            flow_id=uuid4(), domain_pack_id=pack2.id, category="contract"
        )

        await repo.create(tenant_id, data1)
        await repo.create(tenant_id, data2)

        # List procedures in pack1
        results = await repo.list_by_domain_pack(tenant_id, pack1.id)

        assert len(results) >= 1
        assert all(p.domain_pack_id == pack1.id for p in results)

    @pytest.mark.asyncio
    async def test_list_by_domain_pack_empty_returns_empty_list(
        self, db_session: AsyncSession, tenant_id
    ):
        """
        GIVEN: Domain pack with no procedures
        WHEN: Listing procedures
        THEN: Returns empty list
        """
        pack = await create_domain_pack(db_session, tenant_id)
        repo = ProcedureMetadataRepository(db_session)

        results = await repo.list_by_domain_pack(tenant_id, pack.id)

        assert results == []


class TestProcedureMetadataRepositoryRead:
    """Tests for reading procedure metadata"""

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Existing procedure metadata
        WHEN: Getting by ID and tenant
        THEN: Returns the procedure
        """
        pack = await create_domain_pack(db_session, tenant_id)
        repo = ProcedureMetadataRepository(db_session)

        data = ProcedureMetadataCreate(flow_id=uuid4(), domain_pack_id=pack.id, category="test")
        created = await repo.create(tenant_id, data)

        result = await repo.get_by_id(tenant_id, created.id)

        assert result is not None
        assert result.id == created.id
        assert result.flow_id == created.flow_id

    @pytest.mark.asyncio
    async def test_get_by_id_wrong_tenant_returns_none(
        self, db_session: AsyncSession, tenant_id, other_tenant_id
    ):
        """
        GIVEN: Procedure metadata for tenant A
        WHEN: Requesting with tenant B
        THEN: Returns None (tenant scoping)
        """
        pack = await create_domain_pack(db_session, tenant_id)
        repo = ProcedureMetadataRepository(db_session)

        data = ProcedureMetadataCreate(flow_id=uuid4(), domain_pack_id=pack.id, category="test")
        created = await repo.create(tenant_id, data)

        result = await repo.get_by_id(other_tenant_id, created.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_flow_id_returns_metadata(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Procedure metadata with specific flow_id
        WHEN: Looking up by flow_id and tenant
        THEN: Returns the metadata
        """
        pack = await create_domain_pack(db_session, tenant_id)
        flow_id = uuid4()
        repo = ProcedureMetadataRepository(db_session)

        data = ProcedureMetadataCreate(flow_id=flow_id, domain_pack_id=pack.id, category="test")
        await repo.create(tenant_id, data)

        result = await repo.get_by_flow_id(tenant_id, flow_id)

        assert result is not None
        assert result.flow_id == flow_id


class TestProcedureMetadataRepositoryUpdate:
    """Tests for updating procedure metadata"""

    @pytest.mark.asyncio
    async def test_update_procedure_metadata_success(self, db_session: AsyncSession, tenant_id):
        """
        GIVEN: Existing procedure metadata
        WHEN: Updating fields
        THEN: Updates are applied
        """
        pack = await create_domain_pack(db_session, tenant_id)
        repo = ProcedureMetadataRepository(db_session)

        data = ProcedureMetadataCreate(flow_id=uuid4(), domain_pack_id=pack.id, category="test")
        created = await repo.create(tenant_id, data)

        from src.core.procedures.schemas import ProcedureMetadataUpdate

        update_data = ProcedureMetadataUpdate(
            description="Updated description", intent_tags=["new", "tags"]
        )
        result = await repo.update(tenant_id, created.id, update_data)

        assert result is not None
        assert result.description == "Updated description"
        assert result.intent_tags == ["new", "tags"]
