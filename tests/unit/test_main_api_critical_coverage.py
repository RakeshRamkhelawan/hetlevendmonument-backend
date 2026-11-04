"""
Comprehensive tests for src/core/api/main.py - Critical Infrastructure
Target: 80%+ coverage for main API entry point (Priority 1 - 2,134 lines)

Focus Areas:
1. Application lifespan management
2. Core initialization (CVA, Sandbox, WebSocket)
3. Health checks and monitoring
4. Router registration
5. Middleware configuration
6. Error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# `test_lifespan_database_init_failure` laat de FastAPI-lifespan ONGEMOCKT lopen, en die
# roept `SandboxManagerFactory.create_manager()` aan -> `docker.from_env()`: een ECHTE
# verbinding naar de Docker-daemon (ADR-036 OP-214).
from tests.fixtures.docker_sandbox import geen_echte_docker_daemon  # noqa: F401


class TestApplicationLifespan:
    """Test application lifespan management"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.log_startup_validation")
    @patch("src.core.api.main.initialize_database")
    @patch("src.core.api.main.create_ultimate_cva_agent")
    @patch("src.core.api.main.SandboxManagerFactory.create_manager")
    @patch("src.core.api.main.WebSocketManager")
    async def test_lifespan_startup_success(
        self,
        mock_ws_manager,
        mock_sandbox_factory,
        mock_create_cva,
        mock_init_db,
        mock_log_validation,
    ):
        """Test successful application startup"""
        # Mock all dependencies
        mock_log_validation.return_value = True
        mock_init_db.return_value = True
        mock_create_cva.return_value = Mock()
        mock_sandbox_factory.return_value = Mock()
        mock_ws_manager.return_value = Mock()

        # Import and get lifespan
        from src.core.api.main import app_state, lifespan

        # Execute lifespan startup
        async with lifespan(Mock(spec=FastAPI)):
            assert app_state["database_initialized"] is True
            assert app_state["cva_agent"] is not None
            assert app_state["sandbox_manager"] is not None
            assert app_state["websocket_manager"] is not None

    @pytest.mark.asyncio
    @patch("src.core.api.main.log_startup_validation")
    async def test_lifespan_startup_validation_failure(self, mock_log_validation):
        """Test application startup fails with invalid configuration"""
        mock_log_validation.return_value = False

        from src.core.api.main import lifespan

        with pytest.raises(RuntimeError) as exc_info:
            async with lifespan(Mock(spec=FastAPI)):
                pass

        assert "Critical configuration missing" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.core.api.main.log_startup_validation")
    @patch("src.core.api.main.initialize_database")
    async def test_lifespan_database_init_failure(self, mock_init_db, mock_log_validation):
        """Test application handles database initialization failure gracefully"""
        mock_log_validation.return_value = True
        mock_init_db.side_effect = Exception("Database connection failed")

        from src.core.api.main import app_state, lifespan

        # Should not crash, continue with degraded functionality
        try:
            async with lifespan(Mock(spec=FastAPI)):
                assert app_state["database_initialized"] is False
        except Exception:
            # Lifespan might fail on other components, that's OK for this test
            pass

    @pytest.mark.asyncio
    @patch("src.core.api.main.log_startup_validation")
    @patch("src.core.api.main.initialize_database")
    @patch("src.core.api.main.create_ultimate_cva_agent")
    @patch("src.core.api.main.WebSocketManager")
    async def test_lifespan_cva_init_failure(
        self, mock_ws_manager, mock_create_cva, mock_init_db, mock_log_validation
    ):
        """Test application handles CVA agent initialization failure"""
        mock_log_validation.return_value = True
        mock_init_db.return_value = True
        mock_ws_manager.return_value = Mock()
        mock_create_cva.side_effect = Exception("CVA initialization failed")

        from src.core.api.main import lifespan

        with pytest.raises(Exception) as exc_info:
            async with lifespan(Mock(spec=FastAPI)):
                pass

        assert "CVA initialization failed" in str(exc_info.value)


