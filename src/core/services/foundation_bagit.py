"""BagIt-archiefpakket (RFC 8493, BagIt 1.0) voor het Levend Monument.

ADR-029, Cat 4 "duurzame toegankelijkheid": gepubliceerde items worden periodiek als
BagIt-pakket weggeschreven, zodat een extern digitaal archief ze kan opnemen zonder deze
applicatie te kennen.

Deze module is PUUR: geen database, geen opslag, geen klok. `foundation_archive_service`
levert de items (al gefilterd en gemaskeerd) en de bestanden aan; hier wordt alleen het
pakket gebouwd en nagerekend. Daardoor is het formaat los te testen, ook tegen een
onafhankelijke BagIt-validator.

Indeling van het zip-bestand (een map op het hoogste niveau, de naam van de bag):

    <bag_name>/bagit.txt
    <bag_name>/bag-info.txt
    <bag_name>/manifest-sha256.txt
    <bag_name>/manifest-sha512.txt
    <bag_name>/tagmanifest-sha256.txt
    <bag_name>/tagmanifest-sha512.txt
    <bag_name>/data/index.json
    <bag_name>/data/items/<id>/metadata.json
    <bag_name>/data/items/<id>/dc.xml
    <bag_name>/data/items/<id>/tekst.md            (alleen als er tekst is)
    <bag_name>/data/items/<id>/bestanden/<naam>    (alleen als er bestanden zijn)
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from xml.etree import ElementTree as ET

BAGIT_VERSION = "1.0"
#: sha512 is de aanbeveling van RFC 8493 par. 2.4; sha256 erbij omdat veel archieftools
#: alleen die controleren.
HASH_ALGORITHMS: tuple[str, ...] = ("sha256", "sha512")
SOFTWARE_AGENT = "Het Levend Monument archief-export (BagIt 1.0)"

DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
OAI_DC_NAMESPACE = "http://www.openarchives.org/OAI/2.0/oai_dc/"

_BAGIT_TXT = f"BagIt-Version: {BAGIT_VERSION}\nTag-File-Character-Encoding: UTF-8\n".encode()
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class BagError(ValueError):
    """Een pakket kan niet worden gebouwd met deze invoer (programmeerfout bij de aanroeper)."""


@dataclass(frozen=True)
class ArchiveFile:
    """Een bestand bij een item. `name` is al veilig gemaakt (geen pad, geen spaties)."""

    name: str
    data: bytes
    mime_type: str | None = None


@dataclass(frozen=True)
class ArchiveItem:
    """Een gepubliceerd item zoals het het archief in gaat.

    `creator` is al gemaskeerd door de aanroeper: bij een anonieme inzending is hij None.
    """

    identifier: str
    content_id: int
    content_type: str
    title: str
    description: str | None
    body: str | None
    creator: str | None
    language: str
    license: str | None
    location_name: str | None
    lat: float | None
    lng: float | None
    category: str | None
    created_at: datetime
    updated_at: datetime
    tags: tuple[tuple[str, str], ...] = ()
    extra: Mapping[str, object] = field(default_factory=dict)
    files: tuple[ArchiveFile, ...] = ()


@dataclass(frozen=True)
class BagInfo:
    """De beschrijvende velden van `bag-info.txt`."""

    bag_name: str
    source_organization: str
    contact_email: str | None
    external_description: str
    bagging_date: datetime


@dataclass(frozen=True)
class BagResult:
    zip_bytes: bytes
    bag_name: str
    item_count: int
    payload_file_count: int
    payload_octets: int
    sha256: str


def build_bag(items: Sequence[ArchiveItem], info: BagInfo) -> BagResult:
    """Bouw een BagIt 1.0-pakket als zip-bestand.

    Deterministisch: dezelfde invoer geeft byte-voor-byte hetzelfde zip-bestand (vaste
    volgorde, vaste tijdstempel uit `info.bagging_date`). Dat maakt een export
    controleerbaar: opnieuw bouwen moet dezelfde sha256 geven.
    """
    _check_segment(info.bag_name, "bag_name")
    payload: dict[str, bytes] = {}
    for item in sorted(items, key=lambda i: i.content_id):
        basis = f"data/items/{item.content_id}"
        for bestand in item.files:
            _check_segment(bestand.name, "bestandsnaam")
            pad = f"{basis}/bestanden/{bestand.name}"
            if pad in payload:
                raise BagError(f"dubbele bestandsnaam bij item {item.content_id}: {bestand.name}")
            payload[pad] = bestand.data
        payload[f"{basis}/metadata.json"] = _metadata_json(item)
        payload[f"{basis}/dc.xml"] = _dublin_core_xml(item)
        if item.body:
            payload[f"{basis}/tekst.md"] = item.body.encode("utf-8")
    payload["data/index.json"] = _index_json(items)

    octets = sum(len(data) for data in payload.values())
    tag_files: dict[str, bytes] = {
        "bagit.txt": _BAGIT_TXT,
        "bag-info.txt": _bag_info_txt(info, octets, len(payload)),
    }
    for alg in HASH_ALGORITHMS:
        tag_files[f"manifest-{alg}.txt"] = _manifest(payload, alg)
    tag_manifests = {f"tagmanifest-{alg}.txt": _manifest(tag_files, alg) for alg in HASH_ALGORITHMS}

    alle = {**tag_files, **tag_manifests, **payload}
    zip_bytes = _zip(info.bag_name, alle, info.bagging_date)
    return BagResult(
        zip_bytes=zip_bytes,
        bag_name=info.bag_name,
        item_count=len(items),
        payload_file_count=len(payload),
        payload_octets=octets,
        sha256=hashlib.sha256(zip_bytes).hexdigest(),
    )


def verify_bag(zip_bytes: bytes) -> list[str]:
    """Reken een zip-bestand na als BagIt-pakket. Lege lijst = geldig en compleet.

    Controleert: een enkele hoofdmap, `bagit.txt`, elke regel van elk (tag)manifest tegen de
    werkelijke inhoud, dat ELK payloadbestand in ELK manifest staat (compleetheid), en de
    Payload-Oxum uit `bag-info.txt`.
    """
    problemen: list[str] = []
    try:
        archief = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return ["geen geldig zip-bestand"]
    namen = [n for n in archief.namelist() if not n.endswith("/")]
    hoofdmappen = {n.split("/", 1)[0] for n in namen}
    if len(hoofdmappen) != 1:
        return [f"verwacht precies een hoofdmap, gevonden: {sorted(hoofdmappen)}"]
    root = hoofdmappen.pop()
    inhoud = {n[len(root) + 1 :]: archief.read(n) for n in namen}

    if inhoud.get("bagit.txt") != _BAGIT_TXT:
        problemen.append("bagit.txt ontbreekt of heeft niet de verwachte inhoud")

    payload_paden = {p for p in inhoud if p.startswith("data/")}
    tag_paden = {p for p in inhoud if not p.startswith("data/") and not p.startswith("tagmanifest-")}
    for alg in HASH_ALGORITHMS:
        problemen.extend(_check_manifest(inhoud, f"manifest-{alg}.txt", alg, payload_paden))
        problemen.extend(_check_manifest(inhoud, f"tagmanifest-{alg}.txt", alg, tag_paden))

    oxum = _bag_info_value(inhoud.get("bag-info.txt", b""), "Payload-Oxum")
    verwacht = f"{sum(len(inhoud[p]) for p in payload_paden)}.{len(payload_paden)}"
    if oxum != verwacht:
        problemen.append(f"Payload-Oxum klopt niet: staat {oxum!r}, gemeten {verwacht!r}")
    return problemen


# -- intern ---------------------------------------------------------------------------------


def _check_segment(naam: str, wat: str) -> None:
    if not _SAFE_SEGMENT.match(naam):
        raise BagError(f"onveilige {wat}: {naam!r}")


def _hash(data: bytes, alg: str) -> str:
    return hashlib.new(alg, data).hexdigest()


def _encode_path(pad: str) -> str:
    # RFC 8493 par. 2.1.3: %, CR en LF in een bestandspad worden percent-gecodeerd.
    return pad.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _decode_path(pad: str) -> str:
    return pad.replace("%0A", "\n").replace("%0D", "\r").replace("%25", "%")


def _manifest(bestanden: Mapping[str, bytes], alg: str) -> bytes:
    regels = [f"{_hash(bestanden[p], alg)}  {_encode_path(p)}\n" for p in sorted(bestanden)]
    return "".join(regels).encode("utf-8")


def _check_manifest(
    inhoud: Mapping[str, bytes], manifest_naam: str, alg: str, moet_bevatten: set[str]
) -> list[str]:
    ruw = inhoud.get(manifest_naam)
    if ruw is None:
        return [f"{manifest_naam} ontbreekt"]
    problemen: list[str] = []
    genoemd: set[str] = set()
    for regel in ruw.decode("utf-8").splitlines():
        if not regel.strip():
            continue
        delen = regel.split(maxsplit=1)
        if len(delen) != 2:
            problemen.append(f"{manifest_naam}: onleesbare regel {regel!r}")
            continue
        som, pad = delen[0], _decode_path(delen[1])
        genoemd.add(pad)
        if pad not in inhoud:
            problemen.append(f"{manifest_naam}: {pad} staat in het manifest maar niet in de bag")
        elif _hash(inhoud[pad], alg) != som.lower():
            problemen.append(f"{manifest_naam}: controlegetal van {pad} klopt niet")
    for pad in sorted(moet_bevatten - genoemd):
        problemen.append(f"{manifest_naam}: {pad} staat in de bag maar niet in het manifest")
    return problemen


def _bag_info_value(bag_info: bytes, label: str) -> str | None:
    for regel in bag_info.decode("utf-8", errors="replace").splitlines():
        if regel.startswith(f"{label}:"):
            return regel.split(":", 1)[1].strip()
    return None


def _enkele_regel(waarde: str) -> str:
    return " ".join(waarde.split())


def _bag_info_txt(info: BagInfo, octets: int, aantal: int) -> bytes:
    velden: list[tuple[str, str]] = [
        ("Source-Organization", info.source_organization),
        ("External-Description", info.external_description),
        ("External-Identifier", info.bag_name),
        ("Bagging-Date", info.bagging_date.date().isoformat()),
        ("Payload-Oxum", f"{octets}.{aantal}"),
        ("Bag-Software-Agent", SOFTWARE_AGENT),
    ]
    if info.contact_email:
        velden.insert(1, ("Contact-Email", info.contact_email))
    return "".join(f"{label}: {_enkele_regel(waarde)}\n" for label, waarde in velden).encode(
        "utf-8"
    )


def _metadata_json(item: ArchiveItem) -> bytes:
    document: dict[str, object] = {
        "identifier": item.identifier,
        "content_id": item.content_id,
        "type": item.content_type,
        "title": item.title,
        "description": item.description,
        "creator": item.creator,
        "language": item.language,
        "license": item.license,
        "category": item.category,
        "location": {"name": item.location_name, "lat": item.lat, "lng": item.lng},
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "tags": [{"type": t, "value": v} for t, v in item.tags],
        "files": [
            {
                "name": f.name,
                "mime_type": f.mime_type,
                "size_bytes": len(f.data),
                "sha256": _hash(f.data, "sha256"),
            }
            for f in item.files
        ],
        "extra": dict(item.extra),
    }
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _dublin_core_xml(item: ArchiveItem) -> bytes:
    ET.register_namespace("oai_dc", OAI_DC_NAMESPACE)
    ET.register_namespace("dc", DC_NAMESPACE)
    root = ET.Element(f"{{{OAI_DC_NAMESPACE}}}dc")

    def veld(naam: str, waarde: str | None) -> None:
        if waarde:
            ET.SubElement(root, f"{{{DC_NAMESPACE}}}{naam}").text = waarde

    veld("title", item.title)
    veld("creator", item.creator)
    veld("description", item.description)
    veld("date", item.created_at.date().isoformat())
    veld("type", item.content_type)
    veld("identifier", item.identifier)
    veld("rights", item.license)
    veld("coverage", item.location_name)
    veld("language", item.language)
    for soort, waarde in item.tags:
        if soort == "theme":
            veld("subject", waarde)
    for bestand in item.files:
        veld("format", bestand.mime_type)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def _index_json(items: Sequence[ArchiveItem]) -> bytes:
    rijen = [
        {
            "content_id": i.content_id,
            "identifier": i.identifier,
            "title": i.title,
            "updated_at": i.updated_at.isoformat(),
        }
        for i in sorted(items, key=lambda i: i.content_id)
    ]
    return (json.dumps(rijen, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _zip(root: str, bestanden: Mapping[str, bytes], moment: datetime) -> bytes:
    stempel = (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archief:
        for pad in sorted(bestanden):
            info = zipfile.ZipInfo(f"{root}/{pad}", date_time=stempel)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archief.writestr(info, bestanden[pad])
    return buffer.getvalue()
