"""
AI Model Router
Routes queries to the most cost-effective model based on complexity analysis.
"""

from enum import Enum


class QueryComplexity(Enum):
    """Complexity levels for queries"""

    SIMPLE = "simple"  # Fact retrieval, simple formatting
    MODERATE = "moderate"  # Summarization, basic reasoning
    COMPLEX = "complex"  # Multi-step reasoning, code generation, creative writing


class ModelTier(Enum):
    """Model tiers corresponding to complexity"""

    FAST = "fast"  # e.g., Gemini 1.5 Flash
    BALANCED = "balanced"  # e.g., Gemini 1.5 Pro
    POWERFUL = "powerful"  # e.g., Gemini Ultra / GPT-4


class AIRouter:
    """
    Routes queries to appropriate models based on complexity.
    """

    def __init__(self) -> None:
        # Keywords that suggest higher complexity
        self.complex_keywords = [
            "analyze",
            "design",
            "architect",
            "refactor",
            "debug",
            "explain why",
            "compare",
            "contrast",
            "synthesize",
            "generate code",
            "implement",
            "optimize",
        ]

        self.moderate_keywords = [
            "summarize",
            "explain",
            "describe",
            "list",
            "outline",
            "draft",
            "rewrite",
            "translate",
        ]

    def analyze_complexity(self, query: str) -> QueryComplexity:
        """
        Analyze the complexity of a query based on heuristics.

        Args:
            query: The input query string

        Returns:
            QueryComplexity enum value
        """
        if not query:
            return QueryComplexity.SIMPLE

        # 1. Length heuristic
        word_count = len(query.split())
        if word_count > 500:
            return QueryComplexity.COMPLEX
        if word_count > 100:
            return QueryComplexity.MODERATE

        # 2. Keyword heuristic
        query_lower = query.lower()

        for keyword in self.complex_keywords:
            if keyword in query_lower:
                return QueryComplexity.COMPLEX

        for keyword in self.moderate_keywords:
            if keyword in query_lower:
                return QueryComplexity.MODERATE

        # 3. Code detection heuristic
        if "```" in query or "def " in query or "class " in query:
            return QueryComplexity.COMPLEX

        return QueryComplexity.SIMPLE

    def route_to_model(self, complexity: QueryComplexity) -> str:
        """
        Select the appropriate model based on complexity.

        Args:
            complexity: The determined query complexity

        Returns:
            Model name string (mapped to LLMModel values)
        """
        # Map to Gemini models (since we are using Google provider primarily)
        if complexity == QueryComplexity.SIMPLE:
            return "gemini-1.5-flash"
        elif complexity == QueryComplexity.MODERATE:
            return "gemini-1.5-pro"
        else:
            return "gemini-1.5-pro"  # COMPLEX or unknown


# Global router instance
ai_router = AIRouter()
