"""Educational session service (BE-EP-039, ADR-029 Sprint D).

Server-side session storage for the protected edu environment. The session
cookie holds ONLY an opaque random ID (256-bit, secrets.token_urlsafe(32));
this service maps that ID to a pointer payload {access_id, tenant_id}. Role
and code validity are NEVER stored here -- they are re-validated against the
database on every request (audit P0-5 fix, spec O1/O2).

Storage backend is Redis with TTL = 4 hours (14.400 s, "4 schooluren"). The
store is abstracted behind a small interface (O6, same pattern as
FoundationStorageService) so unit tests and offline runs can use the
in-memory implementation while production uses Redis.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.core.typing import AsyncRedisClient

# TTL: 4 hours ("4 schooluren", spec O1).
SESSION_TTL_SECONDS = 14_400

SESSION_KEY_PREFIX = "edu_session:"

# Cookie name and attributes (spec O3): opaque ID only, httponly,
# samesite=Strict, path=/ (no tenant prefix so the frontend does not need
# per-slug cookies), no Domain attribute. The secure flag is set by the API
# layer (production/HTTPS only, same pattern as router_login.py).
SESSION_COOKIE_NAME = "edu_session"


def hash_edu_code(code: str) -> str:
    """SHA-256 over the access code exactly as entered (UTF-8).

    No code-issuing feature exists yet, so the normalization is defined here
    (spec open aannames): no case-folding, no trimming -- the future issuing
    feature MUST use this exact function.
    """
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class EduSessionStoreUnavailableError(Exception):
    """Raised when the session store backend is unreachable.

    Mapped to HTTP 503 by the API layer: without the store, session issuance
    and validation MUST fail loudly, never silently (spec open aannames).
    """


@dataclass(frozen=True)
class EduSessionData:
    """Pointer payload stored per session. Role is deliberately absent."""

    access_id: int
    tenant_id: int


@runtime_checkable
class EduSessionStore(Protocol):
    """Minimal session-store interface (create/read/delete with TTL).

    Implementations: RedisEduSessionStore (production) and
    InMemoryEduSessionStore (tests / offline).
    """

    async def set_session(
        self, session_id: str, data: EduSessionData, ttl_seconds: int
    ) -> None:
        """Store session data under the opaque ID with a TTL in seconds."""
        ...

    async def get_session(self, session_id: str) -> EduSessionData | None:
        """Return session data, or None when unknown or expired."""
        ...

    async def delete_session(self, session_id: str) -> None:
        """Remove a session. Must not raise for unknown IDs."""
        ...


class RedisEduSessionStore:
    """Redis-backed session store. Values are JSON {access_id, tenant_id}."""

    def __init__(self, redis_client: AsyncRedisClient) -> None:
        self._redis = redis_client

    async def set_session(
        self, session_id: str, data: EduSessionData, ttl_seconds: int
    ) -> None:
        payload = json.dumps({"access_id": data.access_id, "tenant_id": data.tenant_id})
        try:
            await self._redis.set(
                f"{SESSION_KEY_PREFIX}{session_id}", payload, ex=ttl_seconds
            )
        except Exception as exc:
            raise EduSessionStoreUnavailableError(str(exc)) from exc

    async def get_session(self, session_id: str) -> EduSessionData | None:
        try:
            raw = await self._redis.get(f"{SESSION_KEY_PREFIX}{session_id}")
        except Exception as exc:
            raise EduSessionStoreUnavailableError(str(exc)) from exc
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
            return EduSessionData(
                access_id=int(parsed["access_id"]),
                tenant_id=int(parsed["tenant_id"]),
            )
        except (ValueError, KeyError, TypeError):
            # Corrupt payload: treat as unknown session (fail closed).
            return None

    async def delete_session(self, session_id: str) -> None:
        try:
            await self._redis.delete(f"{SESSION_KEY_PREFIX}{session_id}")
        except Exception as exc:
            raise EduSessionStoreUnavailableError(str(exc)) from exc


class InMemoryEduSessionStore:
    """In-memory session store implementing EduSessionStore.

    Used by unit tests (offline) and by integration tests via the same
    dependency-override interface when no real Redis is available. Honors
    TTL via a monotonic clock and records the last TTL so tests can assert
    the 14.400 s configuration without a Redis server.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[EduSessionData, float]] = {}
        self.last_ttl_seconds: int | None = None

    async def set_session(
        self, session_id: str, data: EduSessionData, ttl_seconds: int
    ) -> None:
        self.last_ttl_seconds = ttl_seconds
        self._data[session_id] = (data, time.monotonic() + ttl_seconds)

    async def get_session(self, session_id: str) -> EduSessionData | None:
        entry = self._data.get(session_id)
        if entry is None:
            return None
        data, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._data[session_id]
            return None
        return data

    async def delete_session(self, session_id: str) -> None:
        self._data.pop(session_id, None)


class EduSessionService:
    """Session lifecycle: create / get / delete against an EduSessionStore."""

    def __init__(self, store: EduSessionStore) -> None:
        self._store = store

    async def create_session(self, access_id: int, tenant_id: int) -> str:
        """Create a session; returns the opaque ID for the cookie.

        The ID is 256-bit random (secrets.token_urlsafe(32)). No HMAC signing
        is needed: there is nothing to forge in a random ID (spec O1).
        """
        session_id = secrets.token_urlsafe(32)
        await self._store.set_session(
            session_id,
            EduSessionData(access_id=access_id, tenant_id=tenant_id),
            SESSION_TTL_SECONDS,
        )
        return session_id

    async def get_session(self, session_id: str) -> EduSessionData | None:
        """Look up a session by opaque ID. None when unknown/expired."""
        return await self._store.get_session(session_id)

    async def delete_session(self, session_id: str) -> None:
        """Invalidate a session (logout or failed DB revalidation)."""
        await self._store.delete_session(session_id)