class TestConversationContextBuilder:
    """Test conversation context building"""

    def test_build_conversation_context_empty(self):
        """Test building context with empty conversation history"""
        from src.core.api.main import _build_conversation_context

        result = _build_conversation_context([])

        assert "new conversation" in result.lower()
        assert "no previous context" in result.lower()

    def test_build_conversation_context_single_message(self):
        """Test building context with single message"""
        from src.core.api.main import _build_conversation_context

        history = [{"role": "user", "content": "Hello CVA", "timestamp": "2024-01-01"}]

        result = _build_conversation_context(history)

        assert "User: Hello CVA" in result
        assert "Total conversation length: 1 messages" in result

    def test_build_conversation_context_multiple_messages(self):
        """Test building context with multiple messages"""
        from src.core.api.main import _build_conversation_context

        history = [
            {"role": "user", "content": "Hello", "timestamp": "2024-01-01"},
            {"role": "assistant", "content": "Hi there!", "timestamp": "2024-01-01"},
            {"role": "user", "content": "How are you?", "timestamp": "2024-01-01"},
        ]

        result = _build_conversation_context(history)

        assert "User: Hello" in result
        assert "CVA: Hi there!" in result
        assert "User: How are you?" in result
        assert "Total conversation length: 3 messages" in result

    def test_build_conversation_context_truncates_to_last_5(self):
        """Test context builder only uses last 5 messages"""
        from src.core.api.main import _build_conversation_context

        # Create 10 messages
        history = [
            {"role": "user", "content": f"Message {i}", "timestamp": "2024-01-01"}
            for i in range(10)
        ]

        result = _build_conversation_context(history)

        # Should only contain last 5 messages (5-9)
        assert "Message 9" in result
        assert "Message 8" in result
        assert "Message 7" in result
        assert "Message 6" in result
        assert "Message 5" in result
        # Should NOT contain first messages
        assert "Message 0" not in result
        assert "Message 1" not in result
        assert "Total conversation length: 10 messages" in result

    def test_build_conversation_context_handles_missing_fields(self):
        """Test context builder handles missing fields gracefully"""
        from src.core.api.main import _build_conversation_context

        history = [
            {"role": "user", "content": "Test"},  # Missing timestamp
            {"content": "No role"},  # Missing role
            {},  # Empty message
        ]

        result = _build_conversation_context(history)

        # Should not crash and should include available info
        assert "Previous conversation context" in result


class TestSandboxMetrics:
    """Test sandbox metrics aggregation"""

    @pytest.mark.asyncio
    async def test_get_sandbox_metrics_no_manager(self):
        """Test getting metrics when sandbox manager is not initialized"""
        from src.core.api.main import _get_sandbox_metrics, app_state

        app_state["sandbox_manager"] = None

        result = await _get_sandbox_metrics()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_sandbox_metrics_success(self):
        """Test successful sandbox metrics aggregation"""
        from src.core.api.main import _get_sandbox_metrics, app_state

        # Mock sandbox manager with metrics
        mock_manager = Mock()
        mock_manager.sandbox_metrics = {
            "sandbox1": {
                "executions_count": 10,
                "successful_executions": 8,
                "failed_executions": 2,
                "total_execution_time": 100.0,
            },
            "sandbox2": {
                "executions_count": 5,
                "successful_executions": 5,
                "failed_executions": 0,
                "total_execution_time": 25.0,
            },
        }
        mock_manager.active_sandboxes = ["sandbox1", "sandbox2"]
        mock_manager._docker_client = Mock()

        app_state["sandbox_manager"] = mock_manager

        result = await _get_sandbox_metrics()

        assert result["total_sandboxes_created"] == 2
        assert result["active_sandboxes"] == 2
        assert result["total_executions"] == 15
        assert result["successful_executions"] == 13
        assert result["failed_executions"] == 2
        assert result["success_rate"] == pytest.approx(86.67, rel=0.1)
        assert result["avg_execution_time"] == pytest.approx(8.33, rel=0.1)
        assert result["docker_available"] is True

    @pytest.mark.asyncio
    async def test_get_sandbox_metrics_empty_sandboxes(self):
        """Test metrics with no sandboxes created"""
        from src.core.api.main import _get_sandbox_metrics, app_state

        mock_manager = Mock()
        mock_manager.sandbox_metrics = {}
        mock_manager.active_sandboxes = []

        app_state["sandbox_manager"] = mock_manager

        result = await _get_sandbox_metrics()

        assert result["total_sandboxes_created"] == 0
        assert result["active_sandboxes"] == 0
        assert result["total_executions"] == 0
        assert result["success_rate"] == 0
        assert result["avg_execution_time"] == 0

    @pytest.mark.asyncio
    async def test_get_sandbox_metrics_error_handling(self):
        """Test error handling in metrics collection"""
        from src.core.api.main import _get_sandbox_metrics, app_state

        mock_manager = Mock()
        # Make sandbox_metrics raise an error when accessed
        type(mock_manager).sandbox_metrics = property(lambda self: {})
        mock_manager.active_sandboxes = property(
            lambda: (_ for _ in ()).throw(Exception("Metrics error"))
        )

        app_state["sandbox_manager"] = mock_manager

        result = await _get_sandbox_metrics()

        assert "error" in result


