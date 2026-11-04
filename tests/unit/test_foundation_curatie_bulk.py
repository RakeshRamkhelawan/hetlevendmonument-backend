"""Unit tests for BE-EP-053 Foundation Bulk Curation Endpoints.

Validates schema validation, bulk approval, bulk rejection with DSA Art. 17 statement
of reasons, partial success semantics, RBAC enforcement, and tenant isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.core.api.v1.foundation.schemas import (
    BulkApproveRequest,
    BulkFailedItem,
    BulkModerationResponse,
    BulkRejectRequest,
)
from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationContent,
    PortalRole,
    PortalUser,
)


# ============================================================================
# 1. Schema Validation Tests
# ============================================================================


class TestBulkCurationSchemas:
    @pytest.mark.unit
    def test_bulk_approve_request_valid(self) -> None:
        req = BulkApproveRequest(content_ids=[1, 2, 3])
        assert req.content_ids == [1, 2, 3]

    @pytest.mark.unit
    def test_bulk_approve_request_empty_fails(self) -> None:
        with pytest.raises(ValidationError):
            BulkApproveRequest(content_ids=[])

    @pytest.mark.unit
    def test_bulk_approve_request_over_100_fails(self) -> None:
        with pytest.raises(ValidationError):
            BulkApproveRequest(content_ids=list(range(1, 102)))

    @pytest.mark.unit
    def test_bulk_reject_request_valid(self) -> None:
        req = BulkRejectRequest(
            content_ids=[10, 20],
            rejection_reason="In strijd met de erfgoedvoorwaarden van het portaal.",
        )
        assert req.content_ids == [10, 20]
        assert "erfgoedvoorwaarden" in req.rejection_reason

    @pytest.mark.unit
    def test_bulk_reject_request_short_reason_fails(self) -> None:
        with pytest.raises(ValidationError):
            BulkRejectRequest(content_ids=[1], rejection_reason="Nee")

    @pytest.mark.unit
    def test_bulk_reject_request_empty_list_fails(self) -> None:
        with pytest.raises(ValidationError):
            BulkRejectRequest(content_ids=[], rejection_reason="Geldige reden van minimaal 5 tekens")

    @pytest.mark.unit
    def test_bulk_moderation_response_structure(self) -> None:
        res = BulkModerationResponse(
            total_requested=3,
            processed_count=3,
            success_ids=[1, 2],
            failed_items=[BulkFailedItem(id=3, reason="Niet gevonden")],
            message="2 goedgekeurd, 1 overgeslagen.",
        )
        assert res.total_requested == 3
        assert res.success_ids == [1, 2]
        assert len(res.failed_items) == 1
        assert res.failed_items[0].id == 3


# ============================================================================
# 2. Bulk Approve Endpoint Unit Tests
# ============================================================================


class TestBulkApproveEndpoints:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_approve_all_success(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import bulk_approve_content

        curator = PortalUser(id=1, tenant_id=1, email="curator@example.com", role=PortalRole.CURATOR)
        item1 = FoundationContent(id=10, tenant_id=1, status=ContentStatus.PENDING, type=ContentType.STORY, title_nl="V1")
        item2 = FoundationContent(id=11, tenant_id=1, status=ContentStatus.PENDING, type=ContentType.STORY, title_nl="V2")

        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")

        with patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            mock_session.execute.return_value = MagicMock(
                scalars=lambda: MagicMock(all=lambda: [item1, item2])
            )

            req = BulkApproveRequest(content_ids=[10, 11])
            res = await bulk_approve_content(
                tenantSlug="erfgoed",
                data=req,
                current_user=curator,
                session=mock_session,
            )

            assert res.total_requested == 2
            assert res.processed_count == 2
            assert res.success_ids == [10, 11]
            assert len(res.failed_items) == 0
            assert item1.status == ContentStatus.APPROVED
            assert item2.status == ContentStatus.APPROVED
            mock_session.flush.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_approve_partial_success(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import bulk_approve_content

        curator = PortalUser(id=1, tenant_id=1, email="curator@example.com", role=PortalRole.CURATOR)
        # item1 is pending, item2 is al approved
        item1 = FoundationContent(id=10, tenant_id=1, status=ContentStatus.PENDING, type=ContentType.STORY, title_nl="V1")
        item2 = FoundationContent(id=11, tenant_id=1, status=ContentStatus.APPROVED, type=ContentType.STORY, title_nl="V2")
        # item 12 bestaat niet

        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")

        with patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            mock_session.execute.return_value = MagicMock(
                scalars=lambda: MagicMock(all=lambda: [item1, item2])
            )

            req = BulkApproveRequest(content_ids=[10, 11, 12])
            res = await bulk_approve_content(
                tenantSlug="erfgoed",
                data=req,
                current_user=curator,
                session=mock_session,
            )

            assert res.total_requested == 3
            assert res.processed_count == 3
            assert res.success_ids == [10]
            assert len(res.failed_items) == 2

            failed_dict = {f.id: f.reason for f in res.failed_items}
            assert 11 in failed_dict
            assert "approved" in failed_dict[11].lower()
            assert 12 in failed_dict
            assert "niet gevonden" in failed_dict[12].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_approve_cross_tenant_forbidden(self) -> None:
        from fastapi import HTTPException
        from src.core.api.v1.foundation.admin.curatie import bulk_approve_content

        curator_other_tenant = PortalUser(id=1, tenant_id=2, email="curator@example.com", role=PortalRole.CURATOR)
        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")

        with patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            req = BulkApproveRequest(content_ids=[10])
            with pytest.raises(HTTPException) as exc_info:
                await bulk_approve_content(
                    tenantSlug="erfgoed",
                    data=req,
                    current_user=curator_other_tenant,
                    session=mock_session,
                )
            assert exc_info.value.status_code == 403


# ============================================================================
# 3. Bulk Reject Endpoint Unit Tests
# ============================================================================


class TestBulkRejectEndpoints:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_reject_all_success(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import bulk_reject_content

        curator = PortalUser(id=1, tenant_id=1, email="curator@example.com", role=PortalRole.CURATOR)
        item1 = FoundationContent(id=20, tenant_id=1, status=ContentStatus.PENDING, type=ContentType.STORY, title_nl="V3")
        item2 = FoundationContent(id=21, tenant_id=1, status=ContentStatus.PENDING, type=ContentType.STORY, title_nl="V4")

        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")

        with patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            mock_session.execute.return_value = MagicMock(
                scalars=lambda: MagicMock(all=lambda: [item1, item2])
            )

            req = BulkRejectRequest(
                content_ids=[20, 21],
                rejection_reason="Onvoldoende historische context conform collectiebeleid.",
            )
            res = await bulk_reject_content(
                tenantSlug="erfgoed",
                data=req,
                current_user=curator,
                session=mock_session,
            )

            assert res.total_requested == 2
            assert res.processed_count == 2
            assert res.success_ids == [20, 21]
            assert len(res.failed_items) == 0
            assert item1.status == ContentStatus.REJECTED
            assert item1.rejection_reason == "Onvoldoende historische context conform collectiebeleid."
            assert item2.status == ContentStatus.REJECTED
            assert item2.rejection_reason == "Onvoldoende historische context conform collectiebeleid."
            mock_session.flush.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_bulk_reject_partial_success(self) -> None:
        from src.core.api.v1.foundation.admin.curatie import bulk_reject_content

        curator = PortalUser(id=1, tenant_id=1, email="curator@example.com", role=PortalRole.CURATOR)
        item1 = FoundationContent(id=20, tenant_id=1, status=ContentStatus.PENDING, type=ContentType.STORY, title_nl="V3")
        # item 99 bestaat niet

        mock_session = AsyncMock()
        mock_tenant = MagicMock(id=1, slug="erfgoed")

        with patch("src.core.api.v1.foundation.admin.curatie.public_tenant_scope") as mock_scope:
            mock_scope.return_value.__aenter__.return_value = mock_tenant

            mock_session.execute.return_value = MagicMock(
                scalars=lambda: MagicMock(all=lambda: [item1])
            )

            req = BulkRejectRequest(
                content_ids=[20, 99],
                rejection_reason="Niet relevant voor de canon.",
            )
            res = await bulk_reject_content(
                tenantSlug="erfgoed",
                data=req,
                current_user=curator,
                session=mock_session,
            )

            assert res.total_requested == 2
            assert res.processed_count == 2
            assert res.success_ids == [20]
            assert len(res.failed_items) == 1
            assert res.failed_items[0].id == 99
            assert item1.status == ContentStatus.REJECTED
