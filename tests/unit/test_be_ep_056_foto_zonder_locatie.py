"""BE-EP-056: foto's komen zonder locatie en andere metadata in het archief.

Regels die deze tests bewaken:
1. Uit JPEG, PNG en WebP verdwijnt de EXIF (met GPS) en de tekstmetadata.
2. De stand van een foto (EXIF Orientation) blijft zichtbaar goed.
3. Andere bestandstypen komen byte voor byte ongewijzigd terug.
4. Een kapotte of te grote afbeelding wordt geweigerd (geen crash, geen opslag).
5. Het upload-endpoint slaat de opgeschoonde bytes op, niet het origineel.
6. Spraakopnames van een telefoon (.m4a, audio/mp4) zijn toegestaan.
7. Uit MP4-video en .m4a-opnames verdwijnen locatie en titel; beeld en geluid blijven gelijk.
"""

from __future__ import annotations

import contextlib
import inspect
import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from PIL import Image, PngImagePlugin
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from src.core.services import foundation_storage
from src.core.services.foundation_storage import (
    BestandOnleesbaarError,
    detect_allowed_mime,
    verwijder_metadata,
)

GPS_TAG = 0x8825  # GPSInfo
ORIENTATIE_TAG = 0x0112


def _exif_met_gps(orientatie: int | None = None) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "Telefoonmerk"  # Make
    gps = exif.get_ifd(GPS_TAG)
    gps[1] = "N"
    gps[2] = (51.0, 54.0, 36.0)
    gps[3] = "E"
    gps[4] = (4.0, 20.0, 24.0)
    if orientatie is not None:
        exif[ORIENTATIE_TAG] = orientatie
    return exif


def _jpeg_met_gps(breedte: int = 40, hoogte: int = 20, orientatie: int | None = None) -> bytes:
    uit = io.BytesIO()
    Image.new("RGB", (breedte, hoogte), (200, 30, 30)).save(uit, format="JPEG", exif=_exif_met_gps(orientatie))
    return uit.getvalue()


def _heeft_gps(data: bytes) -> bool:
    with Image.open(io.BytesIO(data)) as beeld:
        exif = beeld.getexif()
        return GPS_TAG in exif or bool(exif.get_ifd(GPS_TAG))


class TestMetadataVerdwijnt:
    def test_de_testfoto_heeft_echt_gps(self) -> None:
        assert _heeft_gps(_jpeg_met_gps())

    def test_jpeg_zonder_gps(self) -> None:
        schoon = verwijder_metadata(_jpeg_met_gps(), "image/jpeg")
        assert not _heeft_gps(schoon)
        with Image.open(io.BytesIO(schoon)) as beeld:
            assert beeld.format == "JPEG"
            assert len(beeld.getexif()) == 0

    def test_webp_zonder_exif(self) -> None:
        uit = io.BytesIO()
        Image.new("RGB", (30, 30), (0, 90, 0)).save(uit, format="WEBP", exif=_exif_met_gps())
        bron = uit.getvalue()
        assert _heeft_gps(bron)
        schoon = verwijder_metadata(bron, "image/webp")
        assert not _heeft_gps(schoon)

    def test_png_zonder_tekst_en_exif(self) -> None:
        info = PngImagePlugin.PngInfo()
        info.add_text("Location", "Thuisstraat 1, Vlaardingen")
        uit = io.BytesIO()
        Image.new("RGB", (16, 16), (0, 0, 200)).save(uit, format="PNG", pnginfo=info, exif=_exif_met_gps())
        bron = uit.getvalue()
        assert b"Thuisstraat" in bron
        schoon = verwijder_metadata(bron, "image/png")
        assert b"Thuisstraat" not in schoon
        assert not _heeft_gps(schoon)

    def test_de_stand_van_de_foto_blijft_goed(self) -> None:
        # Orientation 6 = 90 graden gedraaid: een liggende opname van 40x20
        # hoort na verwerking staand (20x40) te zijn, zonder Orientation-tag.
        schoon = verwijder_metadata(_jpeg_met_gps(40, 20, orientatie=6), "image/jpeg")
        with Image.open(io.BytesIO(schoon)) as beeld:
            assert beeld.size == (20, 40)
            assert ORIENTATIE_TAG not in beeld.getexif()


