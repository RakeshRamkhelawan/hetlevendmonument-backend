"""De lijstweergave geeft de doelgroep van lesmateriaal mee (educatieve omgeving groepeert erop)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.core.api.v1.foundation.schemas import FoundationContentListItem

pytestmark = [pytest.mark.unit]


def _item(**extra: object) -> FoundationContentListItem:
    return FoundationContentListItem.model_validate(
        {
            "id": 7,
            "type": "educational_workbook",
            "title_nl": "Werkblad groep 7-8, les 1: Schiedam, 1602",
            "status": "approved",
            "created_at": datetime(2026, 11, 2, tzinfo=timezone.utc),
            **extra,
        }
    )


def test_doelgroep_staat_in_het_lijstitem() -> None:
    assert _item(target_age_group="groep-7-8").model_dump()["target_age_group"] == "groep-7-8"


def test_zonder_doelgroep_is_het_veld_leeg() -> None:
    assert _item().target_age_group is None