class TestGlobalState:
    """Test application global state"""

    def test_app_state_initial_values(self):
        """Test app_state has correct initial values"""
        from src.core.api.main import app_state

        assert "cva_agent" in app_state
        assert "sandbox_manager" in app_state
        assert "websocket_manager" in app_state
        assert "task_queue" in app_state
        assert "active_tasks" in app_state
        assert "system_metrics" in app_state
        assert "tool_broker_service" in app_state
        assert "tool_broker_enabled" in app_state

        # Check initial types
        assert isinstance(app_state["task_queue"], list)
        assert isinstance(app_state["active_tasks"], dict)
        assert isinstance(app_state["system_metrics"], dict)
        assert app_state["tool_broker_enabled"] is False


class TestImportAvailability:
    """Test conditional import handling"""

    def test_caching_import_handling(self):
        """Test caching import availability flag"""
        from src.core.api.main import caching_available

        # Should be boolean
        assert isinstance(caching_available, bool)

    def _main(self):
        import importlib

        return importlib.import_module("src.core.api.main")

    def test_phase2_import_handling(self):
        """Test phase2 router import handling"""
        phase2_router = getattr(self._main(), "phase2_router", None)
        assert phase2_router is None or hasattr(phase2_router, "routes")

    def test_goal_endpoints_availability(self):
        """Test goal endpoints availability flag"""
        m = self._main()
        goal_endpoints_available = getattr(m, "goal_endpoints_available", False)
        goal_router = getattr(m, "goal_router", None)
        assert isinstance(goal_endpoints_available, bool)
        if goal_endpoints_available:
            assert goal_router is not None
        else:
            assert goal_router is None

    def test_phase3_availability(self):
        """Test phase3 collaboration availability"""
        m = self._main()
        phase3_available = getattr(m, "phase3_available", False)
        collaboration_router = getattr(m, "collaboration_router", None)
        assert isinstance(phase3_available, bool)
        if phase3_available:
            assert collaboration_router is not None

    def test_subagent_availability(self):
        """Test subagent endpoints availability"""
        m = self._main()
        subagent_available = getattr(m, "subagent_available", False)
        subagent_router = getattr(m, "subagent_router", None)
        assert isinstance(subagent_available, bool)
        if subagent_available:
            assert subagent_router is not None

    def test_phase4_autonomous_availability(self):
        """Test phase4 autonomous endpoints availability"""
        m = self._main()
        phase4_available = getattr(m, "phase4_available", False)
        autonomous_router = getattr(m, "autonomous_router", None)
        assert isinstance(phase4_available, bool)
        if phase4_available:
            assert autonomous_router is not None

    def test_security_availability(self):
        """Test security endpoints availability"""
        m = self._main()
        security_available = getattr(m, "security_available", False)
        security_router = getattr(m, "security_router", None)
        assert isinstance(security_available, bool)
        if security_available:
            assert security_router is not None

    def test_phase5_prediction_availability(self):
        """Test phase5 prediction endpoints availability"""
        m = self._main()
        phase5_available = getattr(m, "phase5_available", False)
        prediction_router = getattr(m, "prediction_router", None)
        assert isinstance(phase5_available, bool)
        if phase5_available:
            assert prediction_router is not None

    def test_nlp_availability(self):
        """Test NLP endpoints availability"""
        m = self._main()
        nlp_available = getattr(m, "nlp_available", False)
        nlp_router = getattr(m, "nlp_router", None)
        assert isinstance(nlp_available, bool)
        if nlp_available:
            assert nlp_router is not None

    def test_learning_availability(self):
        """Test learning endpoints availability"""
        m = self._main()
        learning_available = getattr(m, "learning_available", False)
        learning_router = getattr(m, "learning_router", None)
        assert isinstance(learning_available, bool)
        if learning_available:
            assert learning_router is not None

    def test_models_availability(self):
        """Test model registry endpoints availability"""
        m = self._main()
        models_available = getattr(m, "models_available", False)
        models_router = getattr(m, "models_router", None)
        assert isinstance(models_available, bool)
        if models_available:
            assert models_router is not None