class TestAndereBestanden:
    @pytest.mark.parametrize(
        ("mime", "data"),
        [
            ("image/gif", b"GIF89a" + b"\x00" * 20),
            ("audio/mpeg", b"ID3" + b"\x01" * 40),
            ("application/pdf", b"%PDF-1.7 met tekst"),
        ],
    )
    def test_komen_ongewijzigd_terug(self, mime: str, data: bytes) -> None:
        assert verwijder_metadata(data, mime) == data


def _blok(soort: bytes, inhoud: bytes) -> bytes:
    return (8 + len(inhoud)).to_bytes(4, "big") + soort + inhoud


def _groot_blok(soort: bytes, inhoud: bytes) -> bytes:
    # 64-bits lengte: grootte-veld 1, daarna de echte lengte in 8 bytes.
    return (1).to_bytes(4, "big") + soort + (16 + len(inhoud)).to_bytes(8, "big") + inhoud


LOCATIE = b"+51.9123+004.3456/"
TITEL = b"Kerkstraat 3"
BEELD = b"BEELD-EN-GELUIDSDATA" * 8


def _mp4(mdat_groot: bool = False) -> bytes:
    ftyp = _blok(b"ftyp", b"mp42\x00\x00\x00\x00mp42isom")
    mvhd = _blok(b"mvhd", bytes(100))
    udta_film = _blok(b"udta", _blok(b"\xa9xyz", b"\x00\x12\x15\xc7" + LOCATIE))
    meta_film = _blok(b"meta", bytes(4) + _blok(b"hdlr", bytes(24)) + _blok(b"ilst", _blok(b"\xa9nam", TITEL)))
    trak = _blok(b"trak", _blok(b"tkhd", bytes(84)) + _blok(b"udta", _blok(b"\xa9nam", TITEL)) + _blok(b"mdia", bytes(32)))
    moov = _blok(b"moov", mvhd + udta_film + meta_film + trak)
    mdat = _groot_blok(b"mdat", BEELD) if mdat_groot else _blok(b"mdat", BEELD)
    return ftyp + moov + mdat


class TestMp4:
    @pytest.mark.parametrize("soort", ["video/mp4", "audio/mp4"])
    def test_locatie_en_titel_verdwijnen(self, soort: str) -> None:
        bron = _mp4()
        assert LOCATIE in bron and TITEL in bron
        schoon = verwijder_metadata(bron, soort)
        assert LOCATIE not in schoon
        assert TITEL not in schoon
        assert b"udta" not in schoon and b"meta" not in schoon

    def test_indeling_beeld_en_geluid_blijven_gelijk(self) -> None:
        bron = _mp4()
        schoon = verwijder_metadata(bron, "video/mp4")
        assert len(schoon) == len(bron)
        assert schoon.index(BEELD) == bron.index(BEELD)
        assert schoon.startswith(bron[: bron.index(b"moov") - 4])
        assert schoon.count(b"free") == 3

    def test_64_bits_blok(self) -> None:
        schoon = verwijder_metadata(_mp4(mdat_groot=True), "video/mp4")
        assert LOCATIE not in schoon and BEELD in schoon

    def test_kapotte_mp4(self) -> None:
        kapot = _blok(b"ftyp", b"mp42") + (10_000).to_bytes(4, "big") + b"moov" + b"\x00" * 20
        with pytest.raises(BestandOnleesbaarError):
            verwijder_metadata(kapot, "video/mp4")


