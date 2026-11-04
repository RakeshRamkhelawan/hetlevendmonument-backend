"""De ActivePieces-verbinding van EEN tenant -- de enige plek die haar vaststelt (ADR-040 B3/B4).

Voor 2026-10-20 las `ActivePiecesClient` een algemene URL en een algemeen wachtwoord, en kozen
`find_project_for_tenant` en `get_tenant_ap_project` bij twijfel het eerste project van de server of
`str(tenant_id)`: het project van een willekeurig ander bedrijf. Nu geldt:

- De verbinding van een tenant komt uit `ap_verbinding_voor(tenant_id)`.
- Die leest de rij van die tenant uit `tenant_ap_verbindingen` (adres, e-mail, project en het
  WACHTWOORD VERSLEUTELD met de sleutel van die tenant). Een omgevingsroute bestaat niet meer.
- Geen rij is een duidelijke fout (409), nooit een terugval op een ander project of een algemene AP.
- Zonder `MASTER_ENCRYPTION_KEY` faalt het lezen luid (`HoofdsleutelOntbreekt`); een wachtwoord dat
  niet te ontsleutelen valt (andere tenant, beschadigd, andere sleutelversie) geeft dezelfde 409
  als "geen verbinding" en een logregel zonder geheim.

De tenant komt altijd van de aanroeper uit de JWT/ContextVar, nooit uit een body, query of payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from src.core.exceptions.exceptions import NotFoundError, SanskritiError

if TYPE_CHECKING:  # pragma: no cover - alleen voor de typecontrole
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ApVerbinding:
    """Alles wat nodig is om namens EEN tenant met ActivePieces te praten."""

    tenant_id: int
    base_url: str
    email: str
    # Nooit in een repr of logregel: een dataclass zet anders elk veld in de tekst.
    wachtwoord: str = field(repr=False)
    project_id: str


class ApVerbindingOntbreektError(SanskritiError):
    """409 -- deze tenant heeft (nog) geen eigen workflowbuilder-verbinding."""

    def __init__(self, reden: str) -> None:
        super().__init__(
            message=(
                "De workflowbuilder is voor uw bedrijf nog niet ingesteld: "
                f"{reden} Neem contact op met de beheerder van het platform."
            ),
            error_code="AP_VERBINDING_ONTBREEKT",
            status_code=409,
        )


class ApProjectIsNietVanDezeKlantError(SanskritiError):
    """403 -- er is gevraagd om een project dat niet bij de verbinding van deze tenant hoort."""

    def __init__(self) -> None:
        super().__init__(
            message="Dit project hoort niet bij uw bedrijf. Er is niets uitgevoerd.",
            error_code="AP_PROJECT_NIET_VAN_DEZE_KLANT",
            status_code=403,
        )


class ApRessourceNietGevondenError(NotFoundError):
    """404 -- een flow, run of verbinding die niet in het project van DEZE tenant staat.

    Een id van een andere tenant geeft hetzelfde antwoord als een id dat niet bestaat: wie het
    onderscheid kon zien, kon daarmee ontdekken welke id's bij andere klanten horen.
    """

    def __init__(self, soort: str) -> None:
        super().__init__(resource_type=soort, error_code="AP_NIET_GEVONDEN")


async def ap_verbinding_voor(tenant_id: int, db: "AsyncSession | None" = None) -> ApVerbinding:
    """De verbinding van `tenant_id`, of een `ApVerbindingOntbreektError` -- nooit een terugval.

    Met `db` binnen een verzoek; zonder `db` opent deze functie een eigen sessie (agents en
    achtergrondtaken hebben er geen bij de hand).
    """
    if db is not None:
        return await _lees_verbinding(db, tenant_id)

    from src.core.database.database import get_async_session

    async with get_async_session() as eigen_sessie:
        return await _lees_verbinding(eigen_sessie, tenant_id)


async def _lees_verbinding(db: "AsyncSession", tenant_id: int) -> ApVerbinding:
    # Lokale imports: zie `tenant_llm_provider_service` -- de koppelingsbudgetten van de
    # DSM-indeling zijn vol, en deze module wordt door veel plekken geimporteerd.
    from src.core.database.bypass_session import adopt_tenant
    from src.core.repositories.tenant_ap_verbinding_repository import TenantAPVerbindingRepository
    from src.core.security.tenant_secret_encryption import (
        InvalidToken,
        OnbekendeSleutelversie,
        TenantSecretEncryption,
    )

    async with adopt_tenant(db, tenant_id):
        rij = await TenantAPVerbindingRepository(db).get(tenant_id)
    if rij is None:
        logger.warning("ap_verbinding_ontbreekt", tenant_id=tenant_id, reden="geen_rij")
        raise ApVerbindingOntbreektError("er is nog geen verbinding voor dit bedrijf ingesteld.")

    # `HoofdsleutelOntbreekt` hier NIET opvangen: zonder hoofdsleutel moet het lezen luid falen.
    encryptie = TenantSecretEncryption()
    try:
        wachtwoord = encryptie.decrypt(tenant_id, rij.wachtwoord_encrypted)
    except (InvalidToken, OnbekendeSleutelversie) as e:
        logger.error(
            "ap_wachtwoord_niet_te_ontsleutelen", tenant_id=tenant_id, soort=type(e).__name__
        )
        raise ApVerbindingOntbreektError(
            "de opgeslagen inloggegevens zijn niet te lezen."
        ) from e

    return ApVerbinding(
        tenant_id=tenant_id,
        base_url=rij.base_url,
        email=rij.email,
        wachtwoord=wachtwoord,
        project_id=rij.project_id,
    )
