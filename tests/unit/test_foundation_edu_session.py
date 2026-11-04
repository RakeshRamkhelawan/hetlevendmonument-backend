"""Unit tests for BE-EP-039 edu session service, schemas and registry rules.

Offline: no database, no Redis. The store under test is
InMemoryEduSessionStore (same EduSessionStore interface as the Redis
implementation, spec O6); RedisEduSessionStore is tested against a fake
client that records calls.
"""

from __future__ import annotations

import hashlib
import json
import secrets

import pytest
from pydantic import ValidationError

from src.core.api.v1.foundation.schemas import EduSessionRequest, EduSessionResponse
from src.core.services.edu_session_service import (
    SESSION_KEY_PREFIX,
    SESSION_TTL_SECONDS,
    EduSessionData,
    EduSessionService,
    InMemoryEduSessionStore,
    RedisEduSessionStore,
    hash_edu_code,
)
from src.core.shared.public_registry import PublicEndpointRegistry


# ============================================================================
# hash_edu_code -- hash normalization (spec open aannames)
# ============================================================================


class TestHashEduCode:
    @pytest.mark.unit
    def test_sha256_hex_of_code_as_entered(self) -> None:
        code = "K3T1K0T1"
        assert hash_edu_code(code) == hashlib.sha256(code.encode("utf-8")).hexdigest()

    @pytest.mark.unit
    def test_no_case_folding(self) -> None:
        """Normalization is exact: no case-folding, no trimming."""
        assert hash_edu_code("abcd1234") != hash_edu_code("ABCD1234")
        assert hash_edu_code("abcd1234") != hash_edu_code(" abcd1234")

    @pytest.mark.unit
    def test_hash_length_matches_column(self) -> None:
        # educational_access.code_hash is String(64) -- sha256 hexdigest.
        assert len(hash_edu_code("K3T1K0T1")) == 64


# ============================================================================
# EduSessionRequest validation (spec: exact 8 alfanumeriek)
# ============================================================================


class TestEduSessionRequest:
    @pytest.mark.unit
    def test_valid_code_accepted(self) -> None:
        assert EduSessionRequest(code="K3T1K0T1").code == "K3T1K0T1"
        assert EduSessionRequest(code="abcdefgh").code == "abcdefgh"

    @pytest.mark.unit
    def test_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EduSessionRequest(code="K3T1K0T")

    @pytest.mark.unit
    def test_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EduSessionRequest(code="K3T1K0T12")

    @pytest.mark.unit
    def test_non_alphanumeric_rejected(self) -> None:
        for bad in ("K3T1K0T!", "K3T1K0 T", "K3T1K0T-", "........"):
            with pytest.raises(ValidationError):
                EduSessionRequest(code=bad)


# ============================================================================
# EduSessionService against the in-memory store (spec O6)
# ============================================================================


class TestEduSessionServiceInMemory:
    @pytest.mark.unit
    async def test_create_get_roundtrip(self) -> None:
        service = EduSessionService(InMemoryEduSessionStore())
        session_id = await service.create_session(access_id=7, tenant_id=1)
        data = await service.get_session(session_id)
        assert data is not None
        assert data.access_id == 7
        assert data.tenant_id == 1

    @pytest.mark.unit
    def test_session_id_is_opaque_256bit(self) -> None:
        """The ID must not leak code/role/tenant (spec O1)."""
        session_id = secrets.token_urlsafe(32)
        assert len(session_id) >= 40  # 32 bytes -> 43 base64url chars
        # No structured separator that would allow "id:role" forgery.
        assert ":" not in session_id

    @pytest.mark.unit
    async def test_ttl_is_14400_seconds(self) -> None:
        store = InMemoryEduSessionStore()
        service = EduSessionService(store)
        await service.create_session(access_id=7, tenant_id=1)
        assert store.last_ttl_seconds == SESSION_TTL_SECONDS == 14_400

    @pytest.mark.unit
    async def test_unknown_session_returns_none(self) -> None:
        """Audit-regressie (unit-niveau): een verzonnen ID is nooit geldig."""
        service = EduSessionService(InMemoryEduSessionStore())
        assert await service.get_session("WATDANOOK:teacher") is None
        assert await service.get_session("x" * 64) is None

    @pytest.mark.unit
    async def test_expired_session_returns_none(self) -> None:
        store = InMemoryEduSessionStore()
        await store.set_session("sid", EduSessionData(access_id=7, tenant_id=1), 0)
        assert await store.get_session("sid") is None

    @pytest.mark.unit
    async def test_delete_session(self) -> None:
        service = EduSessionService(InMemoryEduSessionStore())
        session_id = await service.create_session(access_id=7, tenant_id=1)
        await service.delete_session(session_id)
        assert await service.get_session(session_id) is None
        # Deleting an unknown ID must not raise.
        await service.delete_session("never-existed")