class TestWeigeren:
    def test_kapotte_afbeelding(self) -> None:
        with pytest.raises(BestandOnleesbaarError):
            verwijder_metadata(b"\xff\xd8\xff\xe0 dit is geen echte jpeg", "image/jpeg")

    def test_te_veel_pixels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(foundation_storage, "_MAX_PIXELS", 100)
        with pytest.raises(BestandOnleesbaarError):
            verwijder_metadata(_jpeg_met_gps(20, 20), "image/jpeg")


class TestTelefoonopnames:
    def test_m4a_is_toegestaan(self) -> None:
        m4a = bytes.fromhex("00000020667479704d344120000000004d34412069736f6d6d703432") + b"\x00" * 64
        assert detect_allowed_mime(m4a, filename="opname.m4a", declared_content_type="audio/x-m4a") == "audio/mp4"
        assert foundation_storage.mime_extension("audio/mp4") == ".m4a"


# --- Endpoint: worden de opgeschoonde bytes opgeslagen? ---------------------


class _Opslag:
    max_upload_size_bytes = 5 * 1024 * 1024

    def __init__(self) -> None:
        self.opgeslagen: bytes | None = None

    async def upload(self, *, tenant_id: int, content_id: int, filename: str | None, data: bytes, mime_type: str) -> str:
        self.opgeslagen = data
        return f"https://opslag.example/{tenant_id}/{content_id}/x.jpg"


def _verzoek() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/hetlevendmonument/foundation/content/5/upload",
            "headers": [],
            "app": MagicMock(),
            "client": ("127.0.0.1", 1),
        }
    )


async def _upload(data: bytes, bestandsnaam: str, soort: str) -> tuple[_Opslag, Any]:
    from src.core.api.v1.foundation import upload as upload_module
    from src.core.models.foundation_content import PortalRole

    tenant = MagicMock()
    tenant.id = 7
    gebruiker = MagicMock()
    gebruiker.id = 11
    gebruiker.tenant_id = 7
    gebruiker.role = PortalRole.VISITOR
    inhoud = MagicMock()
    inhoud.id = 5
    inhoud.uploader_id = 11

    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = inhoud
    sessie = AsyncMock()
    sessie.execute.return_value = resultaat
    sessie.add = MagicMock()

    @contextlib.asynccontextmanager
    async def scope(slug: str, s: Any):  # noqa: ARG001
        yield tenant

    opslag = _Opslag()
    bestand = UploadFile(file=io.BytesIO(data), filename=bestandsnaam, headers=Headers({"content-type": soort}))
    endpoint = inspect.unwrap(upload_module.upload_content_file)
    with patch.object(upload_module, "public_tenant_scope", side_effect=scope), patch.object(
        upload_module.AuditService, "log_event", new=AsyncMock()
    ):
        antwoord = await endpoint(
            content_id=5,
            tenantSlug="hetlevendmonument",
            request=_verzoek(),
            file=bestand,
            extra=False,
            current_user=gebruiker,
            session=sessie,
            storage=opslag,
        )
    return opslag, antwoord


class TestEndpoint:
    @pytest.mark.asyncio
    async def test_het_endpoint_slaat_de_foto_zonder_gps_op(self) -> None:
        bron = _jpeg_met_gps()
        opslag, antwoord = await _upload(bron, "foto.jpg", "image/jpeg")
        assert opslag.opgeslagen is not None
        assert opslag.opgeslagen != bron
        assert not _heeft_gps(opslag.opgeslagen)
        assert antwoord.file_size_bytes == len(opslag.opgeslagen)

    @pytest.mark.asyncio
    async def test_het_endpoint_weigert_een_kapotte_afbeelding(self) -> None:
        with pytest.raises(HTTPException) as fout:
            await _upload(b"\xff\xd8\xff\xe0 geen echte jpeg" + b"\x00" * 64, "foto.jpg", "image/jpeg")
        assert fout.value.status_code == 400
