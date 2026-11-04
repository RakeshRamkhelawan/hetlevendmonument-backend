"""
Unit tests for OfficerVerdictCache.

Uses an in-memory async Redis double for speed and isolation.
Integration tests with real Redis live in
``tests/integration/copilot/test_cache_integration.py``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.copilot.council.cache import (
    CACHE_KEY_PREFIX,
    OfficerVerdictCache,
    _verdict_from_dict,
    _verdict_to_dict,
)
from src.core.copilot.council.types import (
    DataClassification,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)


class FakeRedis:
    """Minimal async Redis double supporting get/set/scan/delete."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._scan_calls: list[tuple[int, str, int]] = []

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._data[key] = value
        return True

    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[str]]:
        self._scan_calls.append((cursor, match, count))
        keys = [k for k in self._data if self._match(k, match)]
        # Simple pagination: return all keys in one go for test simplicity
        return 0, keys

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                deleted += 1
    def pipeline(self, transaction: bool = True) -> Any:
        # Minimal pipeline fake
        class FakePipeline:
            def __init__(self, parent: FakeRedis):
                self.parent = parent
                self._cmds: list = []
            def delete(self, *keys: str) -> 'FakePipeline':
                self._cmds.append(('delete', keys))
                return self
            async def execute(self) -> list[int]:
                results = []
                for cmd, args in self._cmds:
                    if cmd == 'delete':
                        results.append(await self.parent.delete(*args))
                return results
        return FakePipeline(self)

    def lock(self, name: str, timeout: int | None = None) -> Any:
        class FakeLock:
            async def __aenter__(self) -> 'FakeLock':
                return self
            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass
        return FakeLock()

    @staticmethod
    def _match(key: str, pattern: str) -> bool:
        import fnmatch

        return fnmatch.fnmatch(key, pattern)

    def keys(self, pattern: str) -> list[str]:
        """Not used by production code; exists to verify SCAN is preferred."""
        return [k for k in self._data if self._match(k, pattern)]


def _make_proposal(
    action_type: str = "navigate_to",
    tenant_id: int = 1,
    data_classification: DataClassification = DataClassification.PUBLIC,
    context_snapshot: dict[str, Any] | None = None,
    model_id: str = "deepseek-chat",
    model_version: str = "v3",
) -> Proposal:
    return Proposal(
        proposal_id="123e4567-e89b-12d3-a456-426614174000",
        tenant_id=tenant_id,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type=action_type,
        action_params={},
        reasoning="test",
        data_classification=data_classification,
        confidence=0.95,
        model_id=model_id,
        model_version=model_version,
        context_snapshot=context_snapshot or {},
    )


def _make_verdict(
    officer_name: str = "ComplianceOfficer",
    verdict: VerdictType = VerdictType.APPROVE,
    confidence: float = 0.95,
    reason_code: str = "OK",
    reason_text: str = "",
    evidence: dict[str, Any] | None = None,
) -> OfficerVerdict:
    return OfficerVerdict(
        officer_name=officer_name,
        officer_version="1.0.0",
        verdict=verdict,
        confidence=confidence,
        reason_code=reason_code,
        reason_text=reason_text,
        evidence=evidence or {},
        deliberation_ms=0,
    )


