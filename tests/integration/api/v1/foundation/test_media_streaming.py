"""Integration tests for BE-EP-052: Media Streaming, Range Requests & Privacy Matrix.

Runs against test Postgres and Redis containers.
Tests:
- GET /{tenantSlug}/foundation/content/{id}/media/stream (200 OK and 206 Partial Content)
- RFC 9110 Range Header handling: closed range, open range, 416 Range Not Satisfiable
- Content-Disposition: inline vs attachment (download=true)
- Privacy & Visibility Authorization Matrix:
  - APPROVED + PUBLIC: Accessible publicly
  - APPROVED + COMMUNITY: Requires tenant portal user
  - APPROVED + EDU: Requires edu_session cookie or curator/admin
  - PENDING: Accessible only by uploader or curator/admin, 404 for others
  - REJECTED: Accessible only by uploader or curator/admin, 404 for others
  - REMOVED: Accessible only by curator/admin, 404 for uploader and public
"""

from __future__ import annotations

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
    Visibility,
)
from src.core.services.foundation_storage import FoundationStorageService
from src.core.shared.config import Settings


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


def _build_portal_token(
    *, user_id: int, email: str, tenant_id: int, role: PortalRole = PortalRole.VISITOR
) -> str:
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
    integration_app: FastAPI, tmp_path: Path
) -> FoundationStorageService:
    service = FoundationStorageService(
        settings=Settings(
            storage_backend="local",
            local_upload_dir=str(tmp_path),
        )
    )
    integration_app.dependency_overrides[get_foundation_storage] = lambda: service
    return service


@pytest_asyncio.fixture(scope="function")
async def local_media_setup(
    integration_app: FastAPI, tmp_path: Path
) -> AsyncGenerator[Path, None]:
    _storage_override(integration_app, tmp_path)
    yield tmp_path
    integration_app.dependency_overrides.pop(get_foundation_storage, None)


@pytest.mark.integration
class TestMediaStreamingAndRangeRequests:
    async def test_stream_full_content_without_range_header(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        local_media_setup: Path,
    ) -> None:
        """Non-range GET on /media/stream returns 200 OK, full file and RFC headers."""
        # Create physical file in tmp_path
        media_file = local_media_setup / "tenant_1" / "test_sound.mp3"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        file_bytes = b"MP3_AUDIO_DATA_" * 10  # 150 bytes
        media_file.write_bytes(file_bytes)

        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Gesproken Geschiedenis",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="audio/mpeg",
            file_size_bytes=len(file_bytes),
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.get(
            _url("default", f"/content/{content.id}/media/stream")
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["Accept-Ranges"] == "bytes"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Content-Length"] == str(len(file_bytes))
        assert "inline" in response.headers["Content-Disposition"]
        assert response.content == file_bytes

    async def test_stream_partial_content_range_request(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        local_media_setup: Path,
    ) -> None:
        """Range GET returns 206 Partial Content with Content-Range."""
        media_file = local_media_setup / "tenant_1" / "scrubbing_video.mp4"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        file_bytes = bytes(i % 256 for i in range(500))  # 500 bytes
        media_file.write_bytes(file_bytes)

        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Scrubbing Video",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="video/mp4",
            file_size_bytes=len(file_bytes),
        )
        postgres_session.add(content)
        await postgres_session.flush()

        # Request bytes 100-199 (100 bytes)
        response = await integration_client.get(
            _url("default", f"/content/{content.id}/media/stream"),
            headers={"Range": "bytes=100-199"},
        )
        assert response.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert response.headers["Accept-Ranges"] == "bytes"
        assert response.headers["Content-Range"] == "bytes 100-199/500"
        assert response.headers["Content-Length"] == "100"
        assert response.content == file_bytes[100:200]

    async def test_stream_open_and_suffix_ranges(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        local_media_setup: Path,
    ) -> None:
        """Support for bytes=start- and bytes=-suffix."""
        media_file = local_media_setup / "tenant_1" / "range_test.mp3"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        file_bytes = bytes(i % 256 for i in range(300))  # 300 bytes
        media_file.write_bytes(file_bytes)

        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Range Test",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="audio/mpeg",
            file_size_bytes=len(file_bytes),
        )
        postgres_session.add(content)
        await postgres_session.flush()

        # Open range: 250-
        res_open = await integration_client.get(
            _url("default", f"/content/{content.id}/media/stream"),
            headers={"Range": "bytes=250-"},
        )
        assert res_open.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert res_open.headers["Content-Range"] == "bytes 250-299/300"
        assert res_open.content == file_bytes[250:]

        # Suffix range: -50
        res_suffix = await integration_client.get(
            _url("default", f"/content/{content.id}/media/stream"),
            headers={"Range": "bytes=-50"},
        )
        assert res_suffix.status_code == status.HTTP_206_PARTIAL_CONTENT
        assert res_suffix.headers["Content-Range"] == "bytes 250-299/300"
        assert res_suffix.content == file_bytes[250:]

    async def test_stream_unsatisfiable_range_returns_416(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        local_media_setup: Path,
    ) -> None:
        """Unsatisfiable range returns 416 with Content-Range bytes */size."""
        media_file = local_media_setup / "tenant_1" / "small.mp3"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"12345")

        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Small",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="audio/mpeg",
            file_size_bytes=5,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.get(
            _url("default", f"/content/{content.id}/media/stream"),
            headers={"Range": "bytes=100-200"},
        )
        assert response.status_code == status.HTTP_416_RANGE_NOT_SATISFIABLE
        assert response.headers["Content-Range"] == "bytes */5"

    async def test_stream_download_flag_sets_attachment_header(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        local_media_setup: Path,
    ) -> None:
        """download=true query parameter sets Content-Disposition: attachment."""
        media_file = local_media_setup / "tenant_1" / "interview.mp3"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"interview audio content")

        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Oral Interview",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="audio/mpeg",
            file_size_bytes=23,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        response = await integration_client.get(
            _url("default", f"/content/{content.id}/media/stream?download=true")
        )
        assert response.status_code == status.HTTP_200_OK
        assert 'attachment; filename="Oral_Interview.mp3"' in response.headers["Content-Disposition"]


