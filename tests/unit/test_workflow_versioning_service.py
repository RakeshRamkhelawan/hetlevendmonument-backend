"""
Workflow Versioning Service Unit Tests
========================================

Tests for workflow snapshot, history, and rollback functionality.

Test Classes:
- TestSaveVersion: Version creation and metadata
- TestGetVersionHistory: Version retrieval and ordering
- TestGetVersion: Specific version retrieval
- TestRollback: Rollback and version restoration
- TestCompareVersions: Version comparison logic
- TestEdgeCases: Edge cases and error handling
"""

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.workflow_refinement_endpoints import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
)
from src.core.models.workflow_version_models import WorkflowChangeLog, WorkflowVersion
from src.core.services.workflow_versioning_service import WorkflowVersioningService


@pytest.mark.asyncio
class TestSaveVersion:
    """Tests for saving new workflow versions."""

    async def test_save_version_creates_new_version(
        self, async_session: AsyncSession, isolated_tenant
    ):
        """Verify version creation with proper metadata."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up any existing versions for this workflow
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_test_1")
            )
        )
        await async_session.commit()

        # Create workflow
        workflow = WorkflowDefinition(
            nodes=[
                WorkflowNode(id="n1", name="Start", type="start", x=0, y=0, data={}),
                WorkflowNode(id="n2", name="Process", type="process", x=100, y=0, data={}),
            ],
            edges=[WorkflowEdge(id="e1", source="n1", target="n2", type="smoothstep")],
        )

        # Save version
        version = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_test_1",
            name="Test Workflow",
            workflow=workflow,
            created_by=user_id,
            change_description="Initial version",
            tags=["initial"],
        )

        # Verify
        assert version is not None
        assert version.version_number == 1
        assert version.tenant_id == tenant_id
        assert version.workflow_id == "wf_test_1"
        assert version.name == "Test Workflow"
        assert version.created_by == user_id
        assert version.change_description == "Initial version"
        assert version.tags == ["initial"]
        assert len(version.workflow_spec["nodes"]) == 2
        assert len(version.workflow_spec["edges"]) == 1

    @pytest.mark.skip
    async def test_save_version_increments_number(
        self, async_session: AsyncSession, isolated_tenant
    ):
        """Verify sequential version numbering."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_test_2")
            )
        )
        await async_session.commit()

        workflow = WorkflowDefinition(nodes=[], edges=[])

        # Create version 1
        v1 = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_test_2",
            name="Test",
            workflow=workflow,
            created_by=user_id,
        )
        assert v1.version_number == 1

        # Create version 2
        v2 = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_test_2",
            name="Test",
            workflow=workflow,
            created_by=user_id,
        )
        assert v2.version_number == 2

        # Create version 3
        v3 = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_test_2",
            name="Test",
            workflow=workflow,
            created_by=user_id,
        )
        assert v3.version_number == 3

    async def test_save_version_stores_workflow_spec(
        self, async_session: AsyncSession, isolated_tenant
    ):
        """Verify workflow specification is properly stored."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_test_3")
            )
        )
        await async_session.commit()

        # Create complex workflow
        workflow = WorkflowDefinition(
            nodes=[
                WorkflowNode(id="n1", name="A", type="start", x=0, y=0, data={"key": "value"}),
                WorkflowNode(id="n2", name="B", type="process", x=100, y=0, data={}),
                WorkflowNode(id="n3", name="C", type="end", x=200, y=0, data={}),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2", type="smoothstep"),
                WorkflowEdge(id="e2", source="n2", target="n3", type="smoothstep"),
            ],
        )

        version = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_test_3",
            name="Complex",
            workflow=workflow,
            created_by=user_id,
        )

        # Verify spec
        spec = version.workflow_spec
        assert len(spec["nodes"]) == 3
        assert len(spec["edges"]) == 2
        assert spec["nodes"][0]["id"] == "n1"
        assert spec["nodes"][0]["data"] == {"key": "value"}

    async def test_save_version_tenant_isolation(
        self, async_session: AsyncSession, isolated_tenant
    ):
        """Verify multi-tenant isolation in versions."""
        tenant_id_1 = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Create a different tenant
        from src.core.models.rbac_models import Tenant
        from tests.conftest import TenantFactory

        tenant_id_2 = TenantFactory.next_id()
        tenant_2 = Tenant(
            id=tenant_id_2, name=f"Tenant {tenant_id_2}", slug=f"tenant-{tenant_id_2}"
        )
        async_session.add(tenant_2)
        await async_session.commit()

        # Clean up both tenants
        for tid in [tenant_id_1, tenant_id_2]:
            await async_session.execute(
                delete(WorkflowVersion).where(
                    (WorkflowVersion.tenant_id == tid)
                    & (WorkflowVersion.workflow_id == "wf_shared")
                )
            )
        await async_session.commit()

        workflow = WorkflowDefinition(nodes=[], edges=[])

        # Save version in tenant 1
        v1 = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id_1,
            workflow_id="wf_shared",
            name="Test",
            workflow=workflow,
            created_by=user_id,
        )

        # Save version in tenant 2
        v2 = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=20001,
            workflow_id="wf_shared",
            name="Test",
            workflow=workflow,
            created_by=user_id,
        )

        # Both should be version 1 (separate version tracks per tenant)
        assert v1.version_number == 1
        assert v2.version_number == 1
        assert v1.tenant_id == tenant_id_1
        assert v2.tenant_id == 20001


@pytest.mark.asyncio
class TestGetVersionHistory:
    """Tests for retrieving version history."""

    @pytest.mark.skip
    async def test_get_version_history_multiple_versions(
        self, async_session: AsyncSession, isolated_tenant
    ):
        """Verify history ordering (newest first)."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_hist")
            )
        )
        await async_session.commit()

        workflow = WorkflowDefinition(nodes=[], edges=[])

        # Create 3 versions
        for i in range(1, 4):
            await WorkflowVersioningService.save_version(
                db=async_session,
                tenant_id=tenant_id,
                workflow_id="wf_hist",
                name=f"Version {i}",
                workflow=workflow,
                created_by=user_id,
                change_description=f"Change {i}",
            )

        # Get history
        versions = await WorkflowVersioningService.get_version_history(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_hist",
            limit=10,
        )

        # Verify ordering (newest first)
        assert len(versions) == 3
        assert versions[0].version_number == 3
        assert versions[1].version_number == 2
        assert versions[2].version_number == 1

    @pytest.mark.skip
    async def test_get_version_history_limit(self, async_session: AsyncSession, isolated_tenant):
        """Verify limit parameter works."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_limit")
            )
        )
        await async_session.commit()

        workflow = WorkflowDefinition(nodes=[], edges=[])

        # Create 5 versions
        for i in range(1, 6):
            await WorkflowVersioningService.save_version(
                db=async_session,
                tenant_id=tenant_id,
                workflow_id="wf_limit",
                name=f"v{i}",
                workflow=workflow,
                created_by=user_id,
            )

        # Get with limit
        versions = await WorkflowVersioningService.get_version_history(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_limit",
            limit=2,
        )

        assert len(versions) == 2
        assert versions[0].version_number == 5
        assert versions[1].version_number == 4

    async def test_get_version_history_empty(self, async_session: AsyncSession, isolated_tenant):
        """Verify empty history returns empty list."""
        tenant_id = isolated_tenant["tenant_id"]

        versions = await WorkflowVersioningService.get_version_history(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_nonexistent",
            limit=10,
        )

        assert versions == []


@pytest.mark.asyncio
class TestGetVersion:
    """Tests for retrieving specific versions."""

    @pytest.mark.skip
    async def test_get_specific_version(self, async_session: AsyncSession, isolated_tenant):
        """Verify retrieval of specific version."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_specific")
            )
        )
        await async_session.commit()

        workflow = WorkflowDefinition(
            nodes=[WorkflowNode(id="n1", name="Node", type="process", x=0, y=0, data={})],
            edges=[],
        )

        # Create version
        saved = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_specific",
            name="Test",
            workflow=workflow,
            created_by=user_id,
        )

        # Retrieve it
        retrieved = await WorkflowVersioningService.get_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_specific",
            version_number=1,
        )

        assert retrieved is not None
        assert retrieved.version_number == 1
        assert retrieved.workflow_id == "wf_specific"

    async def test_get_version_not_found(self, async_session: AsyncSession, isolated_tenant):
        """Verify None is returned for non-existent version."""
        tenant_id = isolated_tenant["tenant_id"]

        version = await WorkflowVersioningService.get_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_none",
            version_number=999,
        )

        assert version is None


