"""
Feature Registry Service Unit Tests - TDD Phase 2

Tests for DynamicFeatureRegistry adapting to Clean Architecture (DTOs).
Run: pytest tests/unit/agentic/test_feature_registry.py -v
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.schemas import FeatureDefinition


class TestDynamicFeatureRegistry:
    """Tests for DynamicFeatureRegistry service."""

    @pytest.mark.asyncio
    async def test_load_features_empty_db(self, db_session: AsyncSession, isolated_tenant):
        """Returns empty dict when no features exist for tenant."""
        from src.domains.agentic.services.feature_registry import DynamicFeatureRegistry

        registry = DynamicFeatureRegistry()
        features = await registry.load_features(
            db=db_session, tenant_id=isolated_tenant["tenant_id"]
        )

        assert features == {}

    @pytest.mark.asyncio
    async def test_load_features_returns_dtos(self, db_session: AsyncSession, isolated_tenant):
        """Returns Pydantic DTOs, not SQLAlchemy models."""
        from src.domains.agentic.models import Feature
        from src.domains.agentic.services.feature_registry import DynamicFeatureRegistry

        # Setup
        feature = Feature(
            id="dto_test_feature",
            name="DTO Test",
            description="Testing DTOs",
            category="general",
            is_active=True,
            tenant_id=isolated_tenant["tenant_id"],
            keywords={"en": ["test keyword"]},  # Correct field
        )

        db_session.add(feature)
        await db_session.commit()

        registry = DynamicFeatureRegistry()
        features = await registry.load_features(
            db=db_session, tenant_id=isolated_tenant["tenant_id"]
        )

        assert len(features) == 1
        dto = features["dto_test_feature"]

        # KEY ASSERTION: Must be Pydantic model
        assert isinstance(dto, FeatureDefinition)
        assert dto.id == "dto_test_feature"
        # Check helper method
        # DTO maps Feature.name -> display_name['en']
        assert dto.get_display_name("en") == "DTO Test"

    @pytest.mark.asyncio
    async def test_get_feature_returns_dto(self, db_session: AsyncSession, isolated_tenant):
        """Get specific feature returns DTO."""
        from src.domains.agentic.models import Feature
        from src.domains.agentic.services.feature_registry import DynamicFeatureRegistry

        feature = Feature(
            id="specific_dto",
            name="Specific DTO",
            description="Desc",
            category="general",
            is_active=True,
            tenant_id=isolated_tenant["tenant_id"],
        )
        db_session.add(feature)
        await db_session.commit()

        registry = DynamicFeatureRegistry()
        await registry.load_features(db=db_session, tenant_id=isolated_tenant["tenant_id"])

        result = registry.get_feature(
            tenant_id=isolated_tenant["tenant_id"], feature_id="specific_dto"
        )

        assert isinstance(result, FeatureDefinition)
        assert result.id == "specific_dto"
