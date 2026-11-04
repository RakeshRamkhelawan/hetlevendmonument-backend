"""BE-EP-057: meerdere bestanden per verhaal, en de curator ziet een inzending voor hij beslist.

Regels die deze tests bewaken:
1. Upload met ``extra=true`` voegt een bestand toe (volgorde 2, 3, ...) en laat het
   hoofdbestand staan. Zonder hoofdbestand wordt het eerste bestand het hoofdbestand.
   Zonder ``extra`` vervangt een upload het hoofdbestand (zoals altijd).
2. Maximaal MAX_BESTANDEN_PER_VERHAAL bestanden; de grens wordt gecontroleerd VOOR er iets
   wordt opgeslagen.
3. Een inzender kan alleen extra bestanden toevoegen zolang het verhaal in behandeling is;
   een curator ook daarna.
4. Een extra bestand ophalen gaat door dezelfde toegangscontrole als het hoofdbestand, en het
   bestand moet bij DIT verhaal en DEZE tenant horen.
5. GET /content/{id}: niet-goedgekeurde items alleen voor curator/beheerder van de eigen
   tenant, of de inzender zolang het in behandeling of afgewezen is. De extra bestanden staan
   in het antwoord, op volgorde.
6. De archiefexport neemt de extra bestanden mee; een onleesbaar extra bestand laat de export
   falen.
7. iPhone-video (.mov) is toegestaan en wordt net zo opgeschoond als MP4, inclusief XMP in
   ``uuid``-blokken.
"""

from __future__ import annotations

import contextlib
import inspect
import io
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from src.core.models.foundation_content import (
    MAX_BESTANDEN_PER_VERHAAL,
    ContentStatus,
    ContentType,
    FoundationContent,
    FoundationContentBestand,
    PortalRole,
    Privacy,
    Visibility,
)
from src.core.services.foundation_storage import detect_allowed_mime, verwijder_metadata

TENANT = 7
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # alleen voor de MIME-herkenning; zie _geen_metadata


class _Tenant:
    id = TENANT
    slug = "hetlevendmonument"


class _Savepoint:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _gebruiker(
    rol: PortalRole = PortalRole.VISITOR, id: int = 11, tenant_id: int = TENANT
) -> MagicMock:
    g = MagicMock()
    g.id = id
    g.tenant_id = tenant_id
    g.role = rol
    return g


def _verhaal(
    status: ContentStatus = ContentStatus.PENDING,
    file_url: str | None = "https://opslag/1.jpg",
    uploader_id: int = 11,
) -> FoundationContent:
    c = FoundationContent(
        id=5,
        tenant_id=TENANT,
        uploader_id=uploader_id,
        type=ContentType.STORY,
        title_nl="Oma in Paramaribo",
        status=status,
        privacy=Privacy.PUBLIC,
        visibility=Visibility.PUBLIC,
        is_anonymous=False,
        language="nl",
        rights_confirmed=True,
        ai_tagging_failed=False,
        file_url=file_url,
        file_mime="image/jpeg" if file_url else None,
        file_size_bytes=10 if file_url else None,
        created_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
        updated_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )
    c.tags = []
    return c


def _resultaat(
    *,
    scalar: object = None,
    een: tuple[int, int | None] | None = None,
    alle: list[Any] | None = None,
) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    if een is not None:
        r.one.return_value = een
    r.scalars.return_value.all.return_value = alle or []
    r.scalars.return_value.__iter__ = lambda _self: iter(alle or [])
    return r


def _verzoek() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "app": MagicMock(),
            "client": ("127.0.0.1", 1),
        }
    )


def _scope(*args: Any, **kwargs: Any):  # noqa: ARG001
    @contextlib.asynccontextmanager
    async def cm():
        yield _Tenant()

    return cm()


# --- 1-3: upload ---------------------------------------------------------------------


class _Opslag:
    max_upload_size_bytes = 5 * 1024 * 1024

    def __init__(self) -> None:
        self.aantal = 0

    async def upload(self, **kwargs: Any) -> str:
        self.aantal += 1
        return f"https://opslag/extra-{self.aantal}.png"


