"""
Pack ML Trainer - Refactored to use Central Agent ML Platform

This is now a specialized client of the central ML platform,
specifically configured for pack intent matching.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from src.core.ml.agent_ml_platform import MLTaskType, TrainingRecord, get_ml_platform

logger = logging.getLogger(__name__)


@dataclass
class PackMatchPrediction:
    """Prediction result for pack matching"""

    pack_id: str
    confidence: float
    model_contribution: float
    features_used: dict[str, float]


class PackMLTrainer:
    """
    Pack Intent Matching ML Trainer

    Uses the Central Agent ML Platform for:
    - Model training
    - Prediction serving
    - Feedback collection

    This is a specialized wrapper around the central platform.
    """

    AGENT_ID = "pack_intent_matcher"

    def __init__(self) -> None:
        self._platform = get_ml_platform()
        self._ensure_registered()

    def _ensure_registered(self) -> None:
        """Register with central platform if not already"""
        try:
            # Check if already registered
            self._platform.get_agent_performance(self.AGENT_ID)
        except ValueError:
            # Register
            self._platform.register_agent(
                agent_id=self.AGENT_ID,
                task_type=MLTaskType.INTENT_CLASSIFICATION,
                feature_columns=[
                    "text_similarity",
                    "historical_success",
                    "capability_count",
                    "tenant_preference",
                ],
                target_column="was_helpful",
                model_class="RandomForestClassifier",
                hyperparameters={"n_estimators": 100, "max_depth": 10},
                min_samples=50,
            )
            logger.info(f"Registered {self.AGENT_ID} with central ML platform")

    # =========================================================================
    # Training Data Collection
    # =========================================================================

    def add_training_sample(
        self,
        user_prompt: str,
        matched_pack_id: str,
        matched_pack_name: str,
        pack_description: str,
        pack_capabilities: list[str],
        was_helpful: bool,
        user_rating: int | None = None,
        tenant_id: int = 0,
    ) -> None:
        """Add a training sample from user feedback"""

        # Calculate features
        features = self._calculate_features(
            user_prompt=user_prompt,
            pack_name=matched_pack_name,
            pack_description=pack_description,
            pack_capabilities=pack_capabilities,
            pack_id=matched_pack_id,
            tenant_id=tenant_id,
        )

        # Record via central platform
        self._platform.record_feedback(
            agent_id=self.AGENT_ID,
            features=features,
            prediction=True,  # We predicted this would be helpful
            actual=was_helpful,
            was_correct=was_helpful,  # Correct if it was helpful
            metadata={
                "tenant_id": tenant_id,
                "user_prompt": user_prompt,
                "matched_pack_id": matched_pack_id,
                "matched_pack_name": matched_pack_name,
                "user_rating": user_rating,
            },
        )

        logger.debug(f"Added training sample for pack {matched_pack_id}")

    def add_feedback_batch(
        self, feedbacks: list[dict[str, Any]], pack_lookup: dict[str, dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Add a batch of feedback entries"""
        for fb in feedbacks:
            pack_id: str | None = fb.get("pack_id")
            if pack_id is None:
                continue
            pack_info = pack_lookup.get(pack_id, {})

            self.add_training_sample(
                user_prompt=fb.get("original_prompt", ""),
                matched_pack_id=pack_id,
                matched_pack_name=pack_info.get("name", "Unknown"),
                pack_description=pack_info.get("description", ""),
                pack_capabilities=pack_info.get("capabilities", []),
                was_helpful=fb.get("was_helpful", False),
                user_rating=fb.get("rating"),
                tenant_id=fb.get("tenant_id", 0),
            )

    # =========================================================================
    # Prediction
    # =========================================================================

    def predict_match_quality(
        self,
        user_prompt: str,
        pack_id: str,
        pack_name: str,
        pack_description: str,
        pack_capabilities: list[str],
        tenant_id: int,
    ) -> PackMatchPrediction:
        """
        Predict the quality of a pack match
        """
        # Calculate features
        features = self._calculate_features(
            user_prompt=user_prompt,
            pack_name=pack_name,
            pack_description=pack_description,
            pack_capabilities=pack_capabilities,
            pack_id=pack_id,
            tenant_id=tenant_id,
        )

        # Get prediction from central platform
        result = self._platform.predict(
            agent_id=self.AGENT_ID, features=features, return_confidence=True
        )

        # Calculate model contribution
        rule_confidence = self._calculate_rule_confidence(user_prompt, pack_name, pack_description)

        model_confidence = result.get("confidence", 0.0)
        model_contribution = abs(model_confidence - rule_confidence)

        return PackMatchPrediction(
            pack_id=pack_id,
            confidence=model_confidence,
            model_contribution=model_contribution,
            features_used=features,
        )

    # =========================================================================
    # Feature Calculation
    # =========================================================================

    def _calculate_features(
        self,
        user_prompt: str,
        pack_name: str,
        pack_description: str,
        pack_capabilities: list[str],
        pack_id: str,
        tenant_id: int,
    ) -> dict[str, float]:
        """Calculate features for prediction"""

        # Text similarity (simplified - in production use TF-IDF)
        prompt_words = set(user_prompt.lower().split())
        pack_text = f"{pack_name} {pack_description}".lower()
        pack_words = set(pack_text.split())

        if prompt_words and pack_words:
            intersection = len(prompt_words & pack_words)
            union = len(prompt_words | pack_words)
            text_similarity = intersection / union if union > 0 else 0.0
        else:
            text_similarity = 0.0

        # Historical success (from platform stats)
        historical = self._get_historical_success(pack_id)

        # Capability count (normalized)
        capability_count = len(pack_capabilities) / 10.0

        # Tenant preference
        tenant_pref = self._get_tenant_preference(tenant_id, pack_id)

        return {
            "text_similarity": text_similarity,
            "historical_success": historical,
            "capability_count": capability_count,
            "tenant_preference": tenant_pref,
        }

    def _calculate_rule_confidence(
        self, user_prompt: str, pack_name: str, pack_description: str
    ) -> float:
        """Calculate rule-based confidence for comparison"""
        prompt_lower = user_prompt.lower()
        pack_text = f"{pack_name} {pack_description}".lower()

        prompt_words = set(prompt_lower.split())
        pack_words = set(pack_text.split())
        overlap = len(prompt_words & pack_words)

        return min(0.7, 0.3 + (overlap * 0.1))

    def _get_historical_success(self, pack_id: str) -> float:
        """Get historical success rate for a pack"""
        # This would query the central platform's stats
        # For now, return neutral
        return 0.5

    def _get_tenant_preference(self, tenant_id: int, pack_id: str) -> float:
        """Check if this is a tenant's frequently used pack"""
        # This would query tenant-specific stats
        # For now, return neutral
        return 0.5

    # =========================================================================
    # Analytics (Delegated to Central Platform)
    # =========================================================================

    def get_model_performance(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get model performance metrics"""
        return self._platform.get_agent_performance(self.AGENT_ID)

    def get_improvement_suggestions(self) -> list[str]:
        """Get suggestions for improving the model"""
        performance = self.get_model_performance()
        suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        total_samples = performance.get("training_samples", 0)
        min_samples = 50

        if total_samples < min_samples:
            suggestions.append(
                f"Collect {min_samples - total_samples} more feedback samples "
                f"to start training (currently have {total_samples})"
            )

        accuracy = performance.get("accuracy", 0)
        if accuracy < 0.7 and total_samples > 50:
            suggestions.append(
                f"Model accuracy ({accuracy:.1%}) is below 70%. " f"Review training data quality."
            )

        return suggestions

    def train_model(self) -> bool:
        """Manually trigger model training"""
        return self._platform.train_agent_model(self.AGENT_ID)


# Singleton (backward compatible)
_ml_trainer: PackMLTrainer | None = None


def get_ml_trainer() -> PackMLTrainer:
    """Get or create singleton Pack ML Trainer"""
    global _ml_trainer
    if _ml_trainer is None:
        _ml_trainer = PackMLTrainer()
    return _ml_trainer
