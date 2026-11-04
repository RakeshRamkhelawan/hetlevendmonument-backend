"""
Abstract base class for all Council Officers.

Every Officer must implement deliberate() and must respect the timeout_ms
class variable. On timeout, the Coordinator interprets the absent verdict
as VETO (fail-secure).

Officers may cache deterministic verdicts in Redis for 60s; non-deterministic
verdicts (e.g. consent-dependent, time-dependent) must set can_cache=False.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar
from collections.abc import Awaitable, Callable

from src.core.copilot.council.cache import OfficerVerdictCache
from src.core.copilot.council.types import (
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    VerdictType,
)


class Officer(ABC):
    """Abstract base class for all Council Officers.

    Subclasses MUST define:
        name              -- Officer identifier (e.g. "ComplianceOfficer")
        version           -- Semver version string (e.g. "1.0.0")
        allowed_verdicts  -- Frozen set of VerdictType the Officer may emit
        timeout_ms        -- Per-Officer SLA (default 500ms, max 1500ms)
        can_cache         -- ClassVar[bool]; whether verdicts may be cached
        cache_ttl_seconds -- ClassVar[int]; TTL when can_cache is True

    Subclasses MUST implement:
        deliberate()      -- Async method returning an OfficerVerdict

    Implementations are responsible for:
        - Logging with tenant_id and exc_info=True on errors (CLAUDE.md regel 11)
        - Never raising uncaught exceptions (catch + return VETO with reason_code)
        - Respecting deadline_ms in DeliberationContext (cooperative cancellation)
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = "0.0.0"
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset()
    timeout_ms: ClassVar[int] = 500
    can_veto: ClassVar[bool] = True  # Officers without veto power emit DEFER on failure
    can_cache: ClassVar[bool] = False
    cache_ttl_seconds: ClassVar[int] = 60

    def __init__(self, cache: Any = None) -> None:
        # Subclass constructors call super().__init__(cache=cache) so that
        # _cached_deliberate does not depend on implicit attribute init.
        self._cache = cache

    @abstractmethod
    async def deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        """Adjudicate the proposal. Must return within timeout_ms or be cancelled."""

    async def _cached_deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
        inner: Callable[[Proposal, DeliberationContext], Awaitable[OfficerVerdict]],
    ) -> OfficerVerdict:
        """Wrap deliberate call with cache lookup/store.

        Officers with can_cache=True build their deliberate() as:
            return await self._cached_deliberate(proposal, context, self._actual_deliberate)

        Redis-down policy: cache.get/set fails fail-open (returns None /
        no-op with warning) -- _cached_deliberate sees this as cache miss and
        calls inner(). Council fail-secure guarantees sit in the Officer logic,
        not in the cache layer.
        """
        if not self.__class__.can_cache or self._cache is None:
            return await inner(proposal, context)

        cached = await self._cache.get(self.name, proposal)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        fresh = await inner(proposal, context)

        # Only cache high-confidence verdicts (otherwise not stable enough)
        MIN_CACHEABLE_CONFIDENCE = 0.5
        if fresh.confidence >= MIN_CACHEABLE_CONFIDENCE:
            await self._cache.set(self.name, proposal, fresh, ttl_s=self.cache_ttl_seconds)

        return fresh

    def health_check(self) -> bool:
        """
        Light health check. Override if Officer depends on external services.

        Returns:
            True if Officer is healthy and can deliberate; False otherwise.
            The Coordinator treats False as VETO for all incoming proposals.
        """
        return True
