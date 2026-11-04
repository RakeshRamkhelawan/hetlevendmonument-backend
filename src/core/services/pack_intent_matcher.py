"""
Pack Intent Matcher - Now integrated with Central ML Platform

Matches user prompts to Domain Packs using:
1. Semantic similarity (TF-IDF + Cosine)
2. Keyword matching
3. ML predictions from Central Agent ML Platform
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.core.models.rbac_models import Tenant, User
from src.core.ml.pack_ml_trainer import PackMatchPrediction, get_ml_trainer
from src.core.observability.pack_metrics import get_metrics_collector
from src.core.procedures.models import DomainPack

logger = logging.getLogger(__name__)


@dataclass
class PackMatchResult:
    """Result of matching a user prompt to a Domain Pack"""

    pack_id: str
    pack_name: str
    confidence: float
    match_type: str  # "exact", "semantic", "keyword", "ml_enhanced", "none"
    reason: str
    features: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ml_prediction: PackMatchPrediction | None = None


class PackIntentMatcher:
    """
    Advanced intent matching using hybrid scoring
    - Semantic similarity (TF-IDF + Cosine)
    - Keyword matching
    - ML predictions (Central Agent ML Platform)
    """

    def __init__(self) -> None:
        self.vectorizer = TfidfVectorizer(
            max_features=100, ngram_range=(1, 2), stop_words="english"
        )
        self.ml_trainer = get_ml_trainer()
        self.metrics = get_metrics_collector()

        # Match thresholds
        self.EXACT_THRESHOLD = 0.95
        self.HIGH_THRESHOLD = 0.80
        self.MEDIUM_THRESHOLD = 0.60
        self.LOW_THRESHOLD = 0.40

    async def find_best_pack_match(
        self, tenant_id: int, prompt: str, available_packs: list[DomainPack] | None = None
    ) -> PackMatchResult:
        """
        Find the best matching Domain Pack for a user prompt

        Uses hybrid scoring:
        - Semantic similarity (TF-IDF + Cosine): 40%
        - Keyword overlap: 35%
        - ML prediction: 25%
        """
        start_time = datetime.now(timezone.utc)

        if not available_packs:
            available_packs = await self._get_packs_for_tenant(tenant_id)

        if not available_packs:
            return PackMatchResult(
                pack_id="",
                pack_name="",
                confidence=0.0,
                match_type="none",
                reason="No available packs",
            )

        # Calculate scores for all packs
        scored_packs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pack in available_packs:
            scores = await self._calculate_match_scores(
                prompt=prompt, pack=pack, tenant_id=tenant_id
            )
            scored_packs.append((pack, scores))

        # Sort by total confidence
        scored_packs.sort(key=lambda x: x[1]["total"], reverse=True)

        best_pack, best_scores = scored_packs[0]

        # Determine match type
        match_type = self._determine_match_type(best_scores["total"])

        # Record metrics
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        self.metrics.record_match_attempt(
            tenant_id=tenant_id,
            prompt=prompt,
            matched_pack_id=best_pack.id,
            matched_pack_name=best_pack.name,
            confidence_score=best_scores["total"],
            confidence_level=match_type,
            duration_ms=duration * 1000,
            success=True,
        )

        logger.debug(
            f"Best match for '{prompt[:50]}...': "
            f"{best_pack.name} ({match_type}, {best_scores['total']:.2f})"
        )

        return PackMatchResult(
            pack_id=best_pack.id,
            pack_name=best_pack.name,
            confidence=best_scores["total"],
            match_type=match_type,
            reason=f"Semantic: {best_scores['semantic']:.2f}, "
            f"Keyword: {best_scores['keyword']:.2f}, "
            f"ML: {best_scores['ml']:.2f}",
            features=best_scores["features"],
            ml_prediction=best_scores.get("ml_prediction"),
        )

    async def find_multiple_matches(
        self, tenant_id: int, prompt: str, min_confidence: float = 0.3, max_results: int = 3
    ) -> list[PackMatchResult]:
        """
        Find multiple potential pack matches, sorted by confidence
        """
        packs = await self._get_packs_for_tenant(tenant_id)

        matches: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pack in packs:
            scores = await self._calculate_match_scores(prompt, pack, tenant_id)
            if scores["total"] >= min_confidence:
                matches.append((pack, scores))

        matches.sort(key=lambda x: x[1]["total"], reverse=True)

        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pack, scores in matches[:max_results]:
            match_type = self._determine_match_type(scores["total"])
            results.append(
                PackMatchResult(
                    pack_id=pack.id,
                    pack_name=pack.name,
                    confidence=scores["total"],
                    match_type=match_type,
                    reason=f"Score: {scores['total']:.2f}",
                    features=scores["features"],
                    ml_prediction=scores.get("ml_prediction"),
                )
            )

        return results

    async def _calculate_match_scores(
        self, prompt: str, pack: DomainPack, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Calculate all match scores for a pack"""

        # Semantic similarity (TF-IDF + Cosine)
        semantic_score = self._calculate_semantic_similarity(prompt, pack.description or "")

        # Keyword overlap
        keyword_score = self._calculate_keyword_overlap(prompt, pack.intent_tags or [])

        # ML prediction (if trained)
        ml_score = 0.5  # Default neutral
        ml_prediction = None

        try:
            ml_prediction = self.ml_trainer.predict_match_quality(
                user_prompt=prompt,
                pack_id=str(pack.id),
                pack_name=pack.name,
                pack_description=pack.description or "",
                pack_capabilities=pack.capabilities or [],
                tenant_id=tenant_id,
            )
            ml_score = ml_prediction.confidence
        except Exception as e:
            logger.debug(f"ML prediction failed: {e}")

        # Hybrid scoring
        # Semantic: 40%, Keyword: 35%, ML: 25%
        total_score = semantic_score * 0.40 + keyword_score * 0.35 + ml_score * 0.25

        return {
            "semantic": semantic_score,
            "keyword": keyword_score,
            "ml": ml_score,
            "total": total_score,
            "features": {"semantic": semantic_score, "keyword": keyword_score, "ml": ml_score},
            "ml_prediction": ml_prediction,
        }

    def _calculate_semantic_similarity(self, prompt: str, pack_description: str) -> float:
        """
        Calculate semantic similarity using TF-IDF + Cosine similarity
        """
        if not prompt or not pack_description:
            return 0.0

        try:
            # Create TF-IDF vectors
            texts = [prompt.lower(), pack_description.lower()]
            tfidf_matrix = self.vectorizer.fit_transform(texts)

            # Calculate cosine similarity
            similarity_matrix = cosine_similarity(tfidf_matrix)
            similarity = similarity_matrix[0, 1]

            return float(similarity)
        except Exception as e:
            logger.debug(f"Semantic similarity calculation failed: {e}")
            return 0.0

    def _calculate_keyword_overlap(self, prompt: str, intent_tags: list[str]) -> float:
        """
        Calculate keyword overlap between prompt and intent tags
        """
        if not intent_tags:
            return 0.0

        prompt_words = set(prompt.lower().split())

        matches = 0
        for tag in intent_tags:
            tag_words = set(tag.lower().split())
            if prompt_words & tag_words:  # Intersection
                matches += 1

        return min(matches / len(intent_tags), 1.0)

    def _determine_match_type(self, confidence: float) -> str:
        """Determine match type based on confidence score"""
        if confidence >= self.EXACT_THRESHOLD:
            return "exact"
        elif confidence >= self.HIGH_THRESHOLD:
            return "high"
        elif confidence >= self.MEDIUM_THRESHOLD:
            return "medium"
        elif confidence >= self.LOW_THRESHOLD:
            return "low"
        else:
            return "none"

    async def _get_packs_for_tenant(self, tenant_id: int) -> list[DomainPack]:
        """Get all available packs for a tenant"""
        # In production, query from database
        # For now, return mock data
        return [
            DomainPack(
                id="hr_onboarding",
                name="HR Onboarding Pack",
                description="Employee onboarding and HR procedures",
                intent_tags=["onboarding", "new hire", "employee", "hr"],
                capabilities=["create_employee", "setup_access", "schedule_training"],
            ),
            DomainPack(
                id="it_support",
                name="IT Support Pack",
                description="IT helpdesk and technical support",
                intent_tags=["it support", "technical issue", "computer problem"],
                capabilities=["create_ticket", "assign_engineer", "remote_access"],
            ),
            DomainPack(
                id="finance_expense",
                name="Finance Expense Pack",
                description="Expense reports and reimbursements",
                intent_tags=["expense", "reimbursement", "invoice", "finance"],
                capabilities=["submit_expense", "approve_invoice", "process_payment"],
            ),
        ]

    async def record_feedback(
        self,
        tenant_id: int,
        user_id: int,
        original_prompt: str,
        matched_pack_id: str,
        was_helpful: bool,
        rating: int | None = None,
    ) -> None:
        """Record user feedback for ML training"""

        # Get pack info
        packs = await self._get_packs_for_tenant(tenant_id)
        matched_pack = next((p for p in packs if p.id == matched_pack_id), None)

        if matched_pack:
            self.ml_trainer.add_training_sample(
                user_prompt=original_prompt,
                matched_pack_id=matched_pack_id,
                matched_pack_name=matched_pack.name,
                pack_description=matched_pack.description or "",
                pack_capabilities=matched_pack.capabilities or [],
                was_helpful=was_helpful,
                user_rating=rating,
                tenant_id=tenant_id,
            )

        # Record metrics
        self.metrics.record_feedback(
            tenant_id=tenant_id,
            pack_id=matched_pack_id,
            pack_name=matched_pack.name if matched_pack else "",
            was_helpful=was_helpful,
            rating=rating,
        )

        logger.info(
            f"Recorded feedback for pack {matched_pack_id}: helpful={was_helpful}, rating={rating}"
        )


# Singleton
_matcher: PackIntentMatcher | None = None


def get_intent_matcher() -> PackIntentMatcher:
    """Get or create singleton PackIntentMatcher"""
    global _matcher
    if _matcher is None:
        _matcher = PackIntentMatcher()
    return _matcher