async def _upload(
    verhaal: FoundationContent,
    gebruiker: MagicMock,
    *,
    extra: bool,
    bestaand: tuple[int, int | None] = (0, None),
    vang: list[Any] | None = None,
):
    from src.core.api.v1.foundation import upload as m

    toegevoegd: list[Any] = []
    sessie = AsyncMock()
    sessie.add = MagicMock(side_effect=toegevoegd.append)
    sessie.begin_nested = MagicMock(return_value=_Savepoint())

    async def flush() -> None:
        for obj in toegevoegd:
            if isinstance(obj, FoundationContentBestand) and obj.id is None:
                obj.id = 900

    sessie.flush = AsyncMock(side_effect=flush)
    sessie.execute.side_effect = [_resultaat(scalar=verhaal), _resultaat(een=bestaand)]
    if vang is not None:
        vang.append(sessie)
    opslag = _Opslag()
    bestand = UploadFile(
        file=io.BytesIO(PNG), filename="tweede.png", headers=Headers({"content-type": "image/png"})
    )
    endpoint = inspect.unwrap(m.upload_content_file)
    with (
        patch.object(m, "public_tenant_scope", side_effect=_scope),
        patch.object(m.AuditService, "log_event", new=AsyncMock()),
        patch.object(m, "verwijder_metadata", side_effect=lambda data, mime: data),
    ):
        antwoord = await endpoint(
            content_id=5,
            tenantSlug="hetlevendmonument",
            request=_verzoek(),
            file=bestand,
            extra=extra,
            current_user=gebruiker,
            session=sessie,
            storage=opslag,
        )
    return antwoord, toegevoegd, opslag


class TestUpload:
    @pytest.mark.asyncio
    async def test_extra_bestand_komt_erbij_en_het_hoofdbestand_blijft(self) -> None:
        verhaal = _verhaal()
        antwoord, toegevoegd, _ = await _upload(verhaal, _gebruiker(), extra=True)
        extra = [o for o in toegevoegd if isinstance(o, FoundationContentBestand)]
        assert len(extra) == 1
        assert extra[0].volgorde == 2
        assert extra[0].tenant_id == TENANT and extra[0].content_id == 5
        assert verhaal.file_url == "https://opslag/1.jpg"
        assert antwoord.bestand_id == 900

    @pytest.mark.asyncio
    async def test_volgorde_loopt_door(self) -> None:
        _, toegevoegd, _ = await _upload(_verhaal(), _gebruiker(), extra=True, bestaand=(3, 4))
        extra = [o for o in toegevoegd if isinstance(o, FoundationContentBestand)]
        assert extra[0].volgorde == 5

    @pytest.mark.asyncio
    async def test_zonder_hoofdbestand_wordt_het_eerste_bestand_het_hoofdbestand(self) -> None:
        verhaal = _verhaal(file_url=None)
        from src.core.api.v1.foundation import upload as m

        sessie = AsyncMock()
        sessie.add = MagicMock()
        sessie.execute.side_effect = [_resultaat(scalar=verhaal)]
        bestand = UploadFile(
            file=io.BytesIO(PNG), filename="a.png", headers=Headers({"content-type": "image/png"})
        )
        with (
            patch.object(m, "public_tenant_scope", side_effect=_scope),
            patch.object(m.AuditService, "log_event", new=AsyncMock()),
            patch.object(m, "verwijder_metadata", side_effect=lambda data, mime: data),
        ):
            antwoord = await inspect.unwrap(m.upload_content_file)(
                content_id=5,
                tenantSlug="x",
                request=_verzoek(),
                file=bestand,
                extra=True,
                current_user=_gebruiker(),
                session=sessie,
                storage=_Opslag(),
            )
        assert verhaal.file_url == "https://opslag/extra-1.png"
        assert antwoord.bestand_id is None

    @pytest.mark.asyncio
    async def test_de_grens_geldt_voor_er_iets_wordt_opgeslagen(self) -> None:
        with pytest.raises(HTTPException) as fout:
            await _upload(
                _verhaal(),
                _gebruiker(),
                extra=True,
                bestaand=(MAX_BESTANDEN_PER_VERHAAL - 1, MAX_BESTANDEN_PER_VERHAAL),
            )
        assert fout.value.status_code == 409

    @pytest.mark.asyncio
    async def test_de_telling_eist_dit_verhaal_en_deze_tenant(self) -> None:
        vang: list[Any] = []
        await _upload(_verhaal(), _gebruiker(), extra=True, vang=vang)
        telling = vang[0].execute.call_args_list[1].args[0]
        sql = str(telling.compile(compile_kwargs={"literal_binds": True}))
        assert "foundation_content_bestanden.content_id = 5" in sql
        assert f"foundation_content_bestanden.tenant_id = {TENANT}" in sql

    @pytest.mark.asyncio
    async def test_een_bestand_onder_de_grens_mag_nog(self) -> None:
        _, toegevoegd, opslag = await _upload(
            _verhaal(),
            _gebruiker(),
            extra=True,
            bestaand=(MAX_BESTANDEN_PER_VERHAAL - 2, MAX_BESTANDEN_PER_VERHAAL - 1),
        )
        assert opslag.aantal == 1

    @pytest.mark.parametrize(
        "status", [ContentStatus.APPROVED, ContentStatus.REJECTED, ContentStatus.REMOVED]
    )
    @pytest.mark.asyncio
    async def test_een_inzender_voegt_niets_toe_na_beoordeling(self, status: ContentStatus) -> None:
        with pytest.raises(HTTPException) as fout:
            await _upload(_verhaal(status=status), _gebruiker(), extra=True)
        assert fout.value.status_code == 409

    @pytest.mark.asyncio
    async def test_een_curator_mag_dat_wel(self) -> None:
        _, toegevoegd, _ = await _upload(
            _verhaal(status=ContentStatus.APPROVED, uploader_id=99),
            _gebruiker(PortalRole.CURATOR),
            extra=True,
        )
        assert any(isinstance(o, FoundationContentBestand) for o in toegevoegd)


