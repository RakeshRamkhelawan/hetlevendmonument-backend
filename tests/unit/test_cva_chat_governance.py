"""
Unit tests for CVA Chat Governance integration.

Tests that the CVA chat endpoint properly integrates with:
- GovernanceVetoError propagation from CVAService (ADR-031)
- Timeout handling
- System prompt override protection
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.api.v1.cva.chat_router import chat_endpoint
from src.core.exceptions import GovernanceVetoError
from src.core.schemas.cva_schemas import ChatRequest
from src.core.services.llm.base import LLMTimeoutError
from tests.helpers.limiet_request import echte_request


@pytest.fixture
def mock_current_user():
    """Mock authenticated user for tests."""
    user = Mock()
    user.id = 123
    user.tenant_id = 42
    user.email = "user@example.com"
    user.roles = []
    user.scopes = []
    return user


@pytest.fixture
def mock_llm_service():
    """Mock LLM service for tests."""
    llm_service = AsyncMock()
    llm_service.provider = Mock()
    llm_service.provider.config = Mock(model="test-model", timeout=30)
    llm_service.generate = AsyncMock(
        return_value=("Hello response", {"total_tokens": 10, "model": "test"})
    )
    return llm_service


def create_mock_db_session():
    """Create a properly mocked async DB session with SQLAlchemy result chain."""
    session = AsyncMock()
    mock_scalars = Mock()
    mock_scalars.all = Mock(return_value=[])
    mock_result = Mock()
    mock_result.scalars = Mock(return_value=mock_scalars)
    mock_result.scalar_one_or_none = Mock(return_value=None)
    session.execute = AsyncMock(return_value=mock_result)
    session.add = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock(return_value=None)
    session.refresh = AsyncMock()
    return session


class TestCvaChatGovernance:
    """Test suite for CVA chat governance integration."""

    @pytest.mark.asyncio
    async def test_chat_blocked_by_governance(self, mock_current_user, mock_llm_service):
        """GovernanceVetoError from CVAService propagates through chat_endpoint (ADR-031)."""
        mock_db = create_mock_db_session()

        with patch("src.core.services.cva_service.CVAService") as MockCVAService:
            instance = MockCVAService.return_value
            instance.chat = AsyncMock(
                side_effect=GovernanceVetoError(
                    message="Governance policy violation",
                    decision_id="00000000-0000-0000-0000-000000000001",
                    verdict="BLOCKED",
                )
            )
            with pytest.raises(GovernanceVetoError) as exc_info:
                await chat_endpoint(
                    request=ChatRequest(message="generate a deployment plan"),
                    http_request=echte_request(),
                    db=mock_db,
                    current_user=mock_current_user,
                    llm_service=mock_llm_service,
                )

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "GOVERNANCE_BLOCKED"
        assert exc_info.value.details.get("verdict") == "BLOCKED"

    @pytest.mark.asyncio
    async def test_chat_requires_human_approval(self, mock_current_user, mock_llm_service):
        """HITL_REQUIRED verdict raises GovernanceVetoError with correct verdict field."""
        mock_db = create_mock_db_session()

        with patch("src.core.services.cva_service.CVAService") as MockCVAService:
            instance = MockCVAService.return_value
            instance.chat = AsyncMock(
                side_effect=GovernanceVetoError(
                    message="High-risk action requires human approval",
                    decision_id="00000000-0000-0000-0000-000000000002",
                    verdict="HITL_REQUIRED",
                )
            )
            with pytest.raises(GovernanceVetoError) as exc_info:
                await chat_endpoint(
                    request=ChatRequest(message="start critical migration"),
                    http_request=echte_request(),
                    db=mock_db,
                    current_user=mock_current_user,
                    llm_service=mock_llm_service,
                )

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "GOVERNANCE_BLOCKED"
        assert exc_info.value.details.get("verdict") == "HITL_REQUIRED"

    @pytest.mark.asyncio
    async def test_chat_timeout_returns_503(self, mock_current_user, mock_llm_service):
        """LLMTimeoutError from CVAService is converted to 503 by chat_endpoint."""
        from fastapi import HTTPException

        mock_db = create_mock_db_session()

        with patch("src.core.services.cva_service.CVAService") as MockCVAService:
            instance = MockCVAService.return_value
            instance.chat = AsyncMock(side_effect=LLMTimeoutError("LLM timeout"))
            with pytest.raises(HTTPException) as exc_info:
                await chat_endpoint(
                    request=ChatRequest(message="hello"),
                    http_request=echte_request(),
                    db=mock_db,
                    current_user=mock_current_user,
                    llm_service=mock_llm_service,
                )

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_system_prompt_override_without_admin_returns_403(
        self, mock_current_user, mock_llm_service
    ):
        """System prompt override without admin scope raises 403 before CVAService is called."""
        from fastapi import HTTPException

        mock_db = create_mock_db_session()
        mock_current_user.scopes = ["user:read"]

        with patch("src.core.services.cva_service.CVAService") as MockCVAService:
            instance = MockCVAService.return_value
            instance.chat = AsyncMock()
            with pytest.raises(HTTPException) as exc_info:
                await chat_endpoint(
                    request=ChatRequest(message="hello", system_prompt="override"),
                    http_request=echte_request(),
                    db=mock_db,
                    current_user=mock_current_user,
                    llm_service=mock_llm_service,
                )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Admin privileges required for system prompt override"
        # CVAService.chat must NOT have been called (guard fires before service)
        instance.chat.assert_not_called()
