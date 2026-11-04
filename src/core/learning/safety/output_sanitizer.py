"""
OutputSanitizer -- strips PII and destructive patterns from LLM suggestions.

Security requirements (ADR-026 S.2.4):
- Unicode-normalised pattern matching (NFD + combining marks + homoglyphs)
  to prevent bypass via lookalike characters.
- Credential leak prevention: URLs with embedded credentials are redacted;
  only the violation COUNT is logged, never the URL content.
- None-safety and length cap (50 000 chars) against DoS via large payloads.
- Returns (cleaned_text, violations) so callers can emit Prometheus counters.
"""

import re
import unicodedata
from typing import Any

from loguru import logger

# Maximum input length -- truncate silently before any processing.
MAX_TEXT_LEN = 50_000

# -- Homoglyph map (Cyrillic / Greek lookalikes -> ASCII) ----------------------
# Extend as new bypass techniques are discovered.
_HOMOGLYPH_MAP = str.maketrans({
    # Cyrillic lookalikes -> ASCII (homoglyph bypass prevention, ADR-026 S.2.4)
    0x0435: "e",  # e (cyrillic small ie)
    0x0430: "a",  # a (cyrillic small a)
    0x043E: "o",  # o (cyrillic small o)
    0x0440: "p",  # r (cyrillic small er)
    0x0441: "c",  # s (cyrillic small es)
    0x0443: "y",  # u (cyrillic small u)
    0x0445: "x",  # kh (cyrillic small ha)
    0x0415: "E",  # E (cyrillic capital ie)
    0x0410: "A",  # A (cyrillic capital a)
    0x0412: "B",  # V (cyrillic capital ve)
    0x0421: "C",  # S (cyrillic capital es)
    0x041C: "M",  # M (cyrillic capital em)
    0x041D: "H",  # N (cyrillic capital en)
    0x041A: "K",  # K (cyrillic capital ka)
    0x041E: "O",  # O (cyrillic capital o)
    0x0420: "P",  # R (cyrillic capital er)
    0x0422: "T",  # T (cyrillic capital te)
    0x0425: "X",  # Kh (cyrillic capital ha)
    # Greek lookalikes -> ASCII
    0x03B1: "a",  # alpha
    0x03B2: "b",  # beta
    0x03B3: "g",  # gamma
    0x03B4: "d",  # delta
    0x03B5: "e",  # epsilon
    0x03B6: "z",  # zeta
    0x03B7: "h",  # eta
    0x03B8: "t",  # theta
    0x03B9: "i",  # iota
    0x03BA: "k",  # kappa
    0x03BB: "l",  # lambda
    0x03BC: "m",  # mu
    0x03BD: "n",  # nu
    0x03BE: "x",  # xi
    0x03BF: "o",  # omicron
    0x03C0: "p",  # pi
    0x03C1: "r",  # rho
    0x03C3: "s",  # sigma
    0x03C4: "t",  # tau
    0x03C5: "u",  # upsilon
    0x03C6: "f",  # phi
    0x03C7: "x",  # chi
    0x03C8: "p",  # psi
    0x03C9: "o",  # omega
})


def _normalise(text: str) -> str:
    """NFD decompose, strip combining marks, apply homoglyph map."""
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return stripped.translate(_HOMOGLYPH_MAP)


# -- Compiled patterns ---------------------------------------------------------

# URLs that embed credentials: https://user:pass@host/...
_URL_WITH_CREDENTIALS = re.compile(
    r"https?://[^@\s/]+:[^@\s/]+@[^\s]+",
    re.IGNORECASE,
)

# Generic API-key patterns (sk-..., Bearer ..., token ..., api_key=...)
_API_KEY_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9\-_]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-_\.]{20,}\b", re.IGNORECASE),
    re.compile(r"\bapi[_\-]?key\s*[=:]\s*[A-Za-z0-9\-_\.]{16,}\b", re.IGNORECASE),
    re.compile(r"\btoken\s*[=:]\s*[A-Za-z0-9\-_\.]{16,}\b", re.IGNORECASE),
]

# Dutch/international phone numbers
_PHONE = re.compile(r"(?<!\d)(\+?31|0)[1-9]\d[\s\-\.]?\d{3}[\s\-\.]?\d{4}(?!\d)")

# Email addresses
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Credit card numbers (4 groups of 4 digits, optionally separated)
_CREDIT_CARD = re.compile(r"\b(?:\d[ \-]?){13,16}\b")

# Dutch BSN -- requires explicit context keyword to avoid false positives on
# arbitrary 9-digit numbers (e.g. phone extensions, order IDs).
_BSN = re.compile(
    r"(?:bsn|burgerservicenummer|sofinummer|sofi)\s*[:\-]?\s*\b\d{9}\b",
    re.IGNORECASE,
)

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("url_with_credentials", _URL_WITH_CREDENTIALS),
    ("email", _EMAIL),
    ("phone", _PHONE),
    ("credit_card", _CREDIT_CARD),
    ("bsn", _BSN),
]


class OutputSanitizer:
    """
    Strips PII and sensitive patterns from LLM-generated suggestion text.

    Usage:
        cleaned, violations = OutputSanitizer.clean(suggestion)
        for v in violations:
            record_sanitizer_violation(tenant_id, v)
    """

    @staticmethod
    def clean(text: Any) -> tuple[str, list[str]]:  # TODO(TYPE): replace Any with concrete type
        """
        Sanitise *text*, returning the cleaned version and a list of
        violation-type strings.

        Args:
            text: Raw LLM output.  None or empty string -> returned as-is.

        Returns:
            (cleaned_text, violations)  where violations is a list of strings
            like ["email", "url_with_credentials"].
        """
        if text is None:
            return "", []
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return text, []

        # Length cap -- prevents DoS via enormous payloads
        if len(text) > MAX_TEXT_LEN:
            logger.warning(
                "output_sanitizer_truncated",
                original_len=len(text),
                cap=MAX_TEXT_LEN,
            )
            text = text[:MAX_TEXT_LEN]

        violation_set: set[str] = set()
        normalised = _normalise(text)

        # -- API key patterns (checked on normalised, redacted from original) --
        for pattern in _API_KEY_PATTERNS:
            if pattern.search(normalised):
                violation_set.add("api_key")
                text = pattern.sub("[REDACTED_KEY]", text)
                normalised = pattern.sub("[REDACTED_KEY]", normalised)

        # -- URL with embedded credentials -------------------------------------
        url_matches = list(_URL_WITH_CREDENTIALS.finditer(normalised))
        if url_matches:
            # Log only the count -- never the URL content (credential leak risk)
            logger.warning(
                "output_sanitizer_url_credentials_found",
                count=len(url_matches),
            )
            violation_set.add("url_with_credentials")
            text = _URL_WITH_CREDENTIALS.sub("[REDACTED_URL]", text)
            normalised = _URL_WITH_CREDENTIALS.sub("[REDACTED_URL]", normalised)

        # -- PII patterns ------------------------------------------------------
        for violation_type, pattern in _PATTERNS:
            if violation_type == "url_with_credentials":
                continue  # already handled above
            if pattern.search(normalised):
                violation_set.add(violation_type)
                text = pattern.sub(f"[REDACTED_{violation_type.upper()}]", text)
                normalised = pattern.sub(f"[REDACTED_{violation_type.upper()}]", normalised)

        violations = sorted(violation_set)

        if violations:
            logger.info(
                "output_sanitizer_violations",
                violation_types=violations,
                violation_count=len(violations),
            )

        return text, violations
