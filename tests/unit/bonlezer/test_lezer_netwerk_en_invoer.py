"""De lezer maakt geen netwerkverbinding en weigert wat hij niet kan lezen (bonlezer dag 1).

Deze tests draaien zonder Docling en zonder Tesseract: de converter is een nagemaakte, omdat hier
de OMRINGING van het lezen wordt gemeten (het netwerkslot, de invoercontrole), niet het lezen zelf.
Het echte lezen staat in `scripts/bonlezer_meting.py`, in een container zonder netwerk.

Wat het netwerkslot NIET dekt staat in `src/core/als/bonlezer/lezer.py`: een subproces (Tesseract)
valt erbuiten. Dat is de reden van de container zonder netwerk bij de meting.

Mutatiebewijs (2026-10-15): `geen_netwerk()` zonder de vervangingen laten draaien maakt de drie
netwerktests rood; een slot dat ook na het blok blijft staan maakt de herstel-test rood.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.als.bonlezer import lezer as lezer_module
from src.core.als.bonlezer.lezer import (
    BonLezer,
    GeenNetwerkToegestaan,
    OngeldigBestand,
    geen_netwerk,
)

#: Het begin van een echt bestand per soort: de lezer toetst de INHOUD, niet alleen de extensie.
KOPPEN = {
    ".pdf": b"%PDF-1.4\n",
    ".jpg": b"\xff\xd8\xff\xe0",
    ".jpeg": b"\xff\xd8\xff\xe0",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".tif": b"II*\x00",
    ".tiff": b"II*\x00",
    ".bmp": b"BM",
}


class _NagemaakteConverter:
    """Geeft vaste tekst terug, of probeert eerst het netwerk op."""

    def __init__(self, tekst: str = "TOTAAL 1,00", *, wil_netwerk: bool = False) -> None:
        self.tekst = tekst
        self.wil_netwerk = wil_netwerk

    def convert(self, bron: Path, **_opties: object) -> object:
        if self.wil_netwerk:
            socket.create_connection(("192.0.2.1", 443), timeout=1)
        return SimpleNamespace(document=SimpleNamespace(export_to_text=lambda: self.tekst))


def _bestand(map_: Path, naam: str = "bon.jpg", inhoud: bytes | None = None) -> Path:
    """Een bestand met de goede kop; een beeld is een ECHT klein beeld als Pillow aanwezig is."""
    pad = map_ / naam
    if inhoud is not None:
        pad.write_bytes(inhoud)
        return pad
    soort = pad.suffix.lower()
    if soort in {".jpg", ".jpeg", ".tif", ".tiff", ".png", ".bmp"}:
        try:
            from PIL import Image

            Image.new("L", (5, 5)).save(pad, format={".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF", ".png": "PNG", ".bmp": "BMP"}[soort])
            return pad
        except ImportError:
            pass
    pad.write_bytes(KOPPEN.get(soort, b"x") + b"0")
    return pad


class TestHetNetwerkslot:
    def test_a_connection_inside_the_block_is_refused(self) -> None:
        with geen_netwerk(), pytest.raises(GeenNetwerkToegestaan):
            socket.create_connection(("192.0.2.1", 443), timeout=1)

    def test_a_name_lookup_inside_the_block_is_refused(self) -> None:
        with geen_netwerk(), pytest.raises(GeenNetwerkToegestaan):
            socket.getaddrinfo("example.com", 443)

    def test_connect_ex_inside_the_block_is_refused(self) -> None:
        with geen_netwerk(), socket.socket() as s, pytest.raises(GeenNetwerkToegestaan):
            s.connect_ex(("192.0.2.1", 443))

    def test_the_block_is_lifted_afterwards(self) -> None:
        voor = (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo)

        with geen_netwerk():
            pass

        assert (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo) == voor

    def test_the_block_is_lifted_after_an_exception_inside_it(self) -> None:
        voor = socket.socket.connect

        with pytest.raises(RuntimeError), geen_netwerk():
            raise RuntimeError("fout in het blok")

        assert socket.socket.connect is voor


class TestDeLezerGebruiktHetSlot:
    def test_a_converter_that_wants_the_network_makes_reading_fail(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter(wil_netwerk=True))

        with pytest.raises(GeenNetwerkToegestaan):
            lezer.lees(_bestand(tmp_path))

    def test_a_working_converter_gives_its_text(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter("TOTAAL 12,34"))

        assert lezer.lees(_bestand(tmp_path)) == "TOTAAL 12,34"


class TestDeInvoer:
    def test_an_unknown_file_type_is_refused(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter())

        with pytest.raises(OngeldigBestand):
            lezer.lees(_bestand(tmp_path, "bon.exe"))

    def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter())

        with pytest.raises(OngeldigBestand):
            lezer.lees(tmp_path / "bestaat_niet.pdf")

    def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter())

        with pytest.raises(OngeldigBestand):
            lezer.lees(_bestand(tmp_path, "leeg.pdf", b""))

    @pytest.mark.parametrize("naam", ["bon.PDF", "bon.JPG", "bon.png", "bon.tiff"])
    def test_the_supported_types_are_accepted_in_any_case(self, tmp_path: Path, naam: str) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter("ok"))

        assert lezer.lees(_bestand(tmp_path, naam)) == "ok"


class TestHetNetwerkslotIsEenTripdraadEnGeenHek:
    def test_a_plain_connect_inside_the_block_is_refused(self) -> None:
        with geen_netwerk(), socket.socket() as s, pytest.raises(GeenNetwerkToegestaan):
            s.connect(("192.0.2.1", 443))

    def test_sendto_inside_the_block_is_refused(self) -> None:
        with geen_netwerk(), socket.socket(type=socket.SOCK_DGRAM) as s:
            with pytest.raises(GeenNetwerkToegestaan):
                s.sendto(b"x", ("192.0.2.1", 53))

    def test_two_overlapping_blocks_leave_no_block_behind(self) -> None:
        """Gemeten (Gate 2): twee threads die verweven in en uit het blok gaan lieten het slot staan."""
        voor = (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo)
        binnen_1, binnen_2 = threading.Event(), threading.Event()
        mag_uit_1, mag_uit_2 = threading.Event(), threading.Event()

        def draad(binnen: threading.Event, mag_uit: threading.Event) -> None:
            with geen_netwerk():
                binnen.set()
                mag_uit.wait(5)

        t1 = threading.Thread(target=draad, args=(binnen_1, mag_uit_1))
        t2 = threading.Thread(target=draad, args=(binnen_2, mag_uit_2))
        t1.start()
        binnen_1.wait(5)
        t2.start()
        binnen_2.wait(5)
        mag_uit_1.set()
        t1.join(5)
        tussentijds = socket.socket.connect is not voor[0]
        mag_uit_2.set()
        t2.join(5)

        assert tussentijds, "het slot ging al open terwijl de tweede draad er nog in zat"
        assert (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo) == voor


class TestDeInhoudKlopt:
    def test_a_file_whose_content_does_not_match_its_extension_is_refused(
        self, tmp_path: Path
    ) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter())

        with pytest.raises(OngeldigBestand):
            lezer.lees(_bestand(tmp_path, "bon.pdf", b"MZ\x90\x00dit is een programma"))

    def test_a_file_over_the_size_limit_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lezer_module, "MAX_BYTES", 10)
        lezer = BonLezer(converter=_NagemaakteConverter())

        with pytest.raises(OngeldigBestand):
            lezer.lees(_bestand(tmp_path, "bon.pdf", b"%PDF-1.4\n" + b"0" * 100))

    def test_an_image_over_the_pixel_limit_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        image = pytest.importorskip("PIL.Image")
        pad = tmp_path / "groot.png"
        image.new("L", (60, 60)).save(pad)
        monkeypatch.setattr(lezer_module, "MAX_PIXELS", 1000)
        lezer = BonLezer(converter=_NagemaakteConverter())

        with pytest.raises(OngeldigBestand):
            lezer.lees(pad)

    def test_an_image_within_the_pixel_limit_is_read(self, tmp_path: Path) -> None:
        image = pytest.importorskip("PIL.Image")
        pad = tmp_path / "klein.png"
        image.new("L", (20, 20)).save(pad)

        assert BonLezer(converter=_NagemaakteConverter("ok")).lees(pad) == "ok"

    def test_the_error_does_not_contain_the_file_name(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_NagemaakteConverter())

        with pytest.raises(OngeldigBestand) as fout:
            lezer.lees(_bestand(tmp_path, "klant-jansen-factuur.pdf", b"niet-een-pdf"))

        assert "jansen" not in str(fout.value)


class TestEenBestandMetMeerdereBeelden:
    """Gate 2 ronde 2 (gemeten): een TIFF met een klein eerste beeld en grote vervolgbeelden kwam door."""

    def test_a_tiff_whose_later_frame_is_huge_is_refused(self, tmp_path: Path) -> None:
        image = pytest.importorskip("PIL.Image")
        pad = tmp_path / "bom.tif"
        image.new("1", (10, 10)).save(
            pad, save_all=True, append_images=[image.new("1", (9000, 9000))], compression="group4"
        )

        with pytest.raises(OngeldigBestand):
            BonLezer(converter=_NagemaakteConverter()).lees(pad)

    def test_a_tiff_with_more_frames_than_pages_allowed_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        image = pytest.importorskip("PIL.Image")
        pad = tmp_path / "veel.tif"
        eerste = image.new("1", (10, 10))
        eerste.save(pad, save_all=True, append_images=[image.new("1", (10, 10))] * 2)
        monkeypatch.setattr(lezer_module, "MAX_PAGINAS", 2)

        with pytest.raises(OngeldigBestand):
            BonLezer(converter=_NagemaakteConverter()).lees(pad)

    def test_a_small_two_frame_tiff_is_read(self, tmp_path: Path) -> None:
        image = pytest.importorskip("PIL.Image")
        pad = tmp_path / "twee.tif"
        image.new("1", (10, 10)).save(pad, save_all=True, append_images=[image.new("1", (10, 10))])

        assert BonLezer(converter=_NagemaakteConverter("ok")).lees(pad) == "ok"


class _ConverterMetStatus:
    def __init__(self, waarde: str | None) -> None:
        self.waarde = waarde

    def convert(self, bron: Path, **_opties: object) -> object:
        resultaat = SimpleNamespace(document=SimpleNamespace(export_to_text=lambda: "tekst"))
        if self.waarde is not None:
            resultaat.status = SimpleNamespace(value=self.waarde)
        return resultaat


class TestEenAfgebrokenLezingIsGeenLezing:
    """Docling geeft bij een time-out een gedeeltelijk resultaat (`partial_success`) in plaats van een fout."""

    def test_a_partial_result_is_refused(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_ConverterMetStatus("partial_success"))

        with pytest.raises(OngeldigBestand):
            lezer.lees(_bestand(tmp_path))

    def test_a_failure_status_is_refused(self, tmp_path: Path) -> None:
        lezer = BonLezer(converter=_ConverterMetStatus("failure"))

        with pytest.raises(OngeldigBestand):
            lezer.lees(_bestand(tmp_path))

    def test_a_success_status_is_read(self, tmp_path: Path) -> None:
        assert BonLezer(converter=_ConverterMetStatus("success")).lees(_bestand(tmp_path)) == "tekst"

    def test_a_result_without_a_status_is_read(self, tmp_path: Path) -> None:
        assert BonLezer(converter=_ConverterMetStatus(None)).lees(_bestand(tmp_path)) == "tekst"


class TestHetSlotBlijftNietStaanAlsHetPlaatsenMislukt:
    def test_a_failure_while_placing_the_block_leaves_nothing_behind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        voor = socket.socket.connect
        monkeypatch.setattr(
            lezer_module,
            "_slottargets",
            lambda: [(socket.socket, "connect"), (socket, "bestaat_niet_xyz")],
        )

        with pytest.raises(AttributeError), geen_netwerk():
            pass

        assert socket.socket.connect is voor
        assert lezer_module._DIEPTE == 0
