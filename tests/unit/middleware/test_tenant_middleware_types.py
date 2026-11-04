"""Runtime type-contract tests for tenant middleware scope handling."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTenantMiddlewareScopeExtraction:
    """Verify scopes are extracted and stored as list[str]."""

    @pytest.fixture
    def asgi_scope(self) -> dict[str, Any]:
        return {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users",
            "headers": [(b"authorization", b"Bearer valid-token")],
            "state": {},
            "client": ("127.0.0.1", 12345),
        }

    @pytest.fixture
    def valid_payload(self) -> dict[str, Any]:
        return {
            "sub": "42",
            "email": "test@example.com",
            "tenant_id": 1,
            "roles": ["admin"],
        }

    @pytest.mark.asyncio
    async def test_comma_separated_scopes_split_into_strings(
        self, asgi_scope: dict[str, Any], valid_payload: dict[str, Any]
    ) -> None:
        """Old comma-separated scope strings must become list[str]."""
        from src.core.middleware.tenant_middleware import TenantMiddleware

        app = AsyncMock()
        middleware = TenantMiddleware(app)
        receive = AsyncMock()
        send = AsyncMock()

        payload = {**valid_payload, "scopes": "users:read, users:write ,admin:all"}

        with patch(
            "src.core.middleware.tenant_middleware.PublicEndpointRegistry.is_public",
            return_value=False,
        ):
            with patch(
                "src.core.middleware.tenant_middleware.extract_http_token",
                return_value="valid-token",
            ):
                with patch(
                    "src.core.auth.jwt_handler.jwt_handler.verify_token",
                    return_value=payload,
                ):
                    await middleware(asgi_scope, receive, send)

        stored_scopes = asgi_scope["state"].get("scopes")
        assert isinstance(stored_scopes, list)
        assert stored_scopes == ["users:read", "users:write", "admin:all"]
        assert all(isinstance(s, str) for s in stored_scopes)
        app.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_scopes_preserved_as_strings(
        self, asgi_scope: dict[str, Any], valid_payload: dict[str, Any]
    ) -> None:
        """Modern list scope claims must be preserved as list[str]."""
        from src.core.middleware.tenant_middleware import TenantMiddleware

        app = AsyncMock()
        middleware = TenantMiddleware(app)
        receive = AsyncMock()
        send = AsyncMock()

        payload = {**valid_payload, "scopes": ["users:read", "users:write"]}

        with patch(
            "src.core.middleware.tenant_middleware.PublicEndpointRegistry.is_public",
            return_value=False,
        ):
            with patch(
                "src.core.middleware.tenant_middleware.extract_http_token",
                return_value="valid-token",
            ):
                with patch(
                    "src.core.auth.jwt_handler.jwt_handler.verify_token",
                    return_value=payload,
                ):
                    await middleware(asgi_scope, receive, send)

        stored_scopes = asgi_scope["state"].get("scopes")
        assert isinstance(stored_scopes, list)
        assert stored_scopes == ["users:read", "users:write"]
        assert all(isinstance(s, str) for s in stored_scopes)
        app.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_scope_format_defaults_to_empty_list(
        self, asgi_scope: dict[str, Any], valid_payload: dict[str, Any]
    ) -> None:
        """Unsupported scope types (e.g. dict) must result in an empty list[str]."""
        from src.core.middleware.tenant_middleware import TenantMiddleware

        app = AsyncMock()
        middleware = TenantMiddleware(app)
        receive = AsyncMock()
        send = AsyncMock()

        payload = {**valid_payload, "scopes": {"users:read": True}}

        with patch(
            "src.core.middleware.tenant_middleware.PublicEndpointRegistry.is_public",
            return_value=False,
        ):
            with patch(
                "src.core.middleware.tenant_middleware.extract_http_token",
                return_value="valid-token",
            ):
                with patch(
                    "src.core.auth.jwt_handler.jwt_handler.verify_token",
                    return_value=payload,
                ):
                    await middleware(asgi_scope, receive, send)

        stored_scopes = asgi_scope["state"].get("scopes")
        assert isinstance(stored_scopes, list)
        assert stored_scopes == []
        app.assert_awaited_once()


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over tenantcontext en tokens, niet over de accountstatus, en hebben geen database.

    De controle zelf (uitgezet = 401 ACCOUNT_DISABLED, database weg = 503) wordt gemeten in
    `tests/integration/test_uitgeschakeld_is_uitgeschakeld.py`, tegen een echte database.
    """
    from unittest.mock import AsyncMock, patch

    from src.core.auth import account_status

    with patch.object(
        account_status,
        "haal_account_status",
        AsyncMock(return_value=account_status.AccountStatus.ACTIEF),
    ):
        yield
