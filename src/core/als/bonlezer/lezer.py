"""De lezer: een bestand (PDF of beeld) wordt tekst, lokaal en zonder netwerk (bonlezer dag 1).

Keuze (docs/onderzoek-open-source-bonlezer.md): Docling (MIT) met Tesseract `nld` (Apache-2.0) als
OCR-motor. Beide draaien op deze machine; er gaat niets naar buiten.

Wat "zonder netwerk" hier betekent, en waar dat ophoudt:

1. `geen_netwerk()` is een TRIPDRAAD en geen hek. Binnen het blok faalt een uitgaande
   socketverbinding in dit proces met `GeenNetwerkToegestaan`, zodat een bibliotheek die tijdens het
   lezen iets van het internet wil ophalen luid faalt in plaats van stil te werken. Het dekt
   `connect`, `connect_ex`, `sendto`, `sendmsg` en `getaddrinfo` van de standaardbibliotheek. Het
   dekt NIET: een subproces (Tesseract), sockets die al open stonden, een rechtstreekse aanroep van
   `_socket`, en asyncio-lussen met een eigen resolver. Het slot geldt voor het HELE proces (ook voor
   andere threads) zolang er een blok open is; draai de lezer daarom niet in een proces dat tegelijk
   databaseverbindingen opent.
2. De echte afdwinging is een container zonder netwerk (`docker run --network none`), zoals
   `scripts/bonlezer_meting.py` in de meetopstelling, of een netwerkbeleid op de worker.
3. Docling haalt zijn lay-outmodellen bij het EERSTE gebruik van Hugging Face. Dat mag niet
   tijdens het lezen: de modellen moeten vooraf in `artifacts_pad` staan (Docling zoekt dan alleen
   daar). `maak_converter` zet daarnaast `HF_HUB_OFFLINE` en `TRANSFORMERS_OFFLINE` als extra
   voorzorg. Die staan dan voor het hele proces aan; en omdat `huggingface_hub` ze bij het importeren
   leest, werken ze alleen als dat nog niet is gebeurd. De meting in de container bewijst alleen dat
   het MET `artifacts_pad` zonder netwerk werkt.

Wat de lezer weigert (zie `controleer_bestand`): een soort die niet in `TOEGESTANE_SOORTEN` staat,
een bestand waarvan de inhoud niet bij de extensie past, boven `MAX_BYTES` of (bij een beeld) boven
`MAX_PIXELS`. Docling krijgt bovendien `max_num_pages` en `max_file_size` en een
`document_timeout` mee. Foutmeldingen noemen de bestandsnaam niet: die kan van een klant komen.

De importen van Docling en Pillow staan binnen de functies: een omgeving zonder die pakketten kan de
veldenlaag en de rest van de applicatie gewoon laden.
"""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast

OCR_TAAL = "nld"
TOEGESTANE_SOORTEN = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})

#: Grenzen tegen een bestand dat de worker platlegt. Geen gemeten ondergrens: gekozen ruim boven wat een
#: bon of factuur nodig heeft (een A4 op 300 dpi is ongeveer 8,7 miljoen pixels) en laag genoeg om een
#: bom af te vangen. Aanpassen is een eigen besluit met een meting.
MAX_BYTES = 25_000_000
MAX_PIXELS = 40_000_000
MAX_PAGINAS = 10
MAX_CELLEN = 2000
DOCUMENT_TIMEOUT = 120.0

#: Het begin van een echt bestand per extensie.
_KOPPEN: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".bmp": (b"BM",),
}


class GeenNetwerkToegestaan(RuntimeError):
    """Tijdens het lezen is een uitgaande netwerkverbinding geprobeerd."""


class OngeldigBestand(ValueError):
    """Geen bestand dat de lezer kan lezen (soort, inhoud, grootte of niet aanwezig)."""


class _Converter(Protocol):
    def convert(self, bron: Path, **opties: object) -> object: ...


# -- het netwerkslot (tripdraad) ----------------------------------------------------------------

_SLOT = threading.Lock()
_DIEPTE = 0
_ORIGINEEL: list[tuple[object, str, object]] = []


def _geweigerd(*_: object, **__: object) -> None:
    raise GeenNetwerkToegestaan("de bonlezer mag tijdens het lezen geen netwerk gebruiken")


def _slottargets() -> list[tuple[object, str]]:
    doelen: list[tuple[object, str]] = [
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
        (socket.socket, "sendto"),
        (socket, "getaddrinfo"),
    ]
    if hasattr(socket.socket, "sendmsg"):
        doelen.append((socket.socket, "sendmsg"))
    return doelen


def _plaats_slot() -> None:
    for eigenaar, naam in _slottargets():
        _ORIGINEEL.append((eigenaar, naam, getattr(eigenaar, naam)))
        setattr(eigenaar, naam, _geweigerd)


def _haal_slot_weg() -> None:
    while _ORIGINEEL:
        eigenaar, naam, waarde = _ORIGINEEL.pop()
        setattr(eigenaar, naam, waarde)