# --- 4: extra bestand ophalen ---------------------------------------------------------


async def _haal_extra(
    verhaal: FoundationContent | None,
    bestand: FoundationContentBestand | None,
    gebruiker: MagicMock | None,
):
    from src.core.api.v1.foundation import upload as m

    sessie = AsyncMock()
    verzoeken: list[Any] = []

    async def execute(stmt: Any) -> MagicMock:
        verzoeken.append(stmt)
        return _resultaat(scalar=verhaal if len(verzoeken) == 1 else bestand)

    sessie.execute = AsyncMock(side_effect=execute)
    lever = AsyncMock(return_value="afgeleverd")
    with (
        patch.object(m, "public_tenant_scope", side_effect=_scope),
        patch.object(m, "_lever_media", new=lever),
    ):
        antwoord = await inspect.unwrap(m.get_content_bestand_media)(
            content_id=5,
            bestand_id=900,
            tenantSlug="x",
            request=_verzoek(),
            redirect=False,
            download=False,
            stream=False,
            current_user=gebruiker,
            session=sessie,
            storage=MagicMock(),
            edu_sessions=MagicMock(),
        )
    return antwoord, lever, verzoeken


def _extra() -> FoundationContentBestand:
    return FoundationContentBestand(
        id=900,
        tenant_id=TENANT,
        content_id=5,
        volgorde=2,
        file_url="https://opslag/2.png",
        file_mime="image/png",
        file_size_bytes=12,
        sha256="0" * 64,
    )


class TestExtraOphalen:
    @pytest.mark.asyncio
    async def test_openbaar_verhaal_levert_het_extra_bestand(self) -> None:
        antwoord, lever, _ = await _haal_extra(
            _verhaal(status=ContentStatus.APPROVED), _extra(), None
        )
        assert antwoord == "afgeleverd"
        assert lever.await_args.kwargs["file_url"] == "https://opslag/2.png"

    @pytest.mark.asyncio
    async def test_dezelfde_toegangscontrole_als_het_hoofdbestand(self) -> None:
        # In behandeling + anoniem: de gedeelde controle weigert, ook voor extra bestanden.
        with pytest.raises(HTTPException) as fout:
            await _haal_extra(_verhaal(status=ContentStatus.PENDING), _extra(), None)
        assert fout.value.status_code == 404

    @pytest.mark.asyncio
    async def test_bestand_van_een_ander_verhaal_is_404(self) -> None:
        with pytest.raises(HTTPException) as fout:
            await _haal_extra(_verhaal(status=ContentStatus.APPROVED), None, None)
        assert fout.value.status_code == 404

    @pytest.mark.asyncio
    async def test_de_query_eist_dit_verhaal_en_deze_tenant(self) -> None:
        _, _, verzoeken = await _haal_extra(_verhaal(status=ContentStatus.APPROVED), _extra(), None)
        sql = str(verzoeken[1].compile(compile_kwargs={"literal_binds": True}))
        assert "foundation_content_bestanden.content_id = 5" in sql
        assert f"foundation_content_bestanden.tenant_id = {TENANT}" in sql
        assert "foundation_content_bestanden.id = 900" in sql


