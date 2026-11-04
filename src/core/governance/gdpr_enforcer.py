"""
GDPR Enforcer - Slice 6

Data minimization and classification enforcement for GDPR compliance.
Ensures only necessary data is collected and classified data is protected.

Sprint 4 - S4.6: GDPR compliance checks
"""

import re
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from stdnum import iban as _iban
from stdnum import luhn as _luhn
from stdnum.nl import bsn as _bsn

_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[\w.-]+@[\w.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b"),
    # AUDIT-002: candidate regex only -- a plain 9-digit/IBAN-shaped match is not
    # sufficient evidence of PII on its own (too many false positives, e.g. order
    # IDs). Each candidate is additionally checksum-validated via _CHECKSUM_VALIDATORS
    # below before it counts as detected.
    "bsn": re.compile(r"\b\d{9}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
}

def _luhn_geldig(kandidaat: str) -> bool:
    """Luhn over de CIJFERS van de kandidaat.

    `stdnum.luhn.is_valid` strookt niet met scheidingstekens (gemeten 2026-09-22:
    `"4111 1111 1111 1111"` geeft False, `"4111111111111111"` True), terwijl het patroon
    hierboven streepjes en spaties wel toelaat. De ondergrens van 13 cijfers is de kortste
    kaartlengte die bestaat; korter is per definitie geen kaartnummer.
    """
    cijfers = re.sub(r"\D", "", kandidaat)
    return len(cijfers) >= 13 and _luhn.is_valid(cijfers)


# Checksum validators for candidate-only patterns above. A regex match alone is
# never sufficient for these types -- the checksum (BSN elfproef, IBAN mod-97,
# credit card Luhn) must also pass, or the match is a false positive (e.g. a random
# 9-digit ID).
#
# `credit_card` ONTBRAK hier tot 2026-09-22, en dat was een defect volgens het contract dat
# deze module zelf twaalf regels hierboven opschrijft. Het patroon is elke reeks van 13-20
# cijfers, dus zonder validator werd ALLES met genoeg cijfers een creditcard. Gemeten voor de
# fix:
#
#     "1234-5678-9012-3456"      -> ['credit_card']   verzonnen, geen geldige Luhn
#     "20260922145501"           -> ['credit_card']   een buildnummer
#     "1726937461123"            -> ['credit_card']   een tijdstempel in milliseconden
#     "9780306406157"            -> ['credit_card']   een ISBN
#
# Dat bleef jarenlang onschadelijk omdat niemand op de uitkomst HANDELDE; de PrivacyOfficer
# maskeerde er wat te veel mee en dat valt niet op. Op het moment dat de InputGuard erop ging
# blokkeren, werd elk van die vier een geweigerd chatbericht -- gevonden in Gate 2 op
# 2026-09-22. Zie `tests/unit/governance/test_gdpr_enforcer.py` voor de vier negatieve
# gevallen; de oude test legde met `1234-5678-9012-3456` juist het defect vast.
_CHECKSUM_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "bsn": _bsn.is_valid,
    "iban": _iban.is_valid,
    "credit_card": _luhn_geldig,
}

_pii_token_map: ContextVar[dict[str, str] | None] = ContextVar("_pii_token_map", default=None)


class MinimizationError(Exception):
    """Raised when data minimization principle is violated."""

    pass


class ClassificationError(Exception):
    """Raised when data classification requirements are violated."""

    pass


