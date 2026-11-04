"""
AUDIT-P0-B1: except RuntimeError: tenant_id = 1 fallback in auth/router.py register_user
must be removed and replaced with HTTPException(400).

RED phase: test_register_returns_400_when_no_tenant_context will FAIL
until the fallback is removed from router.py:165.

Root cause: TenantMiddleware excludes /api/v1/auth entirely, so require_tenant_id()
always raises RuntimeError for public auth endpoints. The fallback silently assigns
every registration to tenant 1 -- a cross-tenant security issue.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

TEST_PASSWORD = "Test1234XyzTest"  # nosec B105 - unit test fixture only


def _make_request() -> StarletteRequest:
    """Build a minimal Starlette Request for slowapi compatibility."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/register",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 9999),
        "state": MagicMock(),
    }
    return StarletteRequest(scope)


def _make_response() -> StarletteResponse:
    """Build a minimal Starlette Response for slowapi compatibility."""
    return StarletteResponse()


@contextmanager
def _bypass_rate_limiter(auth_limiter):  # type: ignore[no-untyped-def]
    """Bypass slowapi pre-check and header-injection in unit tests."""
    with patch.object(auth_limiter, "_check_request_limit", AsyncMock(return_value=None)):
        with patch.object(auth_limiter, "_inject_headers", MagicMock(return_value=None)):
            yield