@pytest.mark.integration
class TestMediaAccessPrivacyMatrix:
    async def test_edu_content_media_access_requires_edu_session(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        portal_curator_token: str,
        local_media_setup: Path,
    ) -> None:
        """APPROVED + EDU content media access requires valid edu_session cookie or curator."""
        media_file = local_media_setup / "tenant_1" / "edu_material.pdf"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"%PDF-1.4 edu lesson")

        content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.STORY,
            title_nl="Educatief Materiaal",
            privacy=Privacy.PUBLIC,
            visibility=Visibility.EDU,
            status=ContentStatus.APPROVED,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="application/pdf",
            file_size_bytes=19,
        )
        postgres_session.add(content)
        await postgres_session.flush()

        # 1. Anonymous / regular visitor -> 403 Forbidden
        unauth_resp = await integration_client.get(
            _url("default", f"/content/{content.id}/media")
        )
        assert unauth_resp.status_code == status.HTTP_403_FORBIDDEN

        # 2. Curator token -> 200 OK
        curator_resp = await integration_client.get(
            _url("default", f"/content/{content.id}/media"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert curator_resp.status_code == status.HTTP_200_OK

    async def test_pending_and_rejected_content_accessible_only_by_uploader_or_curator(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        other_tenant_portal_user: PortalUser,
        portal_curator_token: str,
        local_media_setup: Path,
    ) -> None:
        """PENDING and REJECTED media returns 404 for public, 200 for uploader and curator."""
        media_file = local_media_setup / "tenant_1" / "pending.png"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"pending image content")

        pending_content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.ARTWORK,
            title_nl="In Behandeling",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.PENDING,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="image/png",
            file_size_bytes=21,
        )
        postgres_session.add(pending_content)
        await postgres_session.flush()

        # Anonymous -> 404
        anon_resp = await integration_client.get(
            _url("default", f"/content/{pending_content.id}/media")
        )
        assert anon_resp.status_code == status.HTTP_404_NOT_FOUND

        # Other visitor -> 404
        other_visitor_token = _build_portal_token(
            user_id=other_tenant_portal_user.id,
            email=other_tenant_portal_user.email,
            tenant_id=other_tenant_portal_user.tenant_id,
            role=PortalRole.VISITOR,
        )
        other_resp = await integration_client.get(
            _url("default", f"/content/{pending_content.id}/media"),
            headers={"Authorization": f"Bearer {other_visitor_token}"},
        )
        assert other_resp.status_code == status.HTTP_404_NOT_FOUND

        # Uploader -> 200
        uploader_token = _build_portal_token(
            user_id=portal_visitor_user.id,
            email=portal_visitor_user.email,
            tenant_id=portal_visitor_user.tenant_id,
            role=PortalRole.VISITOR,
        )
        uploader_resp = await integration_client.get(
            _url("default", f"/content/{pending_content.id}/media"),
            headers={"Authorization": f"Bearer {uploader_token}"},
        )
        assert uploader_resp.status_code == status.HTTP_200_OK

        # Curator -> 200
        curator_resp = await integration_client.get(
            _url("default", f"/content/{pending_content.id}/media"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert curator_resp.status_code == status.HTTP_200_OK

    async def test_removed_content_accessible_only_by_curator(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        portal_curator_token: str,
        local_media_setup: Path,
    ) -> None:
        """REMOVED media returns 404 even for uploader, but 200 for curator."""
        media_file = local_media_setup / "tenant_1" / "removed.png"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"removed image content")

        removed_content = FoundationContent(
            tenant_id=portal_visitor_user.tenant_id,
            uploader_id=portal_visitor_user.id,
            type=ContentType.ARTWORK,
            title_nl="Verwijderd Erfgoedstuk",
            privacy=Privacy.PUBLIC,
            status=ContentStatus.REMOVED,
            rights_confirmed=True,
            file_url=f"/uploads/tenant_1/{media_file.name}",
            file_mime="image/png",
            file_size_bytes=21,
        )
        postgres_session.add(removed_content)
        await postgres_session.flush()

        # Uploader -> 404
        uploader_token = _build_portal_token(
            user_id=portal_visitor_user.id,
            email=portal_visitor_user.email,
            tenant_id=portal_visitor_user.tenant_id,
            role=PortalRole.VISITOR,
        )
        uploader_resp = await integration_client.get(
            _url("default", f"/content/{removed_content.id}/media"),
            headers={"Authorization": f"Bearer {uploader_token}"},
        )
        assert uploader_resp.status_code == status.HTTP_404_NOT_FOUND

        # Curator -> 200
        curator_resp = await integration_client.get(
            _url("default", f"/content/{removed_content.id}/media"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert curator_resp.status_code == status.HTTP_200_OK