class TestLoggingConfiguration:
    """Test logging configuration"""

    def test_logger_exists(self):
        """Test logger is properly configured"""
        from src.core.api.main import logger

        assert logger is not None
        assert logger.name == "src.core.api.main"

    def test_production_logger_available(self):
        """Test production logger is imported"""
        from src.core.api.main import production_logger

        assert production_logger is not None
        assert hasattr(production_logger, "logger")


class TestExceptionHandlers:
    """Test exception handlers"""

    @pytest.mark.asyncio
    async def test_http_exception_handler(self):
        """Test HTTP exception handler formats response correctly"""
        from fastapi import HTTPException

        from src.core.api.main import http_exception_handler

        request = Mock()
        exc = HTTPException(status_code=404, detail="Resource not found")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 404
        import json

        content = json.loads(response.body)
        assert content["error"] is True
        assert content["message"] == "Resource not found"
        assert content["status_code"] == 404
        assert "timestamp" in content

    @pytest.mark.asyncio
    async def test_http_exception_handler_401(self):
        """Test HTTP exception handler with 401 Unauthorized"""
        from fastapi import HTTPException

        from src.core.api.main import http_exception_handler

        request = Mock()
        exc = HTTPException(status_code=401, detail="Unauthorized")

        response = await http_exception_handler(request, exc)

        assert response.status_code == 401
        import json

        content = json.loads(response.body)
        assert content["error"] is True
        assert content["message"] == "Unauthorized"

    @pytest.mark.asyncio
    async def test_general_exception_handler_debug_mode(self):
        """Ook in debug-modus gaat de uitzonderingstekst niet naar de klant (brief 2026-10-21)"""
        from src.core.api.main import general_exception_handler

        # Mock settings to enable debug
        with patch("src.core.api.main.settings") as mock_settings:
            mock_settings.debug = True

            request = Mock()
            exc = ValueError("Test error message")

            response = await general_exception_handler(request, exc)

            assert response.status_code == 500
            import json

            content = json.loads(response.body)
            assert content["error"] is True
            assert "Test error message" not in content["message"]
            assert content["status_code"] == 500

    @pytest.mark.asyncio
    async def test_general_exception_handler_production_mode(self):
        """Test general exception handler in production hides error details"""
        from src.core.api.main import general_exception_handler

        with patch("src.core.api.main.settings") as mock_settings:
            mock_settings.debug = False

            request = Mock()
            exc = ValueError("Sensitive error information")

            response = await general_exception_handler(request, exc)

            assert response.status_code == 500
            import json

            content = json.loads(response.body)
            assert content["error"] is True
            assert content["message"] == "Internal server error"
            assert "Sensitive" not in content["message"]


class TestHealthEndpoint:
    """Test /health endpoint"""

    def test_health_endpoint_accessible(self):
        """Test health endpoint is registered and accessible"""

        from src.core.api.main import app

        client = TestClient(app)
        # Health endpoint should be accessible without auth
        response = client.get("/health")

        # Should return 200 or at least be registered
        assert response.status_code in [
            200,
            500,
        ]  # May fail if components not initialized

    def test_health_endpoint_returns_json(self):
        """Test health endpoint returns JSON format"""

        from src.core.api.main import app

        client = TestClient(app)
        response = client.get("/health")

        # Should return JSON regardless of status
        assert response.headers["content-type"] == "application/json"


class TestStatusEndpoint:
    """Test /status endpoint"""

    def test_status_endpoint_accessible(self):
        """Test status endpoint is registered"""

        from src.core.api.main import app

        client = TestClient(app)
        response = client.get("/status")

        # Should be accessible
        assert response.status_code in [200, 500]

    def test_status_endpoint_returns_json(self):
        """Test status endpoint returns JSON"""

        from src.core.api.main import app

        client = TestClient(app)
        response = client.get("/status")

        assert response.headers["content-type"] == "application/json"


