"""Offline unit tests for BE-EP-038 anonymous masking.

Covers the pure helper apply_anonymity_mask and the Pydantic model
validators on FoundationContentListItem / FoundationContentDetail. No DB,
no HTTP: these run anywhere and pin the masking rule itself.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.core.api.v1.foundation.schemas import (
    FoundationContentDetail,
    FoundationContentListItem,
    apply_anonymity_mask,
)

NOW = datetime.now(timezone.utc)


class TestApplyAnonymityMask:
    """Pure helper behavior."""

    def test_anonymous_masks_name(self) -> None:
        assert apply_anonymity_mask(True, "Anonieme Schrijver") is None

    def test_non_anonymous_keeps_name(self) -> None:
        assert apply_anonymity_mask(False, "Schrijver Met Naam") == "Schrijver Met Naam"

    def test_none_name_stays_none(self) -> None:
        assert apply_anonymity_mask(False, None) is None
        assert apply_anonymity_mask(True, None) is None

    def test_empty_string_not_masked_when_not_anonymous(self) -> None:
        # Only the anonymity flag masks; empty strings pass through unchanged.
        assert apply_anonymity_mask(False, "") == ""


class TestListItemMasking:
    """FoundationContentListItem masks creator_name after validation."""

    def test_anonymous_item_has_null_creator_name(self) -> None:
        item = FoundationContentListItem.model_validate(
            {
                "id": 1,
                "type": "story",
                "title_nl": "Getuigenis",
                "creator_name": "Verborgen Naam",
                "is_anonymous": True,
                "status": "approved",
                "created_at": NOW,
            }
        )
        assert item.creator_name is None
        # is_anonymous stays visible in the response (spec O3).
        assert item.is_anonymous is True

    def test_non_anonymous_item_keeps_creator_name(self) -> None:
        item = FoundationContentListItem.model_validate(
            {
                "id": 2,
                "type": "artwork",
                "title_nl": "Kunstwerk",
                "creator_name": "Kunstenaar",
                "is_anonymous": False,
                "status": "approved",
                "created_at": NOW,
            }
        )
        assert item.creator_name == "Kunstenaar"

    def test_default_non_anonymous_without_name(self) -> None:
        item = FoundationContentListItem.model_validate(
            {
                "id": 3,
                "type": "poetry",
                "title_nl": "Gedicht",
                "created_at": NOW,
            }
        )
        assert item.creator_name is None
        assert item.is_anonymous is False


class TestDetailMasking:
    """FoundationContentDetail masks creator_name after validation.

    This validator also covers endpoints that return the ORM object
    directly with response_model=FoundationContentDetail (spec O2), e.g.
    get_content and the admin approve/reject responses.
    """

    def test_anonymous_detail_has_null_creator_name(self) -> None:
        detail = FoundationContentDetail.model_validate(
            {
                "id": 10,
                "tenant_id": 1,
                "type": "story",
                "title_nl": "Anoniem verhaal",
                "creator_name": "Verborgen Naam",
                "is_anonymous": True,
                "status": "approved",
                "privacy": "public",
                "created_at": NOW,
            }
        )
        assert detail.creator_name is None
        assert detail.is_anonymous is True

    def test_non_anonymous_detail_keeps_creator_name(self) -> None:
        detail = FoundationContentDetail.model_validate(
            {
                "id": 11,
                "tenant_id": 1,
                "type": "audio",
                "title_nl": "Interview",
                "creator_name": "Verteller",
                "is_anonymous": False,
                "status": "approved",
                "privacy": "public",
                "created_at": NOW,
            }
        )
        assert detail.creator_name == "Verteller"
