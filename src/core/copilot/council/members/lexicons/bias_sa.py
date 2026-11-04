"""
Sanskrit bias-lexicons for EthicsOfficer.

Terms are stored as Unicode escapes to ensure ASCII compatibility.
Source: Classical generalizations and potentially biased demographic terms.
"""

from __future__ import annotations

LEXICON_VERSION_SA = "1.0.0"

# Level 1 (HIGH): explicit demographic assumptions.
# Escaped Devanagari strings for Sanskrit.
HIGH_BIAS_TERMS_SA: frozenset[str] = frozenset(
    {
        "\u0938\u0930\u094d\u0935\u0947 \u092a\u0941\u0930\u0941\u0937\u093e\u0903",     # All men
        "\u0938\u0930\u094d\u0935\u093e\u0903 \u0928\u093e\u0930\u094d\u092f\u0903",     # All women
        "\u0928\u093e\u0930\u094d\u092f\u0903 \u0905\u092c\u0932\u093e\u0903",           # Women are weak
        "\u092e\u094d\u0932\u0947\u091a\u094d\u091b",                                   # Mleccha (outsider/barbarian)
        "\u0939\u0940\u0928 \u091c\u093e\u0924\u093f",                                 # Lower caste
    }
)

# Level 2 (MEDIUM): vague generalizations.
MEDIUM_BIAS_TERMS_SA: frozenset[str] = frozenset(
    {
        "\u0938\u0930\u094d\u0935\u0926\u093e",     # Always
        "\u0915\u0926\u093e\u092a\u093f \u0928",     # Never
        "\u0938\u0930\u094d\u0935\u0935\u093f\u0926\u093f\u0924\u092e\u094d",           # Well known to all
    }
)
