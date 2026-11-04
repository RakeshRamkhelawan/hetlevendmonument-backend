"""
Fixtures for Co-Pilot Council integration tests.

Provides a `real_council` fixture with 8 real Officers (real business logic)
with mocked upstream services (ToolBroker, Shadow CEO, Prana) that are
outside Council scope.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.core.copilot.council.audit_writer import CouncilAuditWriter
from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.members.audit_officer import AuditOfficer
from src.core.copilot.council.members.compliance_officer import ComplianceOfficer
from src.core.copilot.council.members.ethics_officer import EthicsOfficer
from src.core.copilot.council.members.privacy_officer import PrivacyOfficer
from src.core.copilot.council.members.resource_officer import ResourceOfficer
from src.core.copilot.council.members.risk_officer import RiskOfficer
from src.core.copilot.council.members.sanity_officer import SanityOfficer
from src.core.copilot.council.members.security_officer import SecurityOfficer
from src.core.copilot.council.types import (
    DataClassification,
    Proposal,
    ProposalTrigger,
)
from src.core.copilot.notification.budget import NotificationBudgetTracker
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo
from src.core.models.rbac_models import Tenant


class FakeBudgetRedis:
    """Minimal Redis test double that supports the Lua script used by NotificationBudgetTracker."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    async def eval(self, script: str, num_keys: int, *args: Any) -> int:
        """Simulate LUA_INCR_WITH_LIMIT atomic behaviour."""
        key = str(args[0])
        ttl = int(args[1])  # noqa: F841
        limit = int(args[2])
        val = self._counters.get(key, 0) + 1
        self._counters[key] = val
        if val > limit:
            self._counters[key] = val - 1
            return -1
        return val

    def register_script(self, lua: str) -> Any:
        """Return a callable script object backed by this fake Redis."""

        class Script:
            def __init__(self, redis: FakeBudgetRedis) -> None:
                self._redis = redis

            async def __call__(self, keys: list[str], args: list[str]) -> int:
                return await self._redis.eval(lua, len(keys), *keys, *args)

        return Script(self)


async def seed_tenants(db_session: Any, tenant_ids: list[int]) -> None:
    """Insert minimal Tenant rows so FK constraints on council_decisions succeed."""
    from sqlalchemy import select

    for tid in tenant_ids:
        existing = await db_session.execute(select(Tenant).where(Tenant.id == tid))
        if existing.scalar_one_or_none() is None:
            db_session.add(
                Tenant(
                    id=tid,
                    name=f"Test Tenant {tid}",
                    slug=f"test-tenant-{tid}",
                )
            )
    await db_session.commit()


def make_proposal(
    tenant_id: int = 1,
    user_id: int = 1,
    trigger: ProposalTrigger = ProposalTrigger.USER_REQUEST,
    action_type: str = "navigate_to",
    action_params: dict[str, Any] | None = None,
    message: str = "Final message to user.",
    reasoning: str = "User requested action.",
    data_classification: DataClassification = DataClassification.PUBLIC,
    confidence: float = 0.95,
    model_id: str = "deepseek-chat",
    model_version: str = "v3",
    context_snapshot: dict[str, Any] | None = None,
) -> Proposal:
    """Build a Proposal for Council deliberation tests."""
    return Proposal(
        tenant_id=tenant_id,
        user_id=user_id,
        trigger=trigger,
        action_type=action_type,
        action_params=action_params or {},
        message=message,
        reasoning=reasoning,
        data_classification=data_classification,
        confidence=confidence,
        model_id=model_id,
        model_version=model_version,
        context_snapshot=context_snapshot or {},
    )


