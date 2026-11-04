"""Output Validation -- Filters PII, hallucinations, and unsafe content from LLM responses."""

import logging
import re
from re import Pattern

logger = logging.getLogger(__name__)


class OutputValidator:
    """Validates LLM output for PII, confidentiality violations, and unsafe content.

    Masks or removes sensitive data before returning response to user.
    """

    # PII detection patterns
    PII_PATTERNS: dict[str, Pattern[str]] = {
        # MEDIUM-1: Allow spacing/dash variations for encoding evasion protection
        "ssn": re.compile(r"\b\d{3}[\s\-]?\d{2}[\s\-]?\d{4}\b"),  # XXX-XX-XXXX or 123 45 6789
        "creditcard": re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),  # Card number
        # CRITICAL-2: Length-bounded email regex to prevent ReDoS on malformed input
        # Bounds: 1-64 local part, 1-255 domain, 2+ TLD (realistic email constraints)
        "email": re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}\b"),
        "api_key": re.compile(r"\bsk-[a-zA-Z0-9]{15,48}\b"),  # OpenAI-style API key, bounded length
    }

    # Internal/confidential patterns
    INTERNAL_PATTERNS: dict[str, Pattern[str]] = {
        "internal_path": re.compile(r"/etc/[a-zA-Z0-9./]+"),  # Unix paths
        "config_key": re.compile(r"(DATABASE_URL|API_KEY|SECRET|PASSWORD)="),  # Config leaks
        "internal_api": re.compile(r"https?://localhost:[0-9]+/"),  # Local API URLs
    }

    def validate(
        self,
        text: str,
        context: dict[str, int | str] | None = None,
    ) -> tuple[str, list[str]]:
        """
        Validate LLM output for PII and safety issues.

        Args:
            text: LLM output text to validate
            context: Optional context dict with tenant_id, agent_id, etc.

        Returns:
            Tuple of (cleaned_text, issues_list)
            - cleaned_text: Output with PII masked or removed
            - issues_list: List of issues found (empty if all clean)
        """
        if not text:
            return text, []

        context = context or {}
        tenant_id = context.get("tenant_id")
        cleaned = text
        issues: list[str] = []

        # Check for PII
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                issues.append(f"PII detected: {pii_type}")
                cleaned = pattern.sub("[REDACTED]", cleaned)

        # Check for internal/confidential patterns
        for pattern_type, pattern in self.INTERNAL_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                issues.append(f"Internal reference leaked: {pattern_type}")
                cleaned = pattern.sub("[REDACTED]", cleaned)

        # Log issues if any found (CRITICAL-3 & CRITICAL-4: do NOT log issue details or patterns to prevent info disclosure)
        if issues:
            logger.warning(
                "Output validation issues detected",
                extra={
                    "tenant_id": tenant_id,
                    "agent_id": context.get("agent_id"),
                    "issue_count": len(issues),
                    "event": "output_validation_issue",
                },
            )

        return cleaned, issues
