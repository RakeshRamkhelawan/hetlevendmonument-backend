"""Integration tests for the Foundation Portal upload endpoint (BE-EP-036).

Follows the test_content.py pattern. Storage is redirected to tmp_path via a
dependency-override of get_foundation_storage. Runs against Postgres 5435 +
Redis like the other foundation integration tests.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import get_foundation_storage
from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    PortalRole,
    PortalUser,
    Privacy,
)
from src.core.services.foundation_storage import FoundationStorageService
from src.core.shared.config import Settings

PNG_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
EXE_BYTES = b"MZ" + b"\x00" * 64


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


def _build_portal_token(
    *, user_id: int, email: str, tenant_id: int, role: PortalRole = PortalRole.VISITOR
) -> str:
    """Create a portal JWT (aud='portal', scope='portal_uploader')."""
    data: dict[str, object] = {
        "sub": str(user_id),
        "user_id": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "aud": "portal",
        "scope": "portal_uploader",
        "role": role.value,
    }
    return jwt_handler.create_access_token(data=data)


def _storage_override(
    integration_app: FastAPI, tmp_path: Path, **settings_overrides: object
) -> FoundationStorageService:
    """Point the storage service at tmp_path for the duration of one test."""
    base: dict[str, object] = {
        "storage_backend": "local",
        "local_upload_dir": str(tmp_path),
    }
    base.update(settings_overrides)
    service = FoundationStorageService(settings=Settings(**base))  # type: ignore[arg-type]
    integration_app.dependency_overrides[get_foundation_storage] = lambda: service
    return service


@pytest_asyncio.fixture(scope="function")
async def upload_dir(integration_app: FastAPI, tmp_path: Path) -> AsyncGenerator[Path, None]:
    """Default storage override (local backend, tmp_path, default 50 MB cap)."""
    _storage_override(integration_app, tmp_path)
    yield tmp_path
    integration_app.dependency_overrides.pop(get_foundation_storage, None)


# ============================================================================
# Extra seed fixtures (owned content + a second tenant-1 visitor)
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def visitor_owned_content(
    postgres_session: AsyncSession, portal_visitor_user: PortalUser
) -> FoundationContent:
    """Content item in tenant 1 whose uploader is the visitor portal user."""
    content = FoundationContent(
        tenant_id=1,
        uploader_id=portal_visitor_user.id,
        type=ContentType.ARTWORK,
        title_nl="Upload doel",
        privacy=Privacy.PUBLIC,
        status=ContentStatus.PENDING,
        rights_confirmed=True,
    )
    postgres_session.add(content)
    await postgres_session.flush()
    await postgres_session.refresh(content)
    return content


@pytest_asyncio.fixture(scope="function")
async def other_visitor_user(postgres_session: AsyncSession) -> PortalUser:
    """Second tenant-1 visitor: not the uploader, not a curator."""
    user = PortalUser(
        tenant_id=1,
        email="visitor2@test.local",
        display_name="Second Visitor",
        is_verified=True,
        is_blocked=False,
        role=PortalRole.VISITOR,
    )
    postgres_session.add(user)
    await postgres_session.flush()
    await postgres_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def other_visitor_token(other_visitor_user: PortalUser) -> str:
    return _build_portal_token(
        user_id=other_visitor_user.id,
        email=other_visitor_user.email,
        tenant_id=other_visitor_user.tenant_id,
        role=PortalRole.VISITOR,
    )


# ============================================================================
# POST /{tenantSlug}/foundation/content/{content_id}/upload
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentFileUpload:
    """Tests for the content file upload endpoint."""

    async def test_upload_success_owner(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """The uploader of the content can attach a file."""
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_mime"] == "image/png"
        assert data["file_size_bytes"] == len(PNG_BYTES)
        assert data["sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()
        assert data["file_url"].startswith(f"/uploads/foundation/1/{visitor_owned_content.id}/")
        assert data["file_url"].endswith(".png")
        # Local backend really wrote the bytes under the override dir
        rel = data["file_url"].removeprefix("/uploads/")
        written = upload_dir.joinpath(*rel.split("/"))
        assert written.is_file()
        assert written.read_bytes() == PNG_BYTES

    async def test_upload_success_curator_on_other_content(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """A curator may attach a file to someone else's content."""
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["file_mime"] == "image/png"

    async def test_upload_unauthenticated(
        self,
        integration_client: AsyncClient,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """No token -> 401."""
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_upload_cross_tenant_forbidden(
        self,
        integration_client: AsyncClient,
        other_tenant_portal_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """A user from another tenant cannot upload here -> 403."""
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {other_tenant_portal_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_upload_not_owner_gets_404_not_403(
        self,
        integration_client: AsyncClient,
        other_visitor_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """Same-tenant user who is neither uploader nor curator -> 404.

        Gate-2 review MEDIUM (2026-09-09): 403 would leak that the content
        exists (existence oracle); the response must be identical to the
        non-existent-content case.
        """
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {other_visitor_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_upload_not_found_and_unauthorized_are_identical(
        self,
        integration_client: AsyncClient,
        other_visitor_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """Non-existent content and unauthorized content answer identically,
        so content IDs of other users cannot be enumerated."""
        not_found = await integration_client.post(
            _url("default", "/content/99999/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {other_visitor_token}"},
        )
        unauthorized = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {other_visitor_token}"},
        )
        assert not_found.status_code == status.HTTP_404_NOT_FOUND
        assert unauthorized.status_code == status.HTTP_404_NOT_FOUND
        # The global error envelope adds a per-response timestamp; everything
        # else (status_code, error_code, message) must be identical.
        nf_body = not_found.json()["error"]
        un_body = unauthorized.json()["error"]
        nf_body.pop("timestamp", None)
        un_body.pop("timestamp", None)
        assert nf_body == un_body

    async def test_upload_content_not_found(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        upload_dir: Path,
    ) -> None:
        """Unknown content id -> 404."""
        response = await integration_client.post(
            _url("default", "/content/99999/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_upload_oversize_rejected(
        self,
        integration_app: FastAPI,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        visitor_owned_content: FoundationContent,
        tmp_path: Path,
    ) -> None:
        """Cap+1 bytes -> 413 (small cap via storage override)."""
        _storage_override(integration_app, tmp_path, max_upload_size_bytes=1024)
        try:
            response = await integration_client.post(
                _url("default", f"/content/{visitor_owned_content.id}/upload"),
                files={"file": ("foto.png", b"x" * 1025, "image/png")},
                headers={"Authorization": f"Bearer {portal_visitor_token}"},
            )
            assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        finally:
            integration_app.dependency_overrides.pop(get_foundation_storage, None)

    async def test_upload_forbidden_mime_rejected(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """Executable bytes with a .png filename -> 400 (magic bytes win)."""
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("evil.png", EXE_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_upload_empty_file_rejected(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """Empty file -> 400, not 500 (Gate-2 HIGH-1)."""
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("leeg.txt", b"", "text/plain")},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_upload_text_plain_end_to_end(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
    ) -> None:
        """text/plain via the documented fallback works end to end, including
        a charset parameter on the declared Content-Type (Gate-2 MEDIUM)."""
        text_bytes = "Dit is een platte tekst notitie.\n".encode("utf-8")
        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("notitie.txt", text_bytes, "text/plain; charset=utf-8")},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_mime"] == "text/plain"
        assert data["file_url"].endswith(".txt")

    async def test_upload_audit_failure_still_succeeds(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_token: str,
        visitor_owned_content: FoundationContent,
        upload_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Audit runs AFTER the commit of the content update (backend pattern
        #3). A failing audit must not roll back the update or the response:
        the upload returns 200, the file is on storage, AND the file_*
        columns are really persisted in the database (the explicit commit is
        what guarantees this; without it a best_effort rollback could have
        taken the flushed update down with the failed audit)."""
        from src.core.governance.services.audit_service import AuditService

        async def _exploding_log_event(*args: object, **kwargs: object) -> bool:
            raise RuntimeError("audit backend down")

        monkeypatch.setattr(AuditService, "log_event", _exploding_log_event)

        response = await integration_client.post(
            _url("default", f"/content/{visitor_owned_content.id}/upload"),
            files={"file": ("foto.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        rel = data["file_url"].removeprefix("/uploads/")
        assert upload_dir.joinpath(*rel.split("/")).is_file()

        # Reload from the DB (fresh SELECT, not the identity map) and assert
        # the content update survived the exploding audit.
        await postgres_session.refresh(visitor_owned_content)
        assert visitor_owned_content.file_url == data["file_url"]
        assert visitor_owned_content.file_mime == "image/png"
        assert visitor_owned_content.file_size_bytes == len(PNG_BYTES)


# ============================================================================
# Media endpoint (GET /{tenantSlug}/foundation/content/{content_id}/media) - ADR-029 P1-4
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestMediaEndpoint:
    """Tests for secure media serving and SAS URL generation."""

    async def test_get_media_public_success(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
    ) -> None:
        """Public content media returns signed/secure URL."""
        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Verhaal met media",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url="/uploads/foundation/1/1/test.png",
            file_mime="image/png",
            file_size_bytes=1024,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.get(_url("default", f"/content/{content.id}/media"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["url"] == "/uploads/foundation/1/1/test.png"
        assert data["mime_type"] == "image/png"
        assert data["file_size_bytes"] == 1024
        assert data["expires_in_seconds"] == 1800

    async def test_get_media_redirect_success(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
    ) -> None:
        """Redirect parameter returns 307 Temporary Redirect."""
        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Verhaal met redirect",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url="/uploads/foundation/1/2/test.png",
            file_mime="image/png",
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.get(
            _url("default", f"/content/{content.id}/media?redirect=true"),
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert response.headers["location"] == "/uploads/foundation/1/2/test.png"

    async def test_get_media_community_requires_auth(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        portal_visitor_token: str,
    ) -> None:
        """Community content media requires authentication."""
        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Community media",
            privacy=Privacy.COMMUNITY,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url="/uploads/foundation/1/3/test.png",
            file_mime="image/png",
        )
        postgres_session.add(content)
        await postgres_session.flush()

        # Without auth -> 403
        unauth_res = await integration_client.get(_url("default", f"/content/{content.id}/media"))
        assert unauth_res.status_code == status.HTTP_403_FORBIDDEN

        # With auth -> 200
        auth_res = await integration_client.get(
            _url("default", f"/content/{content.id}/media"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert auth_res.status_code == status.HTTP_200_OK

    async def test_get_media_not_found(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """404 when content does not exist or has no media."""
        response = await integration_client.get(_url("default", "/content/999999/media"))
        assert response.status_code == status.HTTP_404_NOT_FOUND
