"""Maak de Nederlandse bonnen- en factuurtestset met VERZONNEN gegevens (bonlezer dag 1).

Waarom dit bestaat. Er is geen openbare set Nederlandse kassabonnen of facturen met antwoorden
(`docs/onderzoek-open-source-bonlezer.md`, sectie "Testset"), en echte bonnen van personen komen
er niet in. Dit script maakt ze zelf, deterministisch (vast zaad): elke run geeft byte-voor-byte
dezelfde bestanden terug, zodat de set in git kan staan en een wijziging zichtbaar is.

Per document ontstaan drie bestanden in `tests/fixtures/bonnen/`:

- `<naam>.pdf` of `<naam>.jpg`: wat een lezer te zien krijgt;
- `<naam>.json`: de JUISTE antwoorden (leverancier, datum, totaal, btw per tarief, ...);
- `<naam>.tekst.txt`: de exacte regels die op het document zijn gezet. Daarmee meet het
  meetscript de veldenlaag los van het lezen (OCR): een fout in de brontekst is een regelfout,
  een fout alleen na het lezen is een leesfout.

Vormen (24 stuks): 8 facturen als PDF met tekstlaag in drie sjablonen, 4 facturen als gescande
PDF (alleen beeld, dus OCR nodig), 12 kassabonnen als foto-achtig JPG (schuin, ruis, onscherp,
ongelijk belicht).

De bedragen kloppen intern: btw per tarief wordt per groep afgerond (half-up) en het totaal is de
som. De namen, adressen, KvK- en btw-nummers zijn verzonnen; een toevallige overeenkomst met een
bestaand bedrijf is niet bedoeld en niet gecontroleerd.

Gebruik:
    python scripts/maak_bonnen_testset.py            # schrijft naar tests/fixtures/bonnen/
    python scripts/maak_bonnen_testset.py --controle # geeft een fout als de bestanden afwijken
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from fpdf import FPDF

REPO = Path(__file__).resolve().parent.parent
DOEL = REPO / "tests" / "fixtures" / "bonnen"
ZAAD = 20261015

MAANDEN = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]  # fmt: skip

TWEE = Decimal("0.01")


@dataclass(frozen=True)
class Regel:
    omschrijving: str
    aantal: int
    prijs: Decimal  # per stuk: zonder btw (facturen) of met btw (bonnen)
    tarief: int  # 9 of 21


LEVERANCIERS_FACTUUR = [
    ("Ruitenwasserij Helderblik BV", "Industrieweg 14, 3902 KL Voorbeeldveen"),
    ("Studio Pixeltuin VOF", "Havenkade 3, 2511 AB Proefstad"),
    ("Kantoorhuis Papierwerk BV", "Handelsstraat 88, 5611 ZG Testhoven"),
    ("Installatiebedrijf Warmtebron", "Ambachtsweg 21, 6811 KD Verzonnen"),
    ("Drukkerij De Zwarte Inkt", "Pers 5, 8011 PA Monsterdam"),
    ("Boekhoudkantoor Saldo & Co", "Marktplein 9, 3511 CK Voorbeeldveen"),
    ("Hovenier Groenpoot", "Tuinlaan 2, 7411 EC Proefstad"),
    ("IT-service Netwerkhulp BV", "Kabelstraat 40, 2201 BX Testhoven"),
    ("Cateraar Lekkerbek", "Keukenpad 17, 9711 LM Verzonnen"),
    ("Transport Wielzicht BV", "Wegenplein 6, 4811 AA Monsterdam"),
    ("Architectenbureau Tekenlijn", "Schetsweg 31, 3012 JD Voorbeeldveen"),
    ("Schildersbedrijf Kwast & Zoon", "Verfstraat 12, 5038 NB Proefstad"),
]

LEVERANCIERS_BON = [
    ("Bakkerij De Gouden Korst", "Dorpsstraat 12, 1234 AB Voorbeeldstad"),
    ("Supermarkt Vers & Vol", "Marktweg 101, 2345 CD Proefstad"),
    ("Tuincentrum Groenhart", "Bloemlaan 7, 3456 EF Testhoven"),
    ("Slagerij Van der Worst", "Vleesstraat 3, 4567 GH Verzonnen"),
    ("Koffiehuis Het Bonenhuis", "Pleinweg 18, 5678 IJ Monsterdam"),
    ("Bouwmarkt Hamer & Spijker", "Industrielaan 55, 6789 KL Voorbeeldveen"),
    ("Drogisterij Gezond Gevoel", "Winkelcentrum 4, 7890 MN Proefstad"),
    ("Snackbar Frituur Fortuin", "Stationsplein 2, 8901 OP Testhoven"),
    ("Boekhandel Leesplezier", "Boekenstraat 16, 9012 QR Verzonnen"),
    ("Groentehal De Oogst", "Tuinweg 33, 1123 ST Monsterdam"),
    ("Kantoorwinkel Pen & Papier", "Schrijfpad 8, 2234 UV Voorbeeldveen"),
    ("Bloemist Roos & Tulp", "Bloemgracht 21, 3345 WX Proefstad"),
]

ARTIKELEN_BON_9 = [
    ("Volkorenbrood", 349), ("Appelflap", 215), ("Melk 1L", 129), ("Kaas jong", 595),
    ("Boerenkool", 189), ("Sinaasappelen", 299), ("Eieren 10st", 275), ("Roggebrood", 310),
    ("Yoghurt", 145), ("Aardappelen 2kg", 249), ("Pindakaas", 235), ("Rookworst", 360),
]  # fmt: skip
ARTIKELEN_BON_21 = [
    ("Tasje", 25), ("Wc-papier 8 rol", 449), ("Batterijen AA", 599), ("Afwasmiddel", 189),
    ("Kaarsen", 349), ("Lijm", 429), ("Schroeven doos", 799), ("Pennen 5st", 395),
    ("Stopcontact", 1295), ("Plantenvoeding", 649), ("Zonnebrand", 999), ("Tijdschrift", 595),
]  # fmt: skip
ARTIKELEN_FACTUUR_21 = [
    ("Werkzaamheden per uur", 7500), ("Materiaalkosten", 12500), ("Voorrijkosten", 3500),
    ("Licentie per maand", 4900), ("Advieswerk dagdeel", 32500), ("Ontwerpkosten", 45000),
    ("Drukwerk 500 stuks", 18500), ("Onderhoud contract", 25000),
]  # fmt: skip
ARTIKELEN_FACTUUR_9 = [
    ("Lunch vergadering", 4250), ("Boeken en tijdschriften", 2900), ("Broodjes personeel", 3100),
]  # fmt: skip


def euro(bedrag: Decimal) -> str:
    """12345.6 -> '12.345,60' (Nederlandse schrijfwijze)."""
    tekst = f"{bedrag:,.2f}"
    return tekst.replace(",", "#").replace(".", ",").replace("#", ".")


def afronden(bedrag: Decimal) -> Decimal:
    return bedrag.quantize(TWEE, rounding=ROUND_HALF_UP)


def maak_nummer(rnd: random.Random, cijfers: int) -> str:
    return "".join(str(rnd.randint(0, 9)) for _ in range(cijfers))


def maak_datum(rnd: random.Random) -> date:
    return date(2026, rnd.randint(1, 10), rnd.randint(1, 28))


def schrijf_datum(d: date, stijl: int) -> str:
    stijlen = [
        f"{d.day:02d}-{d.month:02d}-{d.year}",
        f"{d.day:02d}/{d.month:02d}/{d.year}",
        f"{d.day} {MAANDEN[d.month - 1]} {d.year}",
        f"{d.day:02d}.{d.month:02d}.{d.year}",
        f"{d.year}-{d.month:02d}-{d.day:02d}",
        f"{d.day:02d}-{d.month:02d}-{d.year % 100:02d}",
    ]
    return stijlen[stijl % len(stijlen)]


# -- inhoud van een document -------------------------------------------------------------------


@dataclass
class Document:
    naam: str
    soort: str  # factuur_pdf | factuur_scan | bon_foto
    regels: list[str]  # de tekst zoals die op het document staat
    antwoorden: dict[str, object]


def bouw_factuur(rnd: random.Random, index: int, sjabloon: int, soort: str) -> Document:
    naam_lev, adres = LEVERANCIERS_FACTUUR[index % len(LEVERANCIERS_FACTUUR)]
    kvk = maak_nummer(rnd, 8)
    btw_nr = f"NL{maak_nummer(rnd, 9)}B{rnd.randint(1, 3):02d}"
    nummer = rnd.choice([f"2026-{rnd.randint(100, 999)}", f"F{rnd.randint(10000, 99999)}"])
    datum = maak_datum(rnd)
    stijl = sjabloon * 2 + index

    regels_21 = [
        Regel(o, rnd.randint(1, 4), Decimal(p) / 100, 21)
        for o, p in rnd.sample(ARTIKELEN_FACTUUR_21, rnd.randint(2, 3))
    ]
    regels_9: list[Regel] = []
    if index % 3 == 0:
        o, p = rnd.choice(ARTIKELEN_FACTUUR_9)
        regels_9 = [Regel(o, rnd.randint(1, 3), Decimal(p) / 100, 9)]
    alle = regels_21 + regels_9

    netto: dict[int, Decimal] = {}
    for r in alle:
        netto[r.tarief] = netto.get(r.tarief, Decimal(0)) + r.aantal * r.prijs
    btw = {t: afronden(n * Decimal(t) / 100) for t, n in netto.items()}
    subtotaal = sum(netto.values(), Decimal(0))
    totaal = subtotaal + sum(btw.values(), Decimal(0))

    kop = [naam_lev, adres, f"KvK {kvk}   BTW-nummer {btw_nr}", "", "FACTUUR"]
    if sjabloon == 0:
        meta = [f"Factuurnummer: {nummer}", f"Factuurdatum: {schrijf_datum(datum, stijl)}", ""]
    elif sjabloon == 1:
        meta = [f"Datum: {schrijf_datum(datum, stijl)}", f"Factuurnr.: {nummer}", ""]
    else:
        meta = [f"Factuurnummer {nummer}", f"Factuurdatum {schrijf_datum(datum, stijl)}", ""]

    tabel = ["Omschrijving                Aantal   Prijs     BTW   Bedrag"]
    for r in alle:
        tabel.append(
            f"{r.omschrijving}  {r.aantal} x {euro(r.prijs)}  {r.tarief}%  "
            f"{euro(r.aantal * r.prijs)}"
        )
    voet = ["", f"Subtotaal excl. btw: EUR {euro(subtotaal)}"]
    for t in sorted(btw, reverse=True):
        if sjabloon == 0:
            voet.append(f"BTW {t}% over EUR {euro(netto[t])}: EUR {euro(btw[t])}")
        elif sjabloon == 1:
            voet.append(f"BTW {t}%  EUR {euro(btw[t])}")
        else:
            voet.append(f"Omzetbelasting {t}% ({euro(netto[t])})  {euro(btw[t])}")
    totaal_label = ["Totaal incl. btw", "Totaal te betalen", "Totaalbedrag"][sjabloon]
    voet.append(f"{totaal_label}: EUR {euro(totaal)}")
    voet += ["", f"Betaling binnen 14 dagen op NL00 TEST 0123 4567 89 t.n.v. {naam_lev}"]

    antwoorden: dict[str, object] = {
        "soort": soort,
        "leverancier": naam_lev,
        "datum": datum.isoformat(),
        "totaal": str(totaal),
        "factuurnummer": nummer,
        "btw": {str(t): str(b) for t, b in sorted(btw.items())},
        "btw_nummer": btw_nr,
        "kvk_nummer": kvk,
    }
    return Document(f"factuur_{index + 1:02d}", soort, kop + meta + tabel + voet, antwoorden)


def btw_regels_bon(variant: int, btw: dict[int, Decimal], bruto: dict[int, Decimal]) -> list[str]:
    """De btw-regels van een bon in een van drie opmaken (kort, met grondslag, als tabel)."""
    tarieven = sorted(btw, reverse=True)
    if variant == 0:
        return [f"BTW {t}%  {euro(btw[t])}" for t in tarieven]
    if variant == 1:
        return [f"BTW {t}% over {euro(bruto[t] - btw[t])}  {euro(btw[t])}" for t in tarieven]
    tabel = ["Tarief  Netto  BTW  Bruto"]
    for t in tarieven:
        tabel.append(f"{t}%  {euro(bruto[t] - btw[t])}  {euro(btw[t])}  {euro(bruto[t])}")
    return tabel


def bouw_bon(rnd: random.Random, index: int) -> Document:
    naam_lev, adres = LEVERANCIERS_BON[index % len(LEVERANCIERS_BON)]
    kvk = maak_nummer(rnd, 8)
    btw_nr = f"NL{maak_nummer(rnd, 9)}B{rnd.randint(1, 3):02d}"
    datum = maak_datum(rnd)
    uur, minuut = rnd.randint(8, 20), rnd.randint(0, 59)
    bonnummer = maak_nummer(rnd, 6)

    gemengd = index % 3 != 0  # een op de drie bonnen heeft alleen 9%
    regels: list[Regel] = []
    for o, p in rnd.sample(ARTIKELEN_BON_9, rnd.randint(2, 4)):
        regels.append(Regel(o, rnd.randint(1, 3), Decimal(p) / 100, 9))
    if gemengd or index % 4 == 1:
        for o, p in rnd.sample(ARTIKELEN_BON_21, rnd.randint(1, 3)):
            regels.append(Regel(o, rnd.randint(1, 2), Decimal(p) / 100, 21))

    bruto: dict[int, Decimal] = {}
    for r in regels:
        bruto[r.tarief] = bruto.get(r.tarief, Decimal(0)) + r.aantal * r.prijs
    btw = {t: afronden(b * Decimal(t) / (100 + Decimal(t))) for t, b in bruto.items()}
    totaal = sum(bruto.values(), Decimal(0))

    totaal_label = ["TOTAAL", "TE BETALEN", "Totaal te betalen", "TOTAAL EUR"][index % 4]
    regels_txt = [
        naam_lev.upper(),
        adres,
        f"KvK {kvk}  BTW {btw_nr}",
        "",
        f"Datum {schrijf_datum(datum, index)}  {uur:02d}:{minuut:02d}",
        f"Bon {bonnummer}",
        "",
    ]
    for r in regels:
        regels_txt.append(
            f"{r.omschrijving} {r.aantal}x{euro(r.prijs)}  {euro(r.aantal * r.prijs)}"
        )
    regels_txt.append("")
    regels_txt.append(f"{totaal_label}  {euro(totaal)}")
    regels_txt += btw_regels_bon(index % 3, btw, bruto)
    regels_txt += ["", "Betaald met PIN", "Bedankt en tot ziens!"]

    antwoorden: dict[str, object] = {
        "soort": "bon_foto",
        "leverancier": naam_lev,
        "datum": datum.isoformat(),
        "totaal": str(totaal),
        "factuurnummer": None,
        "btw": {str(t): str(b) for t, b in sorted(btw.items())},
        "btw_nummer": btw_nr,
        "kvk_nummer": kvk,
    }
    return Document(f"bon_{index + 1:02d}", "bon_foto", regels_txt, antwoorden)


# -- weergave ----------------------------------------------------------------------------------


def teken_pagina(regels: list[str], breedte: int, fontgrootte: int, wit: int = 245) -> Image.Image:
    """Zet de regels onder elkaar op een lichtgrijs vlak, zoals een geprinte bon of scan."""
    lettertype = ImageFont.load_default(size=fontgrootte)
    regelhoogte = int(fontgrootte * 1.45)
    hoogte = regelhoogte * (len(regels) + 4)
    beeld = Image.new("L", (breedte, hoogte), wit)
    tekenaar = ImageDraw.Draw(beeld)
    y = regelhoogte
    for regel in regels:
        tekenaar.text((int(fontgrootte * 1.2), y), regel, fill=25, font=lettertype)
        y += regelhoogte
    return beeld


def maak_foto_achtig(beeld: Image.Image, rnd: random.Random, sterkte: float) -> Image.Image:
    """Schuin, ongelijk belicht, korrelig en licht onscherp."""
    hoek = rnd.uniform(-3.5, 3.5) * sterkte
    gedraaid = beeld.rotate(hoek, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=210)
    matrix = np.asarray(gedraaid, dtype=np.float32)
    breedte = matrix.shape[1]
    verloop = np.linspace(1.0 - 0.18 * sterkte, 1.0 + 0.05, breedte, dtype=np.float32)
    matrix = matrix * verloop[None, :]
    ruis = np.random.default_rng(rnd.randint(0, 2**31 - 1)).normal(0, 7 * sterkte, matrix.shape)
    matrix = np.clip(matrix + ruis.astype(np.float32), 0, 255).astype(np.uint8)
    return Image.fromarray(matrix).filter(ImageFilter.GaussianBlur(0.5 * sterkte))


def als_jpeg(beeld: Image.Image, kwaliteit: int = 72) -> bytes:
    buffer = io.BytesIO()
    beeld.convert("L").save(buffer, "JPEG", quality=kwaliteit, optimize=False)
    return buffer.getvalue()


def _nieuwe_pdf() -> FPDF:
    pdf = FPDF(format="A4")
    # Vaste datum en geen compressie: dezelfde invoer geeft dezelfde bytes.
    pdf.set_creation_date(datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc))
    pdf.set_compression(False)
    pdf.set_auto_page_break(False)
    pdf.add_page()
    return pdf


def pdf_met_tekst(regels: list[str]) -> bytes:
    pdf = _nieuwe_pdf()
    pdf.set_font("Helvetica", size=10)
    y = 20.0
    for regel in regels:
        pdf.text(18, y, regel)
        y += 5.2
    return bytes(pdf.output())


def pdf_met_beeld(jpeg: bytes) -> bytes:
    pdf = _nieuwe_pdf()
    pdf.image(io.BytesIO(jpeg), x=10, y=10, w=190)
    return bytes(pdf.output())


def alle_documenten() -> list[Document]:
    rnd = random.Random(ZAAD)
    docs: list[Document] = []
    for i in range(8):
        docs.append(bouw_factuur(rnd, i, i % 3, "factuur_pdf"))
    for i in range(8, 12):
        docs.append(bouw_factuur(rnd, i, i % 3, "factuur_scan"))
    for i in range(12):
        docs.append(bouw_bon(rnd, i))
    return docs


def maak_alles() -> dict[str, bytes]:
    """Geef {bestandsnaam: inhoud}; schrijft zelf niets."""
    rnd = random.Random(ZAAD + 1)
    uit: dict[str, bytes] = {}
    for volgnummer, doc in enumerate(alle_documenten()):
        uit[f"{doc.naam}.json"] = (
            json.dumps(doc.antwoorden, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
        ).encode()
        uit[f"{doc.naam}.tekst.txt"] = ("\n".join(doc.regels) + "\n").encode()
        if doc.soort == "factuur_pdf":
            uit[f"{doc.naam}.pdf"] = pdf_met_tekst(doc.regels)
        elif doc.soort == "factuur_scan":
            beeld = teken_pagina(doc.regels, 1100, 24)
            uit[f"{doc.naam}.pdf"] = pdf_met_beeld(als_jpeg(maak_foto_achtig(beeld, rnd, 0.35), 80))
        else:
            # De storing loopt op per bon (0.7 tot 2.1): de eerste bonnen zijn netjes, de laatste
            # staan schuin, zijn korrelig en onscherp. Zo meet de set ook waar het lezen kantelt.
            sterkte = 0.7 + (volgnummer % 4) * 0.47
            beeld = teken_pagina(doc.regels, 620, 24 if sterkte > 1.5 else 26)
            uit[f"{doc.naam}.jpg"] = als_jpeg(maak_foto_achtig(beeld, rnd, sterkte), 60)
    return uit


def main() -> int:
    parser = argparse.ArgumentParser(description="Maak de bonnen- en factuurtestset")
    parser.add_argument("--controle", action="store_true", help="geen schrijven; vergelijk")
    argumenten = parser.parse_args()

    inhoud = maak_alles()
    if argumenten.controle:
        afwijkend = [
            naam
            for naam, data in inhoud.items()
            if not (DOEL / naam).exists() or (DOEL / naam).read_bytes() != data
        ]
        if afwijkend:
            print("AFWIJKEND of ontbrekend: {}".format(", ".join(sorted(afwijkend))))
            return 1
        print("{} bestanden komen overeen met de generator".format(len(inhoud)))
        return 0

    DOEL.mkdir(parents=True, exist_ok=True)
    for naam, data in inhoud.items():
        (DOEL / naam).write_bytes(data)
    samenvatting = hashlib.sha256(b"".join(inhoud[k] for k in sorted(inhoud))).hexdigest()
    print("{} bestanden naar {} (sha256 {})".format(len(inhoud), DOEL, samenvatting[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
