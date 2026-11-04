"""Printbare PDF van een docentenhandleiding of werkblad (BE-EP-055).

Gebouwd met fpdf2 (requirements-base.txt) en de ingebouwde Helvetica, dus zonder lettertype-
bestanden. Die letters dekken Latin-1: e-trema, c-cedille en dergelijke gaan goed; typografische
aanhalingstekens en streepjes worden gewone tekens.

Dezelfde eenvoudige opmaak als de portal (portal/src/components/FormattedText.tsx):
"## " is een kop, "- " een opsomming, "1. " een genummerde regel, een lege regel scheidt
alinea's. Op een werkblad krijgt elke vraag schrijfregels eronder.
"""

from __future__ import annotations

import re
from typing import Any

from fpdf import FPDF

#: Kopjes waaronder op een werkblad vragen staan (gelijk aan scripts/seed/bouw_lesmateriaal.py).
VRAAG_SECTIES = frozenset(
    {
        "Vragen bij het verhaal",
        "Onderzoeksvragen",
        "Denk mee",
        "Opdracht",
        "Perspectief",
        "Doorwerking",
    }
)

_VERVANG = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
    "\u00a0": " ",
}

_AMBER = (146, 64, 14)
_GRIJS = (120, 113, 108)
_TEKST = (41, 37, 36)
#: Links uitgelijnd: uitgevuld geeft grote gaten bij lange webadressen.
_LINKS: dict[str, str] = {"align": "L"}


def _latin1(tekst: str) -> str:
    for oud, nieuw in _VERVANG.items():
        tekst = tekst.replace(oud, nieuw)
    return tekst.encode("latin-1", errors="replace").decode("latin-1")


class _Pdf(FPDF):
    def __init__(self, voettekst: str) -> None:
        super().__init__(format="A4")
        self._voettekst = voettekst
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(auto=True, margin=18)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*_GRIJS)
        self.cell(0, 6, _latin1(f"{self._voettekst} - pagina {self.page_no()}"), align="C")


def _schrijfregels(pdf: FPDF, aantal: int = 3) -> None:
    pdf.set_draw_color(214, 211, 209)
    for _ in range(aantal):
        pdf.ln(7)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)


def maak_les_pdf(
    titel: str,
    body: str,
    *,
    werkblad: bool,
    bronnen: list[dict[str, str]] | None = None,
    afzender: str = "Het Levend Monument",
) -> bytes:
    """Een A4-PDF met titel, tekst en (bij de handleiding) de bronnenlijst."""
    pdf = _Pdf(voettekst=f"{afzender} - hetlevendmonument.nl")
    pdf.add_page()
    breedte = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_AMBER)
    pdf.cell(0, 5, _latin1(afzender.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*_TEKST)
    pdf.multi_cell(breedte, 8, _latin1(titel), new_x="LMARGIN", new_y="NEXT", **_LINKS)
    if werkblad:
        pdf.ln(3)
        pdf.set_font("Helvetica", size=10)
        pdf.cell(
            0,
            6,
            _latin1("Naam: ______________________________     Klas: ____________"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.ln(3)

    sectie: str | None = None
    for regel in body.replace("\r\n", "\n").split("\n"):
        if regel.startswith("## "):
            sectie = regel[3:].strip()
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(*_AMBER)
            pdf.multi_cell(breedte, 6.5, _latin1(sectie), new_x="LMARGIN", new_y="NEXT", **_LINKS)
            pdf.set_text_color(*_TEKST)
            continue
        if not regel.strip():
            pdf.ln(2)
            continue
        pdf.set_font("Helvetica", size=10.5)
        punt = re.match(r"^- (.*)$", regel)
        nummer = re.match(r"^(\d+)\. (.*)$", regel)
        if punt:
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(
                breedte - 4,
                5.5,
                _latin1(f"- {punt.group(1)}"),
                new_x="LMARGIN",
                new_y="NEXT",
                **_LINKS,
            )
        elif nummer:
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(
                breedte - 4,
                5.5,
                _latin1(f"{nummer.group(1)}. {nummer.group(2)}"),
                new_x="LMARGIN",
                new_y="NEXT",
                **_LINKS,
            )
            if werkblad and sectie in VRAAG_SECTIES:
                _schrijfregels(pdf, 2)
        else:
            pdf.multi_cell(breedte, 5.5, _latin1(regel), new_x="LMARGIN", new_y="NEXT", **_LINKS)
            if (
                werkblad
                and sectie in VRAAG_SECTIES
                and sectie not in ("Vragen bij het verhaal", "Onderzoeksvragen")
            ):
                _schrijfregels(pdf, 4)

    if bronnen and "## Bronnen" not in body:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*_AMBER)
        pdf.cell(0, 6.5, "Bronnen", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_TEKST)
        pdf.set_font("Helvetica", size=9)
        for bron in bronnen:
            tekst = f"- {bron.get('titel', '')} ({bron.get('uitgever', '')})"
            if bron.get("url"):
                tekst += f": {bron['url']}"
            pdf.multi_cell(breedte, 4.8, _latin1(tekst), new_x="LMARGIN", new_y="NEXT", **_LINKS)

    return bytes(pdf.output())
