"""
Unit tests for DigestQueue, Digest, and DigestGenerator.

Covers: enqueue/drain roundtrip, atomic drain, tenant-scoped keys,
grouping, summary text, quiet hours, empty queue, and best_effort
wrapping in send_digest.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.notification.digest import (
    Digest,
    DigestGenerator,
    DigestQueue,
    QueuedSignal,
)
from src.core.copilot.notification.ws_pusher import WSPusher
from src.core.copilot.proactive.types import Signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    severity: Severity = Severity.LOW,
    tenant_id: int = 1,
    user_id: int = 10,
    title: str = "Test signal",
) -> Signal:
    return Signal(
        tenant_id=tenant_id,
        affected_user_id=user_id,
        monitor_name="test_monitor",
        title=title,
        body="Body text",
        severity=severity,
        data_classification=DataClassification.INTERNAL,
        suggested_actions=[],
        detection_reasoning="reason",
        confidence=0.7,
        context={},
    )


def _make_queued(
    severity: Severity = Severity.LOW,
    tenant_id: int = 1,
    user_id: int = 10,
    decision_id: str | None = None,
) -> QueuedSignal:
    return QueuedSignal(
        signal=_make_signal(severity=severity, tenant_id=tenant_id, user_id=user_id),
        decision_id=decision_id or str(uuid4()),
    )


class FakeRedis:
    """Minimal in-memory Redis fake for DigestQueue tests."""

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {}
        self._ttl: dict[str, int] = {}

    async def lpush(self, key: str, value: str) -> int:
        self._store.setdefault(key, []).insert(0, value)
        return len(self._store[key])

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self._store.get(key, [])
        if end == -1:
            return list(items)
        return list(items[start : end + 1])

    async def expire(self, key: str, ttl: int) -> None:
        self._ttl[key] = ttl

    async def delete(self, key: str) -> int:
        return len(self._store.pop(key, []))

    async def eval(self, script: str, numkeys: int, key: str) -> list[str]:
        """Simulate atomic LRANGE + DEL Lua script."""
        items = list(self._store.get(key, []))
        if items:
            self._store.pop(key, None)
        return items


# ---------------------------------------------------------------------------
# QueuedSignal serialisation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
def test_queued_signal_roundtrip_json() -> None:
    qs = _make_queued(severity=Severity.HIGH)
    restored = QueuedSignal.from_json(qs.to_json())

    assert restored.decision_id == qs.decision_id
    assert restored.signal.title == qs.signal.title
    assert restored.signal.severity == qs.signal.severity
    assert restored.signal.tenant_id == qs.signal.tenant_id


@pytest.mark.unit
@pytest.mark.als
def test_queued_signal_from_json_bytes() -> None:
    qs = _make_queued()
    raw_bytes = qs.to_json().encode()
    restored = QueuedSignal.from_json(raw_bytes)
    assert restored.decision_id == qs.decision_id


# ---------------------------------------------------------------------------
# DigestQueue: enqueue / drain roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_digest_queue_enqueue_drain_roundtrip() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)
    signal = _make_signal(tenant_id=1, user_id=10)
    decision_id = str(uuid4())

    await queue.enqueue(user_id=10, signal=signal, decision_id=decision_id)
    results = await queue.drain(user_id=10, tenant_id=1)

    assert len(results) == 1
    assert results[0].decision_id == decision_id
    assert results[0].signal.title == signal.title


@pytest.mark.unit
@pytest.mark.als
async def test_digest_queue_drain_clears_queue() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)
    signal = _make_signal(tenant_id=1, user_id=10)

    await queue.enqueue(user_id=10, signal=signal, decision_id="abc")
    await queue.drain(user_id=10, tenant_id=1)
    second_drain = await queue.drain(user_id=10, tenant_id=1)

    assert second_drain == []


@pytest.mark.unit
@pytest.mark.als
async def test_digest_queue_drain_empty_returns_empty_list() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)

    results = await queue.drain(user_id=99, tenant_id=1)
    assert results == []


@pytest.mark.unit
@pytest.mark.als
async def test_digest_queue_sets_ttl_on_enqueue() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)
    signal = _make_signal(tenant_id=1, user_id=10)

    await queue.enqueue(user_id=10, signal=signal, decision_id="x")
    key = DigestQueue.KEY_TEMPLATE.format(tenant_id=1, user_id=10)

    assert redis._ttl.get(key) == DigestQueue.TTL_SECONDS


@pytest.mark.unit
@pytest.mark.als
async def test_digest_queue_enqueues_multiple_signals() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)

    for i in range(3):
        signal = _make_signal(tenant_id=1, user_id=10, title="Signal %d" % i)
        await queue.enqueue(user_id=10, signal=signal, decision_id=str(i))

    results = await queue.drain(user_id=10, tenant_id=1)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# DigestQueue: tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.multi_tenant
@pytest.mark.als
async def test_digest_queue_key_is_tenant_scoped() -> None:
    """Two tenants sharing user_id=1 must not interfere with each other."""
    redis = FakeRedis()
    queue = DigestQueue(redis)

    signal_t1 = _make_signal(tenant_id=1, user_id=1, title="Tenant1 signal")
    signal_t2 = _make_signal(tenant_id=2, user_id=1, title="Tenant2 signal")

    await queue.enqueue(user_id=1, signal=signal_t1, decision_id="t1")
    await queue.enqueue(user_id=1, signal=signal_t2, decision_id="t2")

    t1_results = await queue.drain(user_id=1, tenant_id=1)
    t2_results = await queue.drain(user_id=1, tenant_id=2)

    assert len(t1_results) == 1
    assert t1_results[0].signal.title == "Tenant1 signal"
    assert len(t2_results) == 1
    assert t2_results[0].signal.title == "Tenant2 signal"


# ---------------------------------------------------------------------------
# Digest: grouping and summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
def test_digest_groups_signals_by_severity() -> None:
    signals = [
        _make_queued(severity=Severity.HIGH),
        _make_queued(severity=Severity.HIGH),
        _make_queued(severity=Severity.LOW),
    ]
    digest = Digest(
        user_id=10,
        generated_at=datetime.now(timezone.utc),
        signals=signals,
    )

    assert len(digest.signals_grouped_by_severity[Severity.HIGH.value]) == 2
    assert len(digest.signals_grouped_by_severity[Severity.LOW.value]) == 1


@pytest.mark.unit
@pytest.mark.als
def test_digest_summary_text_contains_signal_count() -> None:
    signals = [
        _make_queued(severity=Severity.HIGH),
        _make_queued(severity=Severity.HIGH),
        _make_queued(severity=Severity.LOW),
    ]
    digest = Digest(
        user_id=10,
        generated_at=datetime.now(timezone.utc),
        signals=signals,
    )

    assert "3" in digest.summary_text


@pytest.mark.unit
@pytest.mark.als
def test_digest_empty_signals_summary() -> None:
    digest = Digest(user_id=10, generated_at=datetime.now(timezone.utc), signals=[])
    assert digest.summary_text == "No notifications."
    assert digest.signals_grouped_by_severity == {}


# ---------------------------------------------------------------------------
# DigestGenerator
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_digest_generator_skips_users_with_no_signals() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)
    mock_ws = AsyncMock(spec=WSPusher)
    generator = DigestGenerator(digest_queue=queue, ws_pusher=mock_ws)

    result = await generator.generate_for_user(user_id=10, tenant_id=1)

    assert result is None
    mock_ws.push.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_digest_generator_builds_digest_with_queued_signals() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)
    mock_ws = AsyncMock(spec=WSPusher)
    generator = DigestGenerator(digest_queue=queue, ws_pusher=mock_ws)

    signal = _make_signal(tenant_id=1, user_id=10)
    await queue.enqueue(user_id=10, signal=signal, decision_id="dec1")

    digest = await generator.generate_for_user(user_id=10, tenant_id=1)

    assert digest is not None
    assert len(digest.signals) == 1
    assert digest.user_id == 10


@pytest.mark.unit
@pytest.mark.als
async def test_digest_generator_send_digest_pushes_via_ws() -> None:
    redis = FakeRedis()
    queue = DigestQueue(redis)
    mock_ws = AsyncMock(spec=WSPusher)
    generator = DigestGenerator(digest_queue=queue, ws_pusher=mock_ws)

    signal = _make_signal(tenant_id=1, user_id=10)
    await queue.enqueue(user_id=10, signal=signal, decision_id="dec1")
    digest = await generator.generate_for_user(user_id=10, tenant_id=1)
    assert digest is not None

    await generator.send_digest(digest)

    mock_ws.push.assert_awaited_once()
    call_kwargs = mock_ws.push.call_args
    payload = call_kwargs.kwargs["payload"]
    assert payload["type"] == "digest"
    assert len(payload["signals"]) == 1


@pytest.mark.unit
@pytest.mark.als
async def test_digest_send_failure_does_not_propagate() -> None:
    """best_effort wrapper in send_digest must absorb WS push failure."""
    redis = FakeRedis()
    queue = DigestQueue(redis)
    mock_ws = AsyncMock(spec=WSPusher)
    mock_ws.push.side_effect = ConnectionError("Redis down")
    generator = DigestGenerator(digest_queue=queue, ws_pusher=mock_ws)

    digest = Digest(
        user_id=10,
        generated_at=datetime.now(timezone.utc),
        signals=[_make_queued()],
    )

    # Should not raise
    await generator.send_digest(digest)


# ---------------------------------------------------------------------------
# Behavioral test: 3 signals batch into one digest
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_behavioral_three_deferred_signals_delivered_in_one_digest() -> None:
    """
    Behavioral: a user with delivery_mode='digest' receives 3 signals.
    All 3 are stored in the queue and delivered together in a single digest,
    not as 3 individual WS pushes.
    """
    redis = FakeRedis()
    queue = DigestQueue(redis)
    mock_ws = AsyncMock(spec=WSPusher)
    generator = DigestGenerator(digest_queue=queue, ws_pusher=mock_ws)

    # Simulate 3 signals being enqueued by the dispatcher
    for i in range(3):
        signal = _make_signal(tenant_id=1, user_id=10, title="Signal %d" % i)
        await queue.enqueue(user_id=10, signal=signal, decision_id=str(uuid4()))

    # At 09:00 local time the generator fires
    digest = await generator.generate_for_user(user_id=10, tenant_id=1)
    assert digest is not None
    assert len(digest.signals) == 3

    await generator.send_digest(digest)

    # Exactly one WS push containing all 3 signals
    mock_ws.push.assert_awaited_once()
    payload = mock_ws.push.call_args.kwargs["payload"]
    assert len(payload["signals"]) == 3

    # Queue is now empty -- second drain returns nothing
    second_drain = await queue.drain(user_id=10, tenant_id=1)
    assert second_drain == []
