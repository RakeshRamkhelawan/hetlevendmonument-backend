"""GoalAlignmentValidator - Fase 3.2

Runtime validation of goal alignment for agent actions.
Uses keyword matching with Dutch stopword removal.
"""

import re
from typing import Any, List, Optional, Set

from pydantic import BaseModel, Field

from src.core.company.context import AgentExecutionContext, GoalChain

# Dutch stopwords for tokenization
DUTCH_STOPWORDS: set[str] = {
    "de",
    "het",
    "een",
    "van",
    "in",
    "op",
    "aan",
    "met",
    "voor",
    "achter",
    "door",
    "over",
    "onder",
    "naast",
    "tussen",
    "bij",
    "tot",
    "uit",
    "naar",
    "om",
    "te",
    "dat",
    "die",
    "dit",
    "deze",
    "zo",
    "dan",
    "als",
    "maar",
    "want",
    "of",
    "en",
    "is",
    "zijn",
    "was",
    "waren",
    "wordt",
    "worden",
    "werd",
    "werden",
    "heb",
    "heeft",
    "hebben",
    "had",
    "hadden",
    "kan",
    "kunnen",
    "kon",
    "konden",
    "zal",
    "zullen",
    "zou",
    "zouden",
    "moet",
    "moeten",
    "moest",
    "moesten",
    "mag",
    "mogen",
    "mocht",
    "mochten",
    "ik",
    "jij",
    "je",
    "hij",
    "zij",
    "ze",
    "wij",
    "we",
    "jullie",
    "hen",
    "hun",
    "mijn",
    "jouw",
    "zijn",
    "haar",
    "ons",
    "jullie",
    "hun",
    "wie",
    "wat",
    "welke",
    "welk",
    "hoeveel",
    "waar",
    "wanneer",
    "hoe",
    "waarom",
}

# English stopwords for international deployments
ENGLISH_STOPWORDS: set[str] = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "used",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "and",
    "but",
    "if",
    "or",
    "because",
    "until",
    "while",
    "this",
    "that",
    "these",
    "those",
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "you",
    "your",
    "he",
    "him",
    "his",
    "she",
    "her",
    "it",
    "its",
    "they",
    "them",
    "their",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "these",
    "those",
}


class GoalAlignmentResult(BaseModel):
    """Result of goal alignment validation."""

    status: str = Field(..., description="ALIGNED, DRIFT_WARNING, or MISALIGNED")
    score: float = Field(..., ge=0.0, le=1.0, description="Alignment score 0.0-1.0")
    reason: str = Field(..., description="Human-readable explanation (Dutch)")


