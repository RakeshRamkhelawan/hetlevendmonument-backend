"""Unit tests: ExternalAgentService bcrypt api_key verification -- SP-SEC-002 review-fix.

Regression guard for the auth-bypass found in independent review of commit 84917b73:
`if api_key and not bcrypt.checkpw(...)` skipped verification entirely when api_key
was an empty string, which an attacker could trigger via header `agent_id:` (empty
credential after the colon). Fix: explicit-but-empty api_key must fail closed;
only api_key=None (internal/trusted caller, no API-key layer involved) skips the check.
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import bcrypt
import pytest

from src.core.company.external_agent_service import ExternalAgentService
from src.core.exceptions.exceptions import AuthError

CORRECT_CREDENTIAL = "known-good-value-123"
WRONG_CREDENTIAL = "definitely-not-it-456"


def _real_hash(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def mock_agent_with_hash():
    agent = MagicMock()
    agent.api_key_hash = _real_hash(CORRECT_CREDENTIAL)
    agent.company_id = 1
    agent.department_id = 1
    return agent


@pytest.fixture
def service_with_agent(mock_agent_with_hash):
    mock_session = AsyncMock()

    @asynccontextmanager
    async def _get_session():
        yield mock_session

    db = MagicMock()
    db.get_session = _get_session

    tenant_ctx = MagicMock()
    tenant_ctx.tenant_id = 1

    svc = ExternalAgentService(
        db_manager=db,
        tenant_context=tenant_ctx,
        policy_engine=MagicMock(),
        budget_manager=None,
    )
    svc._get_agent = AsyncMock(return_value=mock_agent_with_hash)
    svc._get_pending_tasks = AsyncMock(return_value=[])
    svc._get_task = AsyncMock(return_value=None)
    return svc


class TestGetNextTaskApiKeyVerification:
    @pytest.mark.asyncio
    async def test_empty_credential_raises_auth_error(self, service_with_agent):
        """Empty-but-explicit credential must fail closed, not skip verification."""
        with pytest.raises(AuthError):
            await service_with_agent.get_next_task(uuid.uuid4(), "")

    @pytest.mark.asyncio
    async def test_wrong_credential_raises_auth_error(self, service_with_agent):
        with pytest.raises(AuthError):
            await service_with_agent.get_next_task(uuid.uuid4(), WRONG_CREDENTIAL)

    @pytest.mark.asyncio
    async def test_correct_credential_succeeds(self, service_with_agent):
        result = await service_with_agent.get_next_task(uuid.uuid4(), CORRECT_CREDENTIAL)
        assert result is None  # no pending tasks, but no AuthError raised

    @pytest.mark.asyncio
    async def test_no_credential_provided_skips_verification_for_internal_callers(
        self, service_with_agent
    ):
        """Not passing a credential at all (None default) is the internal/trusted-caller path."""
        result = await service_with_agent.get_next_task(uuid.uuid4())
        assert result is None


class TestCompleteTaskApiKeyVerification:
    @pytest.mark.asyncio
    async def test_empty_credential_raises_auth_error(self, service_with_agent):
        from src.core.company.schemas import TaskCompleteRequest

        data = TaskCompleteRequest(status="completed", output={})
        with pytest.raises(AuthError):
            await service_with_agent.complete_task(uuid.uuid4(), uuid.uuid4(), data, "")

    @pytest.mark.asyncio
    async def test_wrong_credential_raises_auth_error(self, service_with_agent):
        from src.core.company.schemas import TaskCompleteRequest

        data = TaskCompleteRequest(status="completed", output={})
        with pytest.raises(AuthError):
            await service_with_agent.complete_task(
                uuid.uuid4(), uuid.uuid4(), data, WRONG_CREDENTIAL
            )


class TestHeartbeatApiKeyVerification:
    @pytest.mark.asyncio
    async def test_empty_credential_raises_auth_error(self, service_with_agent):
        from src.core.company.schemas import HeartbeatRequest

        with pytest.raises(AuthError):
            await service_with_agent.heartbeat(uuid.uuid4(), "", HeartbeatRequest(status="idle"))

    @pytest.mark.asyncio
    async def test_wrong_credential_raises_auth_error(self, service_with_agent):
        from src.core.company.schemas import HeartbeatRequest

        with pytest.raises(AuthError):
            await service_with_agent.heartbeat(
                uuid.uuid4(), WRONG_CREDENTIAL, HeartbeatRequest(status="idle")
            )
