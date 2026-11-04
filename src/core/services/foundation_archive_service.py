"""Archief-export van gepubliceerde Levend Monument-items als BagIt-pakket (BE-EP-054).

ADR-029 Cat 4, "duurzame toegankelijkheid": wat publiek is, gaat periodiek als BagIt-pakket
(RFC 8493) naar de opslag, met een rij in `foundation_archive_exports` als bewijs.

Keuzes, met reden:

- **Elke export is een volledige momentopname**, geen verschil met de vorige. ADR-029 noemt
  "nieuwe/gewijzigde items"; een volledige momentopname is daar een bovenverzameling van, laat
  ook zien wat er NIET meer publiek is (ingetrokken, verwijderd), en is bij de omvang van een
  stichtingsarchief klein. Een archief dat alleen verschillen krijgt, moet ze zelf correct
  stapelen; een volledige momentopname kan los worden opgenomen.
- **Alleen wat publiek is**: status APPROVED, privacy PUBLIC en visibility PUBLIC. Edu- en
  community-inhoud gaat niet het externe archief in.
- **AVG**: de maker wordt weggelaten bij een anonieme inzending; e-mailadressen van
  inzenders gaan nooit mee; van het vrije JSONB-veld `metadata` gaan alleen de sleutels uit
  `_EXTRA_SLEUTELS` mee (vrije invoer kan bijzondere persoonsgegevens bevatten).
- **Volledig of niet**: kan een bijbehorend bestand niet worden gelezen, dan faalt de hele
  export. Een archiefpakket dat stilletjes bestanden mist, is erger dan geen pakket.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.models.foundation_content import (
    ContentStatus,
    FoundationArchiveExport,
    FoundationContent,
    FoundationContentBestand,
    FoundationPortalSettings,
    Privacy,
    Visibility,
)
from src.core.services.foundation_bagit import (
    ArchiveFile,
    ArchiveItem,
    BagError,
    BagInfo,
    build_bag,
    verify_bag,
)
from src.core.services.foundation_storage import (
    FoundationStorageError,
    FoundationStorageService,
    mime_extension,
)

logger = logging.getLogger(__name__)

#: Sleutels uit `FoundationContent.metadata_` die het archief in mogen. Alles daarbuiten is
#: vrije invoer en blijft binnen de applicatie (AVG, zie de moduledocstring).
_EXTRA_SLEUTELS: tuple[str, ...] = ("fictief", "periode", "bronnen")

#: Bovengrens op de totale omvang van de bestanden in een export. Het pakket wordt in het
#: geheugen gebouwd (piek circa drie keer deze omvang); daarboven weigert de export met een
#: duidelijke fout in plaats van de werker of de API onderuit te halen (Gate 2 HIGH-1).
MAX_PAYLOAD_BYTES = 512 * 1024 * 1024

#: Bij een anonieme inzending gaat de locatie afgerond mee (2 decimalen, circa 1 km), zodat
#: de plek een inzender niet herleidbaar maakt (Gate 2 M6).
_ANONIEM_DECIMALEN = 2

TRIGGER_SCHEMA = "schema"
TRIGGER_HANDMATIG = "handmatig"


class ArchiveExportError(RuntimeError):
    """De export is niet gemaakt; er is niets opgeslagen en geen rij geschreven."""


@dataclass(frozen=True)
class ExportTenant:
    """De gegevens van de tenant die de export nodig heeft (los van het ORM-model)."""

    id: int
    slug: str
    name: str


class FoundationArchiveService:
    def __init__(self, storage: FoundationStorageService | None = None) -> None:
        self._storage = storage if storage is not None else FoundationStorageService()

    async def export(
        self,
        *,
        session: AsyncSession,
        tenant: ExportTenant,
        now: datetime,
        trigger: str,
        portal_user_id: int | None = None,
    ) -> FoundationArchiveExport:
        """Maak een volledige momentopname, sla hem op en leg hem vast.

        De rij wordt toegevoegd en geflusht; committen doet de aanroeper.
        """
        if trigger not in (TRIGGER_SCHEMA, TRIGGER_HANDMATIG):
            raise ValueError(f"onbekende trigger: {trigger!r}")

        items = await self.collect_items(session=session, tenant=tenant)
        info = await self._bag_info(session=session, tenant=tenant, now=now)
        try:
            resultaat = build_bag(items, info)
        except BagError as e:
            raise ArchiveExportError("pakket kon niet worden gebouwd") from e

        # Narekenen voor het opslaan: een pakket dat niet klopt, gaat de opslag niet in.
        problemen = verify_bag(resultaat.zip_bytes)
        if problemen:
            raise ArchiveExportError(f"gebouwd pakket is ongeldig: {problemen[:3]}")

        try:
            url = await self._storage.upload_archive(
                tenant_id=tenant.id, bag_name=resultaat.bag_name, data=resultaat.zip_bytes
            )
        except FoundationStorageError as e:
            raise ArchiveExportError("opslaan van het archiefpakket is mislukt") from e

        rij = FoundationArchiveExport(
            tenant_id=tenant.id,
            bag_name=resultaat.bag_name,
            item_count=resultaat.item_count,
            payload_file_count=resultaat.payload_file_count,
            size_bytes=len(resultaat.zip_bytes),
            sha256=resultaat.sha256,
            storage_url=url,
            trigger=trigger,
            created_by_portal_user_id=portal_user_id,
            created_at=now,
        )
        session.add(rij)
        try:
            await session.flush()
        except SQLAlchemyError as e:
            # Geen pakket in de opslag dat de tabel niet kent (Gate 2 H2): een verweesd
            # pakket met persoonsgegevens is bij een AVG-verzoek niet terug te vinden.
            try:
                await self._storage.delete_archive(url, tenant_id=tenant.id)
            except FoundationStorageError:
                logger.error(
                    "foundation_archive.orphan_not_removed tenant_id=%s url=%s",
                    tenant.id,
                    url,
                    exc_info=True,
                )
            raise ArchiveExportError("vastleggen van de export is mislukt") from e
        logger.info(
            "foundation_archive.export_ok tenant_id=%s bag=%s items=%s bytes=%s",
            tenant.id,
            resultaat.bag_name,
            resultaat.item_count,
            len(resultaat.zip_bytes),
        )
        return rij

    async def collect_items(
        self, *, session: AsyncSession, tenant: ExportTenant
    ) -> list[ArchiveItem]:
        """Alle publieke, goedgekeurde items van deze tenant, met tags en bestanden."""
        result = await session.execute(
            select(FoundationContent)
            .options(selectinload(FoundationContent.tags))
            .where(
                FoundationContent.tenant_id == tenant.id,
                FoundationContent.status == ContentStatus.APPROVED,
                FoundationContent.privacy == Privacy.PUBLIC,
                FoundationContent.visibility == Visibility.PUBLIC,
            )
            .order_by(FoundationContent.id)
        )
        inhoud = list(result.scalars().all())
        # BE-EP-057: de extra bestanden van deze items in een keer, per item op volgorde.
        extra_per_item: dict[int, list[FoundationContentBestand]] = {}
        if inhoud:
            for bestand in (
                await session.execute(
                    select(FoundationContentBestand)
                    .where(
                        FoundationContentBestand.tenant_id == tenant.id,
                        FoundationContentBestand.content_id.in_([c.id for c in inhoud]),
                    )
                    .order_by(
                        FoundationContentBestand.content_id, FoundationContentBestand.volgorde
                    )
                )
            ).scalars():
                extra_per_item.setdefault(bestand.content_id, []).append(bestand)

        items: list[ArchiveItem] = []
        totaal = 0
        for content in inhoud:
            extra_bestanden = extra_per_item.get(content.id, [])
            # Vooraf op de vastgelegde bestandsgrootte, zodat een te groot bestand niet eerst
            # helemaal wordt ingelezen (Gate 2 ronde 2, LOW-B).
            verwacht = (content.file_size_bytes or 0) + sum(
                b.file_size_bytes for b in extra_bestanden
            )
            if totaal + verwacht > MAX_PAYLOAD_BYTES:
                raise ArchiveExportError(
                    f"collectie groter dan {MAX_PAYLOAD_BYTES // (1024 * 1024)} MB; "
                    "export geweigerd"
                )
            item = await self._to_item(content, tenant, extra_bestanden)
            totaal += sum(len(f.data) for f in item.files) + len(item.body or "")
            if totaal > MAX_PAYLOAD_BYTES:
                raise ArchiveExportError(
                    f"collectie groter dan {MAX_PAYLOAD_BYTES // (1024 * 1024)} MB; "
                    "export geweigerd"
                )
            items.append(item)
        return items

    async def discard(self, export: FoundationArchiveExport) -> None:
        """Verwijder het pakket van een export waarvan de vastlegging NA de flush mislukte.

        Best effort: lukt het niet, dan staat de URL in de log, zodat het pakket bij een
        AVG-verzoek terug te vinden is (Gate 2 ronde 2, MEDIUM-B).
        """
        try:
            await self._storage.delete_archive(export.storage_url, tenant_id=export.tenant_id)
        except FoundationStorageError:
            logger.error(
                "foundation_archive.orphan_not_removed tenant_id=%s url=%s",
                export.tenant_id,
                export.storage_url,
                exc_info=True,
            )

    async def read_archive(self, export: FoundationArchiveExport) -> bytes:
        """Lees een eerder gemaakt pakket terug en controleer dat het niet is veranderd."""
        try:
            data = await self._storage.read_bytes(export.storage_url, tenant_id=export.tenant_id)
        except FoundationStorageError as e:
            raise ArchiveExportError("archiefpakket niet gevonden in de opslag") from e
        if hashlib.sha256(data).hexdigest() != export.sha256:
            raise ArchiveExportError("archiefpakket in de opslag wijkt af van het controlegetal")
        return data

    async def _to_item(
        self,
        content: FoundationContent,
        tenant: ExportTenant,
        extra_bestanden: list[FoundationContentBestand] | None = None,
    ) -> ArchiveItem:
        bestanden: tuple[ArchiveFile, ...] = ()
        if content.file_url:
            try:
                data = await self._storage.read_bytes(content.file_url, tenant_id=tenant.id)
            except FoundationStorageError as e:
                raise ArchiveExportError(
                    f"bestand van item {content.id} kon niet worden gelezen"
                ) from e
            naam = f"origineel{mime_extension(content.file_mime) or '.bin'}"
            bestanden = (ArchiveFile(naam, data, content.file_mime),)
        # BE-EP-057: extra bestanden als origineel-2, origineel-3, ... Volledig of niet:
        # een extra bestand dat niet te lezen is, laat de hele export falen.
        for bestand in extra_bestanden or []:
            try:
                data = await self._storage.read_bytes(bestand.file_url, tenant_id=tenant.id)
            except FoundationStorageError as e:
                raise ArchiveExportError(
                    f"bestand {bestand.volgorde} van item {content.id} kon niet worden gelezen"
                ) from e
            naam = f"origineel-{bestand.volgorde}{mime_extension(bestand.file_mime) or '.bin'}"
            bestanden = (*bestanden, ArchiveFile(naam, data, bestand.file_mime))

        ruw = content.metadata_ if isinstance(content.metadata_, dict) else {}
        extra = {k: ruw[k] for k in _EXTRA_SLEUTELS if k in ruw}
        tags = tuple(sorted((str(t.tag_type.value), t.value) for t in content.tags))
        return ArchiveItem(
            identifier=f"oai:{tenant.slug}:{content.id}",
            content_id=content.id,
            content_type=str(content.type.value),
            title=content.title_nl,
            description=content.description_nl,
            body=content.body_nl,
            creator=None if content.is_anonymous else content.creator_name,
            language=content.language,
            license=content.license or "CC-BY-NC-SA-4.0",
            location_name=content.location_name,
            lat=_locatie(content.lat, content.is_anonymous),
            lng=_locatie(content.lng, content.is_anonymous),
            category=content.category,
            created_at=content.created_at,
            updated_at=content.updated_at,
            tags=tags,
            extra=extra,
            files=bestanden,
        )

    async def _bag_info(
        self, *, session: AsyncSession, tenant: ExportTenant, now: datetime
    ) -> BagInfo:
        result = await session.execute(
            select(FoundationPortalSettings).where(
                FoundationPortalSettings.tenant_id == tenant.id
            )
        )
        instellingen = result.scalar_one_or_none()
        organisatie = (
            instellingen.platform_name_nl if instellingen is not None else tenant.name
        )
        return BagInfo(
            bag_name=f"levendmonument-{tenant.slug}-{now.strftime('%Y%m%dT%H%M%SZ')}",
            source_organization=organisatie,
            contact_email=instellingen.contact_email if instellingen is not None else None,
            external_description=(
                f"Volledige momentopname van de publieke collectie van {organisatie}, "
                "BagIt 1.0, met Dublin Core per item."
            ),
            bagging_date=now,
        )


def _locatie(waarde: float | None, is_anoniem: bool) -> float | None:
    if waarde is None or not is_anoniem:
        return waarde
    return round(waarde, _ANONIEM_DECIMALEN)
