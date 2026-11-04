"""Shared HTTP authentication token extraction helpers."""

from typing import Optional


def normalize_access_token(token: str | None) -> str | None:
    """Return a stripped token value with optional surrounding quotes removed."""
    if token is None:
        return None

    normalized = token.strip()
    if not normalized:
        return None

    if normalized.startswith('"') and normalized.endswith('"') and len(normalized) >= 2:
        normalized = normalized[1:-1].strip()

    return normalized or None


def extract_bearer_token(authorization: str | None) -> str | None:
    """Extract a bearer token from an Authorization header."""
    if not authorization:
        return None

    if not authorization.lower().startswith("bearer "):
        return None

    return normalize_access_token(authorization[7:])


def extract_access_token_cookie(cookie_header: str | None) -> str | None:
    """Extract the access_token cookie value from a raw Cookie header."""
    if not cookie_header:
        return None

    for cookie in cookie_header.split(";"):
        if "=" not in cookie:
            continue

        name, value = cookie.split("=", 1)
        if name.strip() == "access_token":
            return normalize_access_token(value)

    return None


def extract_http_token(
    authorization: str | None = None,
    access_token_cookie: str | None = None,
    credentials_token: str | None = None,
) -> str | None:
    """Extract the canonical HTTP auth token using header-first precedence."""
    token = normalize_access_token(credentials_token)
    if token:
        return token

    token = extract_bearer_token(authorization)
    if token:
        return token

    return normalize_access_token(access_token_cookie)
