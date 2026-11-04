"""
Unit tests voor UserBehaviorObserver.

Controleert:
- Succesvolle track() geeft trace_id terug
- Feature flag uitgeschakeld → None
- Consent uitgeschakeld → None
- Rate limit overschreden → None
- Privacy filter failure → None (fail-secure)
- Batch.add() wordt aangeroepen met geanonimiseerde data
- Event bus wordt gepubliceerd
- Observer gooit nooit een exception
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.batching.batch_manager import ObservationBatchManager, PendingObservation
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.events.event_bus import TwinEventBus
from src.core.learning.observers.user_behavior_observer import UserBehaviorObserver
from src.core.learning.rate_limiting.redis_rate_limiter import RedisRateLimiter


def _make_observer(
    feature_flag_enabled: bool = True,
    consent_enabled: bool = True,
    rate_allowed: bool = True,
) -> tuple:
    """Helper: maak een observer met alle mocks geconfigureerd."""
    batch = AsyncMock(spec=ObservationBatchManager)
    batch.add = AsyncMock(return_value=True)

    consent = AsyncMock(spec=TwinConsentManager)
    consent.is_tracking_enabled = AsyncMock(return_value=consent_enabled)

    rate = AsyncMock(spec=RedisRateLimiter)
    rate.is_allowed = AsyncMock(return_value=rate_allowed)

    bus = AsyncMock(spec=TwinEventBus)
    bus.publish_async = AsyncMock()

    observer = UserBehaviorObserver(
        batch_manager=batch,
        consent_manager=consent,
        rate_limiter=rate,
        event_bus=bus,
    )
    return observer, batch, consent, rate, bus


@pytest.mark.asyncio
class TestUserBehaviorObserverHappyPath:
    """Tests voor succesvolle tracking."""

    async def test_track_returns_trace_id(self):
        observer, batch, consent, rate, bus = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            result = await observer.track(
                user_id="user@example.com",
                tenant_id=1,
                session_id="sess_abc",
                behavior_type="file_edit",
                context={"edit_count": 3},
            )

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_track_calls_batch_add(self):
        observer, batch, consent, rate, bus = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            await observer.track(
                user_id="user@example.com",
                tenant_id=1,
                session_id="sess_abc",
                behavior_type="file_edit",
            )

        batch.add.assert_called_once()

    async def test_track_anonymizes_user_id(self):
        """De geopgeslagen user_id is gehashed, niet de originele."""
        observer, batch, consent, rate, bus = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            await observer.track(
                user_id="real_user@example.com",
                tenant_id=1,
                session_id="sess_abc",
                behavior_type="file_edit",
            )

        call_args = batch.add.call_args[0][0]
        assert isinstance(call_args, PendingObservation)
        assert "real_user@example.com" not in call_args.human_user_id
        assert len(call_args.human_user_id) == 16  # hash is 16 chars

    async def test_track_publishes_event(self):
        observer, batch, consent, rate, bus = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            await observer.track(
                user_id="user@example.com",
                tenant_id=1,
                session_id="sess_abc",
                behavior_type="rapid_switch",
            )

        bus.publish_async.assert_called_once()

    async def test_track_without_event_bus_does_not_crash(self):
        batch = AsyncMock(spec=ObservationBatchManager)
        batch.add = AsyncMock(return_value=True)
        consent = AsyncMock(spec=TwinConsentManager)
        consent.is_tracking_enabled = AsyncMock(return_value=True)
        rate = AsyncMock(spec=RedisRateLimiter)
        rate.is_allowed = AsyncMock(return_value=True)

        observer = UserBehaviorObserver(
            batch_manager=batch,
            consent_manager=consent,
            rate_limiter=rate,
            event_bus=None,  # geen event bus
        )

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            result = await observer.track("user", 1, "sess", "edit")

        assert result is not None


@pytest.mark.asyncio
class TestUserBehaviorObserverGating:
    """Tests voor de pipeline gates (feature flag, consent, rate limit)."""

    async def test_feature_flag_disabled_returns_none(self):
        observer, batch, consent, rate, bus = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=False,
        ):
            result = await observer.track("user", 1, "sess", "edit")

        assert result is None
        batch.add.assert_not_called()

    async def test_consent_disabled_returns_none(self):
        observer, batch, consent, rate, bus = _make_observer(consent_enabled=False)

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            result = await observer.track("user", 1, "sess", "edit")

        assert result is None
        batch.add.assert_not_called()

    async def test_rate_limit_exceeded_returns_none(self):
        observer, batch, consent, rate, bus = _make_observer(rate_allowed=False)

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            result = await observer.track("user", 1, "sess", "file_edit")

        assert result is None
        batch.add.assert_not_called()


@pytest.mark.asyncio
class TestUserBehaviorObserverFailSafe:
    """Tests voor fail-safe gedrag."""

    async def test_privacy_filter_failure_rejects_observation(self):
        """Als privacy filter faalt → reject (fail-secure)."""
        observer, batch, consent, rate, bus = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            with patch(
                "src.core.learning.observers.user_behavior_observer.PrivacyFilter.filter_context",
                side_effect=RuntimeError("filter error"),
            ):
                result = await observer.track("user", 1, "sess", "edit")

        assert result is None
        batch.add.assert_not_called()

    async def test_batch_add_failure_does_not_raise(self):
        """Batch.add fout → gelogged maar geen crash."""
        observer, batch, consent, rate, bus = _make_observer()
        batch.add = AsyncMock(side_effect=RuntimeError("batch error"))

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            result = await observer.track("user", 1, "sess", "edit")

        # Moet None teruggeven (niet crashen)
        assert result is None

    async def test_consent_check_failure_does_not_raise(self):
        """Consent check error → gelogged maar geen crash."""
        observer, batch, consent, rate, bus = _make_observer()
        consent.is_tracking_enabled = AsyncMock(side_effect=RuntimeError("DB error"))

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            result = await observer.track("user", 1, "sess", "edit")

        assert result is None

    async def test_observer_never_raises(self):
        """De observer mag NOOIT een exception gooien."""
        observer, batch, consent, rate, bus = _make_observer()

        # Inject chaos - alles gaat stuk
        batch.add = AsyncMock(side_effect=Exception("chaos"))
        consent.is_tracking_enabled = AsyncMock(side_effect=Exception("chaos"))
        rate.is_allowed = AsyncMock(side_effect=Exception("chaos"))

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            try:
                result = await observer.track("user", 1, "sess", "edit")
                # Must return None, not raise
                assert result is None
            except Exception:
                pytest.fail("UserBehaviorObserver.track() moet nooit een exception gooien")

    async def test_event_bus_failure_does_not_stop_tracking(self):
        """Event bus fout stopt het batchen niet."""
        observer, batch, consent, rate, bus = _make_observer()
        bus.publish_async = AsyncMock(side_effect=RuntimeError("bus error"))

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            result = await observer.track("user", 1, "sess", "edit")

        # Batch moet nog steeds aangeroepen zijn (event bus fout ≠ reject)
        # Maar omdat de bus error buiten de try-block ligt, zal het falen
        # Eigenlijk zou publish_async een fire-and-forget task zijn...
        # De observer publiceert via publish_async (fire-and-forget), dus de
        # fout kan niet hier gecaught worden. batch.add is al aangeroepen.
        batch.add.assert_called_once()


@pytest.mark.asyncio
class TestUserBehaviorObserverContextFiltering:
    """Tests voor context privacy filtering."""

    async def test_code_with_secrets_is_filtered(self):
        observer, batch, consent, rate, bus = _make_observer()

        with patch(
            "src.core.learning.observers.user_behavior_observer.is_feature_enabled",
            return_value=True,
        ):
            await observer.track(
                user_id="user",
                tenant_id=1,
                session_id="sess",
                behavior_type="code_edit",
                context={
                    "code_snippet": "password = 'my_secret_db_pass'",
                    "edit_count": 5,
                },
            )

        call_args = batch.add.call_args[0][0]
        assert "my_secret_db_pass" not in str(call_args.context)
