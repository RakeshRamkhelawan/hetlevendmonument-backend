"""
Scope Validator Coverage Tests - Week 3, Subagent 2 (REWRITTEN)
Target: scope_validator.py (25.00% -> 70%+)

Tests for scope validation and permission checking:
- require_scopes dependency
- Tenant isolation checks
- Permission mapping
- Error handling

REWRITTEN: Uses FastAPI TestClient with proper dependency overrides
to test the require_scopes dependency correctly.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def get_real_require_scopes():
    """Import the REAL require_scopes, bypassing any conftest patches."""
    from src.core.auth.scope_validator import require_scopes

    return require_scopes


class TestRequireScopesTestMode:
    """Test require_scopes in TEST MODE (TESTING=1)

    SEC-004: The MagicMock bypass has been removed. Passing a MagicMock session
    no longer short-circuits auth — full validation is enforced regardless of
    session type or TESTING environment variable.
    """

    @pytest.mark.asyncio
    async def test_test_mode_no_longer_bypasses_checks(self):
        """SEC-004: TESTING=1 must NOT bypass validation; mock sessions get 403."""
        require_scopes = get_real_require_scopes()

        # Create test app with the real require_scopes
        app = FastAPI()

        @app.get("/test-scopes")
        async def test_endpoint(user_id: int = Depends(require_scopes("users:read"))):
            return {"user_id": user_id}

        # Override dependencies
        async def mock_get_current_user_id():
            return 123

        async def mock_get_async_session():
            return MagicMock(spec=AsyncSession)

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        with patch.dict(os.environ, {"TESTING": "1"}):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/test-scopes")

        # Bypass is gone: MagicMock session cannot satisfy tenant/user checks → 403
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_test_mode_no_longer_bypasses_multiple_scopes(self):
        """SEC-004: Multiple scopes with a mock session still results in 403."""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-multi")
        async def test_endpoint(
            user_id: int = Depends(require_scopes("users:read", "users:write", "admin:all")),
        ):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 456

        async def mock_get_async_session():
            return MagicMock(spec=AsyncSession)

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        with patch.dict(os.environ, {"TESTING": "1"}):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/test-multi")

        # Bypass is gone: MagicMock session cannot satisfy tenant/user checks → 403
        assert response.status_code == 403


class TestRequireScopesNormalMode:
    """Test require_scopes in normal mode (TESTING not set or empty)"""

    @pytest.mark.asyncio
    async def test_normal_mode_user_not_in_tenant_raises_403(self):
        """Normal mode should raise 403 if user not found in tenant"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-tenant")
        async def test_endpoint(user_id: int = Depends(require_scopes("users:read"))):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 1

        # Mock session that returns None for user lookup (user not in tenant)
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch("src.core.auth.scope_validator.require_tenant_id", return_value=1):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/test-tenant")

        assert response.status_code == 403
        assert "tenant" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_normal_mode_user_in_tenant_with_permission(self):
        """Normal mode with valid user and permission should return user_id"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-valid")
        async def test_endpoint(user_id: int = Depends(require_scopes("users:read"))):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 1

        # Mock user exists in tenant
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.tenant_id = 1

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        # Mock RBACService
        mock_rbac = MagicMock()
        mock_rbac.has_permission = AsyncMock(return_value=True)

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch("src.core.auth.scope_validator.require_tenant_id", return_value=1):
                with patch("src.core.services.rbac_service.RBACService", return_value=mock_rbac):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/test-valid")

        assert response.status_code == 200
        assert response.json()["user_id"] == 1


class TestRequireScopesPermissionChecks:
    """Test permission checking logic"""

    @pytest.mark.asyncio
    async def test_permission_denied_raises_403(self):
        """Missing permission should raise 403 Forbidden"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-denied")
        async def test_endpoint(user_id: int = Depends(require_scopes("admin:delete"))):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 1

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.tenant_id = 1

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        # RBAC denies permission
        mock_rbac = MagicMock()
        mock_rbac.has_permission = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch("src.core.auth.scope_validator.require_tenant_id", return_value=1):
                with patch("src.core.services.rbac_service.RBACService", return_value=mock_rbac):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/test-denied")

        assert response.status_code == 403
        assert "admin:delete" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_multiple_scopes_all_pass(self):
        """All scopes granted should return user_id"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-multi-pass")
        async def test_endpoint(
            user_id: int = Depends(require_scopes("users:read", "users:write", "admin:view")),
        ):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 99

        mock_user = MagicMock()
        mock_user.id = 99
        mock_user.tenant_id = 1

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        # All scopes granted
        mock_rbac = MagicMock()
        mock_rbac.has_permission = AsyncMock(return_value=True)

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch("src.core.auth.scope_validator.require_tenant_id", return_value=1):
                with patch("src.core.services.rbac_service.RBACService", return_value=mock_rbac):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/test-multi-pass")

        assert response.status_code == 200
        assert response.json()["user_id"] == 99


class TestRequireScopesParsing:
    """Test scope string parsing"""

    @pytest.mark.asyncio
    async def test_invalid_scope_format_raises_500(self):
        """Invalid scope format (no colon) should raise 500 error"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-invalid")
        async def test_endpoint(
            user_id: int = Depends(require_scopes("invalid_scope_format")),
        ):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 1

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.tenant_id = 1

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        mock_rbac = MagicMock()

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch("src.core.auth.scope_validator.require_tenant_id", return_value=1):
                with patch("src.core.services.rbac_service.RBACService", return_value=mock_rbac):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/test-invalid")

        assert response.status_code == 500


class TestRequireScopesEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_empty_scopes_returns_user_id(self):
        """No required scopes should still validate user and return user_id"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-empty")
        async def test_endpoint(user_id: int = Depends(require_scopes())):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 42

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.tenant_id = 1

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        mock_rbac = MagicMock()
        mock_rbac.has_permission = AsyncMock()  # Should not be called

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch("src.core.auth.scope_validator.require_tenant_id", return_value=1):
                with patch("src.core.services.rbac_service.RBACService", return_value=mock_rbac):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/test-empty")

        assert response.status_code == 200
        assert response.json()["user_id"] == 42


class TestRequireScopesTenantIsolation:
    """Test tenant isolation checks"""

    @pytest.mark.asyncio
    async def test_user_wrong_tenant_denied(self):
        """User from different tenant should be denied"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-wrong-tenant")
        async def test_endpoint(user_id: int = Depends(require_scopes("users:read"))):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 1

        # User not found in tenant 2 (they are in tenant 1)
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        mock_rbac = MagicMock()

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch(
                "src.core.auth.scope_validator.require_tenant_id", return_value=2
            ):  # Request for tenant 2
                with patch("src.core.services.rbac_service.RBACService", return_value=mock_rbac):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/test-wrong-tenant")

        assert response.status_code == 403
        assert "tenant" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_tenant_check_failure_without_test_mode_raises(self):
        """Tenant context failure without test mode should raise"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-tenant-fail")
        async def test_endpoint(user_id: int = Depends(require_scopes("users:read"))):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 1

        mock_session = AsyncMock(spec=AsyncSession)

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch(
                "src.core.auth.scope_validator.require_tenant_id",
                side_effect=HTTPException(status_code=400, detail="Missing tenant"),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/test-tenant-fail")

        assert response.status_code == 400


class TestRequireScopesLogging:
    """Test logging behavior"""

    @pytest.mark.asyncio
    async def test_permission_denied_logs_warning(self):
        """Permission denied should log a warning"""
        require_scopes = get_real_require_scopes()

        app = FastAPI()

        @app.get("/test-log")
        async def test_endpoint(user_id: int = Depends(require_scopes("admin:super"))):
            return {"user_id": user_id}

        async def mock_get_current_user_id():
            return 5

        mock_user = MagicMock()
        mock_user.id = 5
        mock_user.tenant_id = 1

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        async def mock_get_async_session():
            return mock_session

        from src.core.auth.dependencies import get_current_user_id
        from src.core.database.database import get_db

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_db] = mock_get_async_session

        mock_rbac = MagicMock()
        mock_rbac.has_permission = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"TESTING": ""}, clear=False):
            with patch("src.core.auth.scope_validator.require_tenant_id", return_value=1):
                with patch("src.core.services.rbac_service.RBACService", return_value=mock_rbac):
                    with patch("src.core.auth.scope_validator.logger") as mock_logger:
                        async with AsyncClient(
                            transport=ASGITransport(app=app), base_url="http://test"
                        ) as client:
                            response = await client.get("/test-log")

                        # Verify warning was logged
                        mock_logger.warning.assert_called()

        assert response.status_code == 403
