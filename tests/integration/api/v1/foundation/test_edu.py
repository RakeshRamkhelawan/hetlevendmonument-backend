"""Integration tests for BE-EP-039 edu session + content endpoints.

Real Postgres via the shared integration fixtures. The session store runs
through the SAME EduSessionStore interface as production (O6): by default an
InMemoryEduSessionStore is injected via dependency override so the suite is
deterministic without a local Redis; a dedicated TTL test uses a real Redis
when one is reachable (docker-compose.ci / dev) and skips otherwise.

Covers the audit P0-5 regression tests from the spec DoD:
- a self-set cookie with an invented value NEVER grants access (401);
- a valid session whose code was deactivated mid-session gives 401.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    get_edu_session_service,
)
from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    EducationalAccess,
    EducationalRole,
    FoundationContent,
    PortalRole,
    PortalUser,
    Privacy,
    Visibility,
)
from src.core.services.edu_session_service import (
    EduSessionData,
    EduSessionService,
    InMemoryEduSessionStore,
    RedisEduSessionStore,
    hash_edu_code,
)
from src.core.shared.datetime_utils import utc_now

EDU_CODE = "K3T1K0T1"


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def edu_store(
    integration_app: FastAPI,
) -> AsyncGenerator[InMemoryEduSessionStore, None]:
    """Override the session-store dependency with the in-memory implementation.

    Same EduSessionStore interface as production (O6); real-Redis TTL is
    verified separately in TestSessionTtlRealRedis.
    """
    store = InMemoryEduSessionStore()

    async def override() -> EduSessionService:
        return EduSessionService(store)

    integration_app.dependency_overrides[get_edu_session_service] = override
    try:
        yield store
    finally:
        integration_app.dependency_overrides.pop(get_edu_session_service, None)


@pytest_asyncio.fixture(scope="function")
async def edu_access(postgres_session: AsyncSession) -> EducationalAccess:
    """Active teacher code for tenant_id=1, no expiry."""
    access = EducationalAccess(
        tenant_id=1,
        code_hash=hash_edu_code(EDU_CODE),
        email="docent@test.local",
        role=EducationalRole.TEACHER,
        is_active=True,
        expires_at=None,
    )
    postgres_session.add(access)
    await postgres_session.flush()
    await postgres_session.refresh(access)
    return access


@pytest_asyncio.fixture(scope="function")
async def edu_approved_content(postgres_session: AsyncSession) -> FoundationContent:
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.EDUCATIONAL_WORKBOOK,
        title_nl="Werkblad Ketikoti",
        privacy=Privacy.PUBLIC,
        visibility=Visibility.EDU,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
        target_age_group="12-14",
        category="lesmateriaal",
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def edu_pending_content(postgres_session: AsyncSession) -> FoundationContent:
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.EDUCATIONAL_VIDEO,
        title_nl="Video in moderatie",
        privacy=Privacy.PUBLIC,
        visibility=Visibility.EDU,
        status=ContentStatus.PENDING,
        rights_confirmed=True,
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def edu_other_tenant_content(postgres_session: AsyncSession) -> FoundationContent:
    content = FoundationContent(
        tenant_id=2,
        type=ContentType.TEACHER_GUIDE,
        title_nl="Handleiding andere tenant",
        privacy=Privacy.PUBLIC,
        visibility=Visibility.EDU,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def edu_anonymous_content(postgres_session: AsyncSession) -> FoundationContent:
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.STORY,
        title_nl="Anoniem leerlingverhaal",
        creator_name="Geheime Naam",
        is_anonymous=True,
        privacy=Privacy.PUBLIC,
        visibility=Visibility.EDU,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def mismatch_content(postgres_session: AsyncSession) -> FoundationContent:
    """N-2-invariant probe: privacy=PUBLIC but visibility=EDU.

    This row must NEVER appear via the public endpoints, despite the PUBLIC
    privacy level (O5).
    """
    content = FoundationContent(
        tenant_id=1,
        type=ContentType.STORY,
        title_nl="Mismatch rij",
        privacy=Privacy.PUBLIC,
        visibility=Visibility.EDU,
        status=ContentStatus.APPROVED,
        rights_confirmed=True,
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


async def _create_session(client: AsyncClient, slug: str = "default", code: str = EDU_CODE):
    return await client.post(_url(slug, "/edu/session"), json={"code": code})


# ============================================================================
# POST /edu/session
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestEduSessionCreate:
    async def test_create_session_success(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        response = await _create_session(integration_client)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["role"] == "teacher"
        assert data["expires_at"] is None

        # Cookie attributes (spec O3): httponly, samesite=Strict, path=/,
        # max_age = 4 hours; the value is the opaque ID only.
        set_cookie = response.headers.get("set-cookie", "")
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "samesite=strict" in set_cookie.lower()
        assert "Path=/" in set_cookie
        assert str(SESSION_TTL_SECONDS) in set_cookie

        cookie_value = integration_client.cookies.get(SESSION_COOKIE_NAME)
        assert cookie_value is not None
        assert EDU_CODE not in cookie_value
        assert "teacher" not in cookie_value
        assert ":" not in cookie_value

        # TTL configured on the store (4 schooluren).
        assert edu_store.last_ttl_seconds == SESSION_TTL_SECONDS == 14_400

    async def test_create_session_unknown_code_uniform_401(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        response = await _create_session(integration_client, code="ZZZZ9999")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid or expired code"

    async def test_create_session_inactive_code_uniform_401(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        postgres_session: AsyncSession,
    ) -> None:
        edu_access.is_active = False
        await postgres_session.flush()
        response = await _create_session(integration_client)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid or expired code"

    async def test_create_session_expired_code_uniform_401(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        postgres_session: AsyncSession,
    ) -> None:
        edu_access.expires_at = utc_now() - timedelta(minutes=1)
        await postgres_session.flush()
        response = await _create_session(integration_client)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid or expired code"

    async def test_create_session_malformed_code_422(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
    ) -> None:
        for bad in ("K3T1K0T", "K3T1K0T12", "K3T1K0T!"):
            response = await _create_session(integration_client, code=bad)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_create_session_unknown_tenant_404(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
    ) -> None:
        response = await _create_session(integration_client, slug="nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_create_session_code_of_other_tenant_401(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        """A valid code for tenant 1 must not open a session on tenant 2."""
        response = await _create_session(integration_client, slug="other")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# GET / DELETE /edu/session
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestEduSessionInfoAndDelete:
    async def test_get_session_success(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200
        response = await integration_client.get(_url("default", "/edu/session"))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "teacher"

    async def test_get_session_without_cookie_401_from_session_check(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        """401 must come from require_edu_session, not from TenantMiddleware
        on the wrong grounds (edu auth is cookie-based, not JWT)."""
        response = await integration_client.get(_url("default", "/edu/session"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid or expired edu session"

    async def test_delete_session_lifecycle(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200
        session_id = integration_client.cookies.get(SESSION_COOKIE_NAME)
        assert session_id is not None

        response = await integration_client.delete(_url("default", "/edu/session"))
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Session is gone server-side; the old cookie value is useless.
        assert await edu_store.get_session(session_id) is None
        response = await integration_client.get(_url("default", "/edu/session"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# Audit P0-5 regressietests (DoD)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestEduAuditRegression:
    async def test_forged_cookie_never_grants_access(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_approved_content: FoundationContent,
    ) -> None:
        """Audit-regressietest 1: a self-set cookie with an invented value
        (including the gap-analysis `code:role` shape) gives 401, always."""
        for forged in ("WATDANOOK:teacher", "K3T1K0T1:teacher", "x" * 64):
            integration_client.cookies.set(SESSION_COOKIE_NAME, forged)
            response = await integration_client.get(_url("default", "/edu/content"))
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            # Wiped cookie is signaled back to the client.
            assert SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")

    async def test_deactivated_code_invalidates_live_session(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_approved_content: FoundationContent,
        postgres_session: AsyncSession,
    ) -> None:
        """Audit-regressietest 2: a VALID session whose code is deactivated
        mid-session gives 401 on the next request, and the session is removed
        from the store (spec O2)."""
        assert (await _create_session(integration_client)).status_code == 200
        session_id = integration_client.cookies.get(SESSION_COOKIE_NAME)
        assert session_id is not None

        # Works before deactivation.
        assert (await integration_client.get(_url("default", "/edu/content"))).status_code == 200

        edu_access.is_active = False
        await postgres_session.flush()

        response = await integration_client.get(_url("default", "/edu/content"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert await edu_store.get_session(session_id) is None

    async def test_expired_code_invalidates_live_session(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        postgres_session: AsyncSession,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200
        edu_access.expires_at = utc_now() - timedelta(minutes=1)
        await postgres_session.flush()
        response = await integration_client.get(_url("default", "/edu/session"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_session_of_other_tenant_rejected(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        """A session for tenant 1 must not read tenant 2's edu content."""
        assert (await _create_session(integration_client)).status_code == 200
        response = await integration_client.get(_url("other", "/edu/content"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# GET /edu/content -- lijst + detail
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestEduContentList:
    async def test_list_requires_session(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_approved_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(_url("default", "/edu/content"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid or expired edu session"

    async def test_list_returns_only_edu_approved_of_tenant(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_approved_content: FoundationContent,
        edu_pending_content: FoundationContent,
        edu_other_tenant_content: FoundationContent,
        approved_public_content: FoundationContent,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200
        response = await integration_client.get(_url("default", "/edu/content"))
        assert response.status_code == status.HTTP_200_OK
        ids = {item["id"] for item in response.json()["items"]}
        assert edu_approved_content.id in ids
        assert edu_pending_content.id not in ids  # status gate
        assert edu_other_tenant_content.id not in ids  # tenant gate
        assert approved_public_content.id not in ids  # visibility gate

    async def test_list_type_and_age_filters(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_approved_content: FoundationContent,
        edu_anonymous_content: FoundationContent,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200

        response = await integration_client.get(
            _url("default", "/edu/content?type=educational_workbook")
        )
        ids = {item["id"] for item in response.json()["items"]}
        assert ids == {edu_approved_content.id}

        response = await integration_client.get(
            _url("default", "/edu/content?target_age_group=12-14")
        )
        ids = {item["id"] for item in response.json()["items"]}
        assert ids == {edu_approved_content.id}

        response = await integration_client.get(_url("default", "/edu/content?type=bogus-type"))
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_list_applies_anonymity_mask(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_anonymous_content: FoundationContent,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200
        response = await integration_client.get(_url("default", "/edu/content"))
        assert response.status_code == status.HTTP_200_OK
        item = next(i for i in response.json()["items"] if i["id"] == edu_anonymous_content.id)
        assert item["creator_name"] is None
        assert item["is_anonymous"] is True

    async def test_list_pagination(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_approved_content: FoundationContent,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200
        response = await integration_client.get(_url("default", "/edu/content?page=1&page_size=5"))
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5


@pytest.mark.asyncio
@pytest.mark.integration
class TestEduContentDetail:
    async def test_detail_success(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_approved_content: FoundationContent,
    ) -> None:
        assert (await _create_session(integration_client)).status_code == 200
        response = await integration_client.get(
            _url("default", f"/edu/content/{edu_approved_content.id}")
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == edu_approved_content.id
        assert response.json()["type"] == "educational_workbook"

    async def test_detail_uniform_404(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
        edu_pending_content: FoundationContent,
        edu_other_tenant_content: FoundationContent,
        approved_public_content: FoundationContent,
    ) -> None:
        """Uniforme 404 voor pending / andere tenant / niet-edu / onbekend."""
        assert (await _create_session(integration_client)).status_code == 200
        for content_id in (
            edu_pending_content.id,
            edu_other_tenant_content.id,
            approved_public_content.id,
            999999,
        ):
            response = await integration_client.get(_url("default", f"/edu/content/{content_id}"))
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert response.json()["detail"] == "Content not found"


# ============================================================================
# O5 / N-2-invariant: edu-content onzichtbaar via publieke endpoints
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestEduInvisibleInPublicArchive:
    async def test_mismatch_row_not_in_public_list_anonymous(
        self,
        integration_client: AsyncClient,
        mismatch_content: FoundationContent,
        approved_public_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(_url("default", "/content"))
        assert response.status_code == status.HTTP_200_OK
        ids = {item["id"] for item in response.json()["items"]}
        assert mismatch_content.id not in ids
        assert approved_public_content.id in ids

    async def test_mismatch_row_not_in_public_list_authenticated(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        mismatch_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(
            _url("default", "/content"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        ids = {item["id"] for item in response.json()["items"]}
        assert mismatch_content.id not in ids

    async def test_mismatch_row_detail_404_anonymous(
        self,
        integration_client: AsyncClient,
        mismatch_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(_url("default", f"/content/{mismatch_content.id}"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_mismatch_row_detail_404_authenticated(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        mismatch_content: FoundationContent,
    ) -> None:
        response = await integration_client.get(
            _url("default", f"/content/{mismatch_content.id}"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# BE-SEC-057: /edu/codes vereist curator/admin JWT (was: volledig onbeveiligd)
# ============================================================================


def _codes_token(*, user_id: int, email: str, tenant_id: int, role: PortalRole) -> str:
    """Portal JWT (aud='portal', scope='portal_uploader') -- same shape as the
    foundation conftest helper, repeated here for a tenant-2 curator."""
    return jwt_handler.create_access_token(
        data={
            "sub": str(user_id),
            "user_id": user_id,
            "email": email,
            "tenant_id": tenant_id,
            "aud": "portal",
            "scope": "portal_uploader",
            "role": role.value,
        }
    )


@pytest_asyncio.fixture(scope="function")
async def other_tenant_curator_token(postgres_session: AsyncSession) -> str:
    """Curator of tenant_id=2: must NOT manage codes of tenant_id=1."""
    user = PortalUser(
        tenant_id=2,
        email="curator-other@test.local",
        display_name="Other Tenant Curator",
        is_verified=True,
        is_blocked=False,
        role=PortalRole.CURATOR,
    )
    postgres_session.add(user)
    await postgres_session.flush()
    await postgres_session.refresh(user)
    return _codes_token(
        user_id=user.id, email=user.email, tenant_id=user.tenant_id, role=PortalRole.CURATOR
    )


def _codes_payload() -> dict[str, object]:
    return {
        "class_name": "Groep 8A",
        "teacher_email": "meester.jan@school.nl",
        "role": "student",
        "valid_hours": 4,
    }


@pytest.mark.asyncio
@pytest.mark.integration
class TestEduCodesAuth:
    """Markt-review 2026-09-24: POST/GET/DELETE /edu/codes hingen zonder enige
    auth in de router. Anoniem minten, PII lezen (docent-e-mails + klasnamen)
    en revoken moeten 401/403 geven; curator/admin van de EIGEN tenant mag."""

    async def test_anonymous_gets_401_on_all_code_endpoints(
        self,
        integration_client: AsyncClient,
    ) -> None:
        response = await integration_client.post(
            _url("default", "/edu/codes"), json=_codes_payload()
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = await integration_client.get(_url("default", "/edu/codes"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = await integration_client.delete(_url("default", "/edu/codes/1"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_visitor_role_gets_403_on_all_code_endpoints(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Authenticated portal user without curator/admin role: 403."""
        headers = {"Authorization": f"Bearer {portal_visitor_token}"}
        response = await integration_client.post(
            _url("default", "/edu/codes"), json=_codes_payload(), headers=headers
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await integration_client.get(_url("default", "/edu/codes"), headers=headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await integration_client.delete(
            _url("default", "/edu/codes/1"), headers=headers
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_edu_session_cookie_grants_no_codes_access(
        self,
        integration_client: AsyncClient,
        edu_store: InMemoryEduSessionStore,
        edu_access: EducationalAccess,
    ) -> None:
        """A valid edu session cookie (teacher role) is NOT a JWT and must not
        open the code-management endpoints."""
        assert (await _create_session(integration_client)).status_code == 200
        response = await integration_client.get(_url("default", "/edu/codes"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_curator_can_mint_list_and_revoke(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
    ) -> None:
        headers = {"Authorization": f"Bearer {portal_curator_token}"}

        create = await integration_client.post(
            _url("default", "/edu/codes"), json=_codes_payload(), headers=headers
        )
        assert create.status_code == status.HTTP_201_CREATED
        code_id = create.json()["id"]
        assert len(create.json()["code"]) == 8

        listing = await integration_client.get(_url("default", "/edu/codes"), headers=headers)
        assert listing.status_code == status.HTTP_200_OK
        ids = {item["id"] for item in listing.json()["items"]}
        assert code_id in ids

        revoke = await integration_client.delete(
            _url("default", f"/edu/codes/{code_id}"), headers=headers
        )
        assert revoke.status_code == status.HTTP_204_NO_CONTENT

        listing = await integration_client.get(_url("default", "/edu/codes"), headers=headers)
        assert code_id not in {item["id"] for item in listing.json()["items"]}

    async def test_admin_can_mint_code(
        self,
        integration_client: AsyncClient,
        portal_admin_token: str,
    ) -> None:
        headers = {"Authorization": f"Bearer {portal_admin_token}"}
        response = await integration_client.post(
            _url("default", "/edu/codes"), json=_codes_payload(), headers=headers
        )
        assert response.status_code == status.HTTP_201_CREATED

    async def test_curator_of_other_tenant_gets_403(
        self,
        integration_client: AsyncClient,
        other_tenant_curator_token: str,
    ) -> None:
        """Tenant isolation: a curator of tenant 2 must not mint, list or
        revoke codes on tenant 1's slug -- not even read them."""
        headers = {"Authorization": f"Bearer {other_tenant_curator_token}"}
        response = await integration_client.post(
            _url("default", "/edu/codes"), json=_codes_payload(), headers=headers
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await integration_client.get(_url("default", "/edu/codes"), headers=headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await integration_client.delete(
            _url("default", "/edu/codes/1"), headers=headers
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_curator_cannot_use_other_tenants_slug(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
    ) -> None:
        """Reverse direction: tenant-1 curator on tenant-2 slug -> 403."""
        headers = {"Authorization": f"Bearer {portal_curator_token}"}
        response = await integration_client.get(_url("other", "/edu/codes"), headers=headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# TTL against real Redis (only when one is reachable; same interface)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestSessionTtlRealRedis:
    async def test_real_redis_ttl_is_14400(self) -> None:
        try:
            from src.core.database.redis import get_redis_client

            client = await get_redis_client()
            await client.ping()
        except Exception:
            pytest.skip("Geen Redis bereikbaar in deze testomgeving")

        store = RedisEduSessionStore(client)
        session_id = "ttl-probe-be-ep-039"
        try:
            await store.set_session(
                session_id, EduSessionData(access_id=1, tenant_id=1), SESSION_TTL_SECONDS
            )
            ttl = await client.ttl(f"edu_session:{session_id}")
            assert 14_000 < ttl <= SESSION_TTL_SECONDS
        finally:
            await store.delete_session(session_id)
