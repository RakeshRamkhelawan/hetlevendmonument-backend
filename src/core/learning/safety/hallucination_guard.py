"""
HallucinationGuard -- lightweight heuristic filter for LLM suggestions.

Checks whether a suggestion makes ungrounded absolute claims that could
mislead developers.  This is intentionally conservative: false negatives
(letting a borderline suggestion through) are preferable to false positives
(blocking a genuinely helpful one).

Rules checked:
    1. Absolute-certainty language  ("always", "never", "100%", "guaranteed")
    2. Fabricated statistics         (unsourced percentages/numbers in claims)
    3. Tool/file references absent from context  (e.g. "open foo.ts" but
       no "foo.ts" in context)
    4. Empty or whitespace-only suggestions
"""

import re
from typing import Any

from loguru import logger

# -- Compiled patterns --------------------------------------------------------

_ABSOLUTE_CLAIMS = re.compile(
    r"\b(always|never|guaranteed|100%|certainly|definitely|impossible|"
    r"every single|without exception|no exception)\b",
    re.IGNORECASE,
)

# Bare percentage or "X times faster / X times slower" outside a known range
_FABRICATED_STATS = re.compile(
    r"\b(\d{2,3}%|\d+x\s+(?:faster|slower|better|worse|more|less)\b)",
    re.IGNORECASE,
)

# References to specific file names ("open foo.py", "in bar.ts") that are
# not present anywhere in the context dict.
_FILE_REFERENCE = re.compile(r"\b[\w\-]+\.(py|ts|tsx|js|jsx|yaml|yml|json|toml|md)\b")


class HallucinationGuard:
    """
    Check a suggestion for hallucination signals.

    Usage:
        is_safe, reason = HallucinationGuard.check(suggestion, context)
        if not is_safe:
            # reason can carry the matched text verbatim (e.g. a filename or a
            # digit run) -- log only the category, never reason itself. See
            # ADR-036 D2-002/OP-38, BE-AGT-055.
            logger.warning("twin_suggestion_flagged", category=(reason or "").split(":", 1)[0])
    """

    @staticmethod
    def check(suggestion: Any, context: dict[str, Any]) -> tuple[bool, str | None]:  # TODO(TYPE): replace Any with concrete type
        """
        Evaluate *suggestion* for hallucination risk.

        Args:
            suggestion: LLM-generated text.
            context:    Behaviour-context dict passed to the LLM (used to
                        ground file references).

        Returns:
            (True, None)         -- suggestion looks safe
            (False, reason_str)  -- flag raised, with human-readable reason
        """
        if not suggestion or not isinstance(suggestion, str) or not suggestion.strip():
            return False, "empty_suggestion"

        # -- Rule 1: absolute-certainty language --------------------------------
        abs_match = _ABSOLUTE_CLAIMS.search(suggestion)
        if abs_match:
            logger.info(
                "hallucination_guard_absolute_claim",
                matched=abs_match.group(0),
            )
            return False, f"absolute_claim:{abs_match.group(0).lower()}"

        # -- Rule 2: fabricated statistics --------------------------------------
        # ADR-036 D2-002/OP-38 (fix-sprint dag 6, correctie na blinde reviewronde 2): het
        # percentage-alternatief (`\d{2,3}%`) is begrensd tot 2-3 cijfers en dus PII-vrij, maar
        # de "Nx faster/slower/..."-alternatief (`\d+x ...`) heeft een ONBEGRENSDE cijferreeks
        # -- zelf nagemeten dat "0612345678x faster" matcht. Een aanvallergestuurde tekst kan zo
        # een telefoonnummer-achtige reeks laten loggen. Daarom niet loggen als los veld, zelfde
        # behandeling als Rule 3 hieronder.
        stat_match = _FABRICATED_STATS.search(suggestion)
        if stat_match:
            logger.info("hallucination_guard_fabricated_stat")
            return False, f"fabricated_stat:{stat_match.group(0)}"

        # -- Rule 3: file references not grounded in context -------------------
        # ADR-036 D2-002/OP-38 (fix-sprint dag 6, bijvangst): `fname` is een open match uit
        # vrije modeltekst, net als Rule 2's "Nx faster"-tak hierboven. Alleen Rule 1
        # (`_ABSOLUTE_CLAIMS`) matcht een echt gesloten, vaste woordenlijst zonder cijfer- of
        # vrije-tekstcomponent en kan dus geen persoonsgegeven zijn -- die tak blijft daarom wel
        # `matched=` loggen. Een bestandsnaam kan wel een persoonsnaam bevatten
        # (bv. "jan_jansen_salaris.pdf") -- niet loggen als los veld, alleen het FEIT dat de
        # regel triggerde. `reason` bevat de bestandsnaam nog wel (nodig voor de caller om te
        # rapporteren WAT niet klopte), maar de aanroeper (`SanityOfficer`) redigeert dat al
        # tot een categorie voordat het de hashketen ingaat (zie BE-AGT-054).
        context_text = " ".join(str(v) for v in context.values() if v)
        for file_match in _FILE_REFERENCE.finditer(suggestion):
            fname = file_match.group(0)
            if fname not in context_text:
                logger.info("hallucination_guard_ungrounded_file_ref")
                return False, f"ungrounded_file_ref:{fname}"

        return True, None
