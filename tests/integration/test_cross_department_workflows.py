"""
Integration Tests for Cross-Department Workflows (Sprint 3 - S3.8)

Tests end-to-end scenarios involving multiple domain packs working together.
Validates the full execution graph assembly and inter-pack contract compliance.
"""

from typing import Any, Dict
from uuid import uuid4

import pytest

from src.core.procedures.multi_pack_assembler import MultiPackAssembler
from src.core.procedures.schemas import ExecutionGraph


class TestMultiPackAssembly:
    """Test multi-pack execution graph assembly"""

    @pytest.fixture
    def assembler(self) -> MultiPackAssembler:
        """Provide assembler instance"""
        return MultiPackAssembler()

    @pytest.fixture
    def tenant_id(self) -> str:
        """Mock tenant ID"""
        return uuid4()

    @pytest.mark.asyncio
    async def test_simple_two_pack_assembly(self, assembler: MultiPackAssembler, tenant_id: str):
        """Test assembling graph with 2 packs"""
        pack_configs = [
            {
                "pack_id": uuid4(),
                "domain": "finance",
                "order": 1,
                "name": "Finance Budget Check",
            },
            {
                "pack_id": uuid4(),
                "domain": "legal",
                "order": 2,
                "name": "Legal Review",
                "depends_on": ["finance"],
            },
        ]

        graph = await assembler.build_execution_graph(tenant_id, pack_configs)

        assert isinstance(graph, ExecutionGraph)
        assert graph.tenant_id == tenant_id
        assert len(graph.segments) == 2
        assert graph.segments[0].domain == "finance"
        assert graph.segments[1].domain == "legal"
        assert "finance" in graph.segments[1].dependencies

    @pytest.mark.asyncio
    async def test_three_pack_procurement_flow(self, assembler: MultiPackAssembler, tenant_id: str):
        """Test F2 flagship: Finance → Legal → Ops procurement flow"""
        pack_configs = [
            {
                "pack_id": uuid4(),
                "domain": "finance",
                "order": 1,
                "name": "Finance: Budget Check",
                "depends_on": [],
            },
            {
                "pack_id": uuid4(),
                "domain": "legal",
                "order": 2,
                "name": "Legal: Contract Review",
                "depends_on": ["finance"],
            },
            {
                "pack_id": uuid4(),
                "domain": "ops",
                "order": 3,
                "name": "Ops: Procurement",
                "depends_on": ["finance", "legal"],
            },
        ]

        graph = await assembler.build_execution_graph(tenant_id, pack_configs)

        # Validate graph structure
        assert len(graph.segments) == 3
        assert graph.segments[0].domain == "finance"
        assert graph.segments[1].domain == "legal"
        assert graph.segments[2].domain == "ops"

        # Validate dependencies
        assert len(graph.segments[0].dependencies) == 0
        assert "finance" in graph.segments[1].dependencies
        assert "finance" in graph.segments[2].dependencies
        assert "legal" in graph.segments[2].dependencies

        # Validate each segment has steps
        for segment in graph.segments:
            assert len(segment.steps) > 0

    @pytest.mark.asyncio
    async def test_cross_tenant_access_blocked(self, assembler: MultiPackAssembler):
        """Test that cross-tenant access is blocked"""
        tenant_a = uuid4()
        tenant_b = uuid4()

        pack_configs = [
            {
                "pack_id": uuid4(),
                "domain": "finance",
                "order": 1,
                "name": "Finance Pack",
                "tenant_id": tenant_b,  # Different tenant!
            }
        ]

        with pytest.raises(ValueError, match="Cross-tenant access not allowed"):
            await assembler.build_execution_graph(tenant_a, pack_configs)

    @pytest.mark.asyncio
    async def test_missing_required_field_raises_error(
        self, assembler: MultiPackAssembler, tenant_id: str
    ):
        """Test that missing required config fields raise errors"""
        # Missing pack_id
        with pytest.raises(ValueError, match="pack_id is required"):
            await assembler.build_execution_graph(
                tenant_id, [{"domain": "finance", "order": 1, "name": "Test"}]
            )

        # Missing domain
        with pytest.raises(ValueError, match="domain is required"):
            await assembler.build_execution_graph(
                tenant_id, [{"pack_id": uuid4(), "order": 1, "name": "Test"}]
            )

        # Missing order
        with pytest.raises(ValueError, match="order is required"):
            await assembler.build_execution_graph(
                tenant_id, [{"pack_id": uuid4(), "domain": "finance", "name": "Test"}]
            )

    @pytest.mark.asyncio
    async def test_execution_order_respected(self, assembler: MultiPackAssembler, tenant_id: str):
        """Test that packs are ordered correctly even if configs are unordered"""
        pack_configs = [
            {"pack_id": uuid4(), "domain": "ops", "order": 3, "name": "Ops"},
            {"pack_id": uuid4(), "domain": "finance", "order": 1, "name": "Finance"},
            {"pack_id": uuid4(), "domain": "legal", "order": 2, "name": "Legal"},
        ]

        graph = await assembler.build_execution_graph(tenant_id, pack_configs)

        assert graph.segments[0].domain == "finance"
        assert graph.segments[1].domain == "legal"
        assert graph.segments[2].domain == "ops"

    @pytest.mark.asyncio
    async def test_estimated_duration_aggregated(
        self, assembler: MultiPackAssembler, tenant_id: str
    ):
        """Test that estimated durations are summed correctly"""
        pack_configs = [
            {"pack_id": uuid4(), "domain": "finance", "order": 1, "name": "Finance"},
            {"pack_id": uuid4(), "domain": "legal", "order": 2, "name": "Legal"},
        ]

        graph = await assembler.build_execution_graph(tenant_id, pack_configs)

        # Each segment estimates 2 minutes (mock value)
        assert graph.estimated_duration_minutes == 4  # 2 segments * 2 min