@pytest.mark.asyncio
class TestRollback:
    """Tests for rollback functionality."""

    @pytest.mark.skip
    async def test_rollback_to_previous_version(self, async_session: AsyncSession, isolated_tenant):
        """Verify rollback creates new version with restored content."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_rollback")
            )
        )
        await async_session.commit()

        # Create version 1 with 1 node
        workflow_v1 = WorkflowDefinition(
            nodes=[WorkflowNode(id="n1", name="Node 1", type="start", x=0, y=0, data={})],
            edges=[],
        )
        await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_rollback",
            name="Initial",
            workflow=workflow_v1,
            created_by=user_id,
        )

        # Create version 2 with 2 nodes
        workflow_v2 = WorkflowDefinition(
            nodes=[
                WorkflowNode(id="n1", name="Node 1", type="start", x=0, y=0, data={}),
                WorkflowNode(id="n2", name="Node 2", type="end", x=100, y=0, data={}),
            ],
            edges=[],
        )
        await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_rollback",
            name="Updated",
            workflow=workflow_v2,
            created_by=user_id,
        )

        # Rollback to version 1
        new_version = await WorkflowVersioningService.rollback_to_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_rollback",
            target_version=1,
            rolled_back_by=user_id,
        )

        # Verify new version created with v1 content
        assert new_version.version_number == 3
        assert len(new_version.workflow_spec["nodes"]) == 1  # v1 had 1 node
        assert "rollback" in new_version.tags

    async def test_rollback_version_not_found(self, async_session: AsyncSession, isolated_tenant):
        """Verify error when rolling back to non-existent version."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        with pytest.raises(ValueError, match="not found"):
            await WorkflowVersioningService.rollback_to_version(
                db=async_session,
                tenant_id=tenant_id,
                workflow_id="wf_none",
                target_version=999,
                rolled_back_by=user_id,
            )