# -----------------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_miss_returns_none() -> None:
    cache = OfficerVerdictCache(FakeRedis())
    assert await cache.get("ComplianceOfficer", _make_proposal()) is None


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_hit_returns_verdict_with_used_cache_true() -> None:
    cache = OfficerVerdictCache(FakeRedis())
    proposal = _make_proposal()
    verdict = _make_verdict()
    await cache.set("ComplianceOfficer", proposal, verdict, ttl_s=60)
    cached = await cache.get("ComplianceOfficer", proposal)
    assert cached is not None
    assert cached.used_cache is True
    assert cached.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_hit_does_not_alter_other_fields() -> None:
    cache = OfficerVerdictCache(FakeRedis())
    proposal = _make_proposal()
    verdict = _make_verdict(
        reason_code="REASON", reason_text="text", evidence={"risk_category": "low"}
    )
    await cache.set("ComplianceOfficer", proposal, verdict, ttl_s=60)
    cached = await cache.get("ComplianceOfficer", proposal)
    assert cached is not None
    assert cached.reason_code == "REASON"
    assert cached.reason_text == "text"
    assert cached.evidence == {"risk_category": "low"}
    assert cached.confidence == 0.95


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_fingerprint_stable_for_same_inputs() -> None:
    p1 = _make_proposal()
    p2 = _make_proposal()
    assert OfficerVerdictCache.fingerprint(p1) == OfficerVerdictCache.fingerprint(p2)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_fingerprint_changes_with_action_type() -> None:
    p1 = _make_proposal(action_type="a")
    p2 = _make_proposal(action_type="b")
    assert OfficerVerdictCache.fingerprint(p1) != OfficerVerdictCache.fingerprint(p2)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_fingerprint_changes_with_user_role() -> None:
    p1 = _make_proposal(context_snapshot={"user_role": "admin"})
    p2 = _make_proposal(context_snapshot={"user_role": "user"})
    assert OfficerVerdictCache.fingerprint(p1) != OfficerVerdictCache.fingerprint(p2)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_fingerprint_changes_with_language() -> None:
    p1 = _make_proposal(context_snapshot={"language": "nl"})
    p2 = _make_proposal(context_snapshot={"language": "en"})
    assert OfficerVerdictCache.fingerprint(p1) != OfficerVerdictCache.fingerprint(p2)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_set_with_ttl_zero_skips_write() -> None:
    fake = FakeRedis()
    cache = OfficerVerdictCache(fake)
    await cache.set("ComplianceOfficer", _make_proposal(), _make_verdict(), ttl_s=0)
    assert len(fake._data) == 0


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_set_only_caches_confidence_above_threshold() -> None:
    """_cached_deliberate uses >=0.5 threshold; here we verify set() itself stores any value."""
    cache = OfficerVerdictCache(FakeRedis())
    low_confidence = _make_verdict(confidence=0.3)
    await cache.set("ComplianceOfficer", _make_proposal(), low_confidence, ttl_s=60)
    cached = await cache.get("ComplianceOfficer", _make_proposal())
    assert cached is not None
    assert cached.confidence == 0.3


# -----------------------------------------------------------------------------
# Unhappy path
# -----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_get_returns_none_on_corrupt_payload() -> None:
    fake = FakeRedis()
    cache = OfficerVerdictCache(fake)
    proposal = _make_proposal()
    key = cache._key("ComplianceOfficer", proposal.tenant_id, cache.fingerprint(proposal))
    fake._data[key] = "not-json"
    assert await cache.get("ComplianceOfficer", proposal) is None


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_get_deletes_corrupt_payload_after_failure() -> None:
    fake = FakeRedis()
    cache = OfficerVerdictCache(fake)
    proposal = _make_proposal()
    key = cache._key("ComplianceOfficer", proposal.tenant_id, cache.fingerprint(proposal))
    fake._data[key] = "not-json"
    await cache.get("ComplianceOfficer", proposal)
    assert key not in fake._data


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_set_skips_when_verdict_not_serializable() -> None:
    fake = FakeRedis()
    cache = OfficerVerdictCache(fake)
    bad_verdict = _make_verdict()
    # monkey-patch evidence to contain non-JSON-serializable object
    object.__setattr__(bad_verdict, "evidence", {"obj": object()})
    await cache.set("ComplianceOfficer", _make_proposal(), bad_verdict, ttl_s=60)
    assert len(fake._data) == 0


