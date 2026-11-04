"""Dutch bias-lexicons.

Source: curated from AI HLEG Ethics Guidelines + Anthropic Constitutional AI
discouraged language + internal reviews. Versioned upon every change.

ASCII-only for variables and comments; the lexicon-strings themselves
are Dutch and may contain non-ASCII (though currently all ASCII).
"""

from __future__ import annotations

LEXICON_VERSION_NL = "1.0.0"

# Level 1 (HIGH): explicit demographic assumptions.
# Triggers APPROVE_WITH_MODIFICATION on every match.
HIGH_BIAS_TERMS_NL: frozenset[str] = frozenset(
    {
        "alle mannen",
        "alle vrouwen",
        "typisch voor mannen",
        "typisch voor vrouwen",
        "natuurlijk voor",
        "iedereen weet",
        "vanzelfsprekend",
        "logischerwijs hebben",
        "allochtonen",
        "autochtonen",
        "die mensen",
        "typisch westers",
        "mannen zijn beter in",
        "vrouwen zijn beter in",
        "normale mensen",
        "abnormale",
        "de blanke",
        "minderheden",
        "minderwaardig",
        "hoger opgeleid is slimmer",
        "ouderen snappen",
        "jongeren zijn lui",
    }
)

# Level 2 (MEDIUM): vague generalizations.
# Triggers APPROVE_WITH_MODIFICATION only with >= 3 matches.
MEDIUM_BIAS_TERMS_NL: frozenset[str] = frozenset(
    {
        "meestal",
        "altijd",
        "nooit",
        "doorgaans",
        "de meeste",
        "vrijwel iedereen",
        "geen enkele",
        "ieder weldenkend mens",
        "het is algemeen bekend",
        "zonder uitzondering",
        "bijna iedereen",
        "iedereen doet",
        "steeds",
        "ongetwijfeld",
    }
)
