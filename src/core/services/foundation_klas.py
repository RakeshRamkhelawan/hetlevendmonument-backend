"""Welke werkbladen een klas mag zien (BE-EP-055).

Een klas van een docent (StudyCollection met `owner_portal_user_id`) ziet ALLEEN de lessen die
de docent heeft opengezet, ook als dat er nul zijn. Een klascode zonder eigenaar (de oude vorm,
door een curator gemaakt) ziet al het lesmateriaal, zoals voorheen.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import FoundationClassLesson, StudyCollection


async def klas_van_toegang(
    sessie: AsyncSession, tenant_id: int, toegang_id: int
) -> StudyCollection | None:
    """De klas (StudyCollection) bij een klascode, of None."""
    resultaat = await sessie.execute(
        select(StudyCollection)
        .where(
            StudyCollection.tenant_id == tenant_id,
            StudyCollection.educational_access_id == toegang_id,
        )
        .order_by(StudyCollection.id)
        .limit(1)
    )
    return resultaat.scalars().first()


async def toegestane_les_ids(
    sessie: AsyncSession, tenant_id: int, toegang_id: int
) -> set[int] | None:
    """De content-ids die deze klascode mag zien; None betekent: alles (oude klascodes)."""
    klas = await klas_van_toegang(sessie, tenant_id, toegang_id)
    if klas is None or klas.owner_portal_user_id is None:
        return None
    resultaat = await sessie.execute(
        select(FoundationClassLesson.content_id).where(
            FoundationClassLesson.tenant_id == tenant_id,
            FoundationClassLesson.study_collection_id == klas.id,
        )
    )
    return {int(i) for i in resultaat.scalars().all()}