# -----------------------------------------------------------------------------
# Security / tenant isolation
# -----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_tenant_isolation_keys_separate() -> None:
    cache = OfficerVerdictCache(FakeRedis())
    p1 = _make_proposal(tenant_id=1)
    p2 = _make_proposal(tenant_id=2)
    await cache.set("ComplianceOfficer", p1, _make_verdict(), ttl_s=60)
    await cache.set("ComplianceOfficer", p2, _make_verdict(), ttl_s=60)
    assert await cache.get("ComplianceOfficer", p1) is not None
    assert await cache.get("ComplianceOfficer", p2) is not None


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_invalidate_tenant_removes_all_entries_for_that_tenant_only() -> None:
    cache = OfficerVerdictCache(FakeRedis())
    p1 = _make_proposal(tenant_id=1, action_type="a")
    p2 = _make_proposal(tenant_id=1, action_type="b")
    p3 = _make_proposal(tenant_id=2, action_type="a")
    await cache.set("ComplianceOfficer", p1, _make_verdict(), ttl_s=60)
    await cache.set("ComplianceOfficer", p2, _make_verdict(), ttl_s=60)
    await cache.set("ComplianceOfficer", p3, _make_verdict(), ttl_s=60)
    deleted = await cache.invalidate_tenant(1)
    assert deleted == 2
    assert await cache.get("ComplianceOfficer", p1) is None
    assert await cache.get("ComplianceOfficer", p2) is None
    assert await cache.get("ComplianceOfficer", p3) is not None


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_invalidate_tenant_uses_scan_not_keys() -> None:
    fake = FakeRedis()
    cache = OfficerVerdictCache(fake)
    p1 = _make_proposal(tenant_id=1, action_type="a")
    await cache.set("ComplianceOfficer", p1, _make_verdict(), ttl_s=60)
    await cache.invalidate_tenant(1)
    assert len(fake._scan_calls) > 0
    for call in fake._scan_calls:
        assert call[1].startswith(f"{CACHE_KEY_PREFIX}:1:")


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_fingerprint_enum_vs_str_data_classification_equivalent() -> None:
    p1 = _make_proposal(data_classification=DataClassification.PUBLIC)
    p2 = _make_proposal(data_classification="public")  # type: ignore[arg-type]
    assert OfficerVerdictCache.fingerprint(p1) == OfficerVerdictCache.fingerprint(p2)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_fingerprint_rejects_data_classification_without_value() -> None:
    p = _make_proposal(data_classification=12345)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        OfficerVerdictCache.fingerprint(p)


# -----------------------------------------------------------------------------
# Redis-down fail-open
# -----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_get_returns_none_when_redis_raises_connection_error() -> None:
    broken = AsyncMock()
    broken.get = AsyncMock(side_effect=ConnectionError("Redis down"))
    cache = OfficerVerdictCache(broken)
    assert await cache.get("ComplianceOfficer", _make_proposal()) is None


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_set_swallows_redis_errors_no_exception_to_caller() -> None:
    broken = AsyncMock()
    broken.set = AsyncMock(side_effect=ConnectionError("Redis down"))
    cache = OfficerVerdictCache(broken)
    await cache.set("ComplianceOfficer", _make_proposal(), _make_verdict(), ttl_s=60)
    # No exception raised


# -----------------------------------------------------------------------------
# Key validation
# -----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_key_rejects_invalid_officer_name() -> None:
    cache = OfficerVerdictCache(FakeRedis())
    with pytest.raises(ValueError, match="Invalid officer_name"):
        cache._key("bad:name", 1, "abc123")


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_key_allows_valid_officer_name() -> None:
    cache = OfficerVerdictCache(FakeRedis())
    key = cache._key("ComplianceOfficer", 1, "abc123")
    assert key == f"{CACHE_KEY_PREFIX}:1:ComplianceOfficer:abc123"


# -----------------------------------------------------------------------------
# Serialisation round-trip
# -----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_verdict_to_dict_round_trip() -> None:
    v = _make_verdict(evidence={"risk_category": "low"})
    assert v.evidence == {"risk_category": "low"}
    d = _verdict_to_dict(v)
    restored = _verdict_from_dict(d)
    assert restored.officer_name == v.officer_name
    assert restored.verdict == v.verdict
    assert restored.confidence == v.confidence
    assert restored.reason_code == v.reason_code
    assert restored.reason_text == v.reason_text
    assert restored.evidence == v.evidence
    assert restored.used_cache == v.used_cache
    assert restored.deliberation_ms == v.deliberation_ms