@contextmanager
def geen_netwerk() -> Generator[None, None, None]:
    """Binnen dit blok faalt een uitgaande socketverbinding met `GeenNetwerkToegestaan`.

    Een teller met een slot: alleen de eerste binnenkomst plaatst het slot en alleen de laatste uitgang
    haalt het weg, zodat overlappende blokken (twee threads) het slot niet blijvend laten staan.
    Gemeten bij Gate 2: een versie zonder teller liet `socket.getaddrinfo` na twee verweven blokken
    permanent op "geweigerd".
    """
    global _DIEPTE
    with _SLOT:
        if _DIEPTE == 0:
            try:
                _plaats_slot()
            except BaseException:
                _haal_slot_weg()  # niets half geplaatst laten staan
                raise
        _DIEPTE += 1
    try:
        yield
    finally:
        with _SLOT:
            _DIEPTE -= 1
            if _DIEPTE == 0:
                _haal_slot_weg()


# -- invoercontrole -----------------------------------------------------------------------------


def _controleer_pixels(pad: Path) -> None:
    try:
        from PIL import Image
    except ImportError:  # zonder Pillow kan Docling het beeld ook niet lezen
        return
    try:
        with Image.open(pad) as beeld:
            frames = int(getattr(beeld, "n_frames", 1))
            if frames > MAX_PAGINAS:
                aantal_pixels = None
            else:
                # Elk frame apart: een TIFF met een klein eerste beeld en grote vervolgbeelden
                # kwam door een controle op alleen het eerste (Gate 2 ronde 2, gemeten).
                aantal_pixels = 0
                for index in range(frames):
                    beeld.seek(index)
                    aantal_pixels += beeld.size[0] * beeld.size[1]
    except Exception as fout:  # een kapot beeld is een ongeldig bestand, geen crash
        raise OngeldigBestand("het beeld is niet te openen") from fout
    if aantal_pixels is None:
        raise OngeldigBestand("het beeld heeft te veel pagina's")
    if aantal_pixels > MAX_PIXELS:
        raise OngeldigBestand("het beeld heeft te veel pixels")


def controleer_bestand(pad: Path) -> None:
    """Weiger wat de lezer niet hoort te openen. De foutmelding noemt de bestandsnaam niet."""
    soort = pad.suffix.lower()
    if soort not in TOEGESTANE_SOORTEN:
        raise OngeldigBestand(f"soort {soort!r} wordt niet gelezen")
    if not pad.is_file():
        raise OngeldigBestand("het bestand bestaat niet")
    grootte = pad.stat().st_size
    if grootte == 0:
        raise OngeldigBestand("het bestand is leeg")
    if grootte > MAX_BYTES:
        raise OngeldigBestand("het bestand is te groot")
    with pad.open("rb") as bestand:
        begin = bestand.read(16)
    if not any(begin.startswith(kop) for kop in _KOPPEN[soort]):
        raise OngeldigBestand("de inhoud past niet bij de extensie")
    if soort != ".pdf":
        _controleer_pixels(pad)


# -- de converter -------------------------------------------------------------------------------


