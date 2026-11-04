"""
Unit tests voor TwinConsentManager.

Controleert:
- Default consent = ENABLED (opt-out model)
- set_consent_status wijzigt status
- is_tracking_enabled geeft correcte bool
- request_hard_delete zet vlag
- hard_delete verwijdert records
- export_user_data geeft correct JSON
- Cache invalidatie na wijziging
- Fail-safe: cache errors crashen niet
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.consent.consent_manager import (
    ConsentCategories,
    TwinConsentManager,
    TwinConsentStatus,
)
from src.core.learning.twin_models import UserTwinConsent


def _make_db_mock(
    consent_record: UserTwinConsent | None = None,
    raise_error: bool = False,
) -> MagicMock:
    """Maak een mock AsyncSession die consent records retourneert."""
    db = AsyncMock()
    result_mock = MagicMock()

    if consent_record is not None:
        result_mock.scalar_one_or_none.return_value = consent_record
        result_mock.scalars.return_value.all.return_value = []
    else:
        result_mock.scalar_one_or_none.return_value = None
        result_mock.scalars.return_value.all.return_value = []

    if raise_error:
        db.execute = AsyncMock(side_effect=RuntimeError("DB error"))
    else:
        db.execute = AsyncMock(return_value=result_mock)

    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _make_consent_record(
    consent_given: bool = True,
    hard_delete_requested: bool = False,
    behavior_tracking: bool = True,
    profile_aggregation: bool = True,
    ai_interventions: bool = True,
    cross_session_memory: bool = True,
) -> UserTwinConsent:
    record = UserTwinConsent(
        tenant_id=1,
        human_user_id="user_abc",
        consent_given=consent_given,
        hard_delete_requested=hard_delete_requested,
        behavior_tracking=behavior_tracking,
        profile_aggregation=profile_aggregation,
        ai_interventions=ai_interventions,
        cross_session_memory=cross_session_memory,
    )
    record.id = 1
    return record


@pytest.mark.asyncio
class TestConsentStatusRead:
    """Tests voor lezen van consent status."""

    async def test_default_consent_is_disabled(self):
        """Zonder record is consent DISABLED -- opt-in model (AVG).

        Deze test heette test_default_consent_is_enabled en eiste het omgekeerde: dat een
        ontbrekend record als ENABLED werd aangemaakt. Dat is een opt-OUT-default, en die
        is onder de AVG niet toegestaan voor twin-verwerking: consent moet een actieve
        handeling zijn, nooit een aanname. `consent_manager.get_consent_status` documenteert
        het opt-in model expliciet ("Default: DISABLED (opt-in model)"). De test liep achter
        op die correctie en hield daarmee het onveilige gedrag vast (gevonden OP-11,
        2026-07-31).
        """
        db = _make_db_mock(consent_record=None)
        mgr = TwinConsentManager(db=db)
        status = await mgr.get_consent_status("user_abc", 1)
        assert status == TwinConsentStatus.DISABLED

    async def test_enabled_record_returns_enabled(self):
        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)
        status = await mgr.get_consent_status("user_abc", 1)
        assert status == TwinConsentStatus.ENABLED

    async def test_disabled_record_returns_disabled(self):
        record = _make_consent_record(consent_given=False)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)
        status = await mgr.get_consent_status("user_abc", 1)
        assert status == TwinConsentStatus.DISABLED

    async def test_hard_delete_requested_returns_disabled(self):
        record = _make_consent_record(consent_given=True, hard_delete_requested=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)
        status = await mgr.get_consent_status("user_abc", 1)
        assert status == TwinConsentStatus.DISABLED

    async def test_is_tracking_enabled_true(self):
        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)
        assert await mgr.is_tracking_enabled("user_abc", 1) is True

    async def test_is_tracking_enabled_false(self):
        record = _make_consent_record(consent_given=False, behavior_tracking=False)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)
        assert await mgr.is_tracking_enabled("user_abc", 1) is False


@pytest.mark.asyncio
class TestConsentStatusWrite:
    """Tests voor wijzigen van consent status."""

    async def test_set_disabled_updates_record(self):
        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.set_consent_status("user_abc", 1, TwinConsentStatus.DISABLED)

        assert record.consent_given is False

    async def test_set_enabled_updates_record(self):
        record = _make_consent_record(consent_given=False)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.set_consent_status("user_abc", 1, TwinConsentStatus.ENABLED)

        assert record.consent_given is True

    async def test_set_status_calls_flush(self):
        record = _make_consent_record()
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.set_consent_status("user_abc", 1, TwinConsentStatus.DISABLED)

        db.flush.assert_called()


@pytest.mark.asyncio
class TestHardDelete:
    """Tests voor GDPR Artikel 17: Right to Erasure."""

    async def test_request_hard_delete_sets_flag(self):
        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.request_hard_delete("user_abc", 1)

        assert record.hard_delete_requested is True
        assert record.consent_given is False
        assert record.hard_delete_requested_at is not None

    async def test_hard_delete_executes_deletes(self):
        db = _make_db_mock()
        mgr = TwinConsentManager(db=db)

        result = await mgr.hard_delete("user_abc", 1)

        assert isinstance(result, dict)
        assert "observations" in result
        assert "profiles" in result
        assert "consent" in result
        # DB execute werd aangeroepen voor elke tabel
        assert db.execute.call_count >= 3

    async def test_hard_delete_calls_flush(self):
        db = _make_db_mock()
        mgr = TwinConsentManager(db=db)

        await mgr.hard_delete("user_abc", 1)

        db.flush.assert_called()


@pytest.mark.asyncio
class TestCacheIntegration:
    """Tests voor cache (Redis) integratie."""

    async def test_cache_miss_falls_through_to_db(self):
        """Cache miss → DB wordt geconsulteerd."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)  # cache miss
        cache.setex = AsyncMock()

        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db, cache=cache)

        status = await mgr.get_consent_status("user_abc", 1)

        assert status == TwinConsentStatus.ENABLED
        cache.get.assert_called_once()

    async def test_cache_hit_skips_db(self):
        """Cache hit → DB wordt NIET geconsulteerd."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=b"enabled")  # cache hit

        db = _make_db_mock()
        mgr = TwinConsentManager(db=db, cache=cache)

        status = await mgr.get_consent_status("user_abc", 1)

        assert status == TwinConsentStatus.ENABLED
        db.execute.assert_not_called()

    async def test_cache_error_falls_through_gracefully(self):
        """Cache error → geen crash, DB geconsulteerd."""
        cache = AsyncMock()
        cache.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db, cache=cache)

        # Should not raise
        status = await mgr.get_consent_status("user_abc", 1)
        assert status == TwinConsentStatus.ENABLED

    async def test_set_status_invalidates_cache(self):
        """Na set_status → cache key verwijderd."""
        cache = AsyncMock()
        cache.delete = AsyncMock()

        record = _make_consent_record()
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db, cache=cache)

        await mgr.set_consent_status("user_abc", 1, TwinConsentStatus.DISABLED)

        cache.delete.assert_called_once_with("twin:consent:1:user_abc")


class TestGranularConsentCategories:
    """Tests voor 4-category granular consent (ADR-026 2)."""

    async def test_get_consent_categories_returns_all_four(self):
        record = _make_consent_record(
            behavior_tracking=True,
            profile_aggregation=False,
            ai_interventions=True,
            cross_session_memory=False,
        )
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        cats = await mgr.get_consent_categories("user_abc", 1)

        assert cats.behavior_tracking is True
        assert cats.profile_aggregation is False
        assert cats.ai_interventions is True
        assert cats.cross_session_memory is False

    async def test_set_consent_categories_updates_all_four(self):
        record = _make_consent_record(
            behavior_tracking=True,
            profile_aggregation=True,
            ai_interventions=True,
            cross_session_memory=True,
        )
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.set_consent_categories(
            "user_abc",
            1,
            ConsentCategories(
                behavior_tracking=False,
                profile_aggregation=True,
                ai_interventions=False,
                cross_session_memory=True,
            ),
        )

        assert record.behavior_tracking is False
        assert record.profile_aggregation is True
        assert record.ai_interventions is False
        assert record.cross_session_memory is True

    async def test_is_tracking_enabled_checks_behavior_tracking(self):
        record = _make_consent_record(
            consent_given=True,
            behavior_tracking=False,
            profile_aggregation=True,
            ai_interventions=True,
            cross_session_memory=True,
        )
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        assert await mgr.is_tracking_enabled("user_abc", 1) is False

    async def test_legacy_enabled_maps_all_true(self):
        record = _make_consent_record(consent_given=False)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.set_consent_status("user_abc", 1, TwinConsentStatus.ENABLED)

        assert record.behavior_tracking is True
        assert record.profile_aggregation is True
        assert record.ai_interventions is True
        assert record.cross_session_memory is True
        assert record.consent_given is True
        assert record.status == "enabled"

    async def test_legacy_disabled_maps_all_false(self):
        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.set_consent_status("user_abc", 1, TwinConsentStatus.DISABLED)

        assert record.behavior_tracking is False
        assert record.profile_aggregation is False
        assert record.ai_interventions is False
        assert record.cross_session_memory is False
        assert record.consent_given is False
        assert record.status == "disabled"

    async def test_legacy_paused_maps_behavior_false(self):
        record = _make_consent_record(consent_given=True)
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db)

        await mgr.set_consent_status("user_abc", 1, TwinConsentStatus.PAUSED)

        assert record.behavior_tracking is False
        assert record.profile_aggregation is True
        assert record.ai_interventions is True
        assert record.cross_session_memory is True
        assert record.consent_given is False
        assert record.status == "paused"

    async def test_set_categories_invalidates_cache(self):
        cache = AsyncMock()
        cache.delete = AsyncMock()

        record = _make_consent_record()
        db = _make_db_mock(consent_record=record)
        mgr = TwinConsentManager(db=db, cache=cache)

        await mgr.set_consent_categories(
            "user_abc",
            1,
            ConsentCategories(
                behavior_tracking=False,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            ),
        )

        cache.delete.assert_called_once_with("twin:consent:1:user_abc")


class TestConsentCacheKey:
    """Tests voor cache key format."""

    def test_cache_key_format(self):
        key = TwinConsentManager._cache_key("user_abc", 1)
        assert key == "twin:consent:1:user_abc"

    def test_cache_key_different_users(self):
        k1 = TwinConsentManager._cache_key("user_a", 1)
        k2 = TwinConsentManager._cache_key("user_b", 1)
        assert k1 != k2

    def test_cache_key_different_tenants(self):
        k1 = TwinConsentManager._cache_key("user_a", 1)
        k2 = TwinConsentManager._cache_key("user_a", 2)
        assert k1 != k2