class GoalAlignmentValidator:
    """Validator for checking if agent actions align with goals.

    Uses keyword matching with Jaccard similarity.
    Supports Dutch (default) and English languages.
    """

    # Score thresholds
    ALIGNED_THRESHOLD = 0.6
    DRIFT_THRESHOLD = 0.3

    def __init__(self, language: str = "nl") -> None:
        """Initialize validator.

        Args:
            language: "nl" for Dutch (default), "en" for English
        """
        self.language = language
        self.stopwords = DUTCH_STOPWORDS if language == "nl" else ENGLISH_STOPWORDS

    async def validate(
        self, proposed_action: str, context: AgentExecutionContext
    ) -> GoalAlignmentResult:
        """Validate if proposed action aligns with goal chain.

        Args:
            proposed_action: The action to validate
            context: Execution context with goal chain

        Returns:
            Alignment result with status, score, and reason
        """
        # Check if goal chain is complete
        if not context.goal_chain or not context.goal_chain.is_complete():
            return GoalAlignmentResult(
                status="DRIFT_WARNING", score=0.5, reason=self._get_message("incomplete_chain")
            )

        # Empty action check
        if not proposed_action or not proposed_action.strip():
            return GoalAlignmentResult(
                status="DRIFT_WARNING", score=0.5, reason=self._get_message("empty_action")
            )

        # Compute alignment score
        score = await self._compute_alignment(proposed_action, context.goal_chain)

        # Determine status based on score
        if score >= self.ALIGNED_THRESHOLD:
            return GoalAlignmentResult(
                status="ALIGNED", score=score, reason=self._get_message("aligned")
            )
        elif score >= self.DRIFT_THRESHOLD:
            return GoalAlignmentResult(
                status="DRIFT_WARNING", score=score, reason=self._get_message("drift")
            )
        else:
            return GoalAlignmentResult(
                status="MISALIGNED", score=score, reason=self._get_message("misaligned")
            )

    def _get_message(self, key: str) -> str:
        """Get human-readable message in configured language."""
        messages = {
            "nl": {
                "incomplete_chain": "Doelketen is incompleet -- actie wordt niet geblokkeerd maar vereist monitoring",
                "empty_action": "Lege actie -- geen doel om mee te vergelijken",
                "aligned": "Actie is goed afgestemd met organisatiedoelen",
                "drift": "Actie wijkt af van hoofddoelen -- controleer of dit bewust is",
                "misaligned": "Actie is niet in lijn met organisatiedoelen -- overweeg afwijzing",
            },
            "en": {
                "incomplete_chain": "Goal chain incomplete -- action not blocked but requires monitoring",
                "empty_action": "Empty action -- no goal to compare against",
                "aligned": "Action aligns well with organizational goals",
                "drift": "Action diverges from main goals -- verify if intentional",
                "misaligned": "Action not aligned with organizational goals -- consider rejection",
            },
        }
        return messages.get(self.language, messages["en"]).get(key, key)

    async def _compute_alignment(self, action: str, goal_chain: GoalChain) -> float:
        """Compute alignment score using weighted Jaccard similarity.

        Weights:
        - Task title: 0.5
        - Project title: 0.3
        - Strategic title: 0.15
        - Mission title: 0.05

        Args:
            action: The proposed action
            goal_chain: Chain of goals to compare against

        Returns:
            Alignment score 0.0-1.0
        """
        # Tokenize action
        action_tokens = self._tokenize(action)

        if not action_tokens:
            return 0.5  # Neutral for empty tokens

        scores: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        weights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Compare with each level in goal chain (using correct field names)
        if goal_chain.task_goal_title:
            task_tokens = self._tokenize(goal_chain.task_goal_title)
            scores.append(self._jaccard_similarity(action_tokens, task_tokens))
            weights.append(0.5)

        if goal_chain.project_goal_title:
            project_tokens = self._tokenize(goal_chain.project_goal_title)
            scores.append(self._jaccard_similarity(action_tokens, project_tokens))
            weights.append(0.3)

        if goal_chain.strategic_goal_title:
            strategic_tokens = self._tokenize(goal_chain.strategic_goal_title)
            scores.append(self._jaccard_similarity(action_tokens, strategic_tokens))
            weights.append(0.15)

        if goal_chain.mission_title:
            mission_tokens = self._tokenize(goal_chain.mission_title)
            scores.append(self._jaccard_similarity(action_tokens, mission_tokens))
            weights.append(0.05)

        if not scores:
            return 0.5  # Neutral if no goals to compare

        # Weighted average
        total_weight = sum(weights)
        weighted_score = sum(s * w for s, w in zip(scores, weights)) / total_weight

        alignment_score: float = round(weighted_score, 3)
        return alignment_score

    def _tokenize(self, text: str) -> set[str]:
        """Tokenize text with stopword removal.

        Args:
            text: Input text to tokenize

        Returns: Set[Any] of tokens (lowercase, no punctuation)  # TODO(TYPE): replace Any with concrete type
        """
        if not text:
            return set()

        # Convert to lowercase
        text = text.lower()

        # Remove punctuation and split
        # Keep only letters, numbers, and spaces
        text = re.sub(r"[^a-z0-9\s]", " ", text)

        # Split into words
        words = text.split()

        # Remove stopwords
        tokens = {w for w in words if w not in self.stopwords and len(w) > 2}

        return tokens

    def _jaccard_similarity(self, set1: set[str], set2: set[str]) -> float:
        """Calculate Jaccard similarity between two sets.

        Jaccard = |intersection| / |union|

        Args:
            set1: First set of tokens
            set2: Second set of tokens

        Returns:
            Similarity score 0.0-1.0
        """
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union