@pytest.mark.unit
class TestAuthRegisterTenantFallback:
    """register_user must never silently fall back to tenant_id=1."""

    @pytest.mark.asyncio
    async def test_register_is_not_refused_for_a_missing_tenant_context(self):
        """
        Gewijzigd 2026-10-04 (SP-KLANT-01 dag 1, reden: dit legde het OUDE, bewust
        verwijderde gedrag vast -- 400 bij geen tenantcontext). Zonder token maakt de
        registratie een eigen tenant aan; er is dus geen reden meer om te weigeren omdat de
        bezoeker geen tenant heeft. De invariant "nooit stil tenant 1" staat in de test
        hieronder en in tests/integration/security/test_self_registration_*.py.
        """
        from src.core.api.auth import router as auth_router
        from src.core.api.auth.router import register_user
        from src.core.auth.auth_service import UserCreate

        mock_db = AsyncMock()
        user_data = UserCreate(email="newuser@example.com", password=TEST_PASSWORD)
        mock_user = MagicMock()
        mock_user.id = 1

        with patch(
            "src.core.api.auth.router_registration.require_tenant_id",
            side_effect=RuntimeError("Tenant context not set"),
        ):
            with _bypass_rate_limiter(auth_router.auth_limiter):
                with patch(
                    "src.core.api.auth.router_registration.auth_service.get_user_by_email",
                    AsyncMock(return_value=None),
                ):
                    with patch(
                        "src.core.api.auth.router_registration.auth_service.create_user",
                        AsyncMock(return_value=mock_user),
                    ):
                        with patch(
                            "src.core.api.auth.router_registration.RBACService"
                        ) as mock_rbac_cls:
                            mock_rbac = MagicMock()
                            mock_rbac.assign_role = AsyncMock()
                            mock_rbac_cls.return_value = mock_rbac

                            # SP-KLANT-01 dag 1: de 400 "Tenant context required" is
                            # BEWUST verwijderd -- registratie zonder token maakt nu een
                            # eigen tenant aan. Wat blijft: een bezoeker wordt nooit
                            # geweigerd OMDAT hij geen tenant heeft. Een andere fout (of
                            # een ander gedrag van de dubbels) laat de test falen; dat is
                            # voor de bouwer, die de koppeling bezit.
                            geweigerd_om_de_tenant = False
                            try:
                                await register_user(
                                    user_data=user_data,
                                    request=_make_request(),
                                    response=_make_response(),
                                    db=mock_db,
                                )
                            except HTTPException as exc:
                                geweigerd_om_de_tenant = "tenant" in str(exc.detail).lower()
                            assert not geweigerd_om_de_tenant

    @pytest.mark.asyncio
    async def test_register_does_not_create_user_with_hardcoded_tenant_1(self):
        """
        Security: When tenant context is unavailable, create_user must NOT be
        called with tenant_id=1 (gewijzigd 2026-10-04: aanroepen mag, tenant 1 nooit). The fallback silently assigned all registrations
        to tenant 1 -- violating multi-tenant isolation (ADR-003).
        """
        from src.core.api.auth import router as auth_router
        from src.core.api.auth.router import register_user
        from src.core.auth.auth_service import UserCreate

        mock_db = AsyncMock()
        user_data = UserCreate(email="newuser@example.com", password=TEST_PASSWORD)
        mock_create_user = AsyncMock(return_value=MagicMock(id=1))

        with patch(
            "src.core.api.auth.router_registration.require_tenant_id",
            side_effect=RuntimeError("Tenant context not set"),
        ):
            with _bypass_rate_limiter(auth_router.auth_limiter):
                with patch(
                    "src.core.api.auth.router_registration.auth_service.get_user_by_email",
                    AsyncMock(return_value=None),
                ):
                    with patch(
                        "src.core.api.auth.router_registration.auth_service.create_user",
                        mock_create_user,
                    ):
                        with patch(
                            "src.core.api.auth.router_registration.RBACService"
                        ) as mock_rbac_cls:
                            mock_rbac = MagicMock()
                            mock_rbac.assign_role = AsyncMock()
                            mock_rbac_cls.return_value = mock_rbac

                            try:
                                await register_user(
                                    user_data=user_data,
                                    request=_make_request(),
                                    response=_make_response(),
                                    db=mock_db,
                                )
                            except (HTTPException, Exception):
                                pass

        # SP-KLANT-01 dag 1: create_user MAG nu worden aangeroepen (voor de nieuwe tenant);
        # de invariant die blijft is dat het NOOIT met een hardgecodeerde tenant 1 gebeurt.
        for call in mock_create_user.call_args_list:
            kwargs = call.kwargs if call.kwargs else {}
            args = call.args if call.args else ()
            assert 1 not in args, "create_user called with positional tenant_id=1"
            assert kwargs.get("tenant_id") != 1, (
                "create_user must NOT be called with hardcoded tenant_id=1"
            )

    @pytest.mark.asyncio
    async def test_register_succeeds_with_valid_tenant_context(self):
        """
        Happy path + behavioral: when tenant context IS available, registration succeeds.
        Verifies that the fix does not break the normal (tenant-identified) flow.
        """
        from src.core.api.auth import router as auth_router
        from src.core.api.auth.router import register_user
        from src.core.auth.auth_service import UserCreate

        mock_db = AsyncMock()
        user_data = UserCreate(email="newuser@example.com", password=TEST_PASSWORD)

        mock_user = MagicMock()
        mock_user.id = 99
        mock_user.email = "newuser@example.com"

        with patch("src.core.api.auth.router_registration.require_tenant_id", return_value=42):
            with _bypass_rate_limiter(auth_router.auth_limiter):
                with patch(
                    "src.core.api.auth.router_registration.auth_service.get_user_by_email",
                    AsyncMock(return_value=None),
                ):
                    with patch(
                        "src.core.api.auth.router_registration.auth_service.create_user",
                        AsyncMock(return_value=mock_user),
                    ):
                        with patch(
                            "src.core.api.auth.router_registration.RBACService"
                        ) as mock_rbac_cls:
                            mock_rbac = MagicMock()
                            mock_rbac.assign_role = AsyncMock()
                            mock_rbac_cls.return_value = mock_rbac

                            result = await register_user(
                                user_data=user_data,
                                request=_make_request(),
                                response=_make_response(),
                                db=mock_db,
                            )

        assert result is not None
        assert result.id == 99
