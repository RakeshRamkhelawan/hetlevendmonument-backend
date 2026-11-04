"""
Slice 1: ConfidenceScorer Implementation
Multi-signal scoring engine for procedure matching (5 signals with weighted combination)

Signals:
1. Tag Score (0.35) - Direct intent tag matching
2. Semantic Score (0.25) - Vector similarity to intent
3. History Score (0.20) - User's historical execution frequency
4. Recency Score (0.10) - How recently the procedure was executed
5. User Override Score (0.10) - User's manual preference/feedback

Ambiguous Detection: Flag if top 2 candidates differ by < 0.10
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, cast
from uuid import UUID


class _EmbeddingService(Protocol):
    """Protocol for embedding services used by ConfidenceScorer."""

    async def embed_text(self, text: str) -> list[float]: ...


class _ExecutionRecord(Protocol):
    """Protocol for execution records returned by repository."""

    created_at: datetime


class _Repository(Protocol):
    """Protocol for procedure execution repositories used by ConfidenceScorer."""

    async def get_execution_history(
        self, user_id: UUID, procedure_id: UUID, tenant_id: UUID
    ) -> list[dict[str, Any]]: ...  # TODO(TYPE): replace Any with concrete type

    async def get_last_execution(
        self, procedure_id: UUID, tenant_id: UUID
    ) -> _ExecutionRecord | None: ...

    async def get_user_preference(
        self, user_id: UUID, procedure_id: UUID, tenant_id: UUID
    ) -> dict[str, Any] | None: ...  # TODO(TYPE): replace Any with concrete type


from src.core.agents.capabilities.schemas import (
    ConfidenceScorerInput,
    ConfidenceScorerOutput,
    ScoredProcedure,
)

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Multi-signal scoring engine for procedure matching
    Combines 5 independent signals with weighted averaging
    """

    # Weight distribution (must sum to 1.0)
    WEIGHTS = {
        "tag": 0.35,
        "semantic": 0.25,
        "history": 0.20,
        "recency": 0.10,
        "user_override": 0.10,
    }

    # Ambiguity threshold: if top 2 candidates differ by less than this, mark as ambiguous
    AMBIGUITY_THRESHOLD = 0.10

    def __init__(
        self,
        repository: _Repository | None = None,
        embedding_service: _EmbeddingService | None = None,
    ) -> None:
        """
        Initialize ConfidenceScorer

        Args:
            repository: ProcedureExecutionRepository for history lookups
            embedding_service: EmbeddingService for semantic scoring (optional)
        """
        self._repository = repository
        self._embedding_service = embedding_service

    async def score(self, input_data: ConfidenceScorerInput) -> ConfidenceScorerOutput:
        """
        Score all candidate procedures against the user intent

        Args:
            input_data: ConfidenceScorerInput with intent and candidates

        Returns:
            ConfidenceScorerOutput with scored procedures, top match, and ambiguous flags
        """
        try:
            scored_procedures: list[ScoredProcedure] = []

            # Score each candidate procedure
            for candidate in input_data.candidate_procedures:
                procedure_id = UUID(cast(str, candidate["id"]))

                # Calculate individual signal scores
                try:
                    tag_score = await self._tag_score(
                        intent=input_data.user_intent,
                        intent_tags=cast(list[str], candidate.get("intent_tags", [])),
                    )
                except Exception as e:
                    logger.warning(f"Tag scoring failed for {procedure_id}: {e}")
                    tag_score = 0.0

                try:
                    semantic_score = await self._semantic_score(
                        intent=input_data.user_intent,
                        procedure_name=cast(str, candidate.get("name", "")),
                        category=cast(str, candidate.get("category", "")),
                    )
                except Exception as e:
                    logger.warning(f"Semantic scoring failed for {procedure_id}: {e}")
                    semantic_score = 0.0

                try:
                    history_score = await self._history_score(
                        user_id=input_data.user_id,
                        procedure_id=procedure_id,
                        tenant_id=input_data.tenant_id,
                    )
                except Exception as e:
                    logger.warning(f"History scoring failed for {procedure_id}: {e}")
                    history_score = 0.5

                try:
                    recency_score = await self._recency_score(
                        procedure_id=procedure_id, tenant_id=input_data.tenant_id
                    )
                except Exception as e:
                    logger.warning(f"Recency scoring failed for {procedure_id}: {e}")
                    recency_score = 0.5

                try:
                    user_override_score = await self._user_override_score(
                        user_id=input_data.user_id,
                        procedure_id=procedure_id,
                        tenant_id=input_data.tenant_id,
                    )
                except Exception as e:
                    logger.warning(f"User override scoring failed for {procedure_id}: {e}")
                    user_override_score = 0.5

                # Calculate weighted confidence score
                confidence_score = (
                    (tag_score * self.WEIGHTS["tag"])
                    + (semantic_score * self.WEIGHTS["semantic"])
                    + (history_score * self.WEIGHTS["history"])
                    + (recency_score * self.WEIGHTS["recency"])
                    + (user_override_score * self.WEIGHTS["user_override"])
                )

                # Ensure score stays in valid range
                confidence_score = max(0.0, min(1.0, confidence_score))

                scored = ScoredProcedure(
                    procedure_id=procedure_id,
                    procedure_name=cast(str, candidate.get("name", "")),
                    domain_pack_id=UUID(
                        cast(
                            str,
                            candidate.get("domain_pack_id", "00000000-0000-0000-0000-000000000000"),
                        )
                    ),
                    confidence_score=confidence_score,
                    tag_score=tag_score,
                    semantic_score=semantic_score,
                    history_score=history_score,
                    recency_score=recency_score,
                    user_override_score=user_override_score,
                    is_ambiguous=False,  # Will be set after sorting
                    intent_match_reason=None,
                )

                scored_procedures.append(scored)

            # Sort by confidence score (descending)
            scored_procedures.sort(key=lambda x: x.confidence_score, reverse=True)

            # Detect ambiguous matches
            ambiguous_matches: list[ScoredProcedure] = []
            if len(scored_procedures) >= 2:
                top_score = scored_procedures[0].confidence_score
                second_score = scored_procedures[1].confidence_score

                if (top_score - second_score) < self.AMBIGUITY_THRESHOLD:
                    scored_procedures[0].is_ambiguous = True
                    # Collect all procedures within ambiguity threshold
                    for proc in scored_procedures:
                        if abs(proc.confidence_score - top_score) < self.AMBIGUITY_THRESHOLD:
                            ambiguous_matches.append(proc)

            # Return result
            return ConfidenceScorerOutput(
                scored_procedures=scored_procedures,
                top_match=scored_procedures[0] if scored_procedures else None,
                ambiguous_matches=ambiguous_matches,
            )

        except Exception as e:
            logger.error(f"Error in ConfidenceScorer.score(): {e}")
            raise

    # ========================================================================
    # SIGNAL SCORING METHODS (Sub-methods)
    # ========================================================================

    async def _tag_score(self, intent: str, intent_tags: list[str]) -> float:
        """
        Score based on direct intent tag matching

        Heuristic: If procedure's tags overlap with intent keywords, score higher
        Returns: 0.0 - 1.0
        """
        if not intent_tags:
            return 0.0

        try:
            # Simple keyword matching: count overlapping words
            intent_keywords = set(intent.lower().split())
            tag_set = {tag.lower() for tag in intent_tags}

            overlap = intent_keywords & tag_set
            match_ratio = len(overlap) / len(tag_set) if tag_set else 0.0

            return min(1.0, match_ratio)

        except Exception as e:
            logger.warning(f"Error in _tag_score: {e}")
            return 0.0

    async def _semantic_score(self, intent: str, procedure_name: str, category: str) -> float:
        """
        Score based on semantic similarity (vector embeddings)

        If embedding service unavailable, return 0.0 (fail-safe)
        Returns: 0.0 - 1.0
        """
        try:
            if not self._embedding_service:
                # No embedding service available - safe default
                return 0.0

            # Get embeddings and compute similarity
            intent_embedding = await self._embedding_service.embed_text(intent)
            procedure_embedding = await self._embedding_service.embed_text(
                f"{procedure_name} {category}"
            )

            # Compute cosine similarity
            similarity = self._cosine_similarity(intent_embedding, procedure_embedding)
            return max(0.0, min(1.0, similarity))

        except Exception as e:
            logger.warning(f"Error in _semantic_score: {e}")
            # Fail-safe: return 0.0 instead of crashing
            return 0.0

    async def _history_score(self, user_id: UUID, procedure_id: UUID, tenant_id: UUID) -> float:
        """
        Score based on user's historical execution of this procedure

        Cold start (no history): return 0.5 (neutral) instead of 0.0
        Returns: 0.0 - 1.0
        """
        try:
            if not self._repository:
                # No repository - can't check history, return neutral
                return 0.5

            # Get execution history for this procedure by this user
            history = await self._repository.get_execution_history(
                user_id=user_id, procedure_id=procedure_id, tenant_id=tenant_id
            )

            if not history:
                # Cold start: user has never executed this procedure - neutral score
                return 0.5

            # Score based on success rate and frequency
            successful = len([h for h in history if h.get("status") == "completed"])
            total = len(history)
            success_rate = successful / total if total > 0 else 0.0

            # Boost by frequency: cap at 1.0
            frequency_boost = min(0.3, total / 100)  # Max 0.3 boost
            score = success_rate + frequency_boost

            return min(1.0, score)

        except Exception as e:
            logger.warning(f"Error in _history_score: {e}")
            # Cold start on error: return neutral 0.5
            return 0.5

    async def _recency_score(self, procedure_id: UUID, tenant_id: UUID) -> float:
        """
        Score based on how recently this procedure was executed (by any user)

        Recent execution = higher score (indicates active procedure)
        Returns: 0.0 - 1.0
        """
        try:
            if not self._repository:
                return 0.5

            # Get last execution time for this procedure
            last_execution = await self._repository.get_last_execution(
                procedure_id=procedure_id, tenant_id=tenant_id
            )

            if not last_execution:
                # Never executed - neutral score
                return 0.5

            # Score based on days since execution
            days_ago = (datetime.now(timezone.utc) - last_execution.created_at).days

            # Decay function: fresh executions score high, old ones lower
            if days_ago <= 7:
                return 1.0
            elif days_ago <= 30:
                return 0.8
            elif days_ago <= 90:
                return 0.6
            else:
                return 0.3

        except Exception as e:
            logger.warning(f"Error in _recency_score: {e}")
            return 0.5

    async def _user_override_score(
        self, user_id: UUID, procedure_id: UUID, tenant_id: UUID
    ) -> float:
        """
        Score based on explicit user preference/feedback

        Users can mark procedures as favorites, frequently used, etc.
        Returns: 0.0 - 1.0
        """
        try:
            if not self._repository:
                return 0.5

            # Check if user has marked this procedure as favorite or preferred
            preference = await self._repository.get_user_preference(
                user_id=user_id, procedure_id=procedure_id, tenant_id=tenant_id
            )

            if not preference:
                # No explicit feedback - neutral score
                return 0.5

            # Return preference score
            return cast(float, preference.get("score", 0.5))

        except Exception as e:
            logger.warning(f"Error in _user_override_score: {e}")
            return 0.5

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """
        Compute cosine similarity between two vectors

        Returns: 0.0 - 1.0
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product: float = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1: float = sum(a * a for a in vec1) ** 0.5
        magnitude2: float = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        similarity: float = dot_product / (magnitude1 * magnitude2)
        return similarity
