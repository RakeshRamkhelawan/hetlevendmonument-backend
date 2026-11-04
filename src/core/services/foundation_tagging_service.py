"""Foundation content AI tagging service (ADR-029 P1-1, BE-EP-041).

Extracts semantic heritage metadata (theme, location, period, sentiment, language)
from FoundationContent stories, artwork, and audio items using LLM inference with
graceful degradation and fallback according to Netwerk Digitaal Erfgoed (NDE) standards.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypedDict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.models.foundation_content import (
    ContentTag,
    FoundationContent,
    TagType,
)

logger = logging.getLogger(__name__)

# Maximum characters of story body to send to LLM to prevent memory and token exhaustion
MAX_BODY_CHARS: int = 4000

# Regex for extracting JSON from potential markdown code fences
JSON_BLOCK_REGEX = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class TagDict(TypedDict):
    tag_type: str
    value: str
    confidence: float


class FoundationTaggingService:
    """Service for automated AI-tagging of cultural heritage content."""

    def __init__(self) -> None:
        self._tag_type_values = {t.value for t in TagType}

    def _clean_json_text(self, text: str) -> str:
        """Extract valid JSON from LLM output, handling markdown fences if present."""
        match = JSON_BLOCK_REGEX.search(text)
        if match:
            return match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
        return text.strip()

    def _fallback_extract(
        self,
        title: str,
        description: str | None,
        body: str | None,
        location_hint: str | None = None,
    ) -> list[TagDict]:
        """Deterministic keyword-based heuristic fallback when LLM is unavailable."""
        combined = f"{title} {description or ''} {body or ''} {location_hint or ''}".lower()
        tags: list[TagDict] = []

        # Location heuristic
        if location_hint:
            tags.append(
                {
                    "tag_type": TagType.LOCATION.value,
                    "value": location_hint.strip()[:100],
                    "confidence": 0.85,
                }
            )
        elif "vlaardingen" in combined:
            tags.append(
                {
                    "tag_type": TagType.LOCATION.value,
                    "value": "Vlaardingen",
                    "confidence": 0.80,
                }
            )

        # Theme heuristics (common heritage themes)
        if any(w in combined for w in ["oorlog", "bezetting", "bevrijding", "1940", "1945"]):
            tags.append(
                {
                    "tag_type": TagType.THEME.value,
                    "value": "Tweede Wereldoorlog",
                    "confidence": 0.85,
                }
            )
            tags.append(
                {
                    "tag_type": TagType.PERIOD.value,
                    "value": "1940-1945",
                    "confidence": 0.85,
                }
            )
        elif any(w in combined for w in ["vis", "visserij", "haring", "logger", "haven"]):
            tags.append(
                {
                    "tag_type": TagType.THEME.value,
                    "value": "Visserij",
                    "confidence": 0.85,
                }
            )
        elif any(w in combined for w in ["school", "onderwijs", "klas", "leraar", "meester"]):
            tags.append(
                {
                    "tag_type": TagType.THEME.value,
                    "value": "Onderwijs",
                    "confidence": 0.75,
                }
            )
        else:
            tags.append(
                {
                    "tag_type": TagType.THEME.value,
                    "value": "Lokaal erfgoed",
                    "confidence": 0.70,
                }
            )

        # Sentiment heuristic
        if any(w in combined for w in ["herinnering", "vroeger", "toen", "heimwee"]):
            tags.append(
                {
                    "tag_type": TagType.SENTIMENT.value,
                    "value": "nostalgisch",
                    "confidence": 0.75,
                }
            )
        else:
            tags.append(
                {
                    "tag_type": TagType.SENTIMENT.value,
                    "value": "herinnerend",
                    "confidence": 0.65,
                }
            )

        # Language tag
        tags.append(
            {
                "tag_type": TagType.LANGUAGE.value,
                "value": "nl",
                "confidence": 0.99,
            }
        )

        return tags

    async def extract_tags_from_text(
        self,
        title: str,
        description: str | None,
        body: str | None,
        location_hint: str | None = None,
        category_hint: str | None = None,
        tenant_id: int | None = None,
    ) -> tuple[list[TagDict], float | None]:
        """Call LLM service to extract structured heritage tags.

        Het model loopt via `TenantTaalmodel(tenant_id)` (ADR-041 B14): de tekst van een
        inzending is tenantdata en gaat naar het model dat DEZE tenant heeft gekozen.

        Returns (tags_list, moderation_score).
        """
        truncated_body = (body or "")[:MAX_BODY_CHARS]
        prompt = f"""Je bent een erfgoedexpert en metadata-annotator voor het Levend Monument conform de standaarden van het Netwerk Digitaal Erfgoed (NDE).
Analyseer het onderstaande erfgoeditem en extraheer gestructureerde metadata-tags volgens de 5 geldige types:
- theme: cultureel of historisch thema (max 3 tags, bijv. "Tweede Wereldoorlog", "Visserij", "Wederopbouw", "Scheepsbouw", "Onderwijs", "Kunst")
- location: geografische of historische locatie in Nederland (max 3 tags, bijv. "Vlaardingen", "Oude Haven", "Maasboulevard")
- period: historisch tijdvak of jaartal (max 2 tags, bijv. "1940-1945", "19e eeuw", "Wederopbouwperiode", "Jaren '70")
- sentiment: emotionele toonsoort of beleving (max 2 tags, bijv. "nostalgisch", "hoopvol", "verdrietig", "feestelijk", "plechtig")
- language: primaire taalcode (exact 1 tag, bijv. "nl", "en")

