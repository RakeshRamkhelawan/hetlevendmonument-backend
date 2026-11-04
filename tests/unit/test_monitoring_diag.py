"""Diagnostic test to understand 403 failures in monitoring endpoints."""


def test_monitoring_diagnostic(client, auth_headers):
    """Diagnostic: check why monitoring returns 403 under pollution."""
    app = client.app
    print(f"\nDependency overrides count: {len(app.dependency_overrides)}")
    for key, val in app.dependency_overrides.items():
        mod = getattr(key, "__module__", "?")
        name = getattr(key, "__qualname__", getattr(key, "__name__", str(key)))
        print(f"  Override: {mod}.{name}")

    from src.core.auth.dependencies import get_current_user_id
    from src.core.database.database import get_async_session

    has_session = get_async_session in app.dependency_overrides
    has_user_id = get_current_user_id in app.dependency_overrides
    print(f"get_async_session overridden: {has_session}")
    print(f"get_current_user_id overridden: {has_user_id}")
    print(f"get_async_session id: {id(get_async_session)}")

    from src.core.auth import scope_validator

    sv_get_db = scope_validator.get_db_session
    sv_user_id = scope_validator.get_current_user_id
    print(f"scope_validator.get_db_session id: {id(sv_get_db)}")
    print(f"scope_validator.get_current_user_id id: {id(sv_user_id)}")
    print(f"get_db_session is get_async_session: {sv_get_db is get_async_session}")
    print(
        f"sv.get_current_user_id is auth.get_current_user_id: "
        f"{sv_user_id is get_current_user_id}"
    )

    has_sv_session = sv_get_db in app.dependency_overrides
    has_sv_user_id = sv_user_id in app.dependency_overrides
    print(f"sv.get_db_session in overrides: {has_sv_session}")
    print(f"sv.get_current_user_id in overrides: {has_sv_user_id}")

    # Check the routes registered on the app
    monitoring_routes = [r for r in app.routes if hasattr(r, "path") and "monitoring" in r.path and hasattr(r, "methods")]
    print(f"Monitoring routes: {len(monitoring_routes)}")
    for r in monitoring_routes:
        print(f"  {r.methods} {r.path}")

    # Now make the request
    response = client.get("/api/v1/monitoring/health", headers=auth_headers)
    print(f"Response status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response body: {response.text[:500]}")
    assert response.status_code == 200