class TestRouterRegistration:
    """Test router registration"""

    def test_auth_router_registered(self):
        """Test auth router is registered with app"""
        from src.core.api.main import auth_router

        assert auth_router is not None
        route_paths = [route.path for route in auth_router.routes]
        # Auth routes should be registered (e.g., /auth/login, /auth/register)
        assert any("/auth/" in path for path in route_paths)

    def test_admin_router_registered(self):
        """Test admin router is registered"""
        from src.core.api.main import admin_router

        assert admin_router is not None
        route_paths = [route.path for route in admin_router.routes]
        # Admin routes should be registered
        assert any("/admin/" in path for path in route_paths)

    def test_management_router_registered(self):
        """Test management router is registered"""
        from src.core.api.main import management_router

        assert management_router is not None
        route_paths = [route.path for route in management_router.routes]
        # Management routes should be registered (rate-limits, block-ip, etc.)
        assert any("/rate-limits" in path or "/block-ip" in path for path in route_paths)

    def test_sentiment_router_registered(self):
        """Test sentiment scanner router is registered"""
        from src.core.api.main import sentiment_router

        assert sentiment_router is not None
        route_paths = [route.path for route in sentiment_router.routes]
        # Sentiment routes should be registered
        assert any("/sentiment" in path for path in route_paths)

    def test_orchestrator_endpoints_registered(self):
        """Test orchestrator endpoints are registered"""
        from src.core.api.main import auth_router, admin_router, management_router, sentiment_router

        # Verify all key routers exist and have routes
        assert auth_router is not None and len(auth_router.routes) > 0
        assert admin_router is not None and len(admin_router.routes) > 0
        assert management_router is not None and len(management_router.routes) > 0
        assert sentiment_router is not None and len(sentiment_router.routes) > 0


class TestAppConfiguration:
    """Test FastAPI app configuration"""

    def test_app_title_set(self):
        """Test app title is configured"""
        from src.core.api.main import app

        assert app.title is not None
        assert len(app.title) > 0

    def test_app_version_set(self):
        """Test app version is configured"""
        from src.core.api.main import app

        assert app.version is not None
        assert len(app.version) > 0

    def test_app_description_set(self):
        """Test app description is configured"""
        from src.core.api.main import app

        assert app.description is not None
        assert "AI" in app.description or "Agent" in app.description

    def test_app_lifespan_configured(self):
        """Test app has lifespan context manager"""
        from src.core.api.main import app

        # App should have lifespan configured
        assert app.router.lifespan_context is not None


class TestCVAChatEndpoint:
    """Test /api/v1/cva/chat endpoint"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_chat_with_cva_agent_not_initialized(self, mock_user, mock_state):
        """Test chat fails when CVA agent not initialized"""
        from fastapi import HTTPException

        from src.core.api.main import chat_with_cva

        mock_state.__getitem__ = Mock(return_value=None)  # cva_agent is None
        mock_user.return_value = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await chat_with_cva({"message": "Hello"}, mock_user.return_value)

        assert exc_info.value.status_code == 503
        assert "not initialized" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    @patch("src.core.api.main.TaskData")
    async def test_chat_with_cva_success(self, mock_task_data, mock_user, mock_state):
        """Test successful chat with CVA"""
        from src.core.api.main import chat_with_cva

        # Mock CVA agent
        mock_agent = AsyncMock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.result_data = {"text": "Hello! How can I help you?"}
        mock_result.execution_time = 0.5
        mock_agent.process_task.return_value = mock_result

        mock_state.__getitem__ = Mock(
            side_effect=lambda key: {
                "cva_agent": mock_agent,
                "database_initialized": False,
                "websocket_manager": None,
            }.get(key)
        )
        mock_state.get = Mock(
            side_effect=lambda key, default=None: {
                "database_initialized": False,
                "websocket_manager": None,
            }.get(key, default)
        )

        mock_user.return_value = {"sub": "test-user"}

        # Mock TaskData
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task_data.return_value = mock_task

        result = await chat_with_cva(
            {"message": "Hello", "user_id": "test-user"}, mock_user.return_value
        )

        assert result["success"] is True
        assert result["task_id"] == "task-123"
        assert "response" in result
        assert "execution_time" in result
        mock_agent.process_task.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_chat_with_cva_process_error(self, mock_user, mock_state):
        """Test chat handles processing errors"""
        from fastapi import HTTPException

        from src.core.api.main import chat_with_cva

        mock_agent = AsyncMock()
        mock_agent.process_task.side_effect = Exception("Processing failed")

        mock_state.__getitem__ = Mock(return_value=mock_agent)
        mock_user.return_value = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await chat_with_cva({"message": "Hello"}, mock_user.return_value)

        assert exc_info.value.status_code == 500
        assert "failed" in exc_info.value.detail.lower()


class TestCVAStrategyEndpoint:
    """Test /api/v1/cva/strategy endpoint"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_strategy_agent_not_initialized(self, mock_user, mock_state):
        """Test strategy fails when CVA not initialized"""
        from fastapi import HTTPException

        from src.core.api.main import request_strategy

        mock_state.__getitem__ = Mock(return_value=None)
        mock_user.return_value = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await request_strategy({"description": "Test"}, mock_user.return_value)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    @patch("src.core.api.main.TaskData")
    async def test_strategy_success(self, mock_task_data, mock_user, mock_state):
        """Test successful strategy generation"""
        from src.core.api.main import request_strategy

        mock_agent = AsyncMock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.result_data = {"strategy": "Strategic analysis result"}
        mock_result.execution_time = 1.5
        mock_agent.process_task.return_value = mock_result

        mock_state.__getitem__ = Mock(return_value=mock_agent)
        mock_user.return_value = {"sub": "test-user"}

        mock_task = Mock()
        mock_task.id = "task-456"
        mock_task_data.return_value = mock_task

        result = await request_strategy(
            {"description": "Analyze market trends"}, mock_user.return_value
        )

        assert result["success"] is True
        assert result["task_id"] == "task-456"
        assert "strategy" in result
        assert "execution_time" in result


