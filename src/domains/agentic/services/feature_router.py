"""
Feature Router - 4-layer feature detection for the agentic system.

Detection layers (in order):
1. Explicit Header - X-Feature-Context header
2. Route Pattern - URL path matching
3. Session Continuity - Continue previous context
4. LLM Classification - AI-based intent detection

Falls back to 'general_assistant' if no match.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.llm.llm_client import LLMMessage, create_llm_client
from src.domains.agentic.schemas import FeatureDefinition
from src.domains.agentic.services.feature_registry import (
    DynamicFeatureRegistry,
    FeatureContext,
    get_feature_registry,
)
from src.domains.agentic.services.session_manager import AgenticSessionManager

logger = logging.getLogger(__name__)


@dataclass
class DetectionRequest:
    """Request context for feature detection."""

    message: str
    tenant_id: int
    user_id: int
    session_id: str | None = None
    explicit_feature: str | None = None  # From header
    route_path: str | None = None
    locale: str = "en"


class FeatureContextDetector:
    """
    4-layer feature detection system.

    Detects the appropriate feature context for a user request
    using multiple strategies in priority order.
    """

    # LLM classification configuration
    LLM_TIMEOUT_SECONDS = 2.0
    LLM_MAX_TOKENS = 20

    # Default fallback feature
    DEFAULT_FEATURE = "general_assistant"

    def __init__(
        self,
        registry: DynamicFeatureRegistry,
        session_manager: AgenticSessionManager | None = None,
        enable_llm_fallback: bool = True,
    ) -> None:
        """
        Initialize the detector.

        Args:
            registry: Feature registry instance
            session_manager: Session manager for continuity detection
            enable_llm_fallback: Whether to use LLM as final fallback
        """
        self.registry = registry
        self.session_manager = session_manager
        self.enable_llm_fallback = enable_llm_fallback
        self._llm_client: Any | None = None  # TODO(TYPE): replace Any with concrete type

    async def detect_context(self, db: AsyncSession, request: DetectionRequest) -> FeatureContext:
        """
        Detect the feature context for a request.

        Tries each detection layer in order until a match is found.

        Args:
            db: Database session
            request: Detection request

        Returns:
            FeatureContext with detected feature
        """
        # Ensure features are loaded - Returns Dict[str, FeatureDefinition]
        features: dict[str, FeatureDefinition] = await self.registry.load_features(
            db, request.tenant_id
        )

        # Layer 1: Explicit Header
        context = self._check_explicit_header(request, features)
        if context:
            logger.info(f"L1 Header: Detected {context.feature_id}")
            return context

        # Layer 2: Route Pattern
        context = self._check_route_pattern(request)
        if context:
            logger.info(f"L2 Route: Detected {context.feature_id}")
            return context

        # Layer 3: Session Continuity
        context = await self._check_session_continuity(request)
        if context:
            logger.info(f"L3 Session: Continuing {context.feature_id}")
            return context

        # Layer 4: Keyword Matching
        context = self._check_keywords(request)
        if context:
            logger.info(f"L4 Keyword: Detected {context.feature_id}")
            return context

        # Layer 5: LLM Classification (optional)
        if self.enable_llm_fallback:
            context = await self._classify_with_llm(request, features)
            if context:
                logger.info(f"L5 LLM: Classified as {context.feature_id}")
                return context

        # Fallback to default
        logger.info(f"Fallback: Using default {self.DEFAULT_FEATURE}")
        return FeatureContext(
            feature_id=self.DEFAULT_FEATURE, confidence=0.3, detection_layer="fallback"
        )

    def _check_explicit_header(
        self, request: DetectionRequest, features: dict[str, FeatureDefinition]
    ) -> FeatureContext | None:
        """Layer 1: Check explicit feature header."""
        if not request.explicit_feature:
            return None

        # Validate the feature exists
        if request.explicit_feature not in features:
            logger.warning(f"Explicit feature '{request.explicit_feature}' not found")
            return None

        return FeatureContext(
            feature_id=request.explicit_feature,
            confidence=1.0,
            detection_layer="header",
        )

    def _check_route_pattern(self, request: DetectionRequest) -> FeatureContext | None:
        """Layer 2: Match URL route pattern."""
        if not request.route_path:
            return None

        return self.registry.match_by_route(request.tenant_id, request.route_path)

    async def _check_session_continuity(
        self, request: DetectionRequest
    ) -> FeatureContext | None:
        """Layer 3: Continue from previous session context."""
        if not self.session_manager or not request.session_id:
            return None

        # Check session for current feature
        current_feature = await self.session_manager.check_session_continuity(
            request.session_id, request.message
        )

        if not current_feature:
            return None

        # Verify feature still exists (using registry get_feature which uses cache)
        # Assuming registry.get_feature returns FeatureDefinition now
        feature = self.registry.get_feature(request.tenant_id, current_feature)
        if not feature:
            return None

        return FeatureContext(
            feature_id=current_feature,
            confidence=0.85,
            detection_layer="session",
            metadata={"session_id": request.session_id},
        )

    def _check_keywords(self, request: DetectionRequest) -> FeatureContext | None:
        """Layer 4: Match keywords in message."""
        return self.registry.match_by_keywords(request.tenant_id, request.message, threshold=1)

    async def _classify_with_llm(
        self, request: DetectionRequest, features: dict[str, FeatureDefinition]
    ) -> FeatureContext | None:
        """Layer 5: Use LLM to classify intent."""
        try:
            # Lazy init LLM client
            if self._llm_client is None:
                self._llm_client = create_llm_client(provider_name="google")

            # Build feature list for classification
            feature_list: list[str] = []
            for fid, feature in features.items():
                name = feature.get_display_name(request.locale)
                desc = feature.get_description(request.locale)
                feature_list.append(f"- {fid}: {name} - {desc}")

            features_text = "\n".join(feature_list[:10])  # Limit for token efficiency

            # Classification prompt
            system_prompt = """You are a feature classifier. Given a user message and a list of available features,
respond with ONLY the feature_id that best matches the user's intent.
If no feature matches well, respond with "general_assistant".
Respond with just the feature_id, nothing else."""

            user_prompt = f"""Available features:
{features_text}

User message: {request.message}

Best matching feature_id:"""

            # Call LLM
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ]

            response = await self._llm_client.chat_completion(
                messages=messages,
                max_tokens=self.LLM_MAX_TOKENS,
                temperature=0.0,
                timeout=self.LLM_TIMEOUT_SECONDS,
            )

            if response.success:
                feature_id = response.content.strip().lower()

                # Validate response
                if feature_id in features or feature_id == self.DEFAULT_FEATURE:
                    return FeatureContext(
                        feature_id=feature_id, confidence=0.7, detection_layer="llm"
                    )

        except TimeoutError:
            logger.warning("LLM classification timeout")
        except Exception as e:
            logger.error(f"LLM classification error: {e}")

        return None


# Factory function
def create_feature_detector(
    session_manager: AgenticSessionManager | None = None, enable_llm: bool = True
) -> FeatureContextDetector:
    """Create a feature detector instance."""
    return FeatureContextDetector(
        registry=get_feature_registry(),
        session_manager=session_manager,
        enable_llm_fallback=enable_llm,
    )
