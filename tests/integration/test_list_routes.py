"""Test to list all registered routes in integration_app"""

import pytest


def test_list_all_routes(integration_app):
    """List all registered routes to debug 404 issue"""
    print("\n\n========== REGISTERED ROUTES ==========")
    for route in integration_app.routes:
        if hasattr(route, "methods"):
            print(f"{list(route.methods)} {route.path}")
        else:
            print(f"MOUNT {route.path}")
    print("=" * 50)

    # Also check if security_router was included
    routers = [r for r in integration_app.routes if hasattr(r, "path")]
    auth_routes = [r for r in routers if "auth" in r.path.lower()]

    print(f"\n\nAuth-related routes found: {len(auth_routes)}")
    for route in auth_routes:
        if hasattr(route, "methods"):
            print(f"  {list(route.methods)} {route.path}")

    assert len(auth_routes) > 0, "No auth routes found!"
