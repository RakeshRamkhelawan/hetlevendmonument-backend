"""
Verify that the stub goal_endpoints router is NOT registered alongside
the real company-layer goal_router. Both registering at /api/v1/goals
causes route shadowing and in-memory data leaks into production.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client() -> TestClient:
    """Build a TestClient backed by register_all_routers with DB initialised."""
    from src.core.config.unified_config import config as app_config
    from src.core.database.database import db_manager

    # Ensure the async session maker is initialised so auth dependencies can
    # acquire a session (they raise RuntimeError otherwise, masking the real
    # 401 behind a 500).
    if db_manager.async_session_maker is None:
        db_cfg = app_config.get_database_config()
        assert db_cfg is not None, "Database config unavailable in test environment"
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(db_cfg["url"], echo=False)
        db_manager.async_session_maker = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )

    app = FastAPI()
    from src.core.api.router_registry import register_all_routers

    register_all_routers(app)
    return TestClient(app, raise_server_exceptions=False)


def test_goals_stub_not_registered():
    """
    After register_all_routers(), the /api/v1/goals route must be served
    by goal_router (returns 401 Unauthorized when no token), NOT by the
    stub (which returns 404 for GET / because the stub only has POST /create).
    """
    client = _make_client()

    # The REAL goal_router has GET /api/v1/goals/tree
    # The STUB goal_endpoints has POST /api/v1/goals/create
    # After fix: GET /goals/tree should return 401 (auth required), not 404
    response = client.get("/api/v1/goals/tree?company_id=00000000-0000-0000-0000-000000000001")
    assert response.status_code in (401, 403), (
        f"Expected 401/403 from real goal_router, got {response.status_code}. "
        "The stub may still be taking priority."
    )


def test_stub_goal_create_not_accessible():
    """
    The stub endpoint POST /api/v1/goals/create must NOT be reachable
    after the stub is removed from registration.

    NOTE: The real goal_router has GET /{goal_id} which matches the path
    segment 'create', so FastAPI returns 405 (Method Not Allowed) instead
    of 404.  Both 404 and 405 prove the stub POST /create route is gone.
    """
    client = _make_client()

    response = client.post("/api/v1/goals/create", json={"title": "test"})
    # After removal: stub route gone.
    # Real router matches GET /{goal_id} → 405; either 404 or 405 is acceptable.
    assert response.status_code in (404, 405), (
        f"Stub POST /goals/create still reachable (status {response.status_code}). "
        "Remove the stub registration from _register_optional_routers()."
    )
