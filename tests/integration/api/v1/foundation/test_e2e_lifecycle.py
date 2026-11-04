"""End-to-End lifecycle integration tests for Foundation Portal (ADR-029 P1-6).

Validates the complete lifecycle:
1. Public submission (pending status) -> Curation isolation
2. Curator review & approval -> Public discovery (feed & MapLibre Bbox)
3. Media attachment upload -> Secure SAS / media retrieval
4. Content update (PUT)
5. Notice & Takedown request (with Brevo email notification)
6. Soft-delete (DELETE) -> Purged from public visibility
7. Passwordless magic-link authentication & Newsletter subscription flow
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import get_foundation_storage
from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import (
    ContentStatus,
    FoundationContent,
    PortalUser,
    TakedownRequest,
    TakedownStatus,
)
from src.core.services.brevo_email_service import brevo_email_service
from src.core.services.foundation_storage import FoundationStorageService
from src.core.shared.config import Settings

PNG_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
HCAPTCHA_TEST_TOKEN = "10000000-aaaa-bbbb-cccc-000000000001"
MAP_BBOX_QUERY = "sw_lat=51.0&sw_lng=3.0&ne_lat=52.0&ne_lng=4.0"


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


def _storage_override(integration_app: FastAPI, tmp_path: Path) -> FoundationStorageService:
    """Point storage service at tmp_path for local upload testing."""
    config: dict[str, object] = {
        "storage_backend": "local",
        "local_upload_dir": str(tmp_path),
    }
    service = FoundationStorageService(settings=Settings(**config))  # type: ignore[arg-type]
    integration_app.dependency_overrides[get_foundation_storage] = lambda: service
    return service


@pytest_asyncio.fixture(scope="function")
async def upload_dir(integration_app: FastAPI, tmp_path: Path) -> AsyncGenerator[Path, None]:
    """Default local storage override using tmp_path."""
    _storage_override(integration_app, tmp_path)
    yield tmp_path
    integration_app.dependency_overrides.pop(get_foundation_storage, None)


# ============================================================================
# E2E Test Suite
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestFoundationE2ELifecycle:
    """End-to-End lifecycle test suite across the complete heritage story pipeline."""

    async def test_full_heritage_story_lifecycle(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
        portal_visitor_token: str,
        portal_curator_token: str,
        portal_admin_token: str,
        upload_dir: Path,
    ) -> None:
        """E2E flow: Create -> Moderate -> Discover -> Upload Media -> Update -> NTD -> Soft Delete."""
        brevo_email_service.clear_sent_emails()

        # --------------------------------------------------------------------
        # 1. Visitor submits a new heritage story (status: PENDING)
        # --------------------------------------------------------------------
        create_payload = {
            "type": "story",
            "title_nl": "Het Verhaal van de Oude Scheepswerf",
            "description_nl": "Ooggetuigenverslag van scheepsbouwers uit Vlissingen.",
            "body_nl": "Generaties lang bouwden we hier aan de houten vissersschepen...",
            "lat": 51.4425,
            "lng": 3.5736,
            "location_name": "Vlissingen Haven",
            "category": "maritiem-erfgoed",
            "creator_name": "Klaas Visser",
            "is_anonymous": False,
            "privacy": "public",
            "license": "CC-BY-4.0",
            "rights_confirmed": True,
            "metadata": {
                "heritage_types": ["maritiem-erfgoed", "industrieel-erfgoed"],
                "temporal_coverage": "1930-1960",
                "spatial_coverage": "Vlissingen Haven",
            },
        }

        resp_create = await integration_client.post(
            _url("default", "/content"),
            json=create_payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert resp_create.status_code == status.HTTP_201_CREATED
        data_create = resp_create.json()
        content_id = data_create["id"]
        assert data_create["status"] == "pending"
        assert data_create["title_nl"] == "Het Verhaal van de Oude Scheepswerf"

        # --------------------------------------------------------------------
        # 2. Curation Isolation: unapproved story must NOT be publicly visible
        # --------------------------------------------------------------------
        # Feed check
        resp_feed = await integration_client.get(_url("default", "/content"))
        assert resp_feed.status_code == status.HTTP_200_OK
        feed_ids = [item["id"] for item in resp_feed.json()["items"]]
        assert content_id not in feed_ids

        # Map bbox check (bounding box covering Vlissingen)
        resp_map = await integration_client.get(_url("default", f"/map/bbox?{MAP_BBOX_QUERY}"))
        assert resp_map.status_code == status.HTTP_200_OK
        features = resp_map.json()["features"]
        map_ids = [f["properties"]["id"] for f in features]
        assert content_id not in map_ids

        # Direct public GET returns 404 for unapproved content
        resp_public_detail = await integration_client.get(_url("default", f"/content/{content_id}"))
        assert resp_public_detail.status_code == status.HTTP_404_NOT_FOUND

        # --------------------------------------------------------------------
        # 3. Curator inspects moderation queue and approves the story
        # --------------------------------------------------------------------
        resp_queue = await integration_client.get(
            _url("default", "/admin/curatie"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert resp_queue.status_code == status.HTTP_200_OK
        queue_ids = [item["id"] for item in resp_queue.json()["items"]]
        assert content_id in queue_ids

        resp_approve = await integration_client.post(
            _url("default", f"/admin/curatie/{content_id}/approve"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert resp_approve.status_code == status.HTTP_200_OK
        assert resp_approve.json()["status"] == "approved"

        # --------------------------------------------------------------------
        # 4. Public Discovery: story is now searchable and visible on map
        # --------------------------------------------------------------------
        resp_feed_after = await integration_client.get(_url("default", "/content"))
        assert resp_feed_after.status_code == status.HTTP_200_OK
        feed_ids_after = [item["id"] for item in resp_feed_after.json()["items"]]
        assert content_id in feed_ids_after

        resp_map_after = await integration_client.get(
            _url("default", f"/map/bbox?{MAP_BBOX_QUERY}")
        )
        assert resp_map_after.status_code == status.HTTP_200_OK
        map_ids_after = [f["properties"]["id"] for f in resp_map_after.json()["features"]]
        assert content_id in map_ids_after

        resp_detail_approved = await integration_client.get(
            _url("default", f"/content/{content_id}")
        )
        assert resp_detail_approved.status_code == status.HTTP_200_OK
        data_detail = resp_detail_approved.json()
        assert data_detail["id"] == content_id
        assert data_detail["status"] == "approved"
        assert data_detail["category"] == "maritiem-erfgoed"
        assert data_detail["lat"] == 51.4425
        assert data_detail["lng"] == 3.5736

        # --------------------------------------------------------------------
        # 5. Media Upload & Retrieval (P1-4 SAS / media endpoint)
        # --------------------------------------------------------------------
        resp_upload = await integration_client.post(
            _url("default", f"/content/{content_id}/upload"),
            files={"file": ("werf_archief.png", PNG_BYTES, "image/png")},
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert resp_upload.status_code == status.HTTP_200_OK
        upload_data = resp_upload.json()
        assert upload_data["file_mime"] == "image/png"
        assert upload_data["sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()

        # Query media metadata / access URL
        resp_media = await integration_client.get(
            _url("default", f"/content/{content_id}/media"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert resp_media.status_code == status.HTTP_200_OK
        media_data = resp_media.json()
        assert "url" in media_data
        assert media_data["mime_type"] == "image/png"
        assert media_data["expires_in_seconds"] == 1800

        # Media redirect (HTTP 307)
        resp_redirect = await integration_client.get(
            _url("default", f"/content/{content_id}/media?redirect=true"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
            follow_redirects=False,
        )
        assert resp_redirect.status_code == status.HTTP_307_TEMPORARY_REDIRECT

        # --------------------------------------------------------------------
        # 6. Content Update (P1-2 PUT endpoint)
        # --------------------------------------------------------------------
        update_payload = {
            "title_en": "The Story of the Old Shipyard",
            "description_nl": "Aangevuld met nieuwe archieffoto's van de werf.",
            "category": "historisch-erfgoed",
        }
        resp_update = await integration_client.put(
            _url("default", f"/content/{content_id}"),
            json=update_payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert resp_update.status_code == status.HTTP_200_OK
        updated_data = resp_update.json()
        assert updated_data["title_en"] == "The Story of the Old Shipyard"
        assert updated_data["description_nl"] == "Aangevuld met nieuwe archieffoto's van de werf."
        assert updated_data["category"] == "historisch-erfgoed"

        # --------------------------------------------------------------------
        # 7. Notice & Takedown Request (P1-3 hCaptcha + P1-5 Brevo email)
        # --------------------------------------------------------------------
        takedown_payload = {
            "content_id": content_id,
            "reason": "Rechthebbende meldt dat foto niet onder CC-BY valt",
            "contact_email": "rechten@historischarchief.nl",
            "hcaptcha_token": HCAPTCHA_TEST_TOKEN,
        }
        resp_takedown = await integration_client.post(
            _url("default", "/takedown"),
            json=takedown_payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert resp_takedown.status_code == status.HTTP_201_CREATED
        takedown_id = resp_takedown.json()["id"]

        # Verify Brevo email service recorded takedown receipt confirmation
        sent_emails = brevo_email_service.sent_emails
        assert any(
            email["to_email"] == "rechten@historischarchief.nl"
            and f"#{takedown_id}" in email["subject"]
            for email in sent_emails
        )

        # --------------------------------------------------------------------
        # 8. Soft-Delete (P1-2 DELETE endpoint)
        # --------------------------------------------------------------------
        resp_delete = await integration_client.delete(
            _url("default", f"/content/{content_id}"),
            headers={"Authorization": f"Bearer {portal_admin_token}"},
        )
        assert resp_delete.status_code == status.HTTP_200_OK
        assert resp_delete.json()["status"] == "removed"

        # Verify DB status is REMOVED
        stmt = select(FoundationContent).where(FoundationContent.id == content_id)
        result = await postgres_session.execute(stmt)
        deleted_item = result.scalar_one_or_none()
        assert deleted_item is not None
        assert deleted_item.status == ContentStatus.REMOVED

        # Verify removed item is purged from public feed and map
        resp_feed_removed = await integration_client.get(_url("default", "/content"))
        removed_feed_ids = [item["id"] for item in resp_feed_removed.json()["items"]]
        assert content_id not in removed_feed_ids

        resp_map_removed = await integration_client.get(
            _url("default", f"/map/bbox?{MAP_BBOX_QUERY}")
        )
        removed_map_ids = [f["properties"]["id"] for f in resp_map_removed.json()["features"]]
        assert content_id not in removed_map_ids

        # Public detail GET now returns 404
        resp_detail_removed = await integration_client.get(
            _url("default", f"/content/{content_id}")
        )
        assert resp_detail_removed.status_code == status.HTTP_404_NOT_FOUND

    async def test_auth_and_newsletter_lifecycle(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
    ) -> None:
        """E2E flow: Magic link email dispatch -> Verification -> Newsletter subscribe/unsubscribe."""
        brevo_email_service.clear_sent_emails()

        # --------------------------------------------------------------------
        # 1. Request Magic Link (P1-3 hCaptcha + P1-5 Brevo dispatch)
        # --------------------------------------------------------------------
        magic_payload = {
            "email": portal_visitor_user.email,
            "hcaptcha_token": HCAPTCHA_TEST_TOKEN,
        }
        resp_magic = await integration_client.post(
            _url("default", "/auth/magic-link"),
            json=magic_payload,
        )
        assert resp_magic.status_code == status.HTTP_202_ACCEPTED

        # Extract token from Brevo email dispatch
        assert len(brevo_email_service.sent_emails) > 0
        email_record = next(
            e for e in brevo_email_service.sent_emails if e["to_email"] == portal_visitor_user.email
        )
        match = re.search(r"token=([A-Za-z0-9_-]+)", email_record["html_content"])
        assert match is not None, "Magic link verification token not found in dispatched email"
        raw_token = match.group(1)

        # --------------------------------------------------------------------
        # 2. Verify Magic Link Token -> Receive JWT
        # --------------------------------------------------------------------
        resp_verify = await integration_client.post(
            _url("default", "/auth/magic-link/verify"),
            json={"token": raw_token},
        )
        assert resp_verify.status_code == status.HTTP_200_OK
        verify_data = resp_verify.json()
        assert "access_token" in verify_data
        jwt_token = verify_data["access_token"]
        assert verify_data["token_type"] == "bearer"

        # Verify claims on issued JWT
        claims = jwt_handler.verify_token(jwt_token)
        assert claims is not None
        assert str(claims.get("sub")) == str(portal_visitor_user.id)
        assert claims.get("aud") == "portal"
        assert claims.get("scope") == "portal_uploader"

        # Verify token allows calling authenticated endpoint (logout)
        resp_logout = await integration_client.post(
            _url("default", "/auth/logout"),
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp_logout.status_code == status.HTTP_204_NO_CONTENT

        # --------------------------------------------------------------------
        # 3. Newsletter Subscribe -> Brevo Email -> Unsubscribe
        # --------------------------------------------------------------------
        sub_email = "nieuwsbrief_lezer@erfgoed.nl"
        resp_sub = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json={"email": sub_email, "hcaptcha_token": HCAPTCHA_TEST_TOKEN},
        )
        assert resp_sub.status_code == status.HTTP_201_CREATED

        # Verify opt-in verification email was recorded
        optin_email_record = next(
            e for e in brevo_email_service.sent_emails if e["to_email"] == sub_email
        )
        assert "Bevestig uw inschrijving" in optin_email_record["subject"]

        # Extract confirm token from opt-in email
        confirm_match = re.search(r"token=([A-Za-z0-9_-]+)", optin_email_record["html_content"])
        assert confirm_match is not None, "Confirm token not found in newsletter opt-in email"
        confirm_token = confirm_match.group(1)

        # Confirm subscription via double opt-in
        resp_confirm = await integration_client.post(
            _url("default", "/newsletter/confirm"),
            json={"email": sub_email, "token": confirm_token},
        )
        assert resp_confirm.status_code == status.HTTP_200_OK

        # Verify welcome email was dispatched after confirmation
        welcome_emails = [
            e
            for e in brevo_email_service.sent_emails
            if e["to_email"] == sub_email and "Welkom bij de nieuwsbrief" in e["subject"]
        ]
        assert len(welcome_emails) > 0
        welcome_record = welcome_emails[0]

        # Extract unsubscribe token from welcome email
        unsub_match = re.search(r"token=([A-Za-z0-9_-]+)", welcome_record["html_content"])
        assert unsub_match is not None, "Unsubscribe token not found in newsletter welcome email"
        unsub_token = unsub_match.group(1)

        # Unsubscribe
        resp_unsub = await integration_client.post(
            _url("default", "/newsletter/unsubscribe"),
            json={"email": sub_email, "token": unsub_token},
        )
        assert resp_unsub.status_code == status.HTTP_200_OK
        assert "Unsubscribe request received" in resp_unsub.json()["message"]

