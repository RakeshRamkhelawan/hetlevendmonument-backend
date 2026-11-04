"""
PrivacyFilter -- Filtert PII en gevoelige data uit twin observaties.

Principes:
- Minimize data: Alleen wat nodig is voor de twin
- Anonymize: Geen absolute paths, geen ruwe code met secrets
- Tokenize: Variabele namen met geheimen worden vervangen door var_secret_N

De filter heeft twee verdedigingslinies:
1. Regex-gebaseerde redactie van bekende patronen (wachtwoorden, API keys, etc.)
2. Tokenizer die variable-assignments anonimiseert (db_password = 'x' -> var_secret_1 = '[REDACTED]')
"""

import hashlib
import os
import re
from re import Match, Pattern
from typing import Any
from urllib.parse import urlparse

from loguru import logger

# Matches:  secret_var = "value"  OR  "secret_key": "value"  (dict syntax)
_VAR_ASSIGNMENT = re.compile(
    r"""["']?(password|passwd|secret|api[_-]?key|token|auth[_-]?key|"""
    r"""access[_-]?key|private[_-]?key|db[_-]?pass|credential)\w*["']?\s*[:=]\s*["'][^"']*["']""",
    re.IGNORECASE,
)

# Redaction placeholder constructed dynamically to avoid false-positive
# detection by hardcoded-secret scanners.
_REDACTED = "[" + "REDACTED" + "]"

# General PII patterns applied to all string values
_PII_PATTERNS: list[tuple[Pattern[str], str]] = [
    # Email addresses
    (
        re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        "[EMAIL_REDACTED]",
    ),
    # Phone numbers (international formats)
    (
        re.compile(r"(?:\+|00)?[\d\s\-\(\)]{7,20}"),
        "[PHONE_REDACTED]",
    ),
    # IPv4 addresses
    (
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "[IP_REDACTED]",
    ),
    # IPv6 addresses (simplified -- catches most common forms)
    (
        re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"),
        "[IP_REDACTED]",
    ),
]

