"""Dependencies voor het inlezen van een inkoopfactuur (crediteuren dag 2; ADR-033 Laag 2).

De bonlezer is hergebruikt, niet nagebouwd: dezelfde upload en dezelfde nepbare `BonDienst` als bij bonnen. Daarom komt `get_bon_dienst`
uit `bonnen/dependencies.py` (een test of een andere omgeving vervangt hem op een plek). Het RECHT is `payables:write`, niet
`receipts:write`: een inkoopfactuur is een schuld aan een leverancier, geen uitgave op een bon.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.bonnen.dependencies import (
    MAX_BYTES,
    BonDienst,
    UploadFout,
    bonnen_read_limit,
    bonnen_upload_limit,
    get_bon_dienst,
)
from src.core.services.crediteuren_verwerking import start_verwerking
from src.core.services.inkoopfactuur_inlezen import (
    Bevestiging,
    InkoopfactuurInlezen,
    InlezenFout,
    Vastgelegd,
)

from .dependencies import NewSupplier, UserResponse, get_db

__all__ = [
    "MAX_BYTES",
    "Bevestiging",
    "BonDienst",
    "InkoopfactuurInlezen",
    "InlezenFout",
    "NewSupplier",
    "UploadFout",
    "Vastgelegd",
    "bonnen_read_limit",
    "bonnen_upload_limit",
    "get_bon_dienst",
    "get_inlezen_dienst",
    "get_verwerking_starter",
    "vereis_goedkeurrecht",
    "weiger_zelfgoedkeuring",
]


def get_inlezen_dienst(
    db: AsyncSession = Depends(get_db), dienst: BonDienst = Depends(get_bon_dienst)
) -> InkoopfactuurInlezen:
    return InkoopfactuurInlezen(db, dienst)


async def weiger_zelfgoedkeuring(
    db: AsyncSession, request: Request, gebruiker: UserResponse, ticket: object
) -> None:
    """Aanpassen sluit het ticket van de agent: voor de aanvrager gelden dezelfde regels als bij goedkeuren (ADR-039).

    Staat vier ogen aan voor deze actie, dan mag wie de agent startte (de uploader) zijn eigen ticket niet sluiten, ook niet
    via de aanpasroute: anders is dat de weg om de vier-ogen-instelling te omzeilen en eigen gegevens in te voeren (Gate 2).
    Hergebruikt de toets van de HITL-route, inclusief haar auditregel bij een weigering.
    """
    import importlib

    router = importlib.import_module("src.core.api.v1.tool_broker.hitl_router")
    await router._refuse_self_approval_audited(db, request, gebruiker, ticket)


def get_verwerking_starter() -> Callable[[int, str, int], None]:
    """De start van de crediteurenagent als afhankelijkheid: een test of een andere omgeving vervangt hem op een plek."""
    return start_verwerking


async def vereis_goedkeurrecht(db: AsyncSession, gebruiker: UserResponse) -> None:
    """Aanpassen sluit een ticket van de crediteurenagent: alleen wie het goedkeurrecht voor crediteuren heeft (403 anders).

    Zelfde recht als het goedkeuren in de wachtrij (`payables:approve`, rol `goedkeurder`): wie een uitzondering mag
    afhandelen, mag haar ook zelf juist vastleggen, en niemand anders.
    """
    import importlib

    rechten = importlib.import_module("src.core.auth.approval_rights")
    if not await rechten.has_approval_right(db, gebruiker, rechten.PAYABLES_APPROVE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="U heeft het goedkeurrecht voor crediteuren niet; alleen een goedkeurder past een ticket aan.",
        )
