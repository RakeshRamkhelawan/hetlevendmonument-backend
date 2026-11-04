"""Archief-export als dienst (BE-EP-054): selectie, AVG-masking, volledigheid, opslag.

Grens van de mocks: de database-sessie (geen test-Postgres in de unit-laag) en de opslag
(een in-memory nep-opslag die zich gedraagt als `FoundationStorageService`). Het pakket zelf
wordt NIET nagebootst: elke test bouwt een echt BagIt-pakket en rekent het na.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.models.foundation_content import (
    ContentStatus,
    ContentType,
    FoundationArchiveExport,
    FoundationContent,
    Privacy,
    Visibility,
)
from src.core.services.foundation_archive_service import (
    TRIGGER_HANDMATIG,
    ArchiveExportError,
    ExportTenant,
    FoundationArchiveService,
)
from src.core.services.foundation_bagit import verify_bag
from src.core.services.foundation_storage import FoundationStorageError

_NU = datetime(2026, 11, 2, 2, 15, tzinfo=timezone.utc)
_TENANT = ExportTenant(id=5, slug="ketikoti", name="Stichting Het Levend Monument")


class _NepOpslag:
    def __init__(self, bestanden: dict[str, bytes] | None = None) -> None:
        self.bestanden = dict(bestanden or {})
        self.archieven: dict[str, bytes] = {}

    async def read_bytes(self, file_url: str, *, tenant_id: int) -> bytes:
        if file_url in self.archieven:
            return self.archieven[file_url]
        if file_url not in self.bestanden:
            raise FoundationStorageError(f"niet gevonden: {file_url}")
        return self.bestanden[file_url]

    async def upload_archive(self, *, tenant_id: int, bag_name: str, data: bytes) -> str:
        url = f"/uploads/foundation-archief/{tenant_id}/{bag_name}.zip"
        self.archieven[url] = data
        return url

    async def delete_archive(self, file_url: str, *, tenant_id: int) -> None:
        self.archieven.pop(file_url, None)


def _content(content_id: int, **anders: object) -> FoundationContent:
    velden: dict[str, object] = {
        "id": content_id,
        "tenant_id": _TENANT.id,
        "type": ContentType.STORY,
        "title_nl": f"Verhaal {content_id}",
        "description_nl": "Beschrijving",
        "body_nl": "Tekst van het verhaal.",
        "creator_name": "Sandra",
        "is_anonymous": False,
        "language": "nl",
        "privacy": Privacy.PUBLIC,
        "visibility": Visibility.PUBLIC,
        "status": ContentStatus.APPROVED,
        "license": "CC-BY-NC-SA-4.0",
        "location_name": "Vlaardingen",
        "lat": 51.91,
        "lng": 4.32,
        "category": "verhaal",
        "file_url": None,
        "file_mime": None,
        "metadata_": {},
        "created_at": _NU,
        "updated_at": _NU,
    }
    velden.update(anders)
    return FoundationContent(**velden)


def _sessie(inhoud: list[FoundationContent]) -> AsyncMock:
    """Eerste execute: de items; dan (alleen met items) hun extra bestanden (BE-EP-057, geen);
    daarna de portaalinstellingen (geen)."""
    items = MagicMock()
    items.scalars.return_value.all.return_value = inhoud
    extra = MagicMock()
    extra.scalars.return_value = iter([])
    instellingen = MagicMock()
    instellingen.scalar_one_or_none.return_value = None
    sessie = AsyncMock()
    sessie.execute.side_effect = [items, extra, instellingen] if inhoud else [items, instellingen]
    sessie.add = MagicMock()
    return sessie


def _payload(zip_bytes: bytes) -> dict[str, bytes]:
    archief = zipfile.ZipFile(io.BytesIO(zip_bytes))
    return {n.split("/", 1)[1]: archief.read(n) for n in archief.namelist()}


async def _exporteer(
    inhoud: list[FoundationContent], opslag: _NepOpslag
) -> tuple[FoundationArchiveExport, AsyncMock]:
    sessie = _sessie(inhoud)
    rij = await FoundationArchiveService(storage=opslag).export(  # type: ignore[arg-type]
        session=sessie, tenant=_TENANT, now=_NU, trigger=TRIGGER_HANDMATIG, portal_user_id=9
    )
    return rij, sessie


@pytest.mark.asyncio
async def test_de_opgeslagen_export_is_een_geldig_bagit_pakket() -> None:
    opslag = _NepOpslag()

    rij, _ = await _exporteer([_content(1), _content(2)], opslag)

    assert verify_bag(opslag.archieven[rij.storage_url]) == []


@pytest.mark.asyncio
async def test_de_rij_legt_het_controlegetal_van_het_opgeslagen_bestand_vast() -> None:
    opslag = _NepOpslag()

    rij, _ = await _exporteer([_content(1)], opslag)

    assert rij.sha256 == hashlib.sha256(opslag.archieven[rij.storage_url]).hexdigest()


@pytest.mark.asyncio
async def test_de_rij_wordt_aan_de_sessie_toegevoegd() -> None:
    rij, sessie = await _exporteer([_content(1)], _NepOpslag())

    sessie.add.assert_called_once_with(rij)


@pytest.mark.asyncio
async def test_een_anonieme_inzending_gaat_zonder_maker_het_archief_in() -> None:
    opslag = _NepOpslag()

    rij, _ = await _exporteer([_content(3, is_anonymous=True, creator_name="Geheim")], opslag)

    payload = _payload(opslag.archieven[rij.storage_url])
    assert b"Geheim" not in payload["data/items/3/metadata.json"] + payload["data/items/3/dc.xml"]


@pytest.mark.asyncio
async def test_alleen_toegestane_metadatasleutels_gaan_mee() -> None:
    opslag = _NepOpslag()
    metadata = {"fictief": True, "telefoon": "0612345678"}

    rij, _ = await _exporteer([_content(4, metadata_=metadata)], opslag)

    extra = json.loads(_payload(opslag.archieven[rij.storage_url])["data/items/4/metadata.json"])[
        "extra"
    ]
    assert extra == {"fictief": True}


@pytest.mark.asyncio
async def test_het_bestand_van_een_item_gaat_mee_in_het_pakket() -> None:
    opslag = _NepOpslag({"/uploads/foundation/5/6/a.jpg": b"jpegdata"})

    rij, _ = await _exporteer(
        [_content(6, file_url="/uploads/foundation/5/6/a.jpg", file_mime="image/jpeg")], opslag
    )

    assert _payload(opslag.archieven[rij.storage_url])[
        "data/items/6/bestanden/origineel.jpg"
    ] == b"jpegdata"


@pytest.mark.asyncio
async def test_een_onleesbaar_bestand_laat_de_hele_export_mislukken() -> None:
    opslag = _NepOpslag()

    with pytest.raises(ArchiveExportError):
        await _exporteer([_content(7, file_url="/uploads/weg.jpg", file_mime="image/jpeg")], opslag)


@pytest.mark.asyncio
async def test_bij_een_mislukte_export_wordt_niets_opgeslagen() -> None:
    opslag = _NepOpslag()

    with pytest.raises(ArchiveExportError):
        await _exporteer([_content(7, file_url="/uploads/weg.jpg", file_mime="image/jpeg")], opslag)

    assert opslag.archieven == {}


@pytest.mark.asyncio
async def test_de_selectie_vraagt_alleen_publieke_goedgekeurde_items_van_deze_tenant() -> None:
    sessie = _sessie([])

    await FoundationArchiveService(storage=_NepOpslag()).collect_items(  # type: ignore[arg-type]
        session=sessie, tenant=_TENANT
    )

    sql = str(sessie.execute.call_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True}))
    assert all(
        voorwaarde in sql
        for voorwaarde in (
            "foundation_content.tenant_id = 5",
            "foundation_content.status = 'APPROVED'",
            "foundation_content.privacy = 'PUBLIC'",
            "foundation_content.visibility = 'public'",
        )
    ), sql


@pytest.mark.asyncio
async def test_een_gewijzigd_pakket_in_de_opslag_wordt_bij_teruglezen_geweigerd() -> None:
    opslag = _NepOpslag()
    rij, _ = await _exporteer([_content(1)], opslag)
    opslag.archieven[rij.storage_url] = opslag.archieven[rij.storage_url] + b"x"

    with pytest.raises(ArchiveExportError):
        await FoundationArchiveService(storage=opslag).read_archive(rij)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_een_onbekende_trigger_wordt_geweigerd() -> None:
    with pytest.raises(ValueError):
        await FoundationArchiveService(storage=_NepOpslag()).export(  # type: ignore[arg-type]
            session=_sessie([]), tenant=_TENANT, now=_NU, trigger="zomaar"
        )


@pytest.mark.asyncio
async def test_een_anonieme_inzending_krijgt_een_afgeronde_locatie() -> None:
    opslag = _NepOpslag()

    rij, _ = await _exporteer(
        [_content(8, is_anonymous=True, lat=51.912345, lng=4.318765)], opslag
    )

    locatie = json.loads(_payload(opslag.archieven[rij.storage_url])["data/items/8/metadata.json"])[
        "location"
    ]
    assert (locatie["lat"], locatie["lng"]) == (51.91, 4.32)


@pytest.mark.asyncio
async def test_een_niet_anonieme_inzending_houdt_de_exacte_locatie() -> None:
    opslag = _NepOpslag()

    rij, _ = await _exporteer([_content(8, lat=51.912345, lng=4.318765)], opslag)

    locatie = json.loads(_payload(opslag.archieven[rij.storage_url])["data/items/8/metadata.json"])[
        "location"
    ]
    assert (locatie["lat"], locatie["lng"]) == (51.912345, 4.318765)


@pytest.mark.asyncio
async def test_een_te_grote_collectie_wordt_geweigerd_en_niet_opgeslagen() -> None:
    opslag = _NepOpslag({"/uploads/foundation/5/9/a.mp4": b"0123456789"})

    with patch("src.core.services.foundation_archive_service.MAX_PAYLOAD_BYTES", 5):
        with pytest.raises(ArchiveExportError):
            await _exporteer(
                [_content(9, file_url="/uploads/foundation/5/9/a.mp4", file_mime="video/mp4")],
                opslag,
            )

    assert opslag.archieven == {}


@pytest.mark.asyncio
async def test_als_vastleggen_mislukt_wordt_het_opgeslagen_pakket_weer_verwijderd() -> None:
    opslag = _NepOpslag()
    sessie = _sessie([_content(1)])
    sessie.flush.side_effect = IntegrityError("insert", {}, Exception("fk"))

    with pytest.raises(ArchiveExportError):
        await FoundationArchiveService(storage=opslag).export(  # type: ignore[arg-type]
            session=sessie, tenant=_TENANT, now=_NU, trigger=TRIGGER_HANDMATIG
        )

    assert opslag.archieven == {}