@pytest.mark.asyncio
class TestCompareVersions:
    """Tests for version comparison."""

    @pytest.mark.skip
    async def test_compare_versions_node_changes(
        self, async_session: AsyncSession, isolated_tenant
    ):
        """Verify node count changes are tracked."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_compare")
            )
        )
        await async_session.commit()

        # Create version 1: 2 nodes
        workflow_v1 = WorkflowDefinition(
            nodes=[
                WorkflowNode(id="n1", name="N1", type="start", x=0, y=0, data={}),
                WorkflowNode(id="n2", name="N2", type="end", x=100, y=0, data={}),
            ],
            edges=[],
        )
        await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_compare",
            name="V1",
            workflow=workflow_v1,
            created_by=user_id,
        )

        # Create version 2: 3 nodes
        workflow_v2 = WorkflowDefinition(
            nodes=[
                WorkflowNode(id="n1", name="N1", type="start", x=0, y=0, data={}),
                WorkflowNode(id="n2", name="N2", type="process", x=100, y=0, data={}),
                WorkflowNode(id="n3", name="N3", type="end", x=200, y=0, data={}),
            ],
            edges=[],
        )
        await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_compare",
            name="V2",
            workflow=workflow_v2,
            created_by=user_id,
        )

        # Compare
        comparison = await WorkflowVersioningService.compare_versions(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_compare",
            version1=1,
            version2=2,
        )

        assert comparison["nodes_change"] == 1  # 3 - 2 = 1
        assert comparison["edges_change"] == 0

    async def test_compare_versions_not_found(self, async_session: AsyncSession, isolated_tenant):
        """Verify error when comparing non-existent versions."""
        tenant_id = isolated_tenant["tenant_id"]

        with pytest.raises(ValueError, match="not found"):
            await WorkflowVersioningService.compare_versions(
                db=async_session,
                tenant_id=tenant_id,
                workflow_id="wf_none",
                version1=1,
                version2=2,
            )


@pytest.mark.asyncio
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_save_empty_workflow(self, async_session: AsyncSession, isolated_tenant):
        """Verify empty workflow can be saved."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_empty")
            )
        )
        await async_session.commit()

        workflow = WorkflowDefinition(nodes=[], edges=[])

        version = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_empty",
            name="Empty",
            workflow=workflow,
            created_by=user_id,
        )

        assert version is not None
        assert len(version.workflow_spec["nodes"]) == 0
        assert len(version.workflow_spec["edges"]) == 0

    async def test_large_workflow_versioning(self, async_session: AsyncSession, isolated_tenant):
        """Verify handling of large workflows."""
        tenant_id = isolated_tenant["tenant_id"]
        user_id = isolated_tenant["user_id"]

        # Clean up
        await async_session.execute(
            delete(WorkflowVersion).where(
                (WorkflowVersion.tenant_id == tenant_id)
                & (WorkflowVersion.workflow_id == "wf_large")
            )
        )
        await async_session.commit()

        # Create large workflow: 50 nodes
        nodes = [
            WorkflowNode(
                id=f"n{i}",
                name=f"Node {i}",
                type="process",
                x=i * 100,
                y=0,
                data={"index": i},
            )
            for i in range(50)
        ]
        edges = [
            WorkflowEdge(id=f"e{i}", source=f"n{i}", target=f"n{i+1}", type="smoothstep")
            for i in range(49)
        ]
        workflow = WorkflowDefinition(nodes=nodes, edges=edges)

        version = await WorkflowVersioningService.save_version(
            db=async_session,
            tenant_id=tenant_id,
            workflow_id="wf_large",
            name="Large",
            workflow=workflow,
            created_by=user_id,
        )

        assert len(version.workflow_spec["nodes"]) == 50
        assert len(version.workflow_spec["edges"]) == 49
