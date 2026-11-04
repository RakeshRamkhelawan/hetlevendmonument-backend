"""Unit tests for composite tenants router (src.core.api.v1.tenants.router)."""

from fastapi.routing import APIRoute

from src.core.api.v1.tenants.router import router
from src.core.api.v1.tenants.tenants_detail_router import tenants_detail_router
from src.core.api.v1.tenants.tenants_list_router import tenants_list_router
from src.core.api.v1.tenants.tenants_stats_router import tenants_stats_router


def test_tenants_composite_router_configuration() -> None:
    """Verify router prefix and tags match ADR-033 specs."""
    assert router.prefix == "/tenants"
    assert "Tenant Management" in router.tags


def test_tenants_composite_router_includes_all_subrouters() -> None:
    """Verify that routes from all three sub-routers are registered."""
    composite_route_signatures = {
        (route.path, tuple(sorted(route.methods)))
        for route in router.routes
        if isinstance(route, APIRoute)
    }

    # Verify routes from tenants_list_router
    for route in tenants_list_router.routes:
        if isinstance(route, APIRoute):
            expected_path = f"/tenants{route.path}".rstrip("/")
            expected_path = expected_path if expected_path else "/tenants"
            # Route in composite might be /tenants or /tenants/
            assert any(
                path.rstrip("/") == expected_path and methods == tuple(sorted(route.methods))
                for path, methods in composite_route_signatures
            ), f"List route {route.path} missing from composite"

    # Verify routes from tenants_detail_router
    for route in tenants_detail_router.routes:
        if isinstance(route, APIRoute):
            expected_path = f"/tenants{route.path}".rstrip("/")
            assert any(
                path.rstrip("/") == expected_path and methods == tuple(sorted(route.methods))
                for path, methods in composite_route_signatures
            ), f"Detail route {route.path} missing from composite"

    # Verify routes from tenants_stats_router
    for route in tenants_stats_router.routes:
        if isinstance(route, APIRoute):
            expected_path = f"/tenants{route.path}".rstrip("/")
            assert any(
                path.rstrip("/") == expected_path and methods == tuple(sorted(route.methods))
                for path, methods in composite_route_signatures
            ), f"Stats route {route.path} missing from composite"


def test_tenants_composite_router_has_stats_endpoint() -> None:
    """Explicitly verify that /{tenant_id}/stats route is present under /tenants."""
    paths = [route.path for route in router.routes if isinstance(route, APIRoute)]
    assert "/tenants/{tenant_id}/stats" in paths
