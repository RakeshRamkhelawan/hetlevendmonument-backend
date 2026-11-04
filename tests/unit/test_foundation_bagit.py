"""BagIt-archiefpakket (ADR-029 Cat 4): bouwen en narekenen.

Onafhankelijk nagemeten op 2026-11-01 met de referentie-validator van de Library of
Congress (`bagit-python` 1.9.0, `bagit.Bag(...).validate()`): een pakket uit `build_bag`
is geldig, en hetzelfde pakket met een gewijzigde byte in de payload is ongeldig. Die
validator is geen projectafhankelijkheid; deze tests bewaken hetzelfde gedrag met de eigen
`verify_bag`, en de knoeitests hieronder bewijzen dat `verify_bag` niet alles goedkeurt.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from src.core.services.foundation_bagit import (
    ArchiveFile,
    ArchiveItem,
    BagError,
    BagInfo,
    build_bag,
    verify_bag,
)

_MOMENT = datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc)
_BAG = "levendmonument-test-20261101"


def _item(content_id: int = 1, **anders: object) -> ArchiveItem:
    velden: dict[str, object] = {
        "identifier": f"oai:hetlevendmonument.nl:test:{content_id}",
        "content_id": content_id,
        "content_type": "story",
        "title": "Afi en de ochtend van 1 juli",
        "description": "Paramaribo, 1863",
        "body": "Een fictief verhaal.",
        "creator": "Redactie",
        "language": "nl",
        "license": "CC-BY-NC-SA-4.0",
        "location_name": "Paramaribo",
        "lat": 5.8264,
        "lng": -55.1532,
        "category": "verhaal",
        "created_at": _MOMENT,
        "updated_at": _MOMENT,
        "tags": (("theme", "Keti Koti"),),
        "files": (ArchiveFile("foto.jpg", b"jpegbytes", "image/jpeg"),),
    }
    velden.update(anders)
    return ArchiveItem(**velden)  # type: ignore[arg-type]


def _info() -> BagInfo:
    return BagInfo(
        bag_name=_BAG,
        source_organization="Stichting Het Levend Monument",
        contact_email="info@hetlevendmonument.nl",
        external_description="Archief-export",
        bagging_date=_MOMENT,
    )


def _inhoud(zip_bytes: bytes) -> dict[str, bytes]:
    archief = zipfile.ZipFile(io.BytesIO(zip_bytes))
    return {n[len(_BAG) + 1 :]: archief.read(n) for n in archief.namelist()}


def _herpak(zip_bytes: bytes, wijzig: dict[str, bytes | None]) -> bytes:
    """Kopie van het zip-bestand met gewijzigde (bytes) of verwijderde (None) bestanden."""
    bron = zipfile.ZipFile(io.BytesIO(zip_bytes))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as doel:
        for naam in bron.namelist():
            kort = naam[len(_BAG) + 1 :]
            if kort in wijzig:
                nieuw = wijzig[kort]
                if nieuw is not None:
                    doel.writestr(naam, nieuw)
            else:
                doel.writestr(naam, bron.read(naam))
        for kort, data in wijzig.items():
            if f"{_BAG}/{kort}" not in bron.namelist() and data is not None:
                doel.writestr(f"{_BAG}/{kort}", data)
    return buffer.getvalue()


def test_een_gebouwd_pakket_is_geldig() -> None:
    resultaat = build_bag([_item(1), _item(2, files=())], _info())

    assert verify_bag(resultaat.zip_bytes) == []


def test_bouwen_is_deterministisch() -> None:
    eerste = build_bag([_item(1)], _info())
    tweede = build_bag([_item(1)], _info())

    assert eerste.sha256 == tweede.sha256


def test_bagit_txt_noemt_versie_1_0_en_utf8() -> None:
    inhoud = _inhoud(build_bag([_item()], _info()).zip_bytes)

    assert inhoud["bagit.txt"] == b"BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n"


def test_payload_oxum_telt_bytes_en_bestanden_van_de_payload() -> None:
    resultaat = build_bag([_item()], _info())
    inhoud = _inhoud(resultaat.zip_bytes)

    assert f"Payload-Oxum: {resultaat.payload_octets}.{resultaat.payload_file_count}" in inhoud[
        "bag-info.txt"
    ].decode()


def test_elk_item_krijgt_metadata_dublin_core_tekst_en_bestanden() -> None:
    inhoud = _inhoud(build_bag([_item(7)], _info()).zip_bytes)

    assert {
        "data/items/7/metadata.json",
        "data/items/7/dc.xml",
        "data/items/7/tekst.md",
        "data/items/7/bestanden/foto.jpg",
    } <= set(inhoud)


def test_metadata_json_bevat_de_controlegetal_van_het_bestand() -> None:
    inhoud = _inhoud(build_bag([_item(7)], _info()).zip_bytes)
    metadata = json.loads(inhoud["data/items/7/metadata.json"])

    assert metadata["files"][0]["sha256"] == hashlib.sha256(b"jpegbytes").hexdigest()


def test_een_anoniem_item_heeft_geen_maker_in_dublin_core() -> None:
    inhoud = _inhoud(build_bag([_item(3, creator=None)], _info()).zip_bytes)

    assert b"<dc:creator>" not in inhoud["data/items/3/dc.xml"]


def test_een_item_zonder_tekst_krijgt_geen_tekstbestand() -> None:
    inhoud = _inhoud(build_bag([_item(4, body=None)], _info()).zip_bytes)

    assert "data/items/4/tekst.md" not in inhoud


def test_verify_vindt_een_gewijzigde_payloadbyte() -> None:
    zip_bytes = build_bag([_item(1)], _info()).zip_bytes
    geknoeid = _herpak(zip_bytes, {"data/items/1/tekst.md": b"Een ander verhaal."})

    assert any("controlegetal van data/items/1/tekst.md" in p for p in verify_bag(geknoeid))


def test_verify_vindt_een_bestand_dat_niet_in_het_manifest_staat() -> None:
    zip_bytes = build_bag([_item(1)], _info()).zip_bytes
    geknoeid = _herpak(zip_bytes, {"data/extra.txt": b"stiekem"})

    assert any("data/extra.txt staat in de bag maar niet in het manifest" in p for p in verify_bag(geknoeid))


def test_verify_vindt_een_ontbrekend_payloadbestand() -> None:
    zip_bytes = build_bag([_item(1)], _info()).zip_bytes
    geknoeid = _herpak(zip_bytes, {"data/items/1/bestanden/foto.jpg": None})

    assert any("foto.jpg staat in het manifest maar niet in de bag" in p for p in verify_bag(geknoeid))


def test_verify_vindt_een_gewijzigd_tagbestand() -> None:
    zip_bytes = build_bag([_item(1)], _info()).zip_bytes
    inhoud = _inhoud(zip_bytes)
    geknoeid = _herpak(
        zip_bytes, {"bag-info.txt": inhoud["bag-info.txt"].replace(b"Archief-export", b"Anders")}
    )

    assert any("tagmanifest" in p and "bag-info.txt" in p for p in verify_bag(geknoeid))


def test_verify_vindt_een_verkeerde_payload_oxum() -> None:
    resultaat = build_bag([_item(1)], _info())
    inhoud = _inhoud(resultaat.zip_bytes)
    juist = f"Payload-Oxum: {resultaat.payload_octets}.{resultaat.payload_file_count}".encode()
    geknoeid = _herpak(
        resultaat.zip_bytes,
        {"bag-info.txt": inhoud["bag-info.txt"].replace(juist, b"Payload-Oxum: 1.1")},
    )

    assert any(p.startswith("Payload-Oxum klopt niet") for p in verify_bag(geknoeid))


def test_verify_weigert_iets_dat_geen_zip_is() -> None:
    assert verify_bag(b"geen zip") == ["geen geldig zip-bestand"]


def test_een_bestandsnaam_met_een_pad_wordt_geweigerd() -> None:
    with pytest.raises(BagError):
        build_bag([_item(1, files=(ArchiveFile("../ontsnapt.txt", b"x"),))], _info())


def test_een_onveilige_bag_naam_wordt_geweigerd() -> None:
    info = BagInfo(
        bag_name="../ontsnapt",
        source_organization="x",
        contact_email=None,
        external_description="x",
        bagging_date=_MOMENT,
    )

    with pytest.raises(BagError):
        build_bag([_item(1)], info)


def test_twee_bestanden_met_dezelfde_naam_worden_geweigerd() -> None:
    dubbel = (ArchiveFile("a.jpg", b"1"), ArchiveFile("a.jpg", b"2"))

    with pytest.raises(BagError):
        build_bag([_item(1, files=dubbel)], _info())
