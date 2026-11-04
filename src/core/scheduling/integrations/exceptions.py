"""Custom exceptions for calendar integrations.

These exceptions provide better error handling and user feedback
for OAuth and API-related errors.
"""

from typing import Any


class CalendarIntegrationError(Exception):
    """Base exception for calendar integration errors."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message


class OAuthError(CalendarIntegrationError):
    """OAuth authentication/authorization error."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, provider)
        self.error_code = error_code


class InvalidGrantError(OAuthError):
    """OAuth authorization code is invalid or expired."""

    def __init__(self, provider: str | None = None) -> None:
        super().__init__(
            message="The authorization code is invalid or has expired. Please restart the authentication flow.",
            provider=provider,
            error_code="invalid_grant",
        )


class InvalidClientError(OAuthError):
    """OAuth client credentials are invalid."""

    def __init__(self, provider: str | None = None) -> None:
        super().__init__(
            message="Invalid client credentials. Please check your OAuth configuration.",
            provider=provider,
            error_code="invalid_client",
        )


class InvalidScopeError(OAuthError):
    """OAuth scope is invalid or insufficient."""

    def __init__(self, provider: str | None = None) -> None:
        super().__init__(
            message="Invalid or insufficient OAuth scope. Please request the required permissions.",
            provider=provider,
            error_code="invalid_scope",
        )


class TokenExpiredError(OAuthError):
    """OAuth access token has expired and cannot be refreshed."""

    def __init__(self, provider: str | None = None) -> None:
        super().__init__(
            message="Access token has expired and cannot be refreshed. Please reconnect your calendar.",
            provider=provider,
            error_code="token_expired",
        )


class RateLimitError(CalendarIntegrationError):
    """API rate limit exceeded."""

    def __init__(
        self,
        provider: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(
            message=f"Rate limit exceeded for {provider or 'provider'}. Please try again later.",
            provider=provider,
        )
        self.retry_after = retry_after


class CalendarNotFoundError(CalendarIntegrationError):
    """Requested calendar was not found."""

    def __init__(self, calendar_id: str, provider: str | None = None) -> None:
        super().__init__(
            message=f"Calendar '{calendar_id}' not found.",
            provider=provider,
        )
        self.calendar_id = calendar_id


class EventNotFoundError(CalendarIntegrationError):
    """Requested event was not found."""

    def __init__(self, event_id: str, provider: str | None = None) -> None:
        super().__init__(
            message=f"Event '{event_id}' not found.",
            provider=provider,
        )
        self.event_id = event_id


class SyncError(CalendarIntegrationError):
    """Calendar synchronization error."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        partial_result: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(message, provider)
        self.partial_result = partial_result or {}


def raise_for_oauth_error(response_status: int, error_data: dict[str, Any], provider: str) -> None:  # TODO(TYPE): replace Any with concrete type
    """Raise appropriate OAuth exception based on error response.

    Args:
        response_status: HTTP status code
        error_data: Error response data from OAuth provider
        provider: Provider name (google, outlook, etc.)

    Raises:
        OAuthError or subclass: Appropriate exception for the error
    """
    error_code = error_data.get("error", "")
    error_description = error_data.get("error_description", "")

    # Map common OAuth error codes to exceptions
    error_map = {
        "invalid_grant": InvalidGrantError,
        "invalid_client": InvalidClientError,
        "invalid_scope": InvalidScopeError,
        "unauthorized_client": InvalidClientError,
        "unsupported_grant_type": OAuthError,
        "invalid_request": OAuthError,
        "access_denied": OAuthError,
        "server_error": OAuthError,
        "temporarily_unavailable": OAuthError,
    }

    exception_class = error_map.get(error_code, OAuthError)

    if exception_class == OAuthError:
        # Generic OAuth error with details
        message = f"OAuth error ({error_code}): {error_description or 'Unknown error'}"
        raise exception_class(message=message, provider=provider, error_code=error_code)
    else:
        # Specific exception type
        raise exception_class(provider=provider)