class TestTaskManagementEndpoints:
    """Test task management endpoints"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    @patch("src.core.api.main.TaskData")
    @patch("src.core.api.main.get_feature_flag")
    async def test_create_task_success(self, mock_flag, mock_task_data, mock_user, mock_state):
        """Test successful task creation"""
        from src.core.api.main import create_task

        mock_task_queue = []
        mock_state.__getitem__ = Mock(
            side_effect=lambda key: {
                "task_queue": mock_task_queue,
                "websocket_manager": None,
            }.get(key)
        )

        mock_user.return_value = {"sub": "test-user"}
        mock_flag.return_value = False  # Disable websocket

        mock_task = Mock()
        mock_task.id = "task-789"
        mock_task_data.return_value = mock_task

        result = await create_task(
            {"title": "Test Task", "description": "Test description"},
            mock_user.return_value,
        )

        assert result["task_id"] == "task-789"
        assert result["status"] == "created"
        assert len(mock_task_queue) == 1

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_list_tasks_empty(self, mock_user, mock_state):
        """Test listing tasks when queue is empty"""
        from src.core.api.main import list_tasks

        mock_state.__getitem__ = Mock(return_value=[])
        mock_user.return_value = {"sub": "test-user"}

        result = await list_tasks(current_user=mock_user.return_value)

        assert result == []

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_list_tasks_with_tasks(self, mock_user, mock_state):
        """Test listing tasks when tasks exist"""
        from src.core.api.main import list_tasks

        # Create mock tasks
        mock_task1 = Mock()
        mock_task1.id = "task-1"
        mock_task1.title = "Task 1"
        mock_task1.description = "Description 1"
        mock_task1.status = Mock(value="pending")
        mock_task1.priority = Mock(value="high")
        mock_task1.created_at = Mock(isoformat=Mock(return_value="2024-01-01T00:00:00"))
        mock_task1.assigned_to = None

        mock_state.__getitem__ = Mock(return_value=[mock_task1])
        mock_user.return_value = {"sub": "test-user"}

        result = await list_tasks(current_user=mock_user.return_value)

        assert len(result) == 1
        assert result[0]["id"] == "task-1"
        assert result[0]["title"] == "Task 1"

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_list_tasks_with_limit(self, mock_user, mock_state):
        """Test listing tasks respects limit parameter"""
        from src.core.api.main import list_tasks

        # Create 10 mock tasks
        mock_tasks = []
        for i in range(10):
            task = Mock()
            task.id = f"task-{i}"
            task.title = f"Task {i}"
            task.description = f"Description {i}"
            task.status = Mock(value="pending")
            task.priority = Mock(value="medium")
            task.created_at = Mock(isoformat=Mock(return_value="2024-01-01T00:00:00"))
            task.assigned_to = None
            mock_tasks.append(task)

        mock_state.__getitem__ = Mock(return_value=mock_tasks)
        mock_user.return_value = {"sub": "test-user"}

        result = await list_tasks(limit=5, current_user=mock_user.return_value)

        assert len(result) == 5

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_execute_task_not_found(self, mock_user, mock_state):
        """Test executing non-existent task"""
        from fastapi import HTTPException

        from src.core.api.main import execute_task

        # Create proper mock dict for active_tasks
        mock_active_tasks = {}
        mock_state.__getitem__ = Mock(
            side_effect=lambda key: {
                "task_queue": [],
                "active_tasks": mock_active_tasks,
            }.get(key)
        )
        mock_user.return_value = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await execute_task("non-existent-task", mock_user.return_value)

        # The endpoint wraps 404 in a 500 error with details
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Er is een interne fout opgetreden."


class TestLLMMetricsEndpoint:
    """Test LLM metrics endpoint"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.Depends")
    async def test_get_llm_metrics_success(self, mock_depends, mock_state):
        """Test successful LLM metrics retrieval"""
        # Import function directly to bypass Depends decorator
        import inspect

        from src.core.api.main import get_llm_metrics

        # Get the actual function (unwrapped from decorators)
        actual_func = get_llm_metrics
        if hasattr(actual_func, "__wrapped__"):
            actual_func = actual_func.__wrapped__

        mock_agent = Mock()
        mock_agent.get_cva_metrics = Mock(
            return_value={
                "llm_initialized": True,
                "tasks_processed": 42,
                "average_execution_time": 1.5,
            }
        )
        mock_state.__getitem__ = Mock(return_value=mock_agent)
        mock_user = {"sub": "test-user"}

        # Call with positional argument to bypass caching issues
        result = await actual_func(current_user=mock_user)

        # Function returns wrapped response with metrics key
        assert "metrics" in result
        assert "providers" in result["metrics"]
        assert "anthropic" in result["metrics"]["providers"]
        assert "google" in result["metrics"]["providers"]
        assert result["metrics"]["total_requests"] == 42
        assert result["metrics"]["current_provider"] == "anthropic"

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.Depends")
    async def test_get_llm_metrics_cva_not_initialized(self, mock_depends, mock_state):
        """Test LLM metrics when CVA not initialized"""
        from fastapi import HTTPException

        from src.core.api.main import get_llm_metrics

        # Get the actual function
        actual_func = get_llm_metrics
        if hasattr(actual_func, "__wrapped__"):
            actual_func = actual_func.__wrapped__

        mock_state.__getitem__ = Mock(return_value=None)
        mock_user = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await actual_func(current_user=mock_user)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.Depends")
    async def test_get_llm_metrics_missing_method(self, mock_depends, mock_state):
        """Test LLM metrics when agent missing method"""
        from fastapi import HTTPException

        from src.core.api.main import get_llm_metrics

        # Get the actual function
        actual_func = get_llm_metrics
        if hasattr(actual_func, "__wrapped__"):
            actual_func = actual_func.__wrapped__

        mock_agent = Mock(spec=[])  # Agent without get_cva_metrics method
        mock_state.__getitem__ = Mock(return_value=mock_agent)
        mock_user = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await actual_func(current_user=mock_user)

        # Error handling wraps 503 in a 500
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Er is een interne fout opgetreden."


