"""Unit tests for BE-EP-051 Foundation Notice & Takedown Curation Endpoints.

Validates schema validation, status transitions, content takedown logic,
reversal/restore capabilities, and tenant-scoped curation queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.core.api.v1.foundation.schemas import (
    TakedownDetailResponse,
    TakedownListItem,
    TakedownListResponse,
    TakedownResolveRequest,
    TakedownResolveResponse,
)
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    PortalRole,
    PortalUser,
    TakedownRequest,
    TakedownStatus,
)
from src.core.shared.datetime_utils import utc_now


# ============================================================================
# 1. Schema Validation Tests
# ============================================================================


class TestTakedownCurationSchemas:
    @pytest.mark.unit
    def test_takedown_list_item_valid(self) -> None:
        now = utc_now()
        item = TakedownListItem(
            id=1,
            content_id=42,
            content_title="Historische Foto van Haven",
            content_type="artwork",
            content_status="approved",
            requester_name="Jan Jansen",
            requester_email="jan@example.com",
            legal_basis="Auteursrechtinbreuk op foto uit familiearchief",
            status="pending",
            resolution_note=None,
            resolved_at=None,
            created_at=now,
        )
        assert item.id == 1
        assert item.content_id == 42
        assert item.content_title == "Historische Foto van Haven"
        assert item.status == "pending"

    @pytest.mark.unit
    def test_takedown_list_response_valid(self) -> None:
        now = utc_now()
        item = TakedownListItem(
            id=1,
            content_id=42,
            content_title="Verhaal",
            content_type="story",
            content_status="approved",
            requester_name="A. B.",
            requester_email="ab@example.com",
            legal_basis="Portretrecht",
            status="pending",
            created_at=now,
        )
        res = TakedownListResponse(
            items=[item],
            total=1,
            page=1,
            page_size=20,
            status_filter="pending",
        )
        assert res.total == 1
        assert len(res.items) == 1
        assert res.items[0].content_id == 42

    @pytest.mark.unit
    def test_takedown_detail_response_valid(self) -> None:
        now = utc_now()
        detail = TakedownDetailResponse(
            id=1,
            content_id=42,
            content_title="Document archief",
            content_type="document",
            content_status="approved",
            content_description="Oude akte",
            content_creator_name="Onbekend",
            content_file_url="https://blob.example.com/item.pdf",
            requester_name="Rechthebbende",
            requester_email="recht@example.com",
            legal_basis="Inbreuk op auteursrechten",
            status="pending",
            resolution_note=None,
            resolved_at=None,
            created_at=now,
        )
        assert detail.id == 1
        assert detail.content_file_url == "https://blob.example.com/item.pdf"

    @pytest.mark.unit
    def test_takedown_resolve_request_valid(self) -> None:
        req = TakedownResolveRequest(
            status=TakedownStatus.APPROVED,
            resolution_note="Auteursrechtclaim geverifieerd en gegrond verklaard.",
            notify_requester=True,
        )
        assert req.status == TakedownStatus.APPROVED
        assert "gegrond" in req.resolution_note
        assert req.notify_requester is True

    @pytest.mark.unit
    def test_takedown_resolve_request_rejects_empty_or_short_note(self) -> None:
        with pytest.raises(ValidationError):
            TakedownResolveRequest(
                status=TakedownStatus.APPROVED,
                resolution_note="kort",  # < 5 tekens
            )

    @pytest.mark.unit
    def test_takedown_resolve_response_valid(self) -> None:
        res = TakedownResolveResponse(
            id=1,
            content_id=42,
            status="approved",
            content_status="removed",
            resolution_note="Content verwijderd conform art. 6:196c BW.",
            resolved_at=utc_now(),
            message="Notice & Takedown melding succesvol afgehandeld.",
        )
        assert res.status == "approved"
        assert res.content_status == "removed"


# ============================================================================
# 2. Endpoint Authorization & Tenant Isolation Unit Tests
# ============================================================================


class TestTakedownCurationEndpoints:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_takedowns_requires_curator_role(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import get_curatie_takedowns

        curator = PortalUser(
            id=1,
            tenant_id=1,
            email="curator@example.com",
            role=PortalRole.CURATOR,
        )

        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")

        with patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            # Mock DB results
            mock_session.execute.side_effect = [
                MagicMock(scalar=lambda: 0),  # total count
                MagicMock(all=lambda: []),  # items
            ]

            # Curator success
            res = await get_curatie_takedowns(
                tenantSlug="erfgoed",
                status=None,
                page=1,
                page_size=20,
                current_user=curator,
                session=mock_session,
            )
            assert res.total == 0
            assert res.items == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_takedowns_cross_tenant_forbidden(self) -> None:
        from fastapi import HTTPException
        from src.core.api.v1.foundation.admin.curatie import get_curatie_takedowns

        curator_other_tenant = PortalUser(
            id=1,
            tenant_id=2,  # Tenant 2
            email="curator@other.com",
            role=PortalRole.CURATOR,
        )
        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")  # Tenant 1

        with patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            with pytest.raises(HTTPException) as exc_info:
                await get_curatie_takedowns(
                    tenantSlug="erfgoed",
                    status=None,
                    page=1,
                    page_size=20,
                    current_user=curator_other_tenant,
                    session=mock_session,
                )
            assert exc_info.value.status_code == 403
            assert "User does not belong to this tenant" in exc_info.value.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resolve_takedown_approve_removes_content(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import resolve_curatie_takedown

        curator = PortalUser(
            id=1,
            tenant_id=1,
            email="curator@example.com",
            role=PortalRole.CURATOR,
        )
        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed", name="Erfgoed Stichting")

        content = FoundationContent(
            id=42,
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Betwist Verhaal",
            status=ContentStatus.APPROVED,
        )
        takedown = TakedownRequest(
            id=10,
            tenant_id=1,
            content_id=42,
            requester_name="Melder",
            requester_email="melder@example.com",
            legal_basis="Schending portretrecht",
            status=TakedownStatus.PENDING,
        )

        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: takedown),  # takedown lookup
            MagicMock(scalar_one_or_none=lambda: content),  # content lookup
        ]

        payload = TakedownResolveRequest(
            status=TakedownStatus.APPROVED,
            resolution_note="Portretrecht vastgesteld; item offline gehaald.",
            notify_requester=True,
        )

        with (
            patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope,
            patch(
                "src.core.api.v1.foundation.admin.curatie.brevo_email_service.send_takedown_resolution",
                new_callable=AsyncMock,
            ) as mock_brevo,
            patch(
                "src.core.api.v1.foundation.admin.curatie.AuditService.log_event",
                new_callable=AsyncMock,
            ) as mock_audit,
        ):
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            res = await resolve_curatie_takedown(
                takedown_id=10,
                tenantSlug="erfgoed",
                data=payload,
                current_user=curator,
                session=mock_session,
            )

            assert res.status == "approved"
            assert res.content_status == "removed"
            assert takedown.status == TakedownStatus.APPROVED
            assert content.status == ContentStatus.REMOVED
            assert content.takedown_reason == "Portretrecht vastgesteld; item offline gehaald."
            assert content.takedown_at is not None
            mock_brevo.assert_awaited_once()
            mock_audit.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resolve_takedown_reject_keeps_content_active(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import resolve_curatie_takedown

        curator = PortalUser(
            id=1,
            tenant_id=1,
            email="curator@example.com",
            role=PortalRole.CURATOR,
        )
        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed", name="Erfgoed Stichting")

        content = FoundationContent(
            id=42,
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Publiek Verhaal",
            status=ContentStatus.APPROVED,
        )
        takedown = TakedownRequest(
            id=10,
            tenant_id=1,
            content_id=42,
            requester_name="Melder",
            requester_email="melder@example.com",
            legal_basis="Vermeende inbreuk",
            status=TakedownStatus.PENDING,
        )

        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: takedown),  # takedown lookup
            MagicMock(scalar_one_or_none=lambda: content),  # content lookup
        ]

        payload = TakedownResolveRequest(
            status=TakedownStatus.REJECTED,
            resolution_note="Onvoldoende bewijs geleverd; content is publiek domein.",
            notify_requester=True,
        )

        with (
            patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope,
            patch(
                "src.core.api.v1.foundation.admin.curatie.brevo_email_service.send_takedown_resolution",
                new_callable=AsyncMock,
            ) as mock_brevo,
            patch(
                "src.core.api.v1.foundation.admin.curatie.AuditService.log_event",
                new_callable=AsyncMock,
            ) as mock_audit,
        ):
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            res = await resolve_curatie_takedown(
                takedown_id=10,
                tenantSlug="erfgoed",
                data=payload,
                current_user=curator,
                session=mock_session,
            )

            assert res.status == "rejected"
            assert res.content_status == "approved"
            assert takedown.status == TakedownStatus.REJECTED
            assert content.status == ContentStatus.APPROVED
            mock_brevo.assert_awaited_once()
            mock_audit.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_restore_removed_content(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import restore_content

        curator = PortalUser(
            id=1,
            tenant_id=1,
            email="curator@example.com",
            role=PortalRole.CURATOR,
        )
        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")

        content = FoundationContent(
            id=42,
            tenant_id=1,
            type=ContentType.STORY,
            title_nl="Hersteld Verhaal",
            status=ContentStatus.REMOVED,
            takedown_reason="Eerdere melding",
            takedown_at=utc_now(),
        )

        mock_session.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: content),  # lookup
            MagicMock(scalar_one=lambda: content),  # refreshed
        ]

        with (
            patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope,
            patch(
                "src.core.api.v1.foundation.admin.curatie.AuditService.log_event",
                new_callable=AsyncMock,
            ) as mock_audit,
        ):
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            res = await restore_content(
                content_id=42,
                tenantSlug="erfgoed",
                current_user=curator,
                session=mock_session,
            )

            assert content.status == ContentStatus.APPROVED
            assert content.takedown_reason is None
            assert content.takedown_at is None
            mock_audit.assert_awaited_once()
