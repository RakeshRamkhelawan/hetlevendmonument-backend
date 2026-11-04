"""
Concurrent hash chain integrity test for Agent Council.

Proves that 50 simultaneous deliberations for one tenant do not break
the per-tenant hash chain. Uses pg_advisory_xact_lock for serialization.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.members.audit_officer import AuditOfficer
from src.core.copilot.council.members.compliance_officer import ComplianceOfficer
from src.core.copilot.council.members.ethics_officer import EthicsOfficer
from src.core.copilot.council.members.privacy_officer import PrivacyOfficer
from src.core.copilot.council.members.resource_officer import ResourceOfficer
from src.core.copilot.council.members.risk_officer import RiskOfficer
from src.core.copilot.council.members.security_officer import SecurityOfficer
from src.core.copilot.council.models import CouncilDecisionRow
from src.core.copilot.council.types import CouncilDecision, Proposal
from tests.integration.copilot.conftest import make_proposal


@pytest.fixture
def async_session_factory(postgres_engine: Any) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the test engine (no shared transaction)."""
    return async_sessionmaker(
        bind=postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def council_factory() -> Callable[[AsyncSession], AgentCouncil]:
    """Return a callable that builds an AgentCouncil around a *fresh* session.

    Each concurrent task must get its own AsyncSession so that SQLAlchemy
    session-level locking does not accidentally serialize the test.
    """

    def _factory(session: AsyncSession) -> AgentCouncil:
        from unittest.mock import AsyncMock, MagicMock

        from src.core.copilot.council.audit_writer import CouncilAuditWriter
        from src.core.copilot.notification.budget import NotificationBudgetTracker
        from src.core.copilot.notification.preferences_repo import (
            UserNotificationPreferencesRepo,
        )

        class _SessionCtx:
            async def __aenter__(self) -> AsyncSession:
                return session

            async def __aexit__(self, *args: Any) -> None:
                pass

        audit_writer = CouncilAuditWriter(_SessionCtx)
        audit = AuditOfficer(audit_writer)

        mock_guardian = MagicMock()
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = "LOW_RISK"
        compliance = ComplianceOfficer(mock_guardian, mock_classifier)

        mock_gdpr = MagicMock()
        mock_gdpr.detect_pii.return_value = []
        mock_consent = MagicMock()
        mock_consent.has_consent.return_value = True
        mock_twin = MagicMock()
        privacy = PrivacyOfficer(mock_gdpr, mock_consent, mock_twin)

        mock_tool_broker = AsyncMock()
        mock_tool_broker.is_allowed.return_value = True
        mock_prompt_guard = MagicMock()
        mock_prompt_guard.scan.return_value = {"injection_detected": False}
        mock_rbac = AsyncMock()
        mock_rbac.user_has_scope_for.return_value = True
        security = SecurityOfficer(mock_tool_broker, mock_prompt_guard, mock_rbac)

        mock_shadow_ceo = AsyncMock()
        mock_shadow_ceo.assess.return_value = "LOW"
        mock_risk_register = AsyncMock()
        mock_risk_register.actor_track_record.return_value = []
        risk = RiskOfficer(mock_shadow_ceo, mock_risk_register)

        ethics = EthicsOfficer()

        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.check.return_value = True
        mock_prana = AsyncMock()
        mock_prana.has_budget.return_value = True
        fake_redis = MagicMock()
        fake_redis.eval = AsyncMock(return_value=1)
        fake_redis.register_script = MagicMock(return_value=MagicMock())
        budget_tracker = NotificationBudgetTracker(fake_redis)
        prefs_repo = UserNotificationPreferencesRepo(session)
        resource = ResourceOfficer(
            rate_limiter=mock_rate_limiter,
            prana_service=mock_prana,
            budget_tracker=budget_tracker,
            preferences_repo=prefs_repo,
        )

        from src.core.copilot.council.members.sanity_officer import SanityOfficer
        sanity = SanityOfficer()

        return AgentCouncil(
            compliance=compliance,
            privacy=privacy,
            security=security,
            risk=risk,
            ethics=ethics,
            resource=resource,
            sanity=sanity,
            audit=audit,
        )

    return _factory


async def _deliberate_in_own_session(
    council_factory: Callable[[AsyncSession], AgentCouncil],
    session_factory: async_sessionmaker[AsyncSession],
    proposal: Proposal,
) -> CouncilDecision:
    async with session_factory() as own_session:
        # RLS policy vereist tenant context; anders zijn reads invisible
        await own_session.execute(
            text("SET LOCAL app.current_tenant = '1'")
        )
        council = council_factory(own_session)
        return await council.deliberate(proposal)


@pytest.mark.integration
@pytest.mark.chaos
@pytest.mark.als
@pytest.mark.asyncio
async def test_50_concurrent_decisions_chain_intact(
    council_factory: Callable[[AsyncSession], AgentCouncil],
    async_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """50 simultaneous deliberations voor een tenant -> keten consistent.

    Bewijst dat audit_writer.get_previous_hash() + persist() serializable
    is via pg_advisory_xact_lock per tenant. Elke task heeft een EIGEN
    AsyncSession — anders serialiseert SQLAlchemy de calls op session-niveau
    en bewijst de test niets.
    """
    # Schone lei via een FRISSE sessie die direct commit — anders blokkeert
    # de TRUNCATE-lock (ACCESS EXCLUSIVE) de INSERTs van de 50 workers.
    async with async_session_factory() as cleanup_session:
        await cleanup_session.execute(
            text("TRUNCATE TABLE council_decisions, officer_verdicts CASCADE")
        )
        await cleanup_session.commit()

    proposals = [
        make_proposal(tenant_id=1, user_id=u + 1) for u in range(50)
    ]

    decisions = await asyncio.gather(
        *[
            _deliberate_in_own_session(
                council_factory, async_session_factory, p
            )
            for p in proposals
        ],
        return_exceptions=True,
    )

    # Filter eventuele exceptions zichtbaar
    exceptions = [d for d in decisions if isinstance(d, BaseException)]
    assert not exceptions, f"unexpected exceptions: {exceptions[:3]}"

    # Verifieer chain door links te volgen (niet sorteren op timestamp,
    # want creation-time != commit-time bij concurrentie).
    def _verify_chain(items: list, hash_attr: str, prev_attr: str) -> int:
        next_map = {
            getattr(d, prev_attr): d
            for d in items
        }
        genesis = next_map.get(None)
        assert genesis is not None, "geen genesis decision gevonden"
        current = genesis
        count = 1
        seen = {getattr(current, hash_attr)}
        while True:
            nxt = next_map.get(getattr(current, hash_attr))
            if nxt is None:
                break
            nxt_hash = getattr(nxt, hash_attr)
            assert nxt_hash not in seen, f"cycle detected bij {nxt_hash}"
            seen.add(nxt_hash)
            current = nxt
            count += 1
        return count

    mem_count = _verify_chain(
        decisions, "decision_hash", "previous_decision_hash"
    )
    assert mem_count == 50, f"expected chain lengte 50, got {mem_count}"

    # Verifieer ook in DB (geschreven state)
    result = await db_session.execute(
        select(CouncilDecisionRow).where(CouncilDecisionRow.tenant_id == 1)
    )
    rows = result.scalars().all()
    assert len(rows) >= 50, f"expected >=50 rows, got {len(rows)}"
    db_count = _verify_chain(rows, "decision_hash", "previous_decision_hash")
    assert db_count == 50, f"expected db chain lengte 50, got {db_count}"
