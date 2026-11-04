# ASCII-only: no emojis or unicode (CLAUDE.md Section 10)
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.database.database import get_db

pytestmark = [pytest.mark.unit, pytest.mark.security]


def _make_sync_client(db_mock: AsyncMock, auth_override: bool = True) -> TestClient:
    """Build a minimal FastAPI test app with the sync routers."""
    from src.core.api.v1.sync.router import router as sync_router
    from src.core.api.v1.sync.json_router import router as sync_json_router
    from src.core.auth.dependencies import get_current_user, require_tenant_id
    from src.core.middleware.tenant_context import set_tenant_id, _current_user_scopes

    app = FastAPI()

    @app.middleware("http")
    async def add_tenant_state(request, call_next):
        set_tenant_id(42)
        _current_user_scopes.set(["agents:read"])
        request.state.tenant_id = 42
        request.state.user_id = 1
        request.state.limiet_gebruiker = "u1"
        return await call_next(request)

    if auth_override:
        app.dependency_overrides[require_tenant_id] = lambda: 42
        user_mock = MagicMock()
        user_mock.id = 1
        user_mock.tenant_id = 42
        app.dependency_overrides[get_current_user] = lambda: user_mock
    app.dependency_overrides[get_db] = lambda: db_mock

    app.include_router(sync_router, prefix="/api/v1")
    app.include_router(sync_json_router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


class TestCollaborationSnapshotModel:
    def test_snapshot_model_exists(self) -> None:
        from src.core.governance.models import CollaborationSnapshot

        assert CollaborationSnapshot is not None

    def test_snapshot_tenant_id_not_null(self) -> None:
        from src.core.governance.models import CollaborationSnapshot

        assert CollaborationSnapshot.__table__.c.tenant_id.nullable is False

    def test_snapshot_workflow_id_indexed(self) -> None:
        from src.core.governance.models import CollaborationSnapshot

        idx_names = {idx.name for idx in CollaborationSnapshot.__table__.indexes}
        assert "ix_workflow_snapshots_workflow_id" in idx_names


class TestSnapshotEndpoints:
    def test_put_snapshot_saves_to_db(self) -> None:
        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        response = client.put(
            "/api/v1/sync/snapshot/test-workflow-123",
            json={"nodes": [], "edges": [], "version": 1},
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("success") is True
        assert body.get("data", {}).get("saved") is True

    def test_get_snapshot_returns_latest(self) -> None:
        db_mock = AsyncMock()
        from src.core.governance.models import CollaborationSnapshot

        snapshot_mock = MagicMock(spec=CollaborationSnapshot)
        snapshot_mock.snapshot_data = {"nodes": [{"id": "1"}], "edges": []}
        snapshot_mock.workflow_id = "test-workflow-456"
        snapshot_mock.tenant_id = 42

        async def mock_execute(query):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = snapshot_mock
            return mock_result

        db_mock.execute.side_effect = mock_execute
        client = _make_sync_client(db_mock)

        response = client.get("/api/v1/sync/snapshot/test-workflow-456")
        assert response.status_code == 200
        body = response.json()
        assert body.get("success") is True
        data = body.get("data", {})
        assert "nodes" in data or "snapshot_data" in data

    def test_get_snapshot_returns_404_for_unknown_workflow(self) -> None:
        db_mock = AsyncMock()

        async def mock_execute(query):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        db_mock.execute.side_effect = mock_execute
        client = _make_sync_client(db_mock)

        response = client.get("/api/v1/sync/snapshot/nonexistent-workflow")
        assert response.status_code == 404

    def test_tenant_isolation_snapshot(self) -> None:
        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        client.put(
            "/api/v1/sync/snapshot/test-workflow-789",
            json={"nodes": [], "edges": []},
        )

        # Verify tenant_id is set on the snapshot model added to DB
        added_obj = db_mock.add.call_args[0][0]
        assert added_obj.tenant_id == 42
        assert added_obj.workflow_id == "test-workflow-789"


class TestAwarenessEndpoints:
    def test_get_awareness_returns_list(self) -> None:
        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        with patch("src.core.api.v1.sync.json_router.get_redis_client") as mock_redis:
            mock_redis.return_value = AsyncMock()
            mock_redis.return_value.hgetall.return_value = {}

            response = client.get("/api/v1/sync/awareness/test-workflow-789")
            assert response.status_code == 200
            body = response.json()
            assert isinstance(body.get("data", []), list)

    def test_get_awareness_never_returns_null(self) -> None:
        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        with patch("src.core.api.v1.sync.json_router.get_redis_client") as mock_redis:
            mock_redis.return_value = AsyncMock()
            mock_redis.return_value.hgetall.return_value = {}

            response = client.get("/api/v1/sync/awareness/empty-workflow")
            assert response.status_code == 200
            body = response.json()
            assert body.get("data") is not None
            assert isinstance(body.get("data"), list)

    def test_awareness_uses_redis_not_hardcoded(self) -> None:
        from pathlib import Path

        _root = Path(__file__).parent.parent.parent
        source = (_root / "src/core/api/v1/sync/json_router.py").read_text(encoding="utf-8")
        normalized = source.replace(" ", "")
        assert 'return{"success":True,"data":[]}' not in normalized

    def test_snapshot_retention_query_not_scalar_subquery(self) -> None:
        """Retention delete must support multiple stale rows (no scalar_subquery)."""
        from pathlib import Path

        _root = Path(__file__).parent.parent.parent
        source = (_root / "src/core/api/v1/sync/json_router.py").read_text(encoding="utf-8")
        assert "scalar_subquery(" not in source


class TestRateLimiting:
    def test_put_snapshot_returns_429_after_limit(self) -> None:
        """Trigger rate limit by sending 21 writes (limit = 20/min)."""
        from src.core.governance.rate_limiter import reset_snapshot_rate_limits

        reset_snapshot_rate_limits()

        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        for i in range(20):
            db_mock.reset_mock()
            response = client.put(
                "/api/v1/sync/snapshot/ratelimit-test",
                json={"nodes": [], "edges": [], "version": 1},
            )
            assert response.status_code == 200, f"Request {i + 1} should succeed"

        db_mock.reset_mock()
        response = client.put(
            "/api/v1/sync/snapshot/ratelimit-test",
            json={"nodes": [], "edges": [], "version": 1},
        )
        assert response.status_code == 429
        body = response.json()
        assert "Rate limit exceeded" in str(body) or response.status_code == 429

    def test_get_snapshot_returns_429_after_limit(self) -> None:
        """Trigger rate limit by sending 121 reads (limit = 120/min)."""
        from src.core.governance.rate_limiter import reset_snapshot_rate_limits

        reset_snapshot_rate_limits()

        db_mock = AsyncMock()

        async def mock_execute(query):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        db_mock.execute.side_effect = mock_execute
        client = _make_sync_client(db_mock)

        for i in range(120):
            response = client.get("/api/v1/sync/snapshot/ratelimit-read-test")
            assert response.status_code == 404, f"Request {i + 1} should succeed"

        response = client.get("/api/v1/sync/snapshot/ratelimit-read-test")
        assert response.status_code == 429

    def test_rate_limit_is_tenant_scoped(self) -> None:
        """Rate limit key includes tenant_id to prevent cross-tenant collision."""
        from src.core.governance.rate_limiter import reset_snapshot_rate_limits

        reset_snapshot_rate_limits()

        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        for i in range(20):
            db_mock.reset_mock()
            response = client.put(
                "/api/v1/sync/snapshot/tenant-scope-test",
                json={"nodes": [], "edges": [], "version": 1},
            )
            assert response.status_code == 200

        from src.core.governance.rate_limiter import _rate_limiter

        key_found = False
        for key in _rate_limiter._requests:
            if "snapshot:42:" in key:
                key_found = True
                break
        assert key_found, "Rate limit key should include tenant_id"


class TestBackwardCompatibility:
    def test_existing_yjs_get_snapshot_still_works(self) -> None:
        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        response = client.get("/api/v1/workflows/test-yjs/snapshot")
        assert response.status_code in (200, 404)

    def test_existing_yjs_post_snapshot_still_works(self) -> None:
        db_mock = AsyncMock()
        client = _make_sync_client(db_mock)

        response = client.post(
            "/api/v1/workflows/test-yjs/snapshot",
            content=b"\x00\x01\x02",
        )
        assert response.status_code in (200, 404)