def _build_council(
    db_session: Any,
    replace: dict[str, Any] | None = None,
    audit_writer: Any | None = None,
) -> AgentCouncil:
    """Build a Council with optional officer replacements."""
    replace = replace or {}

    class _SessionCtx:
        async def __aenter__(self) -> Any:
            return db_session

        async def __aexit__(self, *args: Any) -> None:
            pass

    def db_session_factory() -> _SessionCtx:
        return _SessionCtx()

    writer = audit_writer if audit_writer is not None else CouncilAuditWriter(db_session_factory)
    audit = replace.get("audit", AuditOfficer(writer))

    # ComplianceOfficer
    if "compliance" in replace:
        compliance = replace["compliance"]
    else:
        mock_guardian = MagicMock()
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = "LOW_RISK"
        compliance = ComplianceOfficer(mock_guardian, mock_classifier)

    # PrivacyOfficer
    if "privacy" in replace:
        privacy = replace["privacy"]
    else:
        mock_gdpr = MagicMock()
        mock_gdpr.detect_pii.return_value = []
        mock_consent = MagicMock()
        mock_consent.has_consent.return_value = True
        mock_twin = MagicMock()
        privacy = PrivacyOfficer(mock_gdpr, mock_consent, mock_twin)

    # SecurityOfficer
    if "security" in replace:
        security = replace["security"]
    else:
        mock_tool_broker = AsyncMock()
        mock_tool_broker.is_allowed.return_value = True
        mock_prompt_guard = MagicMock()
        mock_prompt_guard.scan.return_value = {"injection_detected": False}
        mock_rbac = AsyncMock()
        mock_rbac.user_has_scope_for.return_value = True
        security = SecurityOfficer(mock_tool_broker, mock_prompt_guard, mock_rbac)

    # RiskOfficer
    if "risk" in replace:
        risk = replace["risk"]
    else:
        mock_shadow_ceo = AsyncMock()
        mock_shadow_ceo.assess.return_value = "LOW"
        mock_risk_register = AsyncMock()
        mock_risk_register.actor_track_record.return_value = []
        risk = RiskOfficer(mock_shadow_ceo, mock_risk_register)

    # EthicsOfficer
    ethics = replace.get("ethics", EthicsOfficer())

    # SanityOfficer
    sanity = replace.get("sanity", SanityOfficer())

    # ResourceOfficer
    if "resource" in replace:
        resource = replace["resource"]
    else:
        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.check.return_value = True
        mock_prana = AsyncMock()
        mock_prana.has_budget.return_value = True
        fake_redis = FakeBudgetRedis()
        budget_tracker = NotificationBudgetTracker(fake_redis)
        prefs_repo = UserNotificationPreferencesRepo(db_session)
        resource = ResourceOfficer(
            rate_limiter=mock_rate_limiter,
            prana_service=mock_prana,
            budget_tracker=budget_tracker,
            preferences_repo=prefs_repo,
        )

    council = AgentCouncil(
        compliance=compliance,
        privacy=privacy,
        security=security,
        risk=risk,
        ethics=ethics,
        resource=resource,
        sanity=sanity,
        audit=audit,
    )
    return council


@pytest_asyncio.fixture
async def real_council(db_session: Any) -> AgentCouncil:
    """Build Council with 8 real Officers (real business logic).

    Mocks ONLY upstream services outside Council scope:
    - ToolBroker (sprint 4)
    - Shadow CEO (sprint 4)
    - Prana token meter (sprint 4)
    """
    yield _build_council(db_session)


@pytest_asyncio.fixture
async def real_redis_client():
    """Provide a real Redis async client for integration tests."""
    import src.core.database.redis as redis_module

    # Reset any stale global pool to avoid "Event loop is closed" errors
    if redis_module._redis_pool is not None:
        try:
            await redis_module._redis_pool.disconnect()
        except Exception:
            pass
        redis_module._redis_pool = None

    client = await redis_module.get_redis_client()
    yield client
    try:
        await client.connection_pool.disconnect()
    except Exception:
        pass

    redis_module._redis_pool = None


@pytest.fixture
def real_council_factory(db_session: Any):
    """Factory fixture that returns a callable to build a Council with replacements.

    Usage:
        council = real_council_factory(replace={"compliance": mock_officer})
        council = real_council_factory(audit_writer=broken_writer)
    """

    def _factory(replace=None, audit_writer=None):
        return _build_council(db_session, replace=replace, audit_writer=audit_writer)

    return _factory


