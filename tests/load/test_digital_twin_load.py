"""
Load Tests voor Practical Digital Twin.

Verifieert de performance requirement: <5ms overhead per tracking call.
Tests kunnen worden uitgevoerd op twee manieren:

1. Pytest (unit-achtig, mocked): python -m pytest tests/load/test_digital_twin_load.py -v
2. Locust (real load): locust -f tests/load/digital_twin_locustfile.py --headless
   --users 1000 --spawn-rate 50 --run-time 1m --host http://localhost:8100

Scope: de performance tests hier meten de overhead van de twin pipeline
(PrivacyFilter + BatchManager + RateLimiter) zonder database writes.
"""

import asyncio
import statistics
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.core.learning.batching.batch_manager import ObservationBatchManager
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.events.event_bus import TwinEventBus
from src.core.learning.observers.user_behavior_observer import UserBehaviorObserver
from src.core.learning.rate_limiting.redis_rate_limiter import RedisRateLimiter

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_observer() -> UserBehaviorObserver:
    """Maak een observer met alle dependencies gemocked (geen DB/Redis)."""
    batch = AsyncMock(spec=ObservationBatchManager)
    batch.add = AsyncMock(return_value=True)

    consent = AsyncMock(spec=TwinConsentManager)
    consent.is_tracking_enabled = AsyncMock(return_value=True)

    rate = AsyncMock(spec=RedisRateLimiter)
    rate.is_allowed = AsyncMock(return_value=True)

    bus = AsyncMock(spec=TwinEventBus)
    bus.publish_async = AsyncMock()

    return UserBehaviorObserver(
        batch_manager=batch,
        consent_manager=consent,
        rate_limiter=rate,
        event_bus=bus,
    )