class TestStreamOpExterneOpslag:
    """Op Azure is ``file_url`` een https-URL; ``stream`` moet dan doorsturen, niet 404 geven."""

    @staticmethod
    async def _lever(file_url: str, opslag: MagicMock) -> Any:
        from src.core.api.v1.foundation.upload import _lever_media

        return await _lever_media(
            storage=opslag,
            request=_verzoek(),
            file_url=file_url,
            mime_type="video/quicktime",
            file_size_bytes=10,
            naam="Oma",
            redirect=False,
            download=False,
            stream=True,
        )

    @pytest.mark.asyncio
    async def test_azure_stream_stuurt_door_naar_tijdelijke_url(self) -> None:
        from fastapi.responses import RedirectResponse

        opslag = MagicMock()
        opslag.get_local_file_path = MagicMock(return_value=None)
        opslag.generate_read_url = AsyncMock(return_value="https://sas/oma.mov")
        antwoord = await self._lever(
            "https://acct.blob.core.windows.net/foundation-uploads/7/a.mov", opslag
        )
        assert isinstance(antwoord, RedirectResponse)
        assert antwoord.status_code == 307
        assert antwoord.headers["location"] == "https://sas/oma.mov"

    @pytest.mark.asyncio
    async def test_lokaal_bestand_dat_ontbreekt_blijft_404(self) -> None:
        opslag = MagicMock()
        opslag.get_local_file_path = MagicMock(return_value=None)
        opslag.generate_read_url = AsyncMock(return_value="https://sas/x")
        with pytest.raises(HTTPException) as fout:
            await self._lever("/uploads/7/a.mov", opslag)
        assert fout.value.status_code == 404
        opslag.generate_read_url.assert_not_called()


# --- 5: detail ------------------------------------------------------------------------


async def _detail(
    verhaal: FoundationContent | None,
    gebruiker: MagicMock | None,
    extra: list[FoundationContentBestand] | None = None,
):
    from src.core.api.v1.foundation import content as m

    sessie = AsyncMock()
    sessie.execute.side_effect = [_resultaat(scalar=verhaal), _resultaat(alle=extra or [])]
    with patch.object(m, "public_tenant_scope", side_effect=_scope):
        return await m.get_content(
            content_id=5, tenantSlug="x", current_user=gebruiker, session=sessie
        )


class TestDetail:
    @pytest.mark.asyncio
    async def test_goedgekeurd_voor_iedereen_met_extra_bestanden_op_volgorde(self) -> None:
        tweede, derde = _extra(), _extra()
        derde.id, derde.volgorde = 901, 3
        detail = await _detail(_verhaal(status=ContentStatus.APPROVED), None, [tweede, derde])
        assert [b.volgorde for b in detail.bestanden] == [2, 3]
        assert detail.bestanden[0].id == 900

    @pytest.mark.parametrize(
        ("status", "gebruiker"),
        [
            (ContentStatus.PENDING, None),
            (ContentStatus.PENDING, _gebruiker(id=12)),  # andere bezoeker
            (ContentStatus.PENDING, _gebruiker(PortalRole.TEACHER, id=12)),
            (
                ContentStatus.PENDING,
                _gebruiker(PortalRole.CURATOR, id=12, tenant_id=99),
            ),  # andere tenant
            (ContentStatus.PENDING, _gebruiker(id=11, tenant_id=99)),  # zelfde id, andere tenant
            (ContentStatus.REMOVED, _gebruiker(id=11)),  # inzender, maar offline gehaald
            (ContentStatus.REJECTED, None),
        ],
    )
    @pytest.mark.asyncio
    async def test_niet_goedgekeurd_is_404_voor_anderen(
        self, status: ContentStatus, gebruiker: MagicMock | None
    ) -> None:
        with pytest.raises(HTTPException) as fout:
            await _detail(_verhaal(status=status), gebruiker)
        assert fout.value.status_code == 404

    @pytest.mark.parametrize(
        ("status", "gebruiker"),
        [
            (ContentStatus.PENDING, _gebruiker(id=11)),  # de inzender
            (ContentStatus.REJECTED, _gebruiker(id=11)),
            (ContentStatus.PENDING, _gebruiker(PortalRole.CURATOR, id=12)),
            (ContentStatus.PENDING, _gebruiker(PortalRole.ADMIN, id=12)),
            (ContentStatus.REMOVED, _gebruiker(PortalRole.CURATOR, id=12)),
        ],
    )
    @pytest.mark.asyncio
    async def test_niet_goedgekeurd_zichtbaar_voor_curator_en_inzender(
        self, status: ContentStatus, gebruiker: MagicMock
    ) -> None:
        detail = await _detail(_verhaal(status=status), gebruiker)
        assert detail.id == 5


# --- 6: archief -----------------------------------------------------------------------