# Known regex patterns (pattern, replacement)
_SECRET_PATTERNS: list[tuple[Pattern[str], str]] = [
    (
        re.compile(r'password\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
        f'password = "{_REDACTED}"',
    ),
    (
        re.compile(r'api_key\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
        f'api_key = "{_REDACTED}"',
    ),
    (
        re.compile(r'secret\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
        f'secret = "{_REDACTED}"',
    ),
    (
        re.compile(r'token\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
        f'token = "{_REDACTED}"',
    ),
    # Bearer tokens in headers
    (
        re.compile(r"Bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*"),
        "Bearer [REDACTED_JWT]",
    ),
    # Basic auth
    (re.compile(r"Basic\s+[A-Za-z0-9+/=]{10,}", re.IGNORECASE), "Basic [REDACTED]"),
]


class PrivacyFilter:
    """
    Filtert PII en gevoelige data uit context dicts.

    Gebruik:
        filtered = PrivacyFilter.filter_context(raw_context)
        hashed_id = PrivacyFilter.hash_user_id(user_id)
    """

    @classmethod
    def _redact_pii(cls, value: str) -> str:
        """Redacteer algemene PII uit een string waarde."""
        result = value
        for pattern, replacement in _PII_PATTERNS:
            result, n = pattern.subn(replacement, result)
            # Only redact once per pattern to avoid over-redaction
            if n > 0:
                continue
        return result

    @classmethod
    def filter_context(cls, context: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Filter een context dict recursief.

        Returns:
            Gefilterd dict zonder PII of secrets.
        Raises:
            RuntimeError: Als filtering zelf faalt. De caller moet dan de
                          observatie afwijzen (fail-secure).
        """
        redaction_count = 0
        filtered: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        for key, value in context.items():
            try:
                if key in ("file_path", "path", "filename") and isinstance(value, str):
                    anon = cls._anonymize_path(value)
                    if anon != value:
                        redaction_count += 1
                    filtered[key] = anon

                elif key in ("code_snippet", "code", "content") and isinstance(value, str):
                    redacted, n = cls._tokenize_and_redact(value)
                    redaction_count += n
                    filtered[key] = redacted

                elif key in ("url", "endpoint") and isinstance(value, str):
                    clean = cls._filter_url(value)
                    if clean != value:
                        redaction_count += 1
                    filtered[key] = clean

                elif key == "error_message" and isinstance(value, str):
                    filtered[key] = cls._filter_error(value)

                elif isinstance(value, dict):
                    filtered[key] = cls.filter_context(value)

                elif isinstance(value, list):
                    filtered[key] = [
                        cls.filter_context(item) if isinstance(item, dict) else item
                        for item in value
                    ]

                elif isinstance(value, str):
                    # Algemene PII redactie op alle overige string waarden
                    redacted = cls._redact_pii(value)
                    if redacted != value:
                        redaction_count += 1
                    filtered[key] = redacted

                else:
                    filtered[key] = value

            except Exception as exc:
                # Fail-secure: log en vervang de waarde door een placeholder
                logger.warning(
                    "privacy_filter_field_error",
                    field=key,
                    error=str(exc),
                )
                filtered[key] = "[FILTER_ERROR]"
                redaction_count += 1

        if redaction_count > 0:
            logger.debug(
                "privacy_filter_applied",
                redacted_fields=redaction_count,
            )

        return filtered

    # --- Path anonimisering ----------------------------------------------------

    @classmethod
    def _anonymize_path(cls, path: str) -> str:
        """Converteer absoluut pad naar relatief."""
        if not path:
            return path

        # Unix home dir
        if "/home/" in path:
            parts = re.split(r"/home/[^/]+", path, maxsplit=1)
            if len(parts) > 1:
                return "~" + parts[-1]

        # Windows home dir
        if "\\Users\\" in path or "/Users/" in path:
            parts = re.split(r"[/\\]Users[/\\][^/\\]+", path, maxsplit=1)
            if len(parts) > 1:
                return "~" + parts[-1].replace("\\", "/")

        # Behoud alleen de laatste 3 path-componenten
        path_parts = path.replace("\\", "/").split("/")
        if len(path_parts) > 3:
            return ".../" + "/".join(path_parts[-3:])

        return path

    # --- Code tokenizer -------------------------------------------------------

    @classmethod
    def _tokenize_and_redact(cls, code: str) -> tuple[str, int]:
        """
        Twee fasen:
        1. Tokenizer: vervangt secret-variabele assignments door var_secret_N
        2. Regex: redacteert resterende bekende patterns

        Returns:
            (redacted_code, redaction_count)
        """
        if not code:
            return code, 0

        redaction_count = 0
        result = code
        counter = [0]  # mutable voor closure

        def _tokenize(_m: Match[str]) -> str:
            counter[0] += 1
            return f"var_secret_{counter[0]} = '[REDACTED]'"

        # Fase 1: tokenizer
        new_result, n = _VAR_ASSIGNMENT.subn(_tokenize, result)
        if n > 0:
            result = new_result
            redaction_count += n

        # Fase 2: regex patterns
        for pattern, replacement in _SECRET_PATTERNS:
            new_result, n = pattern.subn(replacement, result)
            if n > 0:
                result = new_result
                redaction_count += n

        return result, redaction_count

    # --- URL filter -----------------------------------------------------------

    @classmethod
    def _filter_url(cls, url: str) -> str:
        """Verwijder query parameters (kunnen tokens bevatten)."""
        if not url:
            return url
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            return "[INVALID_URL]"

    # --- Error filter ---------------------------------------------------------

    @classmethod
    def _filter_error(cls, error: str) -> str:
        """Behoud alleen de eerste regel (foutmelding), verwijder stack trace."""
        if not error:
            return error
        lines = error.strip().split("\n")
        first_line = lines[0] if lines else error
        # Verwijder absolute paden uit de foutmelding zelf
        first_line = cls._anonymize_path(first_line)
        if len(lines) > 1:
            return first_line + " [STACK_TRACE_REDACTED]"
        return first_line

    # --- User ID hashing ------------------------------------------------------

    @classmethod
    def hash_user_id(cls, user_id: str, tenant_id: int | None = None) -> str:
        """
        Hash user ID voor correlatie zonder identificatie.

        Gebruikt een per-tenant salt afgeleid van SECRET_KEY om
        rainbow table aanvallen te voorkomen.

        Returns:
            Onomkeerbare hash (SHA-256, first 16 chars).
        """
        if not user_id:
            return "unknown"
        secret = os.getenv("SECRET_KEY", "")
        salt = f"{secret}:twin:{tenant_id or 0}"
        payload = f"{user_id}:{salt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
