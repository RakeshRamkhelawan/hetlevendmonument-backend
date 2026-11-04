"""Unit tests for FoundationTaggingService (ADR-029 P1-1, BE-EP-041)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    ContentTag,
    FoundationContent,
    Privacy,
    TagType,
    Visibility,
)
from src.core.services.foundation_tagging_service import (
    FoundationTaggingService,
    MAX_BODY_CHARS,
)


@pytest.fixture
def tagging_service() -> FoundationTaggingService:
    return FoundationTaggingService()


def test_clean_json_text(tagging_service: FoundationTaggingService) -> None:
    """Test extracting JSON from various LLM response formats."""
    # 1. Plain JSON
    raw = '{"tags": [{"tag_type": "theme", "value": "Visserij", "confidence": 0.9}]}'
    assert tagging_service._clean_json_text(raw) == raw

    # 2. Markdown fenced JSON
    fenced = (
        '```json\n{"tags": [{"tag_type": "theme", "value": "Visserij", "confidence": 0.9}]}\n```'
    )
    assert tagging_service._clean_json_text(fenced) == raw

    # 3. Surrounding chatter
    chatter = 'Hier zijn de tags:\n{"tags": [{"tag_type": "theme", "value": "Visserij", "confidence": 0.9}]}\nSucces!'
    assert tagging_service._clean_json_text(chatter) == raw


def test_fallback_extract_war_theme(tagging_service: FoundationTaggingService) -> None:
    """Test heuristic keyword fallback for WW2 themes."""
    tags = tagging_service._fallback_extract(
        title="Bommen op de stad in 1944",
        description="Een ooggetuigenverslag van de bezetting",
        body="Tijdens de oorlog was er veel angst.",
        location_hint="Vlaardingen",
    )
    types = {t["tag_type"] for t in tags}
    values = {t["value"] for t in tags}

    assert TagType.THEME.value in types
    assert TagType.LOCATION.value in types
    assert TagType.PERIOD.value in types
    assert TagType.LANGUAGE.value in types

    assert "Tweede Wereldoorlog" in values
    assert "1940-1945" in values
    assert "Vlaardingen" in values


def test_fallback_extract_fishery_theme(tagging_service: FoundationTaggingService) -> None:
    """Test heuristic keyword fallback for fishery themes."""
    tags = tagging_service._fallback_extract(
        title="Varen met de haringlogger",
        description="Vissers op zee",
        body="We voeren de haven uit om te vissen.",
        location_hint="Vlaardingen",
    )
    values = {t["value"] for t in tags}
    assert "Visserij" in values
    assert "Vlaardingen" in values


@pytest.mark.asyncio
async def test_extract_tags_from_text_llm_success(
    tagging_service: FoundationTaggingService,
) -> None:
    """Test successful LLM tag extraction."""
    llm_payload = {
        "tags": [
            {"tag_type": "theme", "value": "Scheepsbouw", "confidence": 0.95},
            {"tag_type": "location", "value": "Oude Haven", "confidence": 0.90},
            {"tag_type": "period", "value": "Wederopbouwperiode", "confidence": 0.85},
            {"tag_type": "sentiment", "value": "trots", "confidence": 0.80},
            {"tag_type": "language", "value": "nl", "confidence": 1.0},
            {"tag_type": "invalid_type", "value": "ignored", "confidence": 0.5},
        ],
        "moderation_score": 0.03,
    }

    taalmodel = MagicMock()
    taalmodel.tekst = AsyncMock(return_value=json.dumps(llm_payload))

    with patch(
        "src.core.services.foundation_tagging_service.TenantTaalmodel",
        return_value=taalmodel,
    ):
        tags, mod_score = await tagging_service.extract_tags_from_text(
            title="De werf aan de haven",
            description="Geschiedenis van de scheepswerf",
            body="Jarenlang bouwden vakmensen hier schepen.",
            tenant_id=7,
        )

    assert mod_score == 0.03
    assert len(tags) == 5  # "invalid_type" should be discarded
    tag_types = [t["tag_type"] for t in tags]
    assert "invalid_type" not in tag_types
    assert TagType.THEME.value in tag_types
    assert TagType.LOCATION.value in tag_types


@pytest.mark.asyncio
async def test_extract_tags_from_text_llm_error_fallback(
    tagging_service: FoundationTaggingService,
) -> None:
    """Test graceful fallback when LLM throws an exception."""
    taalmodel = MagicMock()
    taalmodel.tekst = AsyncMock(side_effect=TimeoutError("LLM API timed out"))

    with patch(
        "src.core.services.foundation_tagging_service.TenantTaalmodel",
        return_value=taalmodel,
    ):
        tags, mod_score = await tagging_service.extract_tags_from_text(
            title="De oude schoolklas",
            description="Mijn leraar vertelde verhalen",
            body="Herinnering aan vroeger.",
        )

    assert mod_score is None
    values = {t["value"] for t in tags}
    assert "Onderwijs" in values
    assert "nostalgisch" in values


@pytest.mark.asyncio
async def test_extract_tags_uses_the_model_of_the_given_tenant(
    tagging_service: FoundationTaggingService,
) -> None:
    """De deur wordt geopend voor DE tenant van het item, niet voor de platformstandaard."""
    taalmodel = MagicMock()
    taalmodel.tekst = AsyncMock(return_value='{"tags": []}')

    with patch(
        "src.core.services.foundation_tagging_service.TenantTaalmodel",
        return_value=taalmodel,
    ) as deur:
        await tagging_service.extract_tags_from_text(
            title="Titel", description=None, body=None, tenant_id=7
        )

    deur.assert_called_once_with(7)


@pytest.mark.asyncio
async def test_tag_content_success(tagging_service: FoundationTaggingService) -> None:
    """Test tag_content persisting tags and updating status."""
    content = FoundationContent(
        id=42,
        tenant_id=1,
        title_nl="Vlaardings erfgoed",
        description_nl="Een mooi verhaal",
        body_nl="Over vissers en de haven.",
        status=ContentStatus.PENDING,
        type=ContentType.STORY,
        visibility=Visibility.PUBLIC,
        privacy=Privacy.PUBLIC,
        ai_tagging_failed=True,
    )

    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=content))

    mock_tags = [
        {"tag_type": "theme", "value": "Visserij", "confidence": 0.90},
        {"tag_type": "location", "value": "Vlaardingen", "confidence": 0.85},
    ]

    with patch.object(
        tagging_service,
        "extract_tags_from_text",
        return_value=(mock_tags, 0.01),
    ):
        result_tags = await tagging_service.tag_content(
            content_id=42,
            tenant_id=1,
            session=session,
        )

    assert len(result_tags) == 2
    assert content.ai_tagging_failed is False
    assert content.moderation_score == 0.01
    assert session.add.call_count == 2
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_tag_content_not_found(tagging_service: FoundationTaggingService) -> None:
    """Test tag_content returns empty list when content item not found."""
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    result = await tagging_service.tag_content(
        content_id=999,
        tenant_id=1,
        session=session,
    )

    assert result == []