class GDPREnforcer:
    """Enforces GDPR data minimization and classification rules."""

    # Trust level hierarchy: low < medium < high
    TRUST_LEVELS = {"low": 1, "medium": 2, "high": 3}

    # Classification requirements (minimum trust level)
    CLASSIFICATION_REQUIREMENTS = {
        "public": 1,  # Any trust level
        "confidential": 2,  # Medium or higher
        "pii": 3,  # High trust only
        "sensitive": 3,  # High trust only
    }

    def __init__(self) -> None:
        """Initialize GDPR enforcer."""
        self.violation_log: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    def enforce_minimization(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Enforce data minimization principle.

        Args:
            payload: Data payload to validate
            schema: Schema with required_fields and optional_fields

        Returns:
            True if compliant

        Raises:
            MinimizationError: If payload violates minimization
        """
        required_fields = set(schema.get("required_fields", []))
        optional_fields = set(schema.get("optional_fields", []))
        allowed_fields = required_fields | optional_fields
        payload_fields = set(payload.keys())

        # Check for missing required fields
        missing_fields = required_fields - payload_fields
        if missing_fields:
            violation = {
                "type": "minimization",
                "missing_fields": list(missing_fields),
                "payload": payload,
            }
            self.violation_log.append(violation)
            raise MinimizationError(f"Missing required fields: {', '.join(missing_fields)}")

        # Check for excessive fields (not in schema)
        excessive_fields = payload_fields - allowed_fields
        if excessive_fields:
            violation = {
                "type": "minimization",
                "excessive_fields": list(excessive_fields),
                "payload": payload,
            }
            self.violation_log.append(violation)
            raise MinimizationError(
                f"Unnecessary fields detected: {', '.join(excessive_fields)}. "
                f"Only {', '.join(allowed_fields)} are allowed."
            )

        return True

    def enforce_classification(self, data_tags: dict[str, str], tool_trust_level: str) -> bool:
        """Enforce data classification access control.

        Args:
            data_tags: Data metadata with 'classification' key
            tool_trust_level: Trust level of accessing tool ('low', 'medium', 'high')

        Returns:
            True if tool has sufficient trust

        Raises:
            ClassificationError: If tool trust insufficient for data classification
        """
        classification = data_tags.get("classification", "public")

        # Get minimum required trust level for this classification
        required_trust_level = self.CLASSIFICATION_REQUIREMENTS.get(classification, 1)

        # Get numeric trust level of tool
        tool_trust_numeric = self.TRUST_LEVELS.get(tool_trust_level, 1)

        if tool_trust_numeric < required_trust_level:
            raise ClassificationError(
                f"Tool trust level '{tool_trust_level}' insufficient for "
                f"data classification '{classification}'. "
                f"Minimum trust level required: "
                f"{self._get_trust_name(required_trust_level)}"
            )

        return True

    def detect_pii(
        self, data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Detect common PII patterns in payload values.

        Returns a list of detected PII type names (e.g. 'email', 'phone',
        'ssn', 'credit_card').  Empty list means no obvious PII found.
        """
        detected: list[str] = []
        values: list[str] = []

        def _collect(v: Any) -> None:  # TODO(TYPE): replace Any with concrete type
            if isinstance(v, dict):
                for item in v.values():
                    _collect(item)
            elif isinstance(v, list):
                for item in v:
                    _collect(item)
            elif isinstance(v, str):
                values.append(v)

        _collect(data)

        for value in values:
            for pii_type, pattern in _PII_PATTERNS.items():
                if pii_type in detected:
                    continue
                validator = _CHECKSUM_VALIDATORS.get(pii_type)
                if validator is None:
                    if pattern.search(value):
                        detected.append(pii_type)
                elif any(validator(m.group(0)) for m in pattern.finditer(value)):
                    detected.append(pii_type)
        return detected

    def redact_pii(self, text: str) -> tuple[str, dict[str, str]]:
        """Mask ALL PII occurrences in text and return (masked_text, token_map).

        token_map maps placeholders back to original values so the caller
        can detokenize the LLM response via detokenize().
        """
        token_map: dict[str, str] = {}
        counter = [0]

        def _make_replacer(
            validator: Callable[[str], bool] | None,
        ) -> Callable[[re.Match[str]], str]:
            def _replacer(match: re.Match[str]) -> str:
                # For checksum-validated types (bsn/iban), leave non-matching
                # candidates untouched -- only a passing checksum is real PII.
                if validator is not None and not validator(match.group(0)):
                    return match.group(0)
                placeholder = f"[TOKEN_PII_{counter[0]}]"
                token_map[placeholder] = match.group(0)
                counter[0] += 1
                return placeholder

            return _replacer

        detected = self.detect_pii({"text": text})
        result = text
        for pii_type in detected:
            pattern = _PII_PATTERNS.get(pii_type)
            if pattern is not None:
                result = pattern.sub(_make_replacer(_CHECKSUM_VALIDATORS.get(pii_type)), result)
        _pii_token_map.set(token_map)
        return result, token_map

    def detokenize(self, text: str, token_map: dict[str, str]) -> str:
        """Restore original PII values from a token_map into masked text."""
        result = text
        for placeholder, original in token_map.items():
            result = result.replace(placeholder, original)
        return result

    def _get_trust_name(self, level: int) -> str:
        """Get trust level name from numeric value."""
        for name, value in self.TRUST_LEVELS.items():
            if value == level:
                return name
        return "unknown"