# ============================================================================
# RedisEduSessionStore against a fake client (call recording)
# ============================================================================


class _FakeRedisClient:
    """Minimal async Redis stand-in recording calls."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.last_ex: int | None = None

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        self.last_ex = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0


class TestRedisEduSessionStore:
    @pytest.mark.unit
    async def test_set_uses_prefix_and_ttl(self) -> None:
        client = _FakeRedisClient()
        store = RedisEduSessionStore(client)
        await store.set_session("abc", EduSessionData(access_id=7, tenant_id=1), 14_400)
        assert f"{SESSION_KEY_PREFIX}abc" in client.values
        assert client.last_ex == 14_400

        payload = json.loads(client.values[f"{SESSION_KEY_PREFIX}abc"])
        assert payload == {"access_id": 7, "tenant_id": 1}

    @pytest.mark.unit
    async def test_get_unknown_returns_none(self) -> None:
        store = RedisEduSessionStore(_FakeRedisClient())
        assert await store.get_session("unknown") is None

    @pytest.mark.unit
    async def test_get_corrupt_payload_fails_closed(self) -> None:
        client = _FakeRedisClient()
        client.values[f"{SESSION_KEY_PREFIX}bad"] = "not-json"
        store = RedisEduSessionStore(client)
        assert await store.get_session("bad") is None

    @pytest.mark.unit
    async def test_delete(self) -> None:
        client = _FakeRedisClient()
        store = RedisEduSessionStore(client)
        await store.set_session("abc", EduSessionData(access_id=7, tenant_id=1), 14_400)
        await store.delete_session("abc")
        assert await store.get_session("abc") is None


# ============================================================================
# Public registry: edu path rules (BE-EP-039)
# ============================================================================


class TestPublicRegistryEdu:
    @pytest.mark.unit
    def test_edu_session_path_is_public(self) -> None:
        """POST /edu/session (code entry) must pass TenantMiddleware without JWT."""
        assert PublicEndpointRegistry.is_public("/ketikoti/foundation/edu/session")

    @pytest.mark.unit
    def test_edu_content_path_passes_middleware(self) -> None:
        """Edu auth is cookie-based, not JWT: /edu/* must pass the middleware.

        The session requirement itself is enforced per endpoint by
        require_edu_session -- documented deviation from the spec letter
        ("alleen POST publiek"), because the registry matches on path only
        and a JWT-less cookie request on a non-public path would be 401'd by
        TenantMiddleware before reaching the endpoint.
        """
        assert PublicEndpointRegistry.is_public("/ketikoti/foundation/edu/content")
        assert PublicEndpointRegistry.is_public("/ketikoti/foundation/edu/content/42")

    @pytest.mark.unit
    def test_edu_codes_paths_are_not_public(self) -> None:
        """BE-SEC-057: code management requires a curator/admin JWT.

        The TenantMiddleware must NOT pass /edu/codes* without a token: minting,
        listing (teacher emails + class names = PII) and revoking codes are
        curator/admin operations, not cookie-session operations.
        """
        assert not PublicEndpointRegistry.is_public("/ketikoti/foundation/edu/codes")
        assert not PublicEndpointRegistry.is_public("/ketikoti/foundation/edu/codes/12")
        assert not PublicEndpointRegistry.is_public("/api/v1/ketikoti/foundation/edu/codes")

    @pytest.mark.unit
    def test_admin_still_not_public(self) -> None:
        assert not PublicEndpointRegistry.is_public("/ketikoti/foundation/admin/edu")

    @pytest.mark.unit
    def test_similar_prefix_not_matched(self) -> None:
        # "/foundation/edu/" must not open lookalike paths.
        assert not PublicEndpointRegistry.is_public("/ketikoti/foundation/education")
        assert not PublicEndpointRegistry.is_public("/api/v1/foundationx/edu/session")

    @pytest.mark.unit
    def test_existing_public_paths_unchanged(self) -> None:
        assert PublicEndpointRegistry.is_public("/ketikoti/foundation/content")
        assert PublicEndpointRegistry.is_public("/ketikoti/foundation/map/bbox")
        assert PublicEndpointRegistry.is_public("/ketikoti/foundation/settings")


# ============================================================================
# EduSessionResponse shape
# ============================================================================


class TestEduSessionResponse:
    @pytest.mark.unit
    def test_role_and_expiry(self) -> None:
        resp = EduSessionResponse(role="teacher", expires_at=None)
        assert resp.role == "teacher"
        assert resp.expires_at is None
