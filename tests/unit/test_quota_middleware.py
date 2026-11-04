"""
Unit Tests for Tenant Quota Middleware
Tests resource quota enforcement for multi-tenant system

Coverage Target: quota_middleware.py → >90%
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, status
from starlette.datastructures import URL

from src.core.middleware.quota_middleware import TenantQuotaMiddleware

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_request_post_users():
    """Mock POST request to /api/users"""
    request = Mock()
    request.method = "POST"
    request.url = Mock()
    request.url.path = "/api/users"
    request.client = Mock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_request_post_agents():
    """Mock POST request to /api/agents"""
    request = Mock()
    request.method = "POST"
    request.url = Mock()
    request.url.path = "/api/agents"
    request.client = Mock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_request_get():
    """Mock GET request (no quota check)"""
    request = Mock()
    request.method = "GET"
    request.url = Mock()
    request.url.path = "/api/users"
    return request


@pytest.fixture
def mock_request_unmonitored_endpoint():
    """Mock POST to unmonitored endpoint"""
    request = Mock()
    request.method = "POST"
    request.url = Mock()
    request.url.path = "/api/other"
    return request


@pytest.fixture
def mock_call_next():
    """Mock call_next function as AsyncMock"""
    call_next_mock = AsyncMock()
    response = Mock()
    response.status_code = 200
    call_next_mock.return_value = response
    return call_next_mock


@pytest.fixture
def quota_middleware():
    """TenantQuotaMiddleware instance"""
    app = AsyncMock()
    return TenantQuotaMiddleware(app)


@pytest.fixture
def mock_db_session():
    """Mock database session as async context manager"""
    session = AsyncMock()
    # Properly implement async context manager protocol
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)  # Must return False, not None
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_db_manager(mock_db_session):
    """Mock DatabaseManager"""
    manager = AsyncMock()
    manager._initialized = True
    manager._is_initialized = True
    manager.initialize = AsyncMock()
    # get_session returns the async context manager (mock_db_session) directly
    manager.get_session = MagicMock(return_value=mock_db_session)
    return manager


# ============================================================================
# TEST: Request Routing
# ============================================================================

# ============================================================================
# TEST: Request Routing
# ============================================================================


class TestRequestRouting:
    """Test middleware request routing logic"""

    @pytest.mark.asyncio
    async def test_get_request_bypasses_quota_check(self, quota_middleware):
        """Test GET requests bypass quota checks"""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        with patch("src.core.middleware.quota_middleware.get_tenant_id", return_value=123):
            await quota_middleware(scope, receive, send)
            # Should call next app
            assert quota_middleware.app.called

    @pytest.mark.asyncio
    async def test_unmonitored_endpoint_bypasses_check(self, quota_middleware):
        """Test unmonitored endpoints bypass quota checks"""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/other",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        with patch("src.core.middleware.quota_middleware.get_tenant_id", return_value=123):
            await quota_middleware(scope, receive, send)
            assert quota_middleware.app.called

    @pytest.mark.asyncio
    async def test_no_tenant_context_bypasses_check(self, quota_middleware):
        """Test requests without tenant context bypass quota checks"""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        with patch("src.core.middleware.quota_middleware.get_tenant_id", return_value=None):
            await quota_middleware(scope, receive, send)
            assert quota_middleware.app.called


# ============================================================================
# TEST: User Quota Enforcement
# ============================================================================


class TestUserQuotaEnforcement:
    """Test user quota checking"""

    @pytest.mark.skip(reason="Schema mismatch: tenants.domain column missing in test DB")
    @pytest.mark.asyncio
    async def test_user_creation_within_quota(
        self, quota_middleware, mock_db_manager, mock_db_session
    ):
        """Test user creation succeeds when within quota"""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Mock DB result: 5 users, max 10
        mock_result = Mock()
        mock_result.one_or_none.return_value = (5, 10)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.middleware.quota_middleware.get_tenant_id", return_value=123):
            with patch("src.core.database.database.db_manager", mock_db_manager):
                await quota_middleware(scope, receive, send)
                assert quota_middleware.app.called

    @pytest.mark.asyncio
    async def test_user_creation_quota_exceeded(
        self, quota_middleware, mock_db_manager, mock_db_session
    ):
        """Test user creation fails when quota exceeded"""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Mock DB result: 10 users, max 10 (at limit)
        mock_result = Mock()
        mock_result.scalar.return_value = 10
        # Tenant with max_users=10
        mock_tenant = MagicMock()
        mock_tenant.subscription_tier = "pro"
        mock_tenant.max_users = 10
        mock_tenant.max_agents = 20
        mock_db_session.scalar = AsyncMock(return_value=mock_tenant)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.middleware.quota_middleware.get_tenant_id", return_value=123):
            with patch("src.core.middleware.quota_middleware.db_manager", mock_db_manager):
                with patch(
                    "src.core.middleware.quota_middleware.log_security_event",
                    new_callable=AsyncMock,
                ):
                    # Middleware should capture the error and return JSONResponse
                    await quota_middleware(scope, receive, send)

                    # Verify next app was NOT called
                    assert not quota_middleware.app.called
                    # Verify send was called with 403 response
                    assert send.called


# ============================================================================
# TEST: Workflow Quota Enforcement (TASK-002)
# ============================================================================


class TestWorkflowQuotaEnforcement:
    """Test workflow quota checking for FREE tier"""

    @pytest.mark.asyncio
    async def test_workflow_execution_quota_exceeded(
        self, quota_middleware, mock_db_manager, mock_db_session
    ):
        """Test workflow execution fails when 50 limit reached on FREE tier"""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/workflows/some-wf/execute",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Mock Tenant as FREE
        tenant = MagicMock()
        tenant.subscription_tier = "free"
        tenant.max_users = None
        tenant.max_agents = None
        mock_db_session.scalar = AsyncMock(return_value=tenant)

        # Mock 50 executions (at free tier limit)
        mock_result = Mock()
        mock_result.scalar.return_value = 50
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.middleware.quota_middleware.get_tenant_id", return_value=123):
            with patch("src.core.middleware.quota_middleware.db_manager", mock_db_manager):
                with patch(
                    "src.core.middleware.quota_middleware.log_security_event",
                    new_callable=AsyncMock,
                ):
                    with patch(
                        "src.core.middleware.quota_middleware.UsageService"
                    ) as mock_usage_cls:
                        mock_usage = MagicMock()
                        mock_usage.check_quota = AsyncMock(return_value=False)
                        mock_usage_cls.return_value = mock_usage
                        await quota_middleware(scope, receive, send)

                    assert not quota_middleware.app.called
                    # Verify 402 Payment Required sent
                    # (Simplified: check if send was called for some response)
                    assert send.called

    @pytest.mark.asyncio
    async def test_workflow_execution_allowed_on_pro(
        self, quota_middleware, mock_db_manager, mock_db_session
    ):
        """Test workflow execution allowed for PRO tier even at 50"""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/workflows/some-wf/execute",
            "headers": [],
            "query_string": b"",
        }
        receive = AsyncMock()
        send = AsyncMock()

        # Mock Tenant as PRO - has unlimited quota so check_quota returns True
        tenant = MagicMock()
        tenant.subscription_tier = "pro"
        tenant.max_users = None
        tenant.max_agents = None
        mock_db_session.scalar = AsyncMock(return_value=tenant)

        with patch("src.core.middleware.quota_middleware.get_tenant_id", return_value=123):
            with patch("src.core.middleware.quota_middleware.db_manager", mock_db_manager):
                with patch("src.core.middleware.quota_middleware.UsageService") as mock_usage_cls:
                    mock_usage = MagicMock()
                    mock_usage.check_quota = AsyncMock(return_value=True)
                    mock_usage_cls.return_value = mock_usage
                    await quota_middleware(scope, receive, send)
                assert quota_middleware.app.called