def maak_converter(artifacts_pad: Path | None = None, taal: str = OCR_TAAL) -> _Converter:
    """Bouw de Docling-converter met Tesseract als OCR-motor, volledig offline.

    `artifacts_pad` wijst naar de map met de vooraf gedownloade Docling-modellen. Zonder die map
    zoekt Docling in zijn standaardcache en probeert het anders te downloaden; dat staat hier uit.
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

    opties = PdfPipelineOptions()
    opties.do_ocr = True
    opties.ocr_options = TesseractCliOcrOptions(lang=[taal])
    opties.document_timeout = DOCUMENT_TIMEOUT
    if artifacts_pad is not None:
        opties.artifacts_path = str(artifacts_pad)

    return cast(
        _Converter,
        DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=opties),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=opties),
            }
        ),
    )


class BonLezer:
    """Leest een bon of factuur als tekst. De converter wordt een keer gebouwd en hergebruikt."""

    def __init__(
        self,
        *,
        artifacts_pad: Path | None = None,
        taal: str = OCR_TAAL,
        converter: _Converter | None = None,
        tekst_uit: Callable[[object], str] | None = None,
    ) -> None:
        self._artifacts_pad = artifacts_pad
        self._taal = taal
        self._converter = converter
        self._tekst_uit = tekst_uit or regels_uit_resultaat

    def converteer(self, pad: Path) -> object:
        """Het ruwe resultaat van de converter, onder het netwerkslot. Voor meten en vergelijken."""
        controleer_bestand(pad)
        with geen_netwerk():
            if self._converter is None:
                self._converter = maak_converter(self._artifacts_pad, self._taal)
            resultaat = self._converter.convert(pad, max_num_pages=MAX_PAGINAS, max_file_size=MAX_BYTES)
        # Docling geeft bij een time-out of een deels mislukte lezing `partial_success` terug in plaats
        # van een fout (waarden gemeten in docling 2.139.0: `success` voor een gewone lezing). Een
        # deel van een document als geheel lezen zou een totaal uit een stuk van de bon geven.
        status = getattr(getattr(resultaat, "status", None), "value", None)
        if status is not None and status != "success":
            raise OngeldigBestand("het bestand is niet volledig gelezen")
        return resultaat

    def lees(self, pad: Path) -> str:
        """De tekst van het bestand. Faalt bij een ongeldig bestand (zie `controleer_bestand`)."""
        return self._tekst_uit(self.converteer(pad))


def _tekst_uit_docling(resultaat: object) -> str:
    """De platte tekst uit een Docling-resultaat (`result.document.export_to_text()`).

    Docling voegt aangrenzende regels samen tot een alinea: een totaalregel staat dan midden in een
    lange regel. Gemeten (docs/evidence/bonlezer-meting-*.md): daardoor las de veldenlaag het totaal
    in 1 van de 24 documenten goed. Voor het lezen van velden is `regels_uit_resultaat` bedoeld.
    """
    document = getattr(resultaat, "document")
    return str(document.export_to_text())


# -- regels opbouwen uit de celposities ----------------------------------------------------------

_Woord = tuple[float, float, float, str]  # (x links, y midden, hoogte, tekst)


def _cellen_per_pagina(resultaat: object) -> list[list[object]]:
    """Per pagina alle tekstcellen (regels bij een PDF met tekstlaag, woorden bij OCR), elk een keer."""
    paginas: list[list[object]] = []
    for pagina in getattr(resultaat, "pages", []):
        gezien: set[int] = set()
        cellen: list[object] = []
        assembled = getattr(pagina, "assembled", None)
        for element in getattr(assembled, "elements", []) or []:
            cluster = getattr(element, "cluster", None)
            for cel in getattr(cluster, "cells", []) or []:
                if id(cel) not in gezien and str(getattr(cel, "text", "")).strip():
                    gezien.add(id(cel))
                    cellen.append(cel)
        paginas.append(cellen)
    return paginas


def _midden_en_hoogte(cel: object) -> tuple[float, float, float]:
    """(x links, y midden, hoogte) van een cel, ongeacht of y omhoog of omlaag oploopt."""
    rechthoek = getattr(cel, "rect")
    y0, y2 = float(rechthoek.r_y0), float(rechthoek.r_y2)
    return float(rechthoek.r_x0), (y0 + y2) / 2, abs(y0 - y2)


def _groepeer_in_regels(woorden: list[_Woord]) -> list[list[_Woord]]:
    """Groepeer woorden in regels, van links naar rechts, ook bij een scheve foto.

    Een woord hoort bij de regel waarvan het LAATSTE woord het dichtst bij zijn hoogte staat, en
    wel binnen een halve celhoogte. Vergelijken met het EERSTE woord van de regel splitst een scheve
    regel (de woorden zakken naar rechts), zoals gemeten in de eerste meting: het label `KvK` en het
    nummer kwamen dan op verschillende regels. De regels zelf volgen op hun gemiddelde hoogte.
    De rekentijd groeit met woorden x regels; daarom begrenst `MAX_CELLEN` het aantal per pagina.
    """
    regels: list[list[_Woord]] = []
    for woord in sorted(woorden, key=lambda w: w[0]):
        beste: list[_Woord] | None = None
        kleinste = float("inf")
        for regel in regels:
            laatste = regel[-1]
            afstand = abs(woord[1] - laatste[1])
            if afstand <= max(woord[2], laatste[2]) * 0.5 and afstand < kleinste:
                beste, kleinste = regel, afstand
        if beste is None:
            regels.append([woord])
        else:
            beste.append(woord)
    return sorted(regels, key=lambda regel: sum(w[1] for w in regel) / len(regel))


def _regels_van_pagina(cellen: list[object]) -> list[str]:
    if len(cellen) > MAX_CELLEN:
        raise OngeldigBestand("te veel tekstcellen op een pagina")
    oorsprong = str(getattr(getattr(cellen[0], "rect"), "coord_origin", "")).upper()
    boven_eerst = "BOTTOMLEFT" not in oorsprong
    gemeten: list[_Woord] = []
    for cel in cellen:
        x, y, hoogte = _midden_en_hoogte(cel)
        gemeten.append((x, y if boven_eerst else -y, hoogte, str(getattr(cel, "text", ""))))
    return [" ".join(woord[3] for woord in regel) for regel in _groepeer_in_regels(gemeten)]


def regels_uit_resultaat(resultaat: object) -> str:
    """Bouw regels op uit de posities van de cellen; val terug op `export_to_text` zonder cellen.

    Cellen waarvan het verticale midden binnen een halve celhoogte van de regel ligt, horen bij
    dezelfde regel; binnen een regel gaat het van links naar rechts. De volgorde van de regels
    volgt de oorsprong van het coordinatenstelsel (boven of onder). Elke pagina wordt apart
    gegroepeerd, zodat een regel op pagina 2 niet met een regel op pagina 1 samenvalt.
    """
    paginas = [cellen for cellen in _cellen_per_pagina(resultaat) if cellen]
    if not paginas:
        return _tekst_uit_docling(resultaat)
    return "\n".join(regel for cellen in paginas for regel in _regels_van_pagina(cellen))
