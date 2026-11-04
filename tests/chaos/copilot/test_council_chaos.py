"""
Chaos tests for Agent Council — deterministic, no wall-clock dependencies.

Covers fail-secure behaviors per ADR-027 §3:
- Officer timeout → REQUIRE_HITL (een mens beslist); crash → synthetic VETO
- Audit write failure → BLOCKED + 0 DB rows
- Total council outage → BLOCKED with all 7 synthetic verdicts
- Concurrent chain integrity via advisory lock

Every test injects exactly ONE fault type so a red test maps to one cause.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, assert_never
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from src.core.copilot.council.audit_writer import AuditWriteError
from src.core.copilot.council.coordinator import AgentCouncil, ConfigurationError
from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.models import CouncilDecisionRow
from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def make_safe_proposal(
    tenant_id: int = 1,
    user_id: int = 1,
    model_id: str = "deepseek-chat",
    model_version: str = "v3",
    action_params: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Proposal:
    """Build a proposal that normally passes all Officers."""
    params = {
        "url": "/dashboard",
        "ai_disclosure": "Deze actie wordt voorgesteld door AI",
        "model_id": model_id,
        "model_version": model_version,
    }
    if action_params is not None:
        params.update(action_params)
    return Proposal(
        tenant_id=tenant_id,
        user_id=user_id,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="navigate_to",
        action_params=params,
        reasoning="User vroeg om naar dashboard te navigeren.",
        data_classification=DataClassification.PUBLIC,
        confidence=0.95,
        model_id=model_id,
        model_version=model_version,
        context_snapshot={},
        **kwargs,
    )


@dataclass(frozen=True)
class SlowResponse:
    """Triggert timeout zonder echte wall-clock wait.

    De Officer wacht op een asyncio.Event die de test bewust nooit set.
    De coordinator's ``asyncio.wait_for(..., timeout=officer.timeout_ms/1000)``
    raised dan TimeoutError op virtueel-bepaalde tijd.
    """

    delay_ms: int


@dataclass(frozen=True)
class RaiseException:
    exc: BaseException


@dataclass(frozen=True)
class FixedVerdict:
    verdict: VerdictType
    reason_code: str = "TEST"


MockBehavior = SlowResponse | RaiseException | FixedVerdict


class MockOfficer(Officer):
    """Instelbare mock Officer voor chaos tests (geen wall-clock dependency)."""

    def __init__(
        self,
        *,
        name: str,
        timeout_ms: int = 800,
        can_veto: bool = True,
        behavior: MockBehavior,
    ) -> None:
        super().__init__()
        self.name = name
        self.version = "test-1.0.0"
        self.timeout_ms = timeout_ms
        self.can_veto = can_veto
        self._behavior = behavior

    async def deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        if isinstance(self._behavior, SlowResponse):
            never = asyncio.Event()
            await never.wait()
            raise RuntimeError("unreachable")
        if isinstance(self._behavior, RaiseException):
            raise self._behavior.exc
        if isinstance(self._behavior, FixedVerdict):
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=self._behavior.verdict,
                confidence=1.0,
                reason_code=self._behavior.reason_code,
                reason_text="test mock",
                evidence={},
            )
        assert_never(self._behavior)


    async def finalize_and_persist(
        self,
        proposal: Proposal,
        officer_verdicts: tuple[OfficerVerdict, ...],
        final_verdict: DecisionVerdict,
        modifications: dict[str, Any] | None,
        hitl_request_id: Any,
        start_ms: float,
        context: DeliberationContext,
    ) -> CouncilDecision:
        """AuditOfficer-path: raise AuditWriteError bij RaiseException."""
        if isinstance(self._behavior, RaiseException):
            raise AuditWriteError("mock audit failure") from self._behavior.exc
        if isinstance(self._behavior, FixedVerdict):
            return CouncilDecision(
                proposal_id=proposal.proposal_id,
                tenant_id=proposal.tenant_id,
                user_id=proposal.user_id,
                verdict=final_verdict,
                officer_verdicts=officer_verdicts,
                explanation_for_user="test",
                decision_hash="HASH",
                previous_decision_hash=None,
                deliberation_ms=0,
            )
        # SlowResponse wordt hier nooit bereikt in de normale flow
        raise RuntimeError("unreachable")


@pytest.fixture
def instant_timeout(monkeypatch: Any) -> None:
    """Patch asyncio.wait_for zodat timeout direct triggert, geen echte wait.

    Patchen op de geimporteerde referentie in coordinator — niet op
    ``asyncio.wait_for`` globaal — zodat andere tests niet beinvloed worden.
    """

    async def fake_wait_for(coro: Any, timeout: float) -> Any:
        task = asyncio.create_task(coro) if not isinstance(coro, asyncio.Task) else coro
        # Geef de event loop één kans om de task af te maken.
        # Officers met instant deliberate() zijn done na één tick;
        # MockOfficer met SlowResponse (never.wait()) blijft hangen.
        await asyncio.sleep(0)
        if task.done():
            return task.result()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise asyncio.TimeoutError()

    monkeypatch.setattr(
        "src.core.copilot.council.coordinator.wait_for",
        fake_wait_for,
    )


# ----------------------------------------------------------------------------
# C2 — Officer timeout
# ----------------------------------------------------------------------------


@pytest.mark.chaos
@pytest.mark.als
async def test_officer_timeout_interpreted_as_veto(
    real_council_factory: Any,
    instant_timeout: None,
) -> None:
    """Officer die langer dan timeout_ms doet -> synthetic VETO -> BLOCKED."""
    slow = MockOfficer(
        name="ComplianceOfficer",
        timeout_ms=800,
        behavior=SlowResponse(delay_ms=900),
    )
    council = real_council_factory(replace={"compliance": slow})
    decision = await council.deliberate(make_safe_proposal())

    assert decision.verdict == DecisionVerdict.HITL_REQUIRED
    uitgesteld = next(
        v for v in decision.officer_verdicts
        if v.officer_name == "ComplianceOfficer"
    )
    assert uitgesteld.verdict == VerdictType.REQUIRE_HITL
    assert uitgesteld.reason_code == "TIMEOUT"


@pytest.mark.chaos
async def test_non_veto_officer_timeout_results_in_defer(
    real_council_factory: Any,
    instant_timeout: None,
) -> None:
    """EthicsOfficer (can_veto=False) timeout -> synthetic DEFER, niet BLOCKED en geen mensticket (geen ticketvloed)."""
    slow_ethics = MockOfficer(
        name="EthicsOfficer",
        timeout_ms=500,
        can_veto=False,
        behavior=SlowResponse(delay_ms=600),
    )
    council = real_council_factory(replace={"ethics": slow_ethics})
    decision = await council.deliberate(make_safe_proposal())

    assert decision.verdict == DecisionVerdict.DEFERRED
    ethics_verdict = next(
        v for v in decision.officer_verdicts
        if v.officer_name == "EthicsOfficer"
    )
    assert ethics_verdict.verdict == VerdictType.REQUIRE_DEFERRAL
    assert ethics_verdict.reason_code == "TIMEOUT"


# ----------------------------------------------------------------------------
# C3 — Audit write failure
# ----------------------------------------------------------------------------


@pytest.mark.chaos
@pytest.mark.als
async def test_audit_write_failure_blocks_execution(
    real_council_factory: Any,
    db_session: Any,
) -> None:
    """DB error in audit_writer.persist() -> BLOCKED, geen council_decisions row."""
    broken_writer = AsyncMock()
    broken_writer.persist.side_effect = RuntimeError("simulated DB outage")
    broken_writer.get_previous_hash.return_value = None

    council = real_council_factory(audit_writer=broken_writer)
    proposal = make_safe_proposal(tenant_id=99)

    decision = await council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.BLOCKED

    # Verifieer dat GEEN row geschreven is — fail-secure
    result = await db_session.execute(
        select(func.count())
        .select_from(CouncilDecisionRow)
        .where(CouncilDecisionRow.tenant_id == 99)
    )
    assert result.scalar() == 0


# ----------------------------------------------------------------------------
# C5/C6 — Officer crash
# ----------------------------------------------------------------------------


@pytest.mark.chaos
@pytest.mark.als
async def test_one_officer_crash_does_not_break_others(
    real_council_factory: Any,
) -> None:
    """RuntimeError in EthicsOfficer -> synthetic DEFER, andere verdicts blijven."""
    crashing_ethics = MockOfficer(
        name="EthicsOfficer",
        can_veto=False,
        behavior=RaiseException(RuntimeError("simulated crash")),
    )
    council = real_council_factory(replace={"ethics": crashing_ethics})
    decision = await council.deliberate(make_safe_proposal())

    # Ethics kan niet vetoen -> DEFER; rest approve -> DEFERRED
    assert decision.verdict == DecisionVerdict.DEFERRED
    others = [
        v for v in decision.officer_verdicts
        if v.officer_name != "EthicsOfficer"
    ]
    assert len(others) == 5, f"expected 5 other officer verdicts, got {len(others)}"
    for v in others:
        assert v.reason_code not in (
            "INTERNAL_ERROR",
            "TIMEOUT",
            "DEPENDENCY_FAILURE",
        )


@pytest.mark.chaos
async def test_veto_capable_officer_crash_blocks_decision(
    real_council_factory: Any,
) -> None:
    """Crash in ComplianceOfficer (can_veto=True) -> BLOCKED (fail-secure)."""
    crashing = MockOfficer(
        name="ComplianceOfficer",
        can_veto=True,
        behavior=RaiseException(ConnectionError("db down")),
    )
    council = real_council_factory(replace={"compliance": crashing})
    decision = await council.deliberate(make_safe_proposal())

    assert decision.verdict == DecisionVerdict.BLOCKED
    veto = next(
        v for v in decision.officer_verdicts
        if v.officer_name == "ComplianceOfficer"
    )
    assert veto.reason_code == "INTERNAL_ERROR"


# ----------------------------------------------------------------------------
# C7 — Audit officer crash
# ----------------------------------------------------------------------------


@pytest.mark.chaos
async def test_audit_officer_crash_blocks_even_if_all_others_approve(
    real_council_factory: Any,
) -> None:
    """Audit is non-voting maar essentieel — crash -> BLOCKED."""
    broken_audit = MockOfficer(
        name="AuditOfficer",
        can_veto=True,
        behavior=RaiseException(RuntimeError("audit DB down")),
    )
    council = real_council_factory(replace={"audit": broken_audit})
    decision = await council.deliberate(make_safe_proposal())
    assert decision.verdict == DecisionVerdict.BLOCKED


# ----------------------------------------------------------------------------
# C8/C9 — Construction validation
# ----------------------------------------------------------------------------


@pytest.mark.chaos
def test_coordinator_rejects_duplicate_officer_name() -> None:
    """Bouwen van Council met 2 Officers met zelfde name -> fail at construction."""
    o1 = MockOfficer(name="EthicsOfficer", behavior=FixedVerdict(VerdictType.APPROVE))
    o2 = MockOfficer(name="EthicsOfficer", behavior=FixedVerdict(VerdictType.APPROVE))
    audit = MockOfficer(name="AuditOfficer", behavior=FixedVerdict(VerdictType.APPROVE))
    with pytest.raises(ConfigurationError, match="duplicate officer"):
        AgentCouncil(
            compliance=MockOfficer(
                name="ComplianceOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            privacy=MockOfficer(
                name="PrivacyOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            security=MockOfficer(
                name="SecurityOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            risk=MockOfficer(
                name="RiskOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            ethics=o1,
            resource=o2,
            audit=audit,
        )


@pytest.mark.chaos
def test_coordinator_rejects_officer_without_version() -> None:
    """Council met Officer zonder version string = configuration error."""
    bad = MockOfficer(
        name="ComplianceOfficer",
        behavior=FixedVerdict(VerdictType.APPROVE),
    )
    bad.version = ""
    audit = MockOfficer(name="AuditOfficer", behavior=FixedVerdict(VerdictType.APPROVE))
    with pytest.raises(ConfigurationError, match="missing a version string"):
        AgentCouncil(
            compliance=bad,
            privacy=MockOfficer(
                name="PrivacyOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            security=MockOfficer(
                name="SecurityOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            risk=MockOfficer(
                name="RiskOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            ethics=MockOfficer(
                name="EthicsOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            resource=MockOfficer(
                name="ResourceOfficer",
                behavior=FixedVerdict(VerdictType.APPROVE),
            ),
            audit=audit,
        )


# ----------------------------------------------------------------------------
# C10 — Missing metadata
# ----------------------------------------------------------------------------


@pytest.mark.chaos
async def test_proposal_without_model_id_in_action_params_is_blocked(
    real_council: Any,
) -> None:
    """AI Act vereist model_id + version in action_params. Ontbreekt -> VETO."""
    bad_proposal = make_safe_proposal(
        action_params={
            "ai_disclosure": "Deze actie wordt voorgesteld door AI",
            "model_id": "",
            "model_version": "",
        },
    )
    decision = await real_council.deliberate(bad_proposal)
    assert decision.verdict == DecisionVerdict.BLOCKED


# ----------------------------------------------------------------------------
# C11 — Network partition placeholder
# ----------------------------------------------------------------------------


@pytest.mark.chaos
async def test_redis_unavailable_council_still_works(
    real_council_factory: Any,
) -> None:
    """Redis down -> cache fail-open: Council still reaches verdict via Officers."""
    from src.core.copilot.council.cache import OfficerVerdictCache

    class BrokenRedis:
        async def get(self, key: str) -> Any:
            raise ConnectionError("Redis is down")

        async def set(self, key: str, value: Any, ex: int | None = None) -> Any:
            raise ConnectionError("Redis is down")

        async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[str]]:
            raise ConnectionError("Redis is down")

        async def delete(self, *keys: str) -> int:
            raise ConnectionError("Redis is down")

    broken_cache = OfficerVerdictCache(BrokenRedis())

    # Inject broken cache into all three cacheable Officers
    council = real_council_factory()
    for officer in council._voting_officers:
        if officer.can_cache:
            officer._cache = broken_cache

    proposal = make_safe_proposal()
    decision = await council.deliberate(proposal)

    # Council must still produce a valid decision (cache fail-open)
    assert decision.verdict in {
        DecisionVerdict.APPROVED,
        DecisionVerdict.MODIFIED,
        DecisionVerdict.HITL_REQUIRED,
        DecisionVerdict.DEFERRED,
        DecisionVerdict.BLOCKED,
    }

    # All cacheable Officers must have used_cache=False (cache miss, not error)
    for v in decision.officer_verdicts:
        if v.officer_name in ("ComplianceOfficer", "SecurityOfficer", "EthicsOfficer"):
            assert v.used_cache is False, (
                f"{v.officer_name} should not report used_cache=True when Redis is down"
            )


# ----------------------------------------------------------------------------
# C12 — Total council outage
# ----------------------------------------------------------------------------


@pytest.mark.chaos
@pytest.mark.als
async def test_all_officers_crash_council_returns_safe_default(
    real_council_factory: Any,
) -> None:
    """Worst-case: ALLE 7 Officers raise -> Council MOET BLOCKED returnen.

    Bewijst dat coordinator nooit een silent APPROVE produceert bij
    totale Council-uitval. Edge case voor disaster-recovery scenarios.
    """

    def crash(name: str, can_veto: bool) -> MockOfficer:
        return MockOfficer(
            name=name,
            can_veto=can_veto,
            behavior=RaiseException(
                ConnectionError("simulated full outage")
            ),
        )

    council = real_council_factory(
        replace={
            "compliance": crash("ComplianceOfficer", True),
            "privacy": crash("PrivacyOfficer", True),
            "security": crash("SecurityOfficer", True),
            "risk": crash("RiskOfficer", True),
            "ethics": crash("EthicsOfficer", False),
            "resource": crash("ResourceOfficer", False),
            "audit": crash("AuditOfficer", True),
        }
    )

    decision = await council.deliberate(make_safe_proposal())

    # Fail-secure: bij twijfel BLOCK — geen silent APPROVE
    assert decision.verdict == DecisionVerdict.BLOCKED

    # Bewijs dat ELKE Officer een synthetic verdict geproduceerd heeft
    names_with_verdict = {v.officer_name for v in decision.officer_verdicts}
    assert len(names_with_verdict) == 7, (
        f"expected 7 synthetic verdicts, got {len(names_with_verdict)}: {names_with_verdict}"
    )

    # En alle synthetic verdicts hebben een failure reason_code
    for v in decision.officer_verdicts:
        assert v.reason_code in (
            "INTERNAL_ERROR",
            "TIMEOUT",
            "DEPENDENCY_FAILURE",
            "AUDIT_WRITE_FAILED",
        ), (
            f"{v.officer_name} had reason_code={v.reason_code} "
            f"(expected failure code)"
        )
