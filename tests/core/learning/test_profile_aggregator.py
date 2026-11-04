"""
Unit tests voor ProfileAggregator.

Controleert:
- aggregate() delegeert naar DB queries
- profile_aggregation consent blocks aggregation
- consent check failure is fail-safe (does not crash)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.learning.services.profile_aggregator import ProfileAggregator
from src.core.learning.twin_models import UserCognitiveProfile


@pytest.mark.asyncio
class TestProfileAggregatorConsent:
    """Tests voor profile_aggregation consent gating."""

    async def test_aggregate_blocked_when_profile_aggregation_false(self):
        """When profile_aggregation=False, aggregate() returns None immediately."""
        db = AsyncMock()
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            return_value=MagicMock(
                behavior_tracking=True,
                profile_aggregation=False,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )

        aggregator = ProfileAggregator(db=db, consent_manager=consent_mgr)
        result = await aggregator.aggregate(tenant_id=1, human_user_id="user_abc")

        assert result is None
        # Should not query DB when blocked by consent
        db.execute.assert_not_awaited()

    async def test_aggregate_allowed_when_profile_aggregation_true(self):
        """When profile_aggregation=True, aggregate() proceeds normally."""
        db = AsyncMock()
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            return_value=MagicMock(
                behavior_tracking=True,
                profile_aggregation=True,
                ai_interventions=True,
                cross_session_memory=True,
            )
        )

        # Mock: no existing profile, no observations
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        aggregator = ProfileAggregator(db=db, consent_manager=consent_mgr)
        result = await aggregator.aggregate(tenant_id=1, human_user_id="user_abc")

        # Returns None because no observations exist (not because of consent)
        assert result is None
        # But DB was queried
        db.execute.assert_awaited()

    async def test_aggregate_without_consent_manager_skips_check(self):
        """When no consent_manager is provided, aggregate() proceeds without check."""
        db = AsyncMock()

        # Mock: no existing profile, no observations
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        aggregator = ProfileAggregator(db=db, consent_manager=None)
        result = await aggregator.aggregate(tenant_id=1, human_user_id="user_abc")

        # Returns None because no observations exist
        assert result is None
        db.execute.assert_awaited()

    async def test_consent_check_failure_is_fail_safe(self):
        """If get_consent_categories crashes, aggregate() should not crash."""
        db = AsyncMock()
        consent_mgr = AsyncMock()
        consent_mgr.get_consent_categories = AsyncMock(
            side_effect=RuntimeError("consent DB down")
        )

        # Mock DB responses for the aggregation path
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        aggregator = ProfileAggregator(db=db, consent_manager=consent_mgr)

        # Should not raise — fail-safe: if we can't check consent, proceed
        # (blocking the user is worse than accidentally aggregating)
        result = await aggregator.aggregate(tenant_id=1, human_user_id="user_abc")

        # Returns None because no observations exist, but no exception raised
        assert result is None
