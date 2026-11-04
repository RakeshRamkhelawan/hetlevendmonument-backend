"""
Simple non-async tests for auth endpoints
Checks route registration without making HTTP requests
"""

import pytest


def test_auth_endpoints_in_route_list():
    """Verify auth endpoints are registered in the app routes."""
    from src.main import create_test_app

    app = create_test_app()

    # Get all routes from the app
    routes = {route.path for route in app.routes}

    # Check if our 3 auth endpoints are registered
    expected_routes = {
        "/api/v1/auth/change-password",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
    }

    for route in expected_routes:
        assert (
            route in routes
        ), f"Route {route} not found in app routes. Available routes: {sorted(routes)}"

    print("✅ All 3 auth endpoints registered")


def test_auth_router_imported():
    """Verify auth router can be imported successfully."""
    try:
        from src.core.api.auth.router import router as auth_router

        print("✅ Auth router imported successfully")
        assert auth_router is not None
    except ImportError as e:
        pytest.fail(f"Failed to import auth router: {e}")


def test_auth_schemas_imported():
    """Verify auth schemas can be imported."""
    try:
        from src.core.api.auth.schemas import (
            ChangePasswordRequest,
            ForgotPasswordRequest,
            PasswordResetConfirm,
        )

        print("✅ All auth schemas imported successfully")
        assert ChangePasswordRequest is not None
        assert ForgotPasswordRequest is not None
        assert PasswordResetConfirm is not None
    except ImportError as e:
        pytest.fail(f"Failed to import auth schemas: {e}")


def test_app_creation_succeeds():
    """Verify app can be created without errors."""
    try:
        from src.main import create_app

        app = create_app()
        assert app is not None
        print(f"✅ App created successfully with {len(app.routes)} routes")
    except Exception as e:
        pytest.fail(f"Failed to create app: {e}")
