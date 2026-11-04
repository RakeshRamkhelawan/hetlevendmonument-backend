"""Prompt Injection Prevention -- Guards against prompt injection attacks in user input."""

import logging
import re
import unicodedata
from re import Pattern

from src.core.exceptions import PromptInjectionError

logger = logging.getLogger(__name__)


class PromptGuard:
    """Detects and prevents prompt injection attacks in user input.

    Uses regex patterns to identify common prompt injection techniques.
    Raises PromptInjectionError if injection attempt is detected.
    """

    # Regex patterns that indicate prompt injection attempts
    # All patterns use bounded quantifiers and case-insensitive flags to prevent ReDoS
    INJECTION_PATTERNS: list[Pattern[str]] = [
        # Pattern 1: "ignore/forget/disregard above instructions"
        re.compile(
            r"(?i)(ignore|forget|disregard)\s*(all\s*)?(above|previous|prior|old)\s*"
            r"(instructions?|prompts?|context|directives?)?",
        ),
        # Pattern 2: Role override ("you are now a...", "act as", "roleplay as")
        re.compile(
            r"(?i)(you\s*are\s*now|act\s*as|pretend\s*(you\s*are|to\s*be)|roleplay\s*as)",
        ),
        # Pattern 3: System prompt override ("system prompt", "new instructions", "override")
        re.compile(
            r"(?i)(system\s*prompt|new\s*instructions?|override\s*(instructions?|system))",
        ),
        # Pattern 4: HIGH-3 -- Metadata query ("what is your system", "show me the prompt", etc.)
        # Restricted to require "system", "prompt", or "instructions" to avoid false positives
        re.compile(
            r"(?i)(what\s*(is|are)\s*(your|the)\s*(system|prompt|instructions)|"
            r"(who|what)\s*(are|is)\s*you\s*(really|actually|truly)|"
            r"your\s*(system\s*)?(prompt|instructions?|context)|"
            r"show\s+(me|us)?\s*(the\s+)?(system\s+)?(prompt|instructions?))",
        ),
        # Pattern 5: HIGH-3 -- Direct extraction ("return/output/print/echo" + "system/original/real")
        re.compile(
            r"(?i)(return|output|print|echo|display)\s*(your|the|my)\s*"
            r"(system|original|real|initial|underlying|base)\s*(prompt|instructions?|context)?",
        ),
        # Pattern 6: HIGH-3 -- Jailbreak delimiters "[BEGIN JAILBREAK|SYSTEM]"
        re.compile(
            r"(?i)\[\s*(BEGIN|START|OPEN)\s*(JAILBREAK|SYSTEM|CORE|HIDDEN|OVERRIDE|UNLOCK)\s*\]",
        ),
        # Pattern 7: HIGH-3 -- ASCII delimiters "<<<SYSTEM", ">>>OVERRIDE"
        re.compile(
            r"(?i)(<<<|>>>|###|---|===)\s*(SYSTEM|CORE|OVERRIDE|JAILBREAK|ADMIN|ROOT)",
        ),
    ]

    def sanitize(
        self,
        text: str,
        tenant_id: int,
        max_length: int = 4000,
    ) -> str:
        """
        Sanitize input text to prevent prompt injection attacks.

        Args:
            text: User input to sanitize
            tenant_id: Tenant ID for logging context
            max_length: Maximum allowed length (default 4000)

        Returns:
            Sanitized text (truncated if needed)

        Raises:
            PromptInjectionError: If injection pattern detected
        """
        if not text:
            return text

        # CRITICAL-1: Normalize Unicode (NFD) to decompose lookalikes ([U+0435] -> e + combining mark)
        text = unicodedata.normalize("NFD", text)

        # Remove zero-width characters: zero-width space, joiner, non-joiner
        zero_width_chars = {"\u200b", "\u200c", "\u200d", "\ufeff"}
        text = "".join(c for c in text if c not in zero_width_chars)

        # Enforce max length BEFORE pattern matching (fail-secure)
        if len(text) > max_length:
            logger.debug(
                "Input truncated to max_length",
                extra={
                    "tenant_id": tenant_id,
                    "original_length": len(text),
                    "max_length": max_length,
                },
            )
            text = text[:max_length]

        # Check for injection patterns
        # Build a simplified string for pattern checking (homoglyph/diacritic removal)
        check_text = unicodedata.normalize("NFD", text)
        check_text = "".join(c for c in check_text if unicodedata.category(c) != "Mn")
        homoglyphs = str.maketrans({
            0x0435: "e",  # e (cyrillic small ie)
            0x03BF: "o",  # o (greek small omicron)
            0x043E: "o",  # o (cyrillic small o)
        })
        check_text = check_text.translate(homoglyphs)

        for idx, pattern in enumerate(self.INJECTION_PATTERNS):
            if pattern.search(check_text):
                logger.warning(
                    "Prompt injection attempt detected",
                    extra={
                        "tenant_id": tenant_id,
                        "pattern_index": idx,
                        "text_length": len(text),
                        "event": "prompt_injection_blocked",
                    },
                )
                raise PromptInjectionError(
                    "Potential prompt injection detected in input. "
                    "Injection patterns are not allowed.",
                )

        return text