Geef per tag een confidence score tussen 0.0 en 1.0. Schat tevens een optionele moderation_score (0.0 = volkomen veilig, 1.0 = ongepast/haatdragend).
Retourneer UITSLUITEND een geldig JSON-object in exact dit formaat:
{{
  "tags": [
    {{"tag_type": "theme", "value": "Visserij", "confidence": 0.95}},
    {{"tag_type": "location", "value": "Vlaardingen", "confidence": 0.90}},
    {{"tag_type": "period", "value": "19e eeuw", "confidence": 0.85}},
    {{"tag_type": "sentiment", "value": "nostalgisch", "confidence": 0.80}},
    {{"tag_type": "language", "value": "nl", "confidence": 1.0}}
  ],
  "moderation_score": 0.02
}}

TE ANALYSEREN ERFGOEDITEM:
Titel: {title}
Categorie: {category_hint or "onbekend"}
Locatiehint: {location_hint or "onbekend"}
Beschrijving: {description or "geen"}
Inhoud: {truncated_body}
"""
        try:
            text_response = await TenantTaalmodel(tenant_id).tekst(prompt)

            clean_json = self._clean_json_text(text_response)
            parsed = json.loads(clean_json)

            raw_tags = parsed.get("tags", [])
            moderation_score = parsed.get("moderation_score")
            if moderation_score is not None:
                try:
                    moderation_score = float(moderation_score)
                    moderation_score = max(0.0, min(1.0, moderation_score))
                except (ValueError, TypeError):
                    moderation_score = None

            validated_tags: list[TagDict] = []
            for t in raw_tags:
                if not isinstance(t, dict):
                    continue
                tag_type = str(t.get("tag_type", "")).lower().strip()
                if tag_type not in self._tag_type_values:
                    continue
                val = str(t.get("value", "")).strip()
                if not val:
                    continue
                val = val[:100]
                try:
                    conf = float(t.get("confidence", 0.7))
                except (ValueError, TypeError):
                    conf = 0.7
                conf = max(0.0, min(1.0, conf))

                validated_tags.append(
                    {
                        "tag_type": tag_type,
                        "value": val,
                        "confidence": conf,
                    }
                )

            if validated_tags:
                return validated_tags, moderation_score

            logger.info("LLM returned no valid tags, falling back to heuristic tags")
            return self._fallback_extract(title, description, body, location_hint), 0.0

        except Exception as e:
            logger.warning(
                "LLM tag extraction failed or timed out: %s. Using heuristic fallback.", e
            )
            return self._fallback_extract(title, description, body, location_hint), None

    async def tag_content(
        self,
        content_id: int,
        tenant_id: int,
        session: AsyncSession,
    ) -> list[ContentTag]:
        """Tag a FoundationContent item within tenant boundary.

        - Loads content item
        - Extracts tags
        - Replaces previous AI tags (keeps is_manual=True tags)
        - Updates ai_tagging_failed and moderation_score
        - Commits/flushes to database
        """
        stmt = select(FoundationContent).where(
            FoundationContent.id == content_id,
            FoundationContent.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        content = result.scalar_one_or_none()

        if content is None:
            logger.warning(
                "foundation_tagging.not_found: content_id=%s, tenant_id=%s",
                content_id,
                tenant_id,
            )
            return []

        try:
            # Extract tags
            extracted_tags, moderation_score = await self.extract_tags_from_text(
                title=content.title_nl,
                description=content.description_nl,
                body=content.body_nl,
                location_hint=content.location_name,
                category_hint=content.category,
                tenant_id=tenant_id,
            )

            # Delete old AI tags for this content item (preserve manual tags)
            await session.execute(
                delete(ContentTag).where(
                    ContentTag.content_id == content.id,
                    ContentTag.is_manual.is_(False),
                )
            )

            # Insert new AI tags
            new_tags: list[ContentTag] = []
            for tag_dict in extracted_tags:
                tag = ContentTag(
                    content_id=content.id,
                    tag_type=TagType(tag_dict["tag_type"]),
                    value=tag_dict["value"],
                    confidence=tag_dict["confidence"],
                    is_manual=False,
                )
                session.add(tag)
                new_tags.append(tag)

            content.ai_tagging_failed = False
            if moderation_score is not None:
                content.moderation_score = moderation_score

            await session.flush()
            logger.info(
                "foundation_tagging.success: content_id=%s, tags_created=%d",
                content_id,
                len(new_tags),
            )
            return new_tags

        except Exception as e:
            logger.exception(
                "foundation_tagging.error: content_id=%s, tenant_id=%s, error=%s",
                content_id,
                tenant_id,
                e,
            )
            content.ai_tagging_failed = True
            await session.flush()
            return []
