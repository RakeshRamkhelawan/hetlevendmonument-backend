"""
Foundation Portal Exceptions

12 exception classes for the Levend Monument Foundation Portal (ADR-029).
Base class FoundationError inherits from SanskritiError (NOT SanskritiSetuException).

All exceptions follow the SanskritiError pattern:
- error_code: machine-readable error code
- status_code: HTTP status code
- details: extra context (never contains PII)
"""

from src.core.exceptions.exceptions import SanskritiError


class FoundationError(SanskritiError):
    """Base for all Foundation Portal exceptions."""

    def __init__(
        self,
        message: str,
        error_code: str = "FOUNDATION_ERROR",
        status_code: int = 500,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class FoundationTenantSlugNotFoundError(FoundationError):
    """Tenant slug not found or inactive. Same message for both to prevent enumeration."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            message="tenant slug not found",
            error_code="TENANT_NOT_FOUND",
            status_code=404,
            details={"slug": slug},
        )


class FoundationTenantDomainNotFoundError(FoundationError):
    """Tenant domain not found or inactive. Same message for both to prevent enumeration."""

    def __init__(self, domain: str) -> None:
        super().__init__(
            message="tenant domain not found",
            error_code="TENANT_NOT_FOUND",
            status_code=404,
            details={"domain": domain},
        )


class InvalidDomainError(FoundationError):
    """Domain format does not match RFC 1035 or contains forbidden characters."""

    def __init__(self, domain: str) -> None:
        super().__init__(
            message="invalid domain format",
            error_code="INVALID_DOMAIN",
            status_code=400,
            details={"domain": domain},
        )



class ContentNotFoundError(FoundationError):
    """FoundationContent record not found."""

    def __init__(self, content_id: int) -> None:
        super().__init__(
            message="content not found",
            error_code="CONTENT_NOT_FOUND",
            status_code=404,
            details={"content_id": content_id},
        )


class InvalidFileTypeError(FoundationError):
    """Uploaded file type is not allowed."""

    def __init__(self, mime_type: str) -> None:
        super().__init__(
            message="invalid file type",
            error_code="INVALID_FILE_TYPE",
            status_code=400,
            details={"mime_type": mime_type},
        )


class FileTooLargeError(FoundationError):
    """Uploaded file exceeds maximum size."""

    def __init__(self, max_size_bytes: int) -> None:
        super().__init__(
            message="file too large",
            error_code="FILE_TOO_LARGE",
            status_code=413,
            details={"max_size_bytes": max_size_bytes},
        )


class RightsNotConfirmedError(FoundationError):
    """Uploader has not confirmed copyright / usage rights."""

    def __init__(self) -> None:
        super().__init__(
            message="rights not confirmed",
            error_code="RIGHTS_NOT_CONFIRMED",
            status_code=400,
        )


class InvalidMagicLinkError(FoundationError):
    """Magic link token is invalid, expired, or already used."""

    def __init__(self, reason: str = "invalid or expired") -> None:
        super().__init__(
            message="invalid magic link",
            error_code="INVALID_MAGIC_LINK",
            status_code=401,
            details={"reason": reason},
        )


class CaptchaFailedError(FoundationError):
    """hCaptcha verification failed."""

    def __init__(self) -> None:
        super().__init__(
            message="captcha verification failed",
            error_code="CAPTCHA_FAILED",
            status_code=400,
        )


class TakedownDuplicateError(FoundationError):
    """Duplicate takedown request for the same content."""

    def __init__(self, content_id: int) -> None:
        super().__init__(
            message="takedown request already exists for this content",
            error_code="TAKEDOWN_DUPLICATE",
            status_code=409,
            details={"content_id": content_id},
        )


class ReservedSlugError(FoundationError):
    """Tenant slug is in the reserved list."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            message="slug is reserved",
            error_code="RESERVED_SLUG",
            status_code=400,
            details={"slug": slug},
        )


class InvalidSlugError(FoundationError):
    """Tenant slug does not match the required pattern."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            message="invalid slug format",
            error_code="INVALID_SLUG",
            status_code=400,
            details={"slug": slug},
        )


class SlugTakenError(FoundationError):
    """Tenant slug is already in use."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            message="slug is already taken",
            error_code="SLUG_TAKEN",
            status_code=409,
            details={"slug": slug},
        )
