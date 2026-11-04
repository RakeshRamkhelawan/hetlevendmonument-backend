"""
Factory for building a production-ready AgentCouncil.

Provides `build_council(db)` that wires all 7 Officers with their
dependencies.  Uses real implementations where full services are
available; thin adapters bridge interface mismatches so Officer
code never changes.

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING, Any
import contextlib

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.core.auth.rbac import RBACService

logger = logging.getLogger(__name__)

from src.core.als.enterprise.shadow.shadow_ceo import ShadowCEO
from src.core.als.infrastructure.redis_pool import get_redis_pool
from src.core.als.infrastructure.signal_bus import SignalBus
from src.core.copilot.council import AgentCouncil
from src.core.copilot.council.audit_writer import CouncilAuditWriter
from src.core.copilot.council.members.audit_officer import AuditOfficer
from src.core.copilot.council.members.compliance_officer import ComplianceOfficer
from src.core.copilot.council.members.ethics_officer import EthicsOfficer
from src.core.copilot.council.members.privacy_officer import PrivacyOfficer

from src.core.copilot.council.members.resource_officer import ResourceOfficer
from src.core.copilot.council.members.risk_officer import RiskOfficer
from src.core.copilot.council.members.sanity_officer import SanityOfficer
from src.core.copilot.council.members.security_officer import SecurityOfficer
from src.core.copilot.council.models import CouncilDecisionRow
from src.core.shared.ai_act_types import AIActRiskLevel
from src.core.shared.rate_limiter import InMemoryRateLimiter
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.events.event_bus import get_twin_event_bus
from src.core.learning.interfaces.llm_provider import MockSuggestionProvider
from src.core.learning.observers.user_behavior_observer import UserBehaviorObserver
from src.core.learning.rate_limiting.redis_rate_limiter import RedisRateLimiter
from src.core.learning.services.practical_twin_service import PracticalTwinService
from src.core.middleware.tenant_context import get_tenant_id, require_tenant_id
from src.core.shared.interfaces import TaskData
from src.core.copilot.council.types import Proposal
from src.core.tool_broker.permission_manager import ToolPermissionManager


class _AIActClassifierAdapter:
    """Bridge between the real AIActClassifier and ComplianceOfficer interface."""

    def __init__(self, classify_fn: Any = None) -> None:
        if classify_fn is None:
            import importlib

            _mod = importlib.import_module("src.core.governance.ai_act_classifier")
            classify_fn = _mod.classify_agent
        self._classify_fn = classify_fn

    def classify(self, action_type: str, action_params: dict[str, object]) -> str:
        dept = str(action_params.get("department") or "general")
        spec = str(action_params.get("specialisation") or action_type)
        caps = action_params.get("capabilities")
        capabilities = [str(c) for c in caps] if isinstance(caps, list) else [action_type]
        risk = self._classify_fn(
            name=action_type,
            department=dept,
            specialisation=spec,
            capabilities=capabilities,
        )
        if risk == AIActRiskLevel.UNACCEPTABLE:
            return "FORBIDDEN_PRACTICE"
        if risk == AIActRiskLevel.HIGH_RISK:
            return "HIGH_RISK"
        return "LOW_RISK"





class _ConsentGateAdapter:
    """Async consent gate adapter backed by TwinConsentManager.

    Fail-secure: returns False when tenant context is missing or DB raises.
    Per ADR-026 GDPR opt-in model: no consent = no twin data access.
    """

    def __init__(self, consent_manager: TwinConsentManager) -> None:
        self._consent_manager = consent_manager

    async def has_consent(self, user_id: int, tenant_id: int) -> bool:
        if tenant_id is None:
            logger.debug("consent_gate_no_tenant_context: fail-secure deny")
            return False
        try:
            categories = await self._consent_manager.get_consent_categories(str(user_id), tenant_id)
            return categories.cross_session_memory
        except Exception as exc:
            logger.warning(
                "consent_gate_check_failed: %s -- fail-secure deny",
                type(exc).__name__,
            )
            return False


class _ToolBrokerAdapter:
    """Bridge SecurityOfficer.is_allowed to ToolPermissionManager.

    agent_id selects the permission profile used for allowlist checks
    (ADR-015). The default "copilot" preserves HTTP Council behaviour;
    background agents pass their own agent_id via build_council(agent_id=...)
    so they are evaluated against their own profile (AUDIT-007, ADR-036 D2).
    Unknown agent_ids resolve to the ADR-015 default-deny -- fail-secure.
    """

    def __init__(self, agent_id: str = "copilot") -> None:
        self._mgr = ToolPermissionManager()
        self._agent_id = agent_id

    async def is_allowed(self, action_type: str, tenant_id: int, user_id: int) -> bool:
        # RC-007: agent_id defaults to "copilot" for HTTP Council backwards
        # compatibility; background agents are checked against their own profile.
        # tenant_id and user_id are unused for MVP; per-tenant tool permissions
        # are post-MVP.
        _ = (tenant_id, user_id)
        return self._mgr.is_tool_allowed(self._agent_id, action_type)


class _PromptGuardAdapter:
    """Adapts sync PromptGuard.sanitize() to SecurityOfficer's .scan() dict interface.

    SecurityOfficer calls .scan(text) expecting {"injection_detected": bool, "patterns": list}.
    The async PromptGuard (src.core.agents.prompt_guard) only has .scan_input() returning
    ScanResult -- a signature mismatch that causes AttributeError in production (SEC-004).
    This adapter wraps the sync PromptGuard which raises PromptInjectionError.
    """

    def __init__(self) -> None:
        from src.core.ai.prompt_guard import PromptGuard as _SyncPromptGuard

        self._guard = _SyncPromptGuard()

    def scan(self, text: str) -> dict[str, object]:
        from src.core.exceptions import PromptInjectionError

        try:
            self._guard.sanitize(text, tenant_id=require_tenant_id())
            return {"injection_detected": False, "patterns": []}
        except PromptInjectionError:
            return {"injection_detected": True, "patterns": ["injection_pattern"]}


class _ShadowCEOAdapter:
    """Bridge RiskOfficer.assess to ShadowCEO.review_task."""

    def __init__(self, shadow: ShadowCEO) -> None:
        self._shadow = shadow

    async def assess(self, proposal: Proposal) -> str:
        task = TaskData(
            title=proposal.action_type,
            description=proposal.reasoning,
            metadata=proposal.action_params,
            tags=[proposal.action_type],
        )
        veto = await self._shadow.review_task(task, proposed_agent="council")
        if veto is None:
            return "LOW"
        level = veto.risk_level.name
        if level == "CRITICAL":
            return "CRITICAL"
        if level == "HIGH":
            return "HIGH"
        if level == "MEDIUM":
            return "MEDIUM"
        return "LOW"


class _RiskRegisterAdapter:
    """Query CouncilDecisionRow for actor track records."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def actor_track_record(
        self, user_id: int, action_type: str
    ) -> list[dict[str, str | None]]:
        from sqlalchemy import select

        try:
            tenant_id = get_tenant_id()
            if tenant_id is None:
                return []
            filters = [
                CouncilDecisionRow.user_id == user_id,
                CouncilDecisionRow.action_type == action_type,
                CouncilDecisionRow.tenant_id == tenant_id,
            ]
            result = await self._db.execute(select(CouncilDecisionRow).where(*filters))
            rows = result.scalars().all()
            return [
                {
                    "verdict": r.verdict,
                    "timestamp": (r.timestamp.isoformat() if r.timestamp else None),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("RiskRegisterAdapter query failed: %s", exc)
            return []


class _RateLimiterAdapter:
    """Bridge IRateLimiter.check to InMemoryRateLimiter.is_allowed."""

    def __init__(self, limiter: InMemoryRateLimiter) -> None:
        self._limiter = limiter

    async def check(self, tenant_id: int, user_id: int, action_type: str) -> bool:
        key = f"council:{tenant_id}:{user_id}:{action_type}"
        return self._limiter.is_allowed(key, max_requests=100, window_seconds=60)


class _PranaServiceAdapter:
    """IPranaService for the Council, backed by the real DB-backed PranaService (ADR-021).

    The department is resolved server-side to the fixed copilot bucket
    (DEFAULT_COPILOT_DEPARTMENT) -- NEVER from the LLM-generated action_params, so a
    proposal cannot budget-shop across departments. Flag-guarded: with
    PRANA_ENFORCEMENT_ENABLED OFF (default) this returns True, so copilot behaviour is
    unchanged until budgets are provisioned and the flag is flipped in production.
    Advisory only + fail-closed (PranaService.has_budget already denies on any error).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def has_budget(self, tenant_id: int, action_type: str) -> bool:
        # Dynamisch via importlib (i.p.v. drie losse `from ... import`) om agent_runtime's
        # governance-koppeling niet verder op te rekken -- zie test_dsm006_ar_governance_fan_out.py
        # (plafond, GEEN buffer) en `_get_prana_guard()` in specialist_base.py voor hetzelfde
        # patroon om dezelfde reden.
        import importlib

        prana_config = importlib.import_module("src.core.governance.prana_config")
        if not prana_config.prana_enforcement_enabled():
            return True
        prana_departments = importlib.import_module("src.core.governance.prana_departments")
        prana_service_mod = importlib.import_module("src.core.governance.prana_service")
        result = await prana_service_mod.PranaService(self._db).has_budget(
            tenant_id, prana_departments.DEFAULT_COPILOT_DEPARTMENT.value, action_type
        )
        return bool(result)


def _db_session_factory(db: AsyncSession) -> contextlib.AbstractAsyncContextManager[AsyncSession]:
    """Wrap an existing AsyncSession for CouncilAuditWriter.

    CouncilAuditWriter expects a callable that returns an async context
    manager.  We bind it to the *same* session that the endpoint uses
    so that the audit write participates in the caller's transaction.
    """

    class _SessionCtx:
        async def __aenter__(self) -> AsyncSession:
            return db

        async def __aexit__(self, *args: object) -> None:
            pass

    return _SessionCtx()


#: Een tenant die niet bestaat, zodat de opwarming van geen enkele echte klant iets leest.
WARMUP_TENANT_ID = 2_147_483_647


async def warm_up_risk_register(
    session_factory: Callable[[], contextlib.AbstractAsyncContextManager[AsyncSession]],
    timeout_seconds: float = 5.0,
    verbindingen: int = 3,
) -> bool:
    """Voer bij het opstarten de registerquery van de RiskOfficer een keer uit.

    Gemeten (2026-10-23, vers proces): de eerste aanroep van de RiskOfficer kost 128 tot 360 ms, de tweede 5 tot 15 ms. De koude
    kosten zijn de eerste verbinding plus de eerste uitvoering van `actor_track_record` (statement bouwen); met die query
    voorverwarmd kwam hij op 8-13 ms. Zonder opwarming valt dat bij de eerste klant, binnen de tijdsgrens van 500 ms.

    Niet-fataal: een kapotte database mag het opstarten niet stoppen, dat doet `_init_database` al. Geeft False bij een
    fout of na `timeout_seconds` (een niet-reagerende pool mag de lifespan niet vasthouden; security-review Gate 2, 2026-10-23).
    `_RiskRegisterAdapter` vangt zelf query-fouten af; True betekent dus "uitgevoerd", niet "de tabel is er". De tenantcontext die er
    al was, wordt hersteld.
    """
    import asyncio

    from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

    vorige = get_tenant_id()

    async def _voer_uit() -> None:
        async with session_factory() as db:
            await _RiskRegisterAdapter(db).actor_track_record(-1, "council_warmup")

    try:
        set_tenant_id(WARMUP_TENANT_ID)
        try:
            # Meerdere sessies tegelijk: een voorstel gebruikt er meer dan een, en elke nieuwe verbinding naar `localhost` kost
            # op Windows 2,1 s (IPv6-poging eerst; gemeten 2026-10-23, tegen 50-66 ms naar 127.0.0.1). Een pool met een enkele
            # opgewarmde verbinding liet het eerste voorstel de rest betalen.
            uitkomsten = await asyncio.wait_for(
                asyncio.gather(*(_voer_uit() for _ in range(verbindingen)), return_exceptions=True),
                timeout=timeout_seconds,
            )
            for uitkomst in uitkomsten:
                # CancelledError is sinds Python 3.8 geen Exception meer en zou langs `except Exception` hieronder glippen,
                # tot in de lifespan; een geannuleerde opwarmsessie is een mislukte opwarming, geen reden om te stoppen.
                if isinstance(uitkomst, asyncio.CancelledError):
                    raise RuntimeError("een opwarmsessie is geannuleerd") from uitkomst
                if isinstance(uitkomst, BaseException):
                    raise uitkomst
        finally:
            set_tenant_id(vorige)
    except Exception as exc:
        logger.warning(
            "Council-opwarming mislukt: %s: %s", type(exc).__name__, exc, exc_info=True
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Module-level singletons for stateless officers (WE-009 fix, ADR-027)
# Safe in asyncio: these officers contain no mutable request-specific state.
# lru_cache is thread-safe in CPython (GIL). Sync cleanup paths in
# InMemoryRateLimiter have no await points -> atomic in asyncio event loop.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_ethics_officer() -> EthicsOfficer:
    """Return module-level singleton EthicsOfficer (stateless lexicon checks)."""
    return EthicsOfficer()


@lru_cache(maxsize=1)
def _get_sanity_officer() -> SanityOfficer:
    """Return module-level singleton SanityOfficer (stateless pattern matching)."""
    return SanityOfficer()


class _NullComplianceGuardian:
    """Null object satisfying the empty ComplianceGuardian Protocol.

    NOTE: ComplianceGuardian Protocol (compliance_officer.py:53) has zero required
    methods -- object() satisfies it at runtime but communicates wrong intent to
    auditors and future engineers who expect an active guardian.

    A real ComplianceGuardianAgent wiring requires 5 dependencies:
    signal_bus, alert_manager, policy_engine, audit_writer, redis.
    That integration is deferred to post-MVP (track in CG-001 follow-up).
    """

    pass


@lru_cache(maxsize=1)
def _get_compliance_officer() -> ComplianceOfficer:
    """Return module-level singleton ComplianceOfficer (stateless policy rules)."""
    return ComplianceOfficer(
        compliance_guardian=_NullComplianceGuardian(),
        ai_act_classifier=_AIActClassifierAdapter(),
    )


@lru_cache(maxsize=1)
def _get_rbac_service() -> RBACService:
    """Return module-level singleton RBACService (stateless scope checks).

    Shared by both the WE-009 SecurityOfficer singleton and per-agent officers
    built via build_council(agent_id=...). RBACService has no __init__ state,
    so sharing is safe -- and a single import site keeps the agent_runtime->auth
    DSM edge count stable (DSM-017).
    """
    from src.core.auth.rbac import RBACService

    return RBACService()


@lru_cache(maxsize=1)
def _get_security_officer() -> SecurityOfficer:
    """Return module-level singleton SecurityOfficer (stateless guards)."""
    return SecurityOfficer(
        tool_broker=_ToolBrokerAdapter(),
        prompt_guard=_PromptGuardAdapter(),
        rbac_checker=_get_rbac_service(),
    )


# Persistent rate limiter -- shared across requests within one worker process.
# InMemoryRateLimiter._cleanup_old_entries() is sync (no await) -> atomic in
# asyncio; safe to share. State does NOT cross Gunicorn workers (by design).
_PERSISTENT_RATE_LIMITER: _RateLimiterAdapter = _RateLimiterAdapter(InMemoryRateLimiter())


async def build_council(db: AsyncSession, agent_id: str = "copilot") -> AgentCouncil:
    """Build a fully wired AgentCouncil for production use.

    Args:
        db: Active AsyncSession (from FastAPI Depends(get_db)).
        agent_id: Permission profile for the SecurityOfficer tool allowlist
            check (ADR-015). The default "copilot" preserves HTTP behaviour
            and reuses the WE-009 singleton; any other value builds a fresh
            SecurityOfficer so background agents are evaluated against their
            own profile (AUDIT-007, ADR-036 D2).

    Returns:
        Configured AgentCouncil instance.
    """
    # Audit writer needs a session factory.
    writer = CouncilAuditWriter(db_session_factory=lambda: _db_session_factory(db))
    audit = AuditOfficer(writer)

    # Stateless officers: reuse module-level singletons (WE-009 fix)
    compliance = _get_compliance_officer()
    if agent_id == "copilot":
        # HTTP path: unchanged WE-009 singleton behaviour.
        security = _get_security_officer()
    else:
        # Background agents (ADR-036 D2): fresh officer wired to the caller's
        # permission profile. PromptGuard is stateless and cheap to construct;
        # RBACService is shared via the module-level singleton (DSM-017: no
        # extra agent_runtime->auth edge).
        security = SecurityOfficer(
            tool_broker=_ToolBrokerAdapter(agent_id=agent_id),
            prompt_guard=_PromptGuardAdapter(),
            rbac_checker=_get_rbac_service(),
        )
    ethics = _get_ethics_officer()
    sanity = _get_sanity_officer()

    # PrivacyOfficer -- stateful: DB-session-backed consent gate (per-request)
    redis = await _get_redis_safe()
    consent_manager = TwinConsentManager(db=db, cache=redis)
    consent_gate = _ConsentGateAdapter(consent_manager=consent_manager)
    twin_service = await _create_twin_service(db, redis)

    # AUDIT-002: real enforcer, not the _NullGDPREnforcer stub -- see
    # src/core/governance/gdpr_enforcer.py for BSN/IBAN checksum-validated detection.
    # importlib avoids direct ImportFrom (DSM boundary agent_runtime -> governance)
    _gdpr_mod = importlib.import_module("src.core.governance.gdpr_enforcer")
    GDPREnforcer = _gdpr_mod.GDPREnforcer
    privacy = PrivacyOfficer(
        gdpr_enforcer=GDPREnforcer(),
        consent_gate=consent_gate,
        twin_service=twin_service,
    )

    # RiskOfficer -- stateful: tenant_id from request context (per-request)
    tenant_id = require_tenant_id()
    pool = get_redis_pool()
    signal_bus = SignalBus(pool)
    shadow_ceo = ShadowCEO(tenant_id=tenant_id, signal_bus=signal_bus)
    risk = RiskOfficer(
        shadow_ceo=_ShadowCEOAdapter(shadow_ceo),
        risk_register=_RiskRegisterAdapter(db),
    )

    # ResourceOfficer -- stateful: DB + Redis per-request; rate limiter persistent
    from src.core.copilot.notification.budget import (
        NotificationBudgetTracker,
    )
    from src.core.copilot.notification.preferences_repo import (
        UserNotificationPreferencesRepo,
    )
    from src.core.database.redis import get_redis_client

    redis_client = await get_redis_client()
    budget_tracker = NotificationBudgetTracker(redis_client)
    prefs_repo = UserNotificationPreferencesRepo(db)

    resource = ResourceOfficer(
        rate_limiter=_PERSISTENT_RATE_LIMITER,  # WE-009: persistent, not per-request
        prana_service=_PranaServiceAdapter(db),
        budget_tracker=budget_tracker,
        preferences_repo=prefs_repo,
    )

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


async def _get_redis_safe() -> redis.Redis | None:  # type: ignore[type-arg]
    """Return a Redis client or None if Redis is unavailable."""
    try:
        from src.core.database.redis import get_redis_client

        return await get_redis_client()
    except Exception:
        return None


async def _create_twin_service(
    db: AsyncSession,
    redis: redis.Redis | None,  # type: ignore[type-arg]
) -> PracticalTwinService:
    """Create a PracticalTwinService without requiring a valid tenant_id."""
    from src.core.learning.batching.batch_manager import (
        get_batch_manager,
    )

    batch_manager = await get_batch_manager()
    consent_manager = TwinConsentManager(db=db, cache=redis)
    rate_limiter = RedisRateLimiter(redis_client=redis)
    event_bus = get_twin_event_bus()
    observer = UserBehaviorObserver(
        batch_manager=batch_manager,
        consent_manager=consent_manager,
        rate_limiter=rate_limiter,
        event_bus=event_bus,
    )
    return PracticalTwinService(
        observer=observer,
        llm_provider=MockSuggestionProvider(response=""),
        consent_manager=consent_manager,
        event_bus=event_bus,
    )