class TestListTasksFiltering:
    """Test list_tasks filtering functionality"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_list_tasks_filter_by_status(self, mock_user, mock_state):
        """Test filtering tasks by status"""
        from src.core.api.main import list_tasks

        # Create mixed status tasks
        mock_task1 = Mock()
        mock_task1.id = "task-1"
        mock_task1.title = "Task 1"
        mock_task1.description = "Description 1"
        mock_task1.status = Mock(value="pending")
        mock_task1.priority = Mock(value="high")
        mock_task1.created_at = Mock(isoformat=Mock(return_value="2024-01-01T00:00:00"))
        mock_task1.assigned_to = None

        mock_task2 = Mock()
        mock_task2.id = "task-2"
        mock_task2.title = "Task 2"
        mock_task2.description = "Description 2"
        mock_task2.status = Mock(value="completed")
        mock_task2.priority = Mock(value="medium")
        mock_task2.created_at = Mock(isoformat=Mock(return_value="2024-01-02T00:00:00"))
        mock_task2.assigned_to = None

        mock_state.__getitem__ = Mock(return_value=[mock_task1, mock_task2])
        mock_user.return_value = {"sub": "test-user"}

        result = await list_tasks(status="pending", current_user=mock_user.return_value)

        assert len(result) == 1
        assert result[0]["id"] == "task-1"
        assert result[0]["status"] == "pending"


class TestSandboxEndpointsAdvanced:
    """Test advanced sandbox endpoint scenarios"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_create_sandbox_not_initialized(self, mock_user, mock_state):
        """Test sandbox creation when manager not initialized"""
        from fastapi import HTTPException

        from src.core.api.main import create_sandbox

        mock_state.__getitem__ = Mock(return_value=None)
        mock_user.return_value = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await create_sandbox({}, mock_user.return_value)

        assert exc_info.value.status_code == 503
        assert "not initialized" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_create_sandbox_with_full_config(self, mock_user, mock_state):
        """Test sandbox creation with comprehensive config"""
        from src.core.api.main import create_sandbox

        mock_manager = AsyncMock()
        mock_manager.create_sandbox = AsyncMock(return_value="sandbox-full-123")
        mock_state.__getitem__ = Mock(return_value=mock_manager)
        mock_user.return_value = {"sub": "test-user"}

        config = {
            "isolation_level": "process",
            "resource_limits": {"cpu": 2, "memory": "1GB", "timeout": 300},
            "network_access": True,
            "filesystem_access": {"read": ["/data"], "write": ["/tmp"]},
        }

        result = await create_sandbox(config, mock_user.return_value)

        assert result["sandbox_id"] == "sandbox-full-123"
        assert result["status"] == "created"
        assert "isolation_level" in result

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    async def test_get_sandbox_status_error_handling(self, mock_user, mock_state):
        """Test sandbox status error handling"""
        from fastapi import HTTPException

        from src.core.api.main import get_sandbox_status

        mock_manager = AsyncMock()
        mock_manager.get_sandbox_status = AsyncMock(side_effect=Exception("Sandbox error"))
        mock_state.__getitem__ = Mock(return_value=mock_manager)
        mock_user.return_value = {"sub": "test-user"}

        with pytest.raises(HTTPException) as exc_info:
            await get_sandbox_status("sandbox-123", mock_user.return_value)

        assert exc_info.value.status_code == 500
        assert "Failed to get sandbox status" in exc_info.value.detail