class TestArchief:
    @pytest.mark.asyncio
    async def test_extra_bestanden_gaan_mee_als_origineel_2(self) -> None:
        from src.core.services.foundation_archive_service import FoundationArchiveService

        opslag = MagicMock()
        opslag.read_bytes = AsyncMock(side_effect=lambda url, tenant_id: url.encode())
        dienst = FoundationArchiveService(storage=opslag)
        tenant = MagicMock()
        tenant.id, tenant.slug = TENANT, "hetlevendmonument"
        item = await dienst._to_item(_verhaal(status=ContentStatus.APPROVED), tenant, [_extra()])
        assert [f.name for f in item.files] == ["origineel.jpg", "origineel-2.png"]

    @pytest.mark.asyncio
    async def test_onleesbaar_extra_bestand_laat_de_export_falen(self) -> None:
        from src.core.services.foundation_archive_service import (
            ArchiveExportError,
            FoundationArchiveService,
        )
        from src.core.services.foundation_storage import FoundationStorageError

        async def lees(url: str, tenant_id: int) -> bytes:
            if url.endswith("2.png"):
                raise FoundationStorageError("weg")
            return b"x"

        opslag = MagicMock()
        opslag.read_bytes = AsyncMock(side_effect=lees)
        tenant = MagicMock()
        tenant.id, tenant.slug = TENANT, "hetlevendmonument"
        with pytest.raises(ArchiveExportError):
            await FoundationArchiveService(storage=opslag)._to_item(
                _verhaal(status=ContentStatus.APPROVED), tenant, [_extra()]
            )


class TestArchiefVerzamelen:
    @pytest.mark.asyncio
    async def test_extra_bestanden_van_deze_items_en_deze_tenant(self) -> None:
        from src.core.services.foundation_archive_service import FoundationArchiveService

        items = MagicMock()
        items.scalars.return_value.all.return_value = [_verhaal(status=ContentStatus.APPROVED)]
        extra = MagicMock()
        extra.scalars.return_value = iter([_extra()])
        sessie = AsyncMock()
        sessie.execute.side_effect = [items, extra]
        opslag = MagicMock()
        opslag.read_bytes = AsyncMock(side_effect=lambda url, tenant_id: url.encode())
        tenant = MagicMock()
        tenant.id, tenant.slug = TENANT, "hetlevendmonument"

        gevonden = await FoundationArchiveService(storage=opslag).collect_items(
            session=sessie, tenant=tenant
        )

        assert [f.name for f in gevonden[0].files] == ["origineel.jpg", "origineel-2.png"]
        sql = str(
            sessie.execute.call_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
        )
        assert f"foundation_content_bestanden.tenant_id = {TENANT}" in sql
        assert "foundation_content_bestanden.content_id IN (5)" in sql

    @pytest.mark.asyncio
    async def test_zonder_items_geen_tweede_query(self) -> None:
        from src.core.services.foundation_archive_service import FoundationArchiveService

        items = MagicMock()
        items.scalars.return_value.all.return_value = []
        sessie = AsyncMock()
        sessie.execute.side_effect = [items]
        tenant = MagicMock()
        tenant.id, tenant.slug = TENANT, "hetlevendmonument"
        assert (
            await FoundationArchiveService(storage=MagicMock()).collect_items(
                session=sessie, tenant=tenant
            )
            == []
        )


# --- 7: iPhone-video ------------------------------------------------------------------


def _blok(soort: bytes, inhoud: bytes) -> bytes:
    return (8 + len(inhoud)).to_bytes(4, "big") + soort + inhoud


class TestIPhoneVideo:
    def _mov(self) -> bytes:
        ftyp = _blok(b"ftyp", b"qt  \x00\x00\x00\x00qt  ")
        xyz = _blok(b"\xa9xyz", b"\x00\x11\x15\xc7+51.9123+004.3456/")
        moov = _blok(b"moov", _blok(b"mvhd", b"\x00" * 20) + _blok(b"udta", xyz))
        xmp = _blok(
            b"uuid",
            bytes.fromhex("be7acfcb97a942e89c71999491e3afac")
            + b"<exif:GPSLatitude>51,54.6N</exif:GPSLatitude>",
        )
        mdat = _blok(b"mdat", b"\x01\x02\x03\x04" * 8)
        return ftyp + moov + xmp + mdat

    def test_mov_is_toegestaan(self) -> None:
        assert (
            detect_allowed_mime(
                self._mov(), filename="IMG_0001.MOV", declared_content_type="video/quicktime"
            )
            == "video/quicktime"
        )

    def test_locatie_en_xmp_verdwijnen_en_de_lengte_blijft(self) -> None:
        bron = self._mov()
        schoon = verwijder_metadata(bron, "video/quicktime")
        assert len(schoon) == len(bron)
        assert b"+51.9123" not in schoon
        assert b"GPSLatitude" not in schoon
        assert schoon.endswith(b"\x01\x02\x03\x04" * 8)
