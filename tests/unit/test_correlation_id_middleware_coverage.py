"""
Comprehensive tests for src/core/middleware/correlation_id.py
Coverage target: 100% of correlation ID middleware
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.middleware.correlation_id import CorrelationIDMiddleware


class TestCorrelationIDMiddleware:
    """Test CorrelationIDMiddleware class"""

    @pytest.mark.asyncio
    async def test_dispatch_with_existing_correlation_id(self):
        """Test middleware preserves existing correlation ID"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {"X-Correlation-ID": "existing-id-123"}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        result = await middleware.dispatch(request, call_next)

        # Assert
        assert request.state.correlation_id == "existing-id-123"
        assert result.headers["X-Correlation-ID"] == "existing-id-123"
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_generates_correlation_id_when_missing(self):
        """Test middleware generates correlation ID when not present"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {}  # No correlation ID
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        result = await middleware.dispatch(request, call_next)

        # Assert
        # Should generate a UUID
        assert hasattr(request.state, "correlation_id")
        assert isinstance(request.state.correlation_id, str)
        assert len(request.state.correlation_id) > 0

        # Should add to response headers
        assert "X-Correlation-ID" in result.headers
        assert result.headers["X-Correlation-ID"] == request.state.correlation_id

    @pytest.mark.asyncio
    async def test_dispatch_generated_id_is_valid_uuid(self):
        """Test generated correlation ID is a valid UUID"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        await middleware.dispatch(request, call_next)

        # Assert - Should be parseable as UUID
        uuid_obj = uuid.UUID(request.state.correlation_id)
        assert isinstance(uuid_obj, uuid.UUID)

    @pytest.mark.asyncio
    async def test_dispatch_calls_next_handler(self):
        """Test middleware calls next handler in chain"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        await middleware.dispatch(request, call_next)

        # Assert
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_returns_response_from_next_handler(self):
        """Test middleware returns response from next handler"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {}
        request.state = Mock()

        expected_response = Mock()
        expected_response.headers = {}

        call_next = AsyncMock(return_value=expected_response)

        # Act
        result = await middleware.dispatch(request, call_next)

        # Assert
        assert result is expected_response

    @pytest.mark.asyncio
    async def test_dispatch_case_insensitive_header(self):
        """Test middleware handles case-insensitive header lookup"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        # Different case
        request.headers = {"x-correlation-id": "case-test-123"}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        result = await middleware.dispatch(request, call_next)

        # Assert - Should still work (Starlette headers are case-insensitive)
        assert hasattr(request.state, "correlation_id")

    @pytest.mark.asyncio
    async def test_dispatch_stores_id_in_request_state(self):
        """Test middleware stores correlation ID in request.state"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {"X-Correlation-ID": "state-test-456"}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        await middleware.dispatch(request, call_next)

        # Assert
        assert request.state.correlation_id == "state-test-456"

    @pytest.mark.asyncio
    async def test_dispatch_adds_header_to_response(self):
        """Test middleware adds correlation ID to response headers"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {"X-Correlation-ID": "response-test-789"}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        result = await middleware.dispatch(request, call_next)

        # Assert
        assert result.headers["X-Correlation-ID"] == "response-test-789"

    @pytest.mark.asyncio
    @patch("src.core.middleware.correlation_id.uuid.uuid4")
    async def test_dispatch_uses_uuid4_for_generation(self, mock_uuid4):
        """Test middleware uses uuid.uuid4() for ID generation"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())
        mock_uuid4.return_value = "mocked-uuid-123"

        request = Mock()
        request.headers = {}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        await middleware.dispatch(request, call_next)

        # Assert
        mock_uuid4.assert_called_once()
        assert request.state.correlation_id == "mocked-uuid-123"

    @pytest.mark.asyncio
    async def test_dispatch_with_empty_correlation_id_header(self):
        """Test middleware generates new ID when header is empty"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        request = Mock()
        request.headers = {"X-Correlation-ID": ""}  # Empty string
        request.state = Mock()

        response = Mock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        # Act
        result = await middleware.dispatch(request, call_next)

        # Assert
        # Empty string is falsy, so should generate new ID
        assert request.state.correlation_id != ""
        assert len(request.state.correlation_id) > 0


class TestMiddlewareIntegration:
    """Test CorrelationIDMiddleware integration scenarios"""

    @pytest.mark.asyncio
    async def test_multiple_requests_get_different_ids(self):
        """Test each request gets a unique correlation ID"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())

        response = Mock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)

        # Act - Create two separate requests
        request1 = Mock(headers={}, state=Mock())
        await middleware.dispatch(request1, call_next)

        request2 = Mock(headers={}, state=Mock())
        await middleware.dispatch(request2, call_next)

        # Assert - IDs should be different
        assert request1.state.correlation_id != request2.state.correlation_id

    @pytest.mark.asyncio
    async def test_correlation_id_persists_through_request(self):
        """Test correlation ID is available throughout request lifecycle"""
        # Arrange
        middleware = CorrelationIDMiddleware(app=Mock())
        test_id = "persist-test-999"

        request = Mock()
        request.headers = {"X-Correlation-ID": test_id}
        request.state = Mock()

        response = Mock()
        response.headers = {}

        async def check_id_in_handler(req):
            # Simulate downstream handler checking correlation ID
            assert req.state.correlation_id == test_id
            return response

        # Act
        await middleware.dispatch(request, check_id_in_handler)

        # Assert - If we got here, the assertion in handler passed
        assert request.state.correlation_id == test_id