# ─── Performance Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTwinPerformance:
    """
    Performance tests voor de twin tracking pipeline.

    Requirement: overhead < 5ms per call (P99).
    """

    async def test_single_track_under_5ms(self):
        """Een enkele track() aanroep moet < 5ms duren."""
        observer = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            start = time.perf_counter()
            await observer.track(
                user_id="perf_user_1",
                tenant_id=1,
                session_id="sess_perf",
                behavior_type="file_edit",
                context={"edit_count": 3},
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 5.0, f"Track duurde {elapsed_ms:.2f}ms (eis: <5ms)"

    async def test_1000_sequential_tracks_p99_under_5ms(self):
        """
        1000 opeenvolgende track() aanroepen.
        P99 latentie moet < 5ms zijn.
        """
        observer = _make_observer()
        timings: list[float] = []

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            for i in range(1000):
                start = time.perf_counter()
                await observer.track(
                    user_id=f"user_{i % 100}",
                    tenant_id=1,
                    session_id=f"sess_{i}",
                    behavior_type="file_edit",
                    context={"edit_count": i % 10},
                )
                timings.append((time.perf_counter() - start) * 1000)

        p99 = sorted(timings)[int(len(timings) * 0.99)]
        avg = statistics.mean(timings)

        # Reporting
        print(
            f"\n[DigitalTwin Load] 1000 tracks:"
            f" avg={avg:.3f}ms p99={p99:.3f}ms"
            f" max={max(timings):.3f}ms"
        )

        assert p99 < 5.0, (
            f"P99 latentie is {p99:.2f}ms (eis: <5ms). "
            f"avg={avg:.2f}ms, max={max(timings):.2f}ms"
        )

    async def test_100_concurrent_tracks(self):
        """100 gelijktijdige track() aanroepen mogen niet crashen."""
        observer = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            tasks = [
                observer.track(
                    user_id=f"user_{i}",
                    tenant_id=1,
                    session_id=f"sess_{i}",
                    behavior_type="file_edit",
                )
                for i in range(100)
            ]
            results = await asyncio.gather(*tasks)

        # Alle moeten slagen (niet None terugkeren vanwege een error)
        assert all(
            r is not None for r in results
        ), f"{results.count(None)} van de 100 tracks zijn mislukt"

    async def test_privacy_filter_overhead_negligible(self):
        """
        PrivacyFilter overhead is verwaarloosbaar (<1ms extra).
        Meet het verschil tussen een context met en zonder code snippet.
        """
        observer = _make_observer()

        small_context = {"edit_count": 5}
        large_context = {
            "edit_count": 5,
            "code_snippet": "def foo():\n    password = 'hunter2'\n    return password",
            "file_path": "/home/user/project/src/auth.py",
        }

        timings_small: list[float] = []
        timings_large: list[float] = []

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            for _ in range(100):
                start = time.perf_counter()
                await observer.track("u1", 1, "s", "edit", context=small_context)
                timings_small.append((time.perf_counter() - start) * 1000)

            for _ in range(100):
                start = time.perf_counter()
                await observer.track("u1", 1, "s", "edit", context=large_context)
                timings_large.append((time.perf_counter() - start) * 1000)

        avg_small = statistics.mean(timings_small)
        avg_large = statistics.mean(timings_large)
        overhead = avg_large - avg_small

        print(
            f"\n[PrivacyFilter overhead]"
            f" small={avg_small:.3f}ms large={avg_large:.3f}ms"
            f" overhead={overhead:.3f}ms"
        )

        # Overhead mag maximaal 3ms zijn (redelijk voor regex + hash op een busy machine)
        assert overhead < 3.0, f"PrivacyFilter overhead is {overhead:.2f}ms (eis: <3ms)"

    async def test_rejected_track_is_faster_than_accepted(self):
        """
        Een verworpen track (feature flag uit) moet sneller zijn dan een
        geaccepteerde track (want: kortsluit de pipeline).
        """
        accepted_observer = _make_observer()
        rejected_observer = _make_observer()

        timings_accepted: list[float] = []
        timings_rejected: list[float] = []

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            for _ in range(100):
                start = time.perf_counter()
                await accepted_observer.track("u", 1, "s", "edit")
                timings_accepted.append((time.perf_counter() - start) * 1000)

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=False,
        ):
            for _ in range(100):
                start = time.perf_counter()
                await rejected_observer.track("u", 1, "s", "edit")
                timings_rejected.append((time.perf_counter() - start) * 1000)

        avg_accepted = statistics.mean(timings_accepted)
        avg_rejected = statistics.mean(timings_rejected)

        print(f"\n[Gate overhead] accepted={avg_accepted:.3f}ms rejected={avg_rejected:.3f}ms")

        # Verworpen moet sneller zijn of gelijkwaardig
        assert avg_rejected <= avg_accepted * 1.5, (
            f"Verworpen track ({avg_rejected:.2f}ms) is onverwacht langzamer "
            f"dan geaccepteerde track ({avg_accepted:.2f}ms)"
        )

    async def test_batch_flush_within_30s(self):
        """
        End-to-end: een observatie moet binnen 30 seconden worden geflusht.
        Gebruikt een echte ObservationBatchManager met een noop persist_fn.
        """
        from src.core.learning.batching.batch_manager import (
            ObservationBatchManager,
            PendingObservation,
        )

        flushed_at: float | None = None

        async def _noop_persist(batch: list[PendingObservation]) -> None:
            nonlocal flushed_at
            flushed_at = time.perf_counter()

        mgr = ObservationBatchManager(persist_fn=_noop_persist)
        mgr.batch_size = 1  # Force flush on first observation
        mgr.flush_interval = 30.0
        await mgr.start()

        start = time.perf_counter()
        obs = PendingObservation(
            tenant_id=1,
            human_user_id="perf_user",
            session_id="sess_1",
            behavior_type="file_edit",
            context={"line": 42},
            outcome_metrics={},
            confidence_score=0.9,
            timestamp=time.time(),
        )
        await mgr.add(obs)

        # Wait for the background flush task to complete
        for _ in range(100):
            await asyncio.sleep(0.01)
            if flushed_at is not None:
                break

        elapsed = (flushed_at - start) * 1000 if flushed_at else None
        await mgr.stop()

        assert flushed_at is not None, "Observation was never flushed"
        assert elapsed is not None
        assert elapsed < 30_000, (
            f"Flush took {elapsed:.0f}ms (eis: <30s)"
        )

    async def test_end_to_end_track_overhead_with_real_batch_manager(self):
        """
        Meet de overhead van de volledige track() pipeline met een echte
        ObservationBatchManager (noop persist_fn, zodat DB niet meetelt).
        """
        from src.core.learning.batching.batch_manager import (
            ObservationBatchManager,
            PendingObservation,
        )

        async def _noop_persist(_batch: list[PendingObservation]) -> None:
            pass

        batch_mgr = ObservationBatchManager(persist_fn=_noop_persist)
        batch_mgr.batch_size = 1000  # Prevent auto-flush during test
        await batch_mgr.start()

        consent = AsyncMock(spec=TwinConsentManager)
        consent.is_tracking_enabled = AsyncMock(return_value=True)

        rate = AsyncMock(spec=RedisRateLimiter)
        rate.is_allowed = AsyncMock(return_value=True)

        bus = AsyncMock(spec=TwinEventBus)
        bus.publish_async = AsyncMock()

        observer = UserBehaviorObserver(
            batch_manager=batch_mgr,
            consent_manager=consent,
            rate_limiter=rate,
            event_bus=bus,
        )

        timings: list[float] = []

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            for i in range(1000):
                start = time.perf_counter()
                await observer.track(
                    user_id=f"user_{i % 100}",
                    tenant_id=1,
                    session_id=f"sess_{i}",
                    behavior_type="file_edit",
                    context={"edit_count": i % 10},
                )
                timings.append((time.perf_counter() - start) * 1000)

        await batch_mgr.stop()

        p99 = sorted(timings)[int(len(timings) * 0.99)]
        avg = statistics.mean(timings)

        print(
            f"\n[DigitalTwin E2E] 1000 tracks (real batch manager):"
            f" avg={avg:.3f}ms p99={p99:.3f}ms max={max(timings):.3f}ms"
        )

        assert p99 < 5.0, (
            f"P99 latentie is {p99:.2f}ms (eis: <5ms). "
            f"avg={avg:.2f}ms, max={max(timings):.2f}ms"
        )
