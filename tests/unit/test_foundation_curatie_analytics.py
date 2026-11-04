"""Unit tests for BE-EP-045 Foundation Curation Analytics & KPI Dashboard.

Validates schema validation, KPI calculations, tag distribution aggregations,
and tenant-scoped queries for GET /{tenantSlug}/foundation/admin/curatie/analytics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.core.api.v1.foundation.schemas import (
    CurationAnalyticsResponse,
    EducationalAnalytics,
    NewsletterAnalytics,
    TagDistributionItem,
)
from src.core.models.foundation_content import (
    ContentStatus,
    FoundationContent,
    PortalRole,
    PortalUser,
)
from src.core.shared.datetime_utils import utc_now


# ============================================================================
# 1. Schema Validation Tests
# ============================================================================


class TestAnalyticsSchemas:
    @pytest.mark.unit
    def test_tag_distribution_item_valid(self) -> None:
        item = TagDistributionItem(
            tag="Klederdracht",
            tag_type="THEME",
            count=15,
            average_confidence=0.88,
        )
        assert item.tag == "Klederdracht"
        assert item.tag_type == "THEME"
        assert item.count == 15
        assert item.average_confidence == 0.88

    @pytest.mark.unit
    def test_tag_distribution_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            TagDistributionItem(
                tag="Test",
                tag_type="THEME",
                count=1,
                average_confidence=1.5,  # > 1.0
            )

    @pytest.mark.unit
    def test_curation_analytics_response_valid(self) -> None:
        res = CurationAnalyticsResponse(
            status_counts={"pending": 5, "approved": 20, "rejected": 2},
            total_content=27,
            average_moderation_seconds=3600.5,
            tag_distribution=[
                TagDistributionItem(
                    tag="Amsterdam",
                    tag_type="LOCATION",
                    count=8,
                    average_confidence=0.92,
                )
            ],
            newsletter=NewsletterAnalytics(
                total_subscribers=120,
                verified_subscribers=110,
            ),
            education=EducationalAnalytics(
                active_codes=6,
                total_codes=10,
            ),
        )
        assert res.total_content == 27
        assert res.status_counts["pending"] == 5
        assert res.average_moderation_seconds == 3600.5
        assert res.newsletter.total_subscribers == 120
        assert res.education.active_codes == 6

    @pytest.mark.unit
    def test_curation_analytics_response_defaults_and_nulls(self) -> None:
        res = CurationAnalyticsResponse(
            status_counts={"pending": 0, "approved": 0, "rejected": 0},
            total_content=0,
            average_moderation_seconds=None,
            tag_distribution=[],
            newsletter=NewsletterAnalytics(total_subscribers=0, verified_subscribers=0),
            education=EducationalAnalytics(active_codes=0, total_codes=0),
        )
        assert res.total_content == 0
        assert res.average_moderation_seconds is None
        assert len(res.tag_distribution) == 0


# ============================================================================
# 2. Analytics Calculation & Endpoint Unit Tests
# ============================================================================


class TestCurationAnalyticsEndpoint:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_curation_analytics_logic(self) -> None:
        """Verify query aggregation logic executes correctly for curator."""
        from src.core.api.v1.foundation.admin.curatie import get_curation_analytics

        mock_tenant = MagicMock()
        mock_tenant.id = 42

        curator = PortalUser(
            id=101,
            tenant_id=42,
            email="curator@erfgoed.nl",
            role=PortalRole.CURATOR,
        )

        mock_session = AsyncMock()

        # Mock query executions:
        # 1. status counts
        status_mock = MagicMock()
        status_mock.all.return_value = [
            (ContentStatus.PENDING, 3),
            (ContentStatus.APPROVED, 12),
            (ContentStatus.REJECTED, 1),
        ]

        # 2. total content
        total_mock = MagicMock()
        total_mock.scalar.return_value = 16

        # 3. moderation duration avg
        dur_mock = MagicMock()
        dur_mock.scalar.return_value = 1800.0  # 30 minutes

        # 4. tag distribution
        tag_mock = MagicMock()
        tag_mock.all.return_value = [
            ("Koloniaal", "THEME", 7, 0.91),
            ("Paramaribo", "LOCATION", 5, 0.85),
        ]

        # 5. newsletter
        news_total_mock = MagicMock()
        news_total_mock.scalar.return_value = 45
        news_ver_mock = MagicMock()
        news_ver_mock.scalar.return_value = 40

        # 6. education
        edu_active_mock = MagicMock()
        edu_active_mock.scalar.return_value = 4
        edu_total_mock = MagicMock()
        edu_total_mock.scalar.return_value = 8

        mock_session.execute.side_effect = [
            status_mock,
            total_mock,
            dur_mock,
            tag_mock,
            news_total_mock,
            news_ver_mock,
            edu_active_mock,
            edu_total_mock,
        ]

        with patch(
            "src.core.api.v1.foundation.admin.curatie.public_tenant_scope"
        ) as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant
            mock_scope.return_value.__aexit__.return_value = None

            result = await get_curation_analytics(
                tenantSlug="erfgoed",
                current_user=curator,
                session=mock_session,
            )

        assert result.total_content == 16
        assert result.status_counts["pending"] == 3
        assert result.status_counts["approved"] == 12
        assert result.status_counts["rejected"] == 1
        assert result.average_moderation_seconds == 1800.0
        assert len(result.tag_distribution) == 2
        assert result.tag_distribution[0].tag == "Koloniaal"
        assert result.tag_distribution[0].average_confidence == 0.91
        assert result.newsletter.total_subscribers == 45
        assert result.newsletter.verified_subscribers == 40
        assert result.education.active_codes == 4
        assert result.education.total_codes == 8
