"""
Feature Registry - Dynamic feature management for the agentic system.

Provides:
- Loading platform and tenant-specific features
- Feature lookup by ID, category, or domain
- Keyword-based feature matching
- Cache management for performance
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import Feature
from src.domains.agentic.schemas import FeatureDefinition

logger = logging.getLogger(__name__)


@dataclass
class FeatureContext:
    """Context for a detected feature."""

    feature_id: str
    confidence: float
    detection_layer: str  # 'header', 'route', 'session', 'keyword', 'llm'
    metadata: dict[str, object] = field(default_factory=dict)


class DynamicFeatureRegistry:
    """
    Dynamic feature registry that loads features from database.

    Features are cached per-tenant for performance.
    Platform features (tenant_id=NULL) are available to all tenants.
    """

    def __init__(self) -> None:
        self._cache: dict[
            int, dict[str, FeatureDefinition]
        ] = {}  # tenant_id -> {feature_id -> FeatureDefinition}
        self._platform_features: dict[str, FeatureDefinition] = {}  # Platform-level features
        self._keyword_index: dict[
            int, dict[str, set[str]]
        ] = {}  # tenant_id -> {keyword -> feature_ids}

    async def load_features(
        self, db: AsyncSession, tenant_id: int, force_refresh: bool = False
    ) -> dict[str, FeatureDefinition]:
        """
        Load features for a tenant, including platform features.

        Args:
            db: Database session
            tenant_id: Tenant to load features for
            force_refresh: Force cache refresh

        Returns: dict[str, Any] mapping feature_id to FeatureDefinition  # TODO(TYPE): replace Any with concrete type
        """
        cache_key = tenant_id

        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        # Load platform features if not loaded
        if not self._platform_features or force_refresh:
            await self._load_platform_features(db)

        # Load tenant-specific features
        stmt = select(Feature).where(Feature.tenant_id == tenant_id, Feature.is_active.is_(True))
        result = await db.execute(stmt)
        tenant_features_db = result.scalars().all()

        # Map to DTOs
        tenant_features = {f.id: self._map_to_dto(f) for f in tenant_features_db}

        # Merge platform and tenant features (tenant overrides platform)
        merged = {**self._platform_features, **tenant_features}

        # Cache the result
        self._cache[cache_key] = merged

        # Build keyword index
        self._build_keyword_index(tenant_id, merged)

        logger.info(f"Loaded {len(merged)} features for tenant {tenant_id}")
        return merged

    async def _load_platform_features(self, db: AsyncSession) -> None:
        """Load platform-level features (tenant_id is NULL)."""
        stmt = select(Feature).where(Feature.tenant_id.is_(None), Feature.is_active.is_(True))
        result = await db.execute(stmt)
        platform_features_db = result.scalars().all()

        self._platform_features = {f.id: self._map_to_dto(f) for f in platform_features_db}
        logger.info(f"Loaded {len(self._platform_features)} platform features")

    def _map_to_dto(self, f: Feature) -> FeatureDefinition:
        """Map SQLAlchemy Feature model to Pydantic FeatureDefinition."""
        # Handle JSON fields that might be None
        keywords_data = f.keywords if f.keywords else {}
        if isinstance(keywords_data, list):
            # Legacy format support: list to dict
            keywords_data = {"en": keywords_data}

        # Create DTO
        return FeatureDefinition(
            id=f.id,
            category=f.category,
            display_name={"en": f.name},  # Default mapping
            description={"en": f.description if f.description is not None else ""},
            domain_context=getattr(f, "domain_context", None),  # Handle if missing
            intent_keywords=keywords_data,  # type: ignore[arg-type]
            # Map other fields as needed
            tenant_id=f.tenant_id,
            is_active=True,
        )

    def _build_keyword_index(self, tenant_id: int, features: dict[str, FeatureDefinition]) -> None:
        """Build keyword index for fast matching."""
        index: dict[str, set[str]] = {}

        for feature_id, feature in features.items():
            if not feature.intent_keywords:
                continue

            # Index all locales
            for locale, keywords in feature.intent_keywords.items():
                if isinstance(keywords, list):
                    for keyword in keywords:
                        keyword_lower = keyword.lower()
                        if keyword_lower not in index:
                            index[keyword_lower] = set()
                        index[keyword_lower].add(feature_id)

        self._keyword_index[tenant_id] = index

    def get_feature(self, tenant_id: int, feature_id: str) -> FeatureDefinition | None:
        """Get a specific feature by ID."""
        if tenant_id not in self._cache:
            return None
        return self._cache[tenant_id].get(feature_id)

    def get_features_by_category(self, tenant_id: int, category: str) -> list[FeatureDefinition]:
        """Get all features in a category."""
        if tenant_id not in self._cache:
            return []
        return [f for f in self._cache[tenant_id].values() if f.category == category]

    def get_features_by_domain(
        self, tenant_id: int, domain_context: str
    ) -> list[FeatureDefinition]:
        """Get features for a specific domain context."""
        if tenant_id not in self._cache:
            return []
        return [
            f
            for f in self._cache[tenant_id].values()
            if f.domain_context == domain_context or f.domain_context is None
        ]

    def match_by_keywords(
        self, tenant_id: int, message: str, threshold: int = 1
    ) -> FeatureContext | None:
        """
        Match a message to features using keyword matching.
        """
        if tenant_id not in self._keyword_index:
            return None

        index = self._keyword_index[tenant_id]
        message_lower = message.lower()

        # Count keyword matches per feature
        feature_scores: dict[str, int] = {}

        for keyword, feature_ids in index.items():
            if keyword in message_lower:
                for feature_id in feature_ids:
                    feature_scores[feature_id] = feature_scores.get(feature_id, 0) + 1

        if not feature_scores:
            return None

        # Get best match
        from typing import cast

        best_feature = max(
            feature_scores, key=cast(Callable[..., Any], feature_scores.get)
        )  # TODO(TYPE): replace Any with concrete type
        best_score = feature_scores[best_feature]

        if best_score < threshold:
            return None

        # Calculate confidence based on score
        confidence = min(1.0, best_score * 0.25)

        return FeatureContext(
            feature_id=best_feature,
            confidence=confidence,
            detection_layer="keyword",
            metadata={"keyword_matches": best_score},
        )

    def match_by_route(self, tenant_id: int, route_path: str) -> FeatureContext | None:
        """Match a route path to a feature."""
        if tenant_id not in self._cache:
            return None

        for feature_id, feature in self._cache[tenant_id].items():
            if not feature.route_patterns:
                continue

            for pattern in feature.route_patterns:
                if self._route_matches(pattern, route_path):
                    return FeatureContext(
                        feature_id=feature_id,
                        confidence=1.0,
                        detection_layer="route",
                        metadata={"matched_pattern": pattern},
                    )

        return None

    @staticmethod
    def _route_matches(pattern: str, path: str) -> bool:
        """Check if a route pattern matches a path."""
        # Simple prefix matching
        if pattern.endswith("*"):
            return path.startswith(pattern[:-1])
        return path == pattern

    def clear_cache(self, tenant_id: int | None = None) -> None:
        """Clear the feature cache."""
        if tenant_id is not None:
            self._cache.pop(tenant_id, None)
            self._keyword_index.pop(tenant_id, None)
        else:
            self._cache.clear()
            self._keyword_index.clear()
            self._platform_features.clear()

    def get_all_feature_ids(self, tenant_id: int) -> list[str]:
        """Get all feature IDs for a tenant."""
        if tenant_id not in self._cache:
            return []
        return list(self._cache[tenant_id].keys())


# Global singleton instance
_registry_instance: DynamicFeatureRegistry | None = None


def get_feature_registry() -> DynamicFeatureRegistry:
    """Get or create the global feature registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = DynamicFeatureRegistry()
    return _registry_instance