# ---------------------------------------------------------------------------
# Sprint 5 Day 5 -- mock fixtures for proactive monitor smoke tests and E2E
# ---------------------------------------------------------------------------


def _make_approved_decision(tenant_id: int = 1, user_id: int = 1) -> Any:
    """Build a minimal CouncilDecision with APPROVED verdict for test use."""
    import hashlib
    from uuid import uuid4

    from src.core.copilot.council.types import CouncilDecision, DecisionVerdict

    h = hashlib.sha256(str(uuid4()).encode()).hexdigest()
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(),
        explanation_for_user="Approved by smoke test fixture",
        decision_hash=h,
        previous_decision_hash=None,
        deliberation_ms=5,
    )


@pytest.fixture
def mock_copilot_service() -> Any:
    """CopilotService mock: submit_proactive_proposal always returns APPROVED."""
    svc = AsyncMock()
    svc.submit_proactive_proposal = AsyncMock(
        side_effect=lambda p: _make_approved_decision(tenant_id=p.tenant_id, user_id=p.user_id)
    )
    return svc


@pytest.fixture
def mock_dispatcher() -> Any:
    """NotificationDispatcher mock: dispatch() is a no-op."""
    disp = AsyncMock()
    disp.dispatch = AsyncMock()
    return disp


@pytest.fixture
def mock_tenant_repo() -> Any:
    """TenantRepo mock: returns tenant_id=1, admin_user_id=42."""
    repo = AsyncMock()
    repo.list_active_ids = AsyncMock(return_value=[1])
    repo.get_primary_admin_user_id = AsyncMock(return_value=42)
    repo.get_platform_admin_tenant_id = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def mock_health_registry() -> Any:
    """HealthMonitorRegistry mock: get_for_tenant returns None by default."""
    reg = MagicMock()
    reg.get_for_tenant = MagicMock(return_value=None)
    return reg


@pytest.fixture
def mock_prom() -> Any:
    """PrometheusClient mock: all metric reads return zero."""
    prom = AsyncMock()
    prom.list_workflows = AsyncMock(return_value=[])
    prom.execution_count = AsyncMock(return_value=0)
    prom.get_histogram_p95 = AsyncMock(return_value=0.0)
    prom.get_counter_sum = AsyncMock(return_value=0.0)
    prom.get_counter_average = AsyncMock(return_value=0.0)
    return prom


@pytest.fixture
def mock_failover_provider() -> Any:
    """FailoverLLMProvider mock: no open circuit states."""
    fp = AsyncMock()
    fp.get_circuit_states = AsyncMock(return_value={})
    return fp


@pytest.fixture
def mock_workflow_repo() -> Any:
    """WorkflowRepo mock: no active workflows."""
    repo = AsyncMock()
    repo.list_active = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_pii_scanner() -> Any:
    """WorkflowPIIScanner mock: no PII fields detected."""
    scanner = MagicMock()
    scanner.scan = MagicMock(return_value=[])
    return scanner


@pytest.fixture
def mock_dpia_repo() -> Any:
    """DPIARepo mock: DPIA always assumed to exist (no signal emitted)."""
    repo = AsyncMock()
    repo.exists_for_workflow = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_event_bus() -> Any:
    """EventBusProtocol mock: subscribe/unsubscribe are no-ops."""
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.unsubscribe = MagicMock()
    return bus


@pytest.fixture
def mock_audit_repo() -> Any:
    """AuditRepo mock (AuditAnomalyMonitor): no permission-denied events."""
    repo = AsyncMock()
    repo.count_permission_denied_per_user = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_role_repo() -> Any:
    """RoleRepo mock: no recent role creation (no grace period skip)."""
    repo = AsyncMock()
    repo.was_any_role_created_after = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def mock_consent_repo() -> Any:
    """ConsentRepo mock: no expiring consents."""
    repo = AsyncMock()
    repo.list_users_with_expiring_consent = AsyncMock(return_value=[])
    return repo