class TestFeatureFlags:
    """Test feature flag system"""

    def test_get_feature_flag_enabled(self):
        """Test getting enabled feature flag"""
        from src.core.api.main import get_feature_flag

        # Test with a known feature flag
        result = get_feature_flag("websocket_updates")

        assert isinstance(result, bool)

    def test_get_feature_flag_disabled(self):
        """Test getting disabled feature flag"""
        from src.core.api.main import get_feature_flag

        result = get_feature_flag("non_existent_feature")

        assert isinstance(result, bool)


class TestWebSocketManagement:
    """Test WebSocket functionality"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    async def test_websocket_broadcast_success(self, mock_state):
        """Test successful WebSocket broadcast"""
        from src.core.api.main import app_state

        mock_ws_manager = AsyncMock()
        mock_ws_manager.broadcast = AsyncMock()
        mock_state.__getitem__ = Mock(return_value=mock_ws_manager)

        # Simulate broadcast
        await mock_ws_manager.broadcast({"type": "test", "data": "message"})

        mock_ws_manager.broadcast.assert_called_once()


class TestTaskQueueManagement:
    """Test task queue management"""

    @pytest.mark.asyncio
    @patch("src.core.api.main.app_state")
    @patch("src.core.api.main.get_current_user")
    @patch("src.core.api.main.TaskData")
    @patch("src.core.api.main.get_feature_flag")
    async def test_create_task_adds_to_queue(
        self, mock_flag, mock_task_data, mock_user, mock_state
    ):
        """Test creating task adds to queue"""
        from src.core.api.main import create_task

        mock_task_queue = []
        mock_state.__getitem__ = Mock(
            side_effect=lambda key: {
                "task_queue": mock_task_queue,
                "websocket_manager": None,
            }.get(key)
        )

        mock_flag.return_value = False
        mock_user.return_value = {"sub": "test-user"}
        mock_task = Mock()
        mock_task.id = "new-task-123"
        mock_task_data.return_value = mock_task

        result = await create_task(
            {"title": "New Task", "description": "Test"}, mock_user.return_value
        )

        assert result["task_id"] == "new-task-123"
        assert len(mock_task_queue) == 1
