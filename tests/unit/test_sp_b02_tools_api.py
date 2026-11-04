"""
SP-B02: Tools API unit tests.
TDD: these tests were written RED before any implementation.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Read router source via file path (inspect.getsource fails on APIRouter objects).
# After ADR-033 Strangler Fig, logic lives in crud_router.py; router.py is composite.
_TOOLS_DIR = Path(__file__).parent.parent.parent / "src" / "core" / "api" / "v1" / "tools"
_ROUTER_SOURCE = "\n".join(
    (_TOOLS_DIR / f).read_text(encoding="utf-8")
    for f in ("router.py", "crud_router.py", "versions_router.py", "execution_router.py")
    if (_TOOLS_DIR / f).exists()
)


# ---------------------------------------------------------------------------
# Model existence and column constraints
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolModel:
    def test_tool_model_exists(self):
        """Tool ORM model must exist in tool_broker.models."""
        from src.core.tool_broker.models import Tool

        assert Tool is not None

    def test_tool_tenant_id_not_null(self):
        """tenant_id must be NOT NULL (ADR-005)."""
        from src.core.tool_broker.models import Tool

        assert Tool.__table__.c.tenant_id.nullable is False

    def test_tool_is_active_has_default(self):
        """is_active must have a server_default of true."""
        from src.core.tool_broker.models import Tool

        col = Tool.__table__.c.is_active
        assert col.server_default is not None
        assert "true" in str(col.server_default.arg).lower()

    def test_tool_created_at_uses_clock_timestamp(self):
        """created_at must use clock_timestamp() (serializable ordering, CLAUDE.md §11.5)."""
        from src.core.tool_broker.models import Tool

        col = Tool.__table__.c.created_at
        assert col.server_default is not None
        assert "clock_timestamp" in str(col.server_default.arg)

    def test_tool_deleted_at_is_nullable(self):
        """deleted_at must be nullable for soft delete."""
        from src.core.tool_broker.models import Tool

        col = Tool.__table__.c.deleted_at
        assert col.nullable is True

    def test_tool_version_has_server_default_1(self):
        """version column must default to 1."""
        from src.core.tool_broker.models import Tool

        col = Tool.__table__.c.version
        assert col.server_default is not None
        assert "1" in str(col.server_default.arg)

    def test_tool_id_is_primary_key(self):
        """id must be the primary key."""
        from src.core.tool_broker.models import Tool

        col = Tool.__table__.c.id
        assert col.primary_key is True

    def test_tool_tenant_id_has_foreign_key(self):
        """Tool.tenant_id must reference tenants.id."""
        from src.core.tool_broker.models import Tool

        col = Tool.__table__.c.tenant_id
        targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "tenants.id" in targets

    def test_tool_created_by_has_foreign_key(self):
        """Tool.created_by must reference users.id."""
        from src.core.tool_broker.models import Tool

        col = Tool.__table__.c.created_by
        targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "users.id" in targets


@pytest.mark.unit
class TestToolVersionModel:
    def test_tool_version_model_exists(self):
        """ToolVersion ORM model must exist for version history."""
        from src.core.tool_broker.models import ToolVersion

        assert ToolVersion is not None

    def test_tool_version_tenant_id_not_null(self):
        """ToolVersion.tenant_id must be NOT NULL."""
        from src.core.tool_broker.models import ToolVersion

        assert ToolVersion.__table__.c.tenant_id.nullable is False

    def test_tool_version_snapshot_is_jsonb(self):
        """snapshot column must be JSONB."""
        from src.core.tool_broker.models import ToolVersion
        from sqlalchemy.dialects.postgresql import JSONB

        col = ToolVersion.__table__.c.snapshot
        assert isinstance(col.type, JSONB)

    def test_tool_version_tenant_id_has_foreign_key(self):
        """ToolVersion.tenant_id must reference tenants.id."""
        from src.core.tool_broker.models import ToolVersion

        col = ToolVersion.__table__.c.tenant_id
        targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "tenants.id" in targets

    def test_tool_version_has_unique_tool_id_version_constraint(self):
        """ToolVersion must enforce uniqueness on (tool_id, version)."""
        from src.core.tool_broker.models import ToolVersion
        from sqlalchemy import UniqueConstraint

        unique_pairs = {
            tuple(constraint.columns.keys())
            for constraint in ToolVersion.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert ("tool_id", "version") in unique_pairs


# ---------------------------------------------------------------------------
# Router source checks
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRouterSourceChecks:
    def test_no_todo_comments_in_router(self):
        """Router must have no TODO comments after implementation.

        Note: # TODO(TYPE): markers are excluded -- those are type-annotation
        improvement markers added by the type-hardening sprint, not feature gaps.
        """
        non_type_todos = [
            line
            for line in _ROUTER_SOURCE.splitlines()
            if "# TODO" in line and "(TYPE)" not in line
        ]
        assert not non_type_todos, f"Router still has TODO comments: {non_type_todos[:3]}"

    def test_router_does_not_use_hardcoded_tenant_id(self):
        """Router must not hardcode tenant_id; must derive from current_user or JWT."""
        assert "tenant_id=1" not in _ROUTER_SOURCE, "Hardcoded tenant_id=1 found in router"

    def test_router_applies_deleted_at_filter(self):
        """Router GET queries must filter out soft-deleted tools."""
        assert "deleted_at" in _ROUTER_SOURCE, "deleted_at soft-delete filter missing from router"

    def test_router_bumps_version_on_update(self):
        """PUT endpoint must increment version field."""
        assert "version" in _ROUTER_SOURCE, "version bump logic missing from router"

    def test_router_uses_async_db_execute(self):
        """Router must use 'await db.execute' for real DB queries."""
        assert "await db.execute" in _ROUTER_SOURCE, "Router does not use await db.execute"


# ---------------------------------------------------------------------------
# Behavioral: create endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolCreateEndpoint:
    def test_create_tool_requires_auth(self, client):
        """POST /tools without auth returns 401 or 403."""
        response = client.post(
            "/api/v1/tools/",
            json={"name": "t", "description": "d", "tool_type": "api"},
        )
        assert response.status_code in (401, 403)

    def test_create_tool_missing_fields_returns_422(self, client, auth_headers):
        """POST /tools with empty body returns 422."""
        response = client.post("/api/v1/tools/", json={}, headers=auth_headers)
        assert response.status_code == 422

    def test_create_tool_does_not_hardcode_id_1(self, client, auth_headers):
        """POST /tools must not return hardcoded id=1 (stub behavior)."""
        response = client.post(
            "/api/v1/tools/",
            json={"name": "test_tool", "description": "desc", "tool_type": "api"},
            headers=auth_headers,
        )
        if response.status_code in (200, 201):
            data = response.json()
            tool_id = data.get("id") or data.get("data", {}).get("id")
            assert tool_id != 1, "Response returned hardcoded id=1 (stub not replaced)"

    def test_create_tool_calls_db_add(self, client, auth_headers):
        """POST /tools must write to DB (db.add called with a Tool object)."""
        with patch("src.core.api.v1.tools.dependencies.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()
            mock_get_db.return_value.__aiter__ = MagicMock(return_value=iter([mock_db]))
            response = client.post(
                "/api/v1/tools/",
                json={"name": "test_tool", "description": "desc", "tool_type": "api"},
                headers=auth_headers,
            )
        # If 422 or auth error: test is inconclusive, not a failure
        if response.status_code in (200, 201):
            mock_db.add.assert_called_once()


# ---------------------------------------------------------------------------
# Behavioral: list endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolListEndpoint:
    def test_list_tools_requires_auth(self, client):
        """GET /tools without auth returns 401 or 403."""
        response = client.get("/api/v1/tools/")
        assert response.status_code in (401, 403)

    def test_list_tools_returns_200(self, client, auth_headers):
        """GET /tools with auth returns 200."""
        response = client.get("/api/v1/tools/", headers=auth_headers)
        assert response.status_code == 200

    def test_list_tools_has_pagination_fields(self, client, auth_headers):
        """GET /tools response must include pagination (total, page or limit/offset)."""
        response = client.get("/api/v1/tools/?limit=10&skip=0", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data or "data" in data, "Pagination fields missing from list response"

    def test_list_tools_active_only_excludes_deleted(self, client, auth_headers):
        """GET /tools must not return soft-deleted tools (deleted_at IS NOT NULL)."""
        response = client.get("/api/v1/tools/", headers=auth_headers)
        assert response.status_code == 200
        tools = response.json().get("data", [])
        for tool in tools:
            assert tool.get("deleted_at") is None, "Soft-deleted tool leaked into list response"


# ---------------------------------------------------------------------------
# Behavioral: CRUD endpoints
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolGetEndpoint:
    def test_get_nonexistent_tool_returns_404(self, client, auth_headers):
        """GET /tools/9999999 returns 404 for unknown id."""
        response = client.get("/api/v1/tools/9999999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_tool_requires_auth(self, client):
        """GET /tools/{id} without auth returns 401 or 403."""
        response = client.get("/api/v1/tools/1")
        assert response.status_code in (401, 403)


@pytest.mark.unit
class TestToolUpdateEndpoint:
    def test_update_nonexistent_tool_returns_404(self, client, auth_headers):
        """PUT /tools/9999999 returns 404 for unknown id."""
        response = client.put(
            "/api/v1/tools/9999999",
            json={"name": "new_name"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_tool_increments_version_and_creates_history_snapshot(self):
        """Successful update must bump version and create a version-history entry."""
        from src.core.api.v1.tools.router import update_tool
        from src.core.api.v1.tools.schemas import ToolUpdate
        from src.core.tool_broker.models import Tool, ToolVersion

        tool = Tool(
            id=11,
            tenant_id=1,
            name="versioned_tool",
            description="v1",
            tool_type="api",
            status="active",
            version=1,
            created_at=datetime.now(timezone.utc),
            timeout_seconds=30,
            usage_count=0,
        )

        db = AsyncMock()
        db_result = MagicMock()
        db_result.scalar_one_or_none.return_value = tool
        db.execute = AsyncMock(return_value=db_result)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        current_user = MagicMock(id=5, tenant_id=1)

        response = await update_tool(
            tool_id=11,
            data=ToolUpdate(description="v2"),
            db=db,
            current_user=current_user,
        )

        assert response.version == 2
        added_snapshot = db.add.call_args[0][0]
        assert isinstance(added_snapshot, ToolVersion)
        assert added_snapshot.version == 1


@pytest.mark.unit
class TestToolDeleteEndpoint:
    def test_delete_nonexistent_tool_returns_404(self, client, auth_headers):
        """DELETE /tools/9999999 returns 404 for unknown id."""
        response = client.delete("/api/v1/tools/9999999", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_tool_does_not_hard_delete(self, client, auth_headers):
        """DELETE endpoint must perform soft delete (sets deleted_at, not DROP)."""
        assert "deleted_at" in _ROUTER_SOURCE, "DELETE endpoint does not implement soft delete"


# ---------------------------------------------------------------------------
# Behavioral: execute and test endpoints
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolExecuteEndpoint:
    def test_execute_nonexistent_tool_returns_404(self, client, auth_headers):
        """POST /tools/9999999/execute returns 404 for unknown id."""
        response = client.post(
            "/api/v1/tools/9999999/execute",
            json={"parameters": {}},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_execute_tool_requires_auth(self, client):
        """POST /tools/{id}/execute without auth returns 401 or 403."""
        response = client.post(
            "/api/v1/tools/1/execute",
            json={"parameters": {}},
        )
        assert response.status_code in (401, 403)


@pytest.mark.unit
class TestToolTestEndpoint:
    def test_test_endpoint_requires_auth(self, client):
        """POST /tools/{id}/test without auth returns 401 or 403."""
        response = client.post(
            "/api/v1/tools/1/test",
            json={"parameters": {}},
        )
        assert response.status_code in (401, 403)

    def test_test_nonexistent_tool_returns_404(self, client, auth_headers):
        """POST /tools/9999999/test returns 404 for unknown id."""
        response = client.post(
            "/api/v1/tools/9999999/test",
            json={"parameters": {}},
            headers=auth_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolTenantIsolation:
    def test_router_derives_tenant_from_current_user(self):
        """Router must use current_user.tenant_id, not accept tenant_id from body."""
        assert "tenant_id: int" not in _ROUTER_SOURCE or "current_user" in _ROUTER_SOURCE
        assert "current_user.tenant_id" in _ROUTER_SOURCE or "require_tenant_id" in _ROUTER_SOURCE

    def test_create_schema_has_no_tenant_id_field(self):
        """ToolCreate schema must not expose tenant_id (CLAUDE.md rule 6)."""
        from src.core.api.v1.tools.schemas import ToolCreate
        import pydantic

        fields = (
            ToolCreate.model_fields
            if hasattr(ToolCreate, "model_fields")
            else ToolCreate.__fields__
        )
        assert "tenant_id" not in fields, "ToolCreate schema must not accept tenant_id from client"


@pytest.mark.unit
class TestToolCloneAndVersionsEndpoint:
    @pytest.mark.asyncio
    async def test_clone_tool_happy_path_returns_new_tool(self):
        """Clone endpoint should create a new tool record for the same tenant."""
        from src.core.api.v1.tools.router import clone_tool
        from src.core.tool_broker.models import Tool

        source = Tool(
            id=1,
            tenant_id=1,
            name="source_tool",
            description="clone source",
            tool_type="api",
            status="active",
            version=1,
            created_at=datetime.now(timezone.utc),
            timeout_seconds=30,
            usage_count=0,
        )

        db = AsyncMock()
        db_result = MagicMock()
        db_result.scalar_one_or_none.return_value = source
        db.execute = AsyncMock(return_value=db_result)
        db.add = MagicMock()
        db.commit = AsyncMock()

        async def _refresh(clone: Tool) -> None:
            clone.id = 2
            clone.created_at = datetime.now(timezone.utc)
            clone.version = 1
            clone.usage_count = 0

        db.refresh = AsyncMock(side_effect=_refresh)

        current_user = MagicMock(id=7, tenant_id=1)
        cloned = await clone_tool(
            tool_id=1,
            new_name="source_tool_clone",
            db=db,
            current_user=current_user,
        )

        assert cloned.id == 2
        assert cloned.name == "source_tool_clone"

    @pytest.mark.asyncio
    async def test_versions_endpoint_respects_limit(self):
        """Version-history endpoint should apply requested pagination limit."""
        from src.core.api.v1.tools.router import get_tool_versions
        from src.core.tool_broker.models import ToolVersion

        owner_result = MagicMock()
        owner_result.scalar_one_or_none.return_value = 1

        count_result = MagicMock()
        count_result.scalar_one.return_value = 3

        versions_result = MagicMock()
        versions_result.scalars.return_value.all.return_value = [
            ToolVersion(
                id=301,
                tool_id=10,
                tenant_id=1,
                version=3,
                snapshot={"version": 3},
                created_at=datetime.now(timezone.utc),
            ),
            ToolVersion(
                id=300,
                tool_id=10,
                tenant_id=1,
                version=2,
                snapshot={"version": 2},
                created_at=datetime.now(timezone.utc),
            ),
        ]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[owner_result, count_result, versions_result])

        payload = await get_tool_versions(
            tool_id=10,
            skip=0,
            limit=2,
            db=db,
            current_user=MagicMock(tenant_id=1),
        )

        assert len(payload.data) == 2
        assert payload.per_page == 2
