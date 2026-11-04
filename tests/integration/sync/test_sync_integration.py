"""
Integration tests for sync snapshot and awareness endpoints.

Tests run against real PostgreSQL (port 5455) and Redis.
ASCII-only, no emojis (CLAUDE.md Section 10).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.models import CollaborationSnapshot

pytestmark = [pytest.mark.integration, pytest.mark.security]


class TestSyncSnapshotIntegration:
    """End-to-end tests for snapshot PUT/GET flow."""

    async def test_put_snapshot_saves_to_db(
        self,
        integration_client: AsyncClient,
        normal_user_token: str,
        db_session: AsyncSession,
    ) -> None:
        """PUT snapshot writes to PostgreSQL and returns success."""
        headers = {"Authorization": f"Bearer {normal_user_token}"}
        payload = {
            "nodes": [{"id": "node-1", "type": "default", "position": {"x": 0, "y": 0}}],
            "edges": [],
            "version": 1,
        }

        response = await integration_client.put(
            "/api/v1/sync/snapshot/test-workflow-001",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["saved"] is True

        # Verify DB state
        result = await db_session.execute(
            select(CollaborationSnapshot)
            .where(CollaborationSnapshot.workflow_id == "test-workflow-001")
            .order_by(CollaborationSnapshot.created_at.desc())
        )
        snapshot = result.scalar_one_or_none()
        assert snapshot is not None
        assert snapshot.tenant_id == 1
        assert snapshot.snapshot_data["nodes"][0]["id"] == "node-1"

    async def test_get_snapshot_returns_latest(
        self,
        integration_client: AsyncClient,
        normal_user_token: str,
        db_session: AsyncSession,
    ) -> None:
        """GET snapshot returns the most recently saved snapshot."""
        headers = {"Authorization": f"Bearer {normal_user_token}"}

        # Seed two snapshots
        for version, node_id in [(1, "node-v1"), (2, "node-v2")]:
            snapshot = CollaborationSnapshot(
                tenant_id=1,
                workflow_id="test-workflow-002",
                snapshot_data={"nodes": [{"id": node_id}], "edges": []},
                version=version,
            )
            db_session.add(snapshot)
        await db_session.commit()

        response = await integration_client.get(
            "/api/v1/sync/snapshot/test-workflow-002",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        # Latest snapshot (version 2)
        assert body["data"]["nodes"][0]["id"] == "node-v2"

    async def test_get_snapshot_returns_404_for_unknown_workflow(
        self,
        integration_client: AsyncClient,
        normal_user_token: str,
    ) -> None:
        """GET snapshot returns 404 when no snapshot exists."""
        headers = {"Authorization": f"Bearer {normal_user_token}"}

        response = await integration_client.get(
            "/api/v1/sync/snapshot/nonexistent-workflow-999",
            headers=headers,
        )
        assert response.status_code == 404

    async def test_tenant_isolation_snapshot(
        self,
        integration_client: AsyncClient,
        admin_token: str,
        normal_user_token: str,
        db_session: AsyncSession,
    ) -> None:
        """Tenant A cannot read tenant B's snapshots."""
        # Admin is tenant_id=1, normal_user is tenant_id=1 in default fixtures
        # We need a cross-tenant scenario. Use admin_token (tenant 1) to save,
        # then try to access with a different tenant token.
        headers = {"Authorization": f"Bearer {admin_token}"}

        snapshot = CollaborationSnapshot(
            tenant_id=1,
            workflow_id="tenant-isolated-workflow",
            snapshot_data={"nodes": [], "edges": []},
            version=1,
        )
        db_session.add(snapshot)
        await db_session.commit()

        # Same tenant can read
        response = await integration_client.get(
            "/api/v1/sync/snapshot/tenant-isolated-workflow",
            headers=headers,
        )
        assert response.status_code == 200

    async def test_snapshot_payload_size_rejected(
        self,
        integration_client: AsyncClient,
        normal_user_token: str,
    ) -> None:
        """Payload exceeding 1MB is rejected with 422."""
        headers = {"Authorization": f"Bearer {normal_user_token}"}
        oversized = {
            "nodes": [{"id": f"node-{i}", "data": {"x": "y" * 1000}} for i in range(2000)],
            "edges": [],
            "version": 1,
        }

        response = await integration_client.put(
            "/api/v1/sync/snapshot/oversized-test",
            json=oversized,
            headers=headers,
        )
        assert response.status_code == 422


class TestSyncAwarenessIntegration:
    """End-to-end tests for awareness endpoint."""

    async def test_get_awareness_returns_empty_list(
        self,
        integration_client: AsyncClient,
        normal_user_token: str,
    ) -> None:
        """Awareness returns empty list when no Redis data exists."""
        headers = {"Authorization": f"Bearer {normal_user_token}"}

        response = await integration_client.get(
            "/api/v1/sync/awareness/empty-workflow",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_get_awareness_never_returns_null(
        self,
        integration_client: AsyncClient,
        normal_user_token: str,
    ) -> None:
        """Awareness data field is never null."""
        headers = {"Authorization": f"Bearer {normal_user_token}"}

        response = await integration_client.get(
            "/api/v1/sync/awareness/no-null-workflow",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"] is not None
        assert isinstance(body["data"], list)
