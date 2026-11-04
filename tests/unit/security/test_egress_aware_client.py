"""Tests for src.core.security.egress_aware_client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions.exceptions import EgressBlockedError
from src.core.security.egress_aware_client import EgressAwareAsyncClient
from src.core.security.egress_control import EgressDecision, EgressResult


class TestEgressAwareAsyncClient:
    """Test egress-aware HTTP client wrapper."""

    @pytest.fixture
    def mock_egress_controller(self):
        controller = MagicMock()
        controller.validate_request = AsyncMock()
        return controller

    @pytest.mark.asyncio
    async def test_blocked_request_raises_egress_blocked_error(self, mock_egress_controller):
        """Blocked domain raises EgressBlockedError, no HTTP request made."""
        mock_egress_controller.validate_request.return_value = EgressResult(
            decision=EgressDecision.BLOCK,
            reason="Domain not in allowlist",
        )

        with patch("src.core.security.egress_aware_client.httpx.AsyncClient") as mock_client_cls:
            mock_inner = MagicMock()
            mock_client_cls.return_value = mock_inner

            client = EgressAwareAsyncClient(
                egress_controller=mock_egress_controller,
                tenant_id=1,
            )

            with pytest.raises(EgressBlockedError) as exc_info:
                await client.get("https://evil.com/api")

            assert "evil.com" in str(exc_info.value)
            assert "Domain not in allowlist" in str(exc_info.value)
            mock_inner.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_allowed_request_proceeds(self, mock_egress_controller):
        """Allowed domain proceeds with HTTP request."""
        mock_egress_controller.validate_request.return_value = EgressResult(
            decision=EgressDecision.ALLOW,
            resolved_ip="1.2.3.4",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("src.core.security.egress_aware_client.httpx.AsyncClient") as mock_client_cls:
            mock_inner = MagicMock()
            mock_inner.request = AsyncMock(return_value=mock_response)
            mock_inner.aclose = AsyncMock()
            mock_client_cls.return_value = mock_inner

            async with EgressAwareAsyncClient(
                egress_controller=mock_egress_controller,
                tenant_id=1,
            ) as client:
                response = await client.get("https://allowed.com/api")

            assert response.status_code == 200
            mock_inner.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_egress_validated_with_correct_params(self, mock_egress_controller):
        """Egress validation receives correct tenant_id, agent_id, request_size."""
        mock_egress_controller.validate_request.return_value = EgressResult(
            decision=EgressDecision.ALLOW,
        )

        with patch("src.core.security.egress_aware_client.httpx.AsyncClient") as mock_client_cls:
            mock_inner = MagicMock()
            mock_inner.request = AsyncMock(return_value=MagicMock())
            mock_inner.aclose = AsyncMock()
            mock_client_cls.return_value = mock_inner

            async with EgressAwareAsyncClient(
                egress_controller=mock_egress_controller,
                tenant_id=42,
                agent_id="test_agent",
            ) as client:
                await client.post(
                    "https://api.example.com/data",
                    content=b"test payload",
                )

        mock_egress_controller.validate_request.assert_called_once()
        call_kwargs = mock_egress_controller.validate_request.call_args[1]
        assert call_kwargs["tenant_id"] == 42
        assert call_kwargs["agent_id"] == "test_agent"
        assert call_kwargs["request_size"] == len(b"test payload")

    @pytest.mark.asyncio
    async def test_rate_limited_request_raises_error(self, mock_egress_controller):
        """Rate limited decision raises EgressBlockedError."""
        mock_egress_controller.validate_request.return_value = EgressResult(
            decision=EgressDecision.RATE_LIMITED,
            reason="Rate limit exceeded",
        )

        with patch("src.core.security.egress_aware_client.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()

            client = EgressAwareAsyncClient(
                egress_controller=mock_egress_controller,
                tenant_id=1,
            )

            with pytest.raises(EgressBlockedError) as exc_info:
                await client.get("https://api.example.com/data")

            assert "Rate limit exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_context_manager_aclose_called(self, mock_egress_controller):
        """Async context manager closes inner httpx client on exit."""
        mock_egress_controller.validate_request.return_value = EgressResult(
            decision=EgressDecision.ALLOW,
        )

        with patch("src.core.security.egress_aware_client.httpx.AsyncClient") as mock_client_cls:
            mock_inner = MagicMock()
            mock_inner.aclose = AsyncMock()
            mock_client_cls.return_value = mock_inner

            async with EgressAwareAsyncClient(
                egress_controller=mock_egress_controller,
                tenant_id=1,
            ) as client:
                pass

            mock_inner.aclose.assert_called_once()
