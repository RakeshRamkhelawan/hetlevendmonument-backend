"""
Hindi bias-lexicons for EthicsOfficer.

Terms are stored as Unicode escapes to ensure ASCII compatibility on Windows.
Source: Curated for demographic generalizations and exclusionary language.
"""

from __future__ import annotations

LEXICON_VERSION_HI = "1.0.0"

# Level 1 (HIGH): explicit demographic assumptions.
# Escaped Devanagari strings.
HIGH_BIAS_TERMS_HI: frozenset[str] = frozenset(
    {
        "\u0938\u092d\u0940 \u092a\u0941\u0930\u0941\u0937",           # All men
        "\u0938\u092d\u0940 \u092e\u0939\u093f\u0932\u093e\u090f\u0901",     # All women
        "\u092e\u0939\u093f\u0932\u093e\u090f\u0901 \u092c\u0947\u0939\u0924\u0930 \u0939\u0948\u0902", # Women are better at
        "\u092a\u0941\u0930\u0941\u0937 \u092c\u0947\u0939\u0924\u0930 \u0939\u0948\u0902", # Men are better at
        "\u0928\u0940\u091a\u0940 \u091c\u093e\u0924\u093f",           # Lower caste
        "\u0905\u091b\u0942\u0924",                                   # Untouchable
        "\u0935\u093f\u0926\u0947\u0936\u0940 \u0932\u094b\u0917",     # Foreigners (outsiders)
        "\u092a\u0936\u094d\u091a\u093f\u092e\u0940 \u0932\u094b\u0917",     # Westerners
        "\u0915\u092e\u091c\u093c\u094b\u0930 \u0935\u0930\u094d\u0917",     # Weak class
    }
)

# Level 2 (MEDIUM): vague generalizations.
MEDIUM_BIAS_TERMS_HI: frozenset[str] = frozenset(
    {
        "\u0939\u092e\u0947\u0936\u093e",     # Always
        "\u0915\u092d\u0940 \u0928\u0939\u0940\u0902", # Never
        "\u0906\u092e\u0924\u094c\u0930 \u092a\u0930", # Generally
        "\u0938\u092c \u0915\u094b \u092a\u0924\u093e \u0939\u0948", # Everyone knows
        "\u092c\u093f\u0928\u093e \u0905\u092a\u0935\u093e\u0926",     # Without exception
    }
)
