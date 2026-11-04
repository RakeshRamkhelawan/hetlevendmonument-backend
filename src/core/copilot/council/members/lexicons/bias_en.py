"""English bias-lexicons.

Source: curated from AI HLEG Ethics Guidelines + Anthropic Constitutional AI
discouraged language + internal reviews. Versioned upon every change.
"""

from __future__ import annotations

LEXICON_VERSION_EN = "1.0.0"

# Level 1 (HIGH): explicit demographic assumptions.
HIGH_BIAS_TERMS_EN: frozenset[str] = frozenset(
    {
        "all men",
        "all women",
        "typical for men",
        "typical for women",
        "natural for",
        "everyone knows",
        "logically they have",
        "those people",
        "typical western",
        "men are better at",
        "women are better at",
        "normal people",
        "abnormal",
        "minorities",
        "inferior",
        "highly educated is smarter",
        "old people don't understand",
        "young people are lazy",
        "obviously",
        "white people",
    }
)

# Level 2 (MEDIUM): vague generalizations.
MEDIUM_BIAS_TERMS_EN: frozenset[str] = frozenset(
    {
        "mostly",
        "always",
        "never",
        "usually",
        "most of the",
        "almost everyone",
        "not a single",
        "self-evident",
        "any reasonable person",
        "it is commonly known",
        "without exception",
        "everyone does",
        "constantly",
        "undoubtedly",
        "generally",
    }
)
