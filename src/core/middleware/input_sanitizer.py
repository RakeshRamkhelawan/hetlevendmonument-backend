"""
Input Sanitization Middleware - OWASP Input Validation

Prevents injection attacks by sanitizing user input before processing.
Focus: SQL Injection, Command Injection, XSS prevention at input level.
"""

import re

from fastapi import HTTPException, status
from loguru import logger


class InputSanitizer:
    """Sanitizes and validates user input to prevent injection attacks."""

    # Dangerous SQL keywords that should not appear in user input
    SQL_KEYWORDS = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "EXEC",
        "EXECUTE",
        "UNION",
        "SELECT",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "--",
        "/*",
        "*/",
        "xp_",
        "sp_",
    ]

    # Dangerous command injection characters
    COMMAND_CHARS = [";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r"]

    # XSS patterns
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe",
        r"<object",
        r"<embed",
    ]

    @staticmethod
    def sanitize_search_query(query: str, max_length: int = 500) -> str:
        """
        Sanitize search query to prevent SQL injection and command injection.

        Args:
            query: User-provided search query
            max_length: Maximum allowed length for query

        Returns:
            Sanitized query string

        Raises:
            HTTPException: If input is invalid or contains dangerous patterns
        """
        if not isinstance(query, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search query must be a string",
            )

        # Strip whitespace
        query = query.strip()

        # Check empty
        if not query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search query cannot be empty",
            )

        # Check length
        if len(query) > max_length:
            logger.warning(
                f"Search query too long: {len(query)} chars (max {max_length})",
                extra={"query_preview": query[:100]},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Search query too long (max {max_length} characters)",
            )

        # Check for SQL injection keywords
        query_upper = query.upper()
        for keyword in InputSanitizer.SQL_KEYWORDS:
            if keyword in query_upper:
                logger.warning(
                    f"SQL keyword detected in search: {keyword}",
                    extra={"query_preview": query[:100]},
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid characters detected in search query",
                )

        # Check for command injection characters
        for char in InputSanitizer.COMMAND_CHARS:
            if char in query:
                logger.warning(
                    f"Command injection character detected: {repr(char)}",
                    extra={"query_preview": query[:100]},
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid characters detected in search query",
                )

        return query

    @staticmethod
    def sanitize_text_input(text: str, max_length: int = 5000) -> str:
        """
        Sanitize general text input to prevent XSS.

        Args:
            text: User-provided text
            max_length: Maximum allowed length

        Returns:
            Sanitized text string

        Raises:
            HTTPException: If input contains XSS patterns
        """
        if not isinstance(text, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text input must be a string",
            )

        # Check length
        if len(text) > max_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Text input too long (max {max_length} characters)",
            )

        # Check for XSS patterns
        for pattern in InputSanitizer.XSS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(
                    "XSS pattern detected in text input",
                    extra={"pattern": pattern, "text_preview": text[:100]},
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid content detected in text input",
                )

        return text

    @staticmethod
    def validate_filename(filename: str) -> str:
        """
        Validate and sanitize uploaded filename.

        Args:
            filename: User-provided filename

        Returns:
            Sanitized filename

        Raises:
            HTTPException: If filename is invalid
        """
        if not isinstance(filename, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename must be a string",
            )

        # Strip whitespace
        filename = filename.strip()

        # Check empty
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename cannot be empty",
            )

        # Check for path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            logger.warning(f"Path traversal attempt in filename: {filename}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

        # Check length
        if len(filename) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename too long (max 255 characters)",
            )

        # Only allow alphanumeric, dash, underscore, dot
        if not re.match(r"^[a-zA-Z0-9._-]+$", filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename contains invalid characters",
            )

        return filename

    @staticmethod
    def validate_email(email: str) -> str:
        """
        Validate email address format.

        Args:
            email: User-provided email

        Returns:
            Lowercase email address

        Raises:
            HTTPException: If email format is invalid
        """
        if not isinstance(email, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email must be a string"
            )

        email = email.strip().lower()

        # Basic email regex (RFC 5321 compliant subset)
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not re.match(email_pattern, email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email address format",
            )

        # Check length (RFC 5321)
        local_part, domain = email.split("@")
        if len(local_part) > 64 or len(email) > 254:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email address too long"
            )

        return email
