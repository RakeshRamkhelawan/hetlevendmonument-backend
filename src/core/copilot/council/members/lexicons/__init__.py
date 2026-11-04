"""Bias-lexicons for EthicsOfficer.

Lexicons are frozen sets of terms that indicate potential bias. Two levels:
HIGH (explicit demographic assumptions) and MEDIUM (vague generalizations).
The lexicon is deliberately limited to prevent over-aggressive false positives.
"""

from src.core.copilot.council.members.lexicons.bias_en import (
    HIGH_BIAS_TERMS_EN,
    LEXICON_VERSION_EN,
    MEDIUM_BIAS_TERMS_EN,
)
from src.core.copilot.council.members.lexicons.bias_hi import (
    HIGH_BIAS_TERMS_HI,
    LEXICON_VERSION_HI,
    MEDIUM_BIAS_TERMS_HI,
)
from src.core.copilot.council.members.lexicons.bias_nl import (
    HIGH_BIAS_TERMS_NL,
    LEXICON_VERSION_NL,
    MEDIUM_BIAS_TERMS_NL,
)
from src.core.copilot.council.members.lexicons.bias_sa import (
    HIGH_BIAS_TERMS_SA,
    LEXICON_VERSION_SA,
    MEDIUM_BIAS_TERMS_SA,
)

__all__ = [
    "HIGH_BIAS_TERMS_NL",
    "MEDIUM_BIAS_TERMS_NL",
    "LEXICON_VERSION_NL",
    "HIGH_BIAS_TERMS_EN",
    "MEDIUM_BIAS_TERMS_EN",
    "LEXICON_VERSION_EN",
    "HIGH_BIAS_TERMS_HI",
    "MEDIUM_BIAS_TERMS_HI",
    "LEXICON_VERSION_HI",
    "HIGH_BIAS_TERMS_SA",
    "MEDIUM_BIAS_TERMS_SA",
    "LEXICON_VERSION_SA",
]