class TestCrossDepartmentEndToEnd:
    """End-to-end integration tests for cross-department scenarios"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invoice_approval_flow_f1(self):
        """
        Test F1 flagship: Invoice Approval
        Single department (Finance) but multi-step with approval gates
        """
        # This would be a full integration test with actual database
        # For now, we test the structure
        assembler = MultiPackAssembler()
        tenant_id = uuid4()

        # Invoice approval involves only finance pack but multiple steps
        pack_configs = [
            {
                "pack_id": uuid4(),
                "domain": "finance",
                "order": 1,
                "name": "Invoice Approval Process",
                "depends_on": [],
            }
        ]

        graph = await assembler.build_execution_graph(tenant_id, pack_configs)

        assert len(graph.segments) == 1
        assert graph.segments[0].domain == "finance"
        # In production, would verify approval gates in steps

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_onboarding_flow_f3(self):
        """
        Test F3 flagship: Employee Onboarding
        HR → IT (parallel) → Legal (parallel) → HR Training
        """
        assembler = MultiPackAssembler()
        tenant_id = uuid4()

        pack_configs = [
            {
                "pack_id": uuid4(),
                "domain": "hr",
                "order": 1,
                "name": "HR: Create Profile",
            },
            {
                "pack_id": uuid4(),
                "domain": "it",
                "order": 2,
                "name": "IT: Setup Accounts",
                "depends_on": ["hr"],
            },
            {
                "pack_id": uuid4(),
                "domain": "legal",
                "order": 2,
                "name": "Legal: Sign Documents",
                "depends_on": ["hr"],
            },
            {
                "pack_id": uuid4(),
                "domain": "hr",
                "order": 3,
                "name": "HR: Assign Training",
                "depends_on": ["it", "legal"],
            },
        ]

        graph = await assembler.build_execution_graph(tenant_id, pack_configs)

        # Verify 4 segments
        assert len(graph.segments) == 4

        # Verify IT and Legal can run in parallel (both depend only on HR)
        it_segment = next(s for s in graph.segments if s.domain == "it")
        legal_segment = next(s for s in graph.segments if s.domain == "legal")
        assert it_segment.dependencies == ["hr"]
        assert legal_segment.dependencies == ["hr"]

        # Verify final HR step depends on both
        final_hr = [s for s in graph.segments if s.domain == "hr" and s.order == 3][0]
        assert "it" in final_hr.dependencies
        assert "legal" in final_hr.dependencies


class TestTenantIsolation:
    """Test tenant isolation in multi-pack scenarios"""

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_use_tenant_b_packs(self):
        """Verify tenant isolation at graph assembly level"""
        assembler = MultiPackAssembler()
        tenant_a = uuid4()
        tenant_b = uuid4()

        # Tenant A tries to use Tenant B's pack
        pack_configs = [
            {
                "pack_id": uuid4(),
                "domain": "finance",
                "order": 1,
                "name": "Finance Pack",
                "tenant_id": tenant_b,  # Belongs to different tenant
            }
        ]

        with pytest.raises(ValueError, match="Cross-tenant access not allowed"):
            await assembler.build_execution_graph(tenant_a, pack_configs)

    @pytest.mark.asyncio
    async def test_platform_templates_accessible_to_all_tenants(self):
        """Verify platform templates (tenant_id=None) are accessible"""
        # Platform templates should be accessible regardless of tenant
        # This would be tested with actual repository in integration tests
        pass  # Placeholder for future implementation
