"""Het SEPA-overschrijvingsbestand (ISO 20022 pain.001.001.09) voor een goedgekeurde betaalrun (crediteuren dag 3, Keten F).

Zuivere functies: geen database, geen netwerk. Het bestand gaat nergens heen; de gebruiker haalt het op en laadt het zelf in zijn
bank. Bedragen zijn gehele centen en worden nooit via een float geschreven.

**Welke versie en waarom.** De EPC-richtlijnen voor SEPA Credit Transfer 2025 (EPC132-08) en de Nederlandse richtlijn van de
Betaalvereniging (NL IG SCT v8.0) werken met de berichtversie van 2019, `pain.001.001.09`. Bron:
https://www.betaalvereniging.nl/en/knowledge-base/standards-in-payments/sepa-implementation-guidelines/. NIET gemeten: welke bank
deze versie nu al accepteert; dat staat in de bankspecificatie van de pilotklant.

**Geen adres.** Vanaf 15 november 2026 staat een ongestructureerd adres in EPC-berichten niet meer toe. Het bestand bevat daarom
geen `PstlAdr`; voor een overschrijving binnen de SEPA-zone is een adres niet verplicht.

**Gemeten tegen het schema:** `tests/integration/test_pain001_valideert_tegen_xsd.py` valideert het resultaat tegen
`tests/fixtures/iso20022/pain.001.001.09.xsd` (de elementvolgorde hieronder is daarmee bewezen; omdraaien van `NbOfTxs` en `CtrlSum`
in `PmtInf` maakt die test rood). `DbtrAgt` heeft hier `Othr/Id = NOTPROVIDED` (de EPC-regel voor een bericht zonder BIC).
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.core.exceptions import ValidatieFout
from src.core.repositories.payable_repository import is_sepa_iban, probeer_iban

__all__ = ["NAMESPACE", "BetaalRegel", "Betaalopdracht", "maak_pain001", "maak_tekst"]

NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"

#: De tekens die de EPC in een SEPA-bericht toestaat (Latijnse basistekenset).
_TOEGESTAAN = re.compile(r"[^A-Za-z0-9/\-?:().,'+ ]")

_NAAM_MAX = 70
_TOELICHTING_MAX = 140
_BERICHT_ID_MAX = 35


@dataclass(frozen=True)
class BetaalRegel:
    """Een inkoopfactuur die in het bestand komt. `bedrag_cents` is een geheel aantal centen in euro."""

    payable_id: int
    naam: str
    iban: str
    bedrag_cents: int
    factuurnummer: str


@dataclass(frozen=True)
class Betaalopdracht:
    """Een betaalrun: van wie naar wie, op welke dag. `bericht_id` is het ticketnummer van de goedkeuring."""

    bericht_id: str
    gemaakt_op: datetime
    uitvoerdatum: date
    debiteur_naam: str
    debiteur_iban: str
    regels: list[BetaalRegel]


#: Letters die NFKD niet ontbindt en die dus stilletjes zouden verdwijnen ("Bjorn" werd "Bjrn"). Als \u-tekens, want code is ASCII.
_VERTALING = str.maketrans(
    {
        "\u00f8": "o",
        "\u00d8": "O",
        "\u0142": "l",
        "\u0141": "L",
        "\u00df": "ss",
        "\u00e6": "ae",
        "\u00c6": "AE",
        "\u0153": "oe",
        "\u0152": "OE",
        "\u0111": "d",
        "\u0110": "D",
        "\u00f0": "d",
        "\u00d0": "D",
        "\u00fe": "th",
        "\u00de": "Th",
    }
)


def maak_tekst(tekst: str, maximum: int) -> str:
    """Maak een tekst geschikt voor een SEPA-bericht: accenten weg, vreemde tekens eruit, geen schuine streep aan de rand.

    De EPC staat alleen de Latijnse basistekenset toe en verbiedt een tekst die met `/` begint of eindigt of `//` bevat.
    """
    ontbonden = unicodedata.normalize("NFKD", tekst.translate(_VERTALING)).encode("ascii", "ignore").decode("ascii")
    schoon = _TOEGESTAAN.sub(" ", ontbonden).replace("//", " ")
    schoon = re.sub(r" +", " ", schoon).strip(" /")
    return schoon[:maximum].rstrip(" /")


def maak_pain001(opdracht: Betaalopdracht, *, vandaag: date | None = None) -> bytes:
    """Bouw het pain.001.001.09-bestand (UTF-8). Een ongeldige opdracht geeft een `ValidatieFout` met een Nederlandse tekst."""
    vandaag = vandaag or datetime.now(timezone.utc).date()
    _controleer(opdracht, vandaag)

    totaal = sum(regel.bedrag_cents for regel in opdracht.regels)
    debiteur_naam = _naam(opdracht.debiteur_naam, "uw bedrijfsnaam")
    debiteur_iban = probeer_iban(opdracht.debiteur_iban) or ""

    wortel = ET.Element("Document", {"xmlns": NAMESPACE})
    initiatie = _kind(wortel, "CstmrCdtTrfInitn")

    kop = _kind(initiatie, "GrpHdr")
    _tekst(kop, "MsgId", opdracht.bericht_id)
    _tekst(
        kop, "CreDtTm", opdracht.gemaakt_op.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    )
    _tekst(kop, "NbOfTxs", str(len(opdracht.regels)))
    _tekst(kop, "CtrlSum", _bedrag(totaal))
    _tekst(_kind(kop, "InitgPty"), "Nm", debiteur_naam)

    groep = _kind(initiatie, "PmtInf")
    _tekst(groep, "PmtInfId", opdracht.bericht_id)
    _tekst(groep, "PmtMtd", "TRF")
    _tekst(groep, "BtchBookg", "true")
    _tekst(groep, "NbOfTxs", str(len(opdracht.regels)))
    _tekst(groep, "CtrlSum", _bedrag(totaal))
    _tekst(_kind(_kind(groep, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
    _tekst(_kind(groep, "ReqdExctnDt"), "Dt", opdracht.uitvoerdatum.isoformat())
    _tekst(_kind(groep, "Dbtr"), "Nm", debiteur_naam)
    _tekst(_kind(_kind(groep, "DbtrAcct"), "Id"), "IBAN", debiteur_iban)
    _tekst(_kind(_kind(_kind(groep, "DbtrAgt"), "FinInstnId"), "Othr"), "Id", "NOTPROVIDED")
    _tekst(groep, "ChrgBr", "SLEV")

    for regel in opdracht.regels:
        transactie = _kind(groep, "CdtTrfTxInf")
        betaal_id = _kind(transactie, "PmtId")
        eind_id = f"CRD-{regel.payable_id}"
        _tekst(betaal_id, "InstrId", eind_id)
        _tekst(betaal_id, "EndToEndId", eind_id)
        bedrag = _kind(_kind(transactie, "Amt"), "InstdAmt")
        bedrag.set("Ccy", "EUR")
        bedrag.text = _bedrag(regel.bedrag_cents)
        _tekst(_kind(transactie, "Cdtr"), "Nm", _naam(regel.naam, "de leverancier"))
        _tekst(_kind(_kind(transactie, "CdtrAcct"), "Id"), "IBAN", probeer_iban(regel.iban) or "")
        toelichting = maak_tekst(f"Factuur {regel.factuurnummer}", _TOELICHTING_MAX)
        _tekst(_kind(transactie, "RmtInf"), "Ustrd", toelichting)

    ET.register_namespace("", NAMESPACE)
    # `tostring` met een encodingnaam levert bytes; typeshed typeert dat overload als `Any`.
    return bytes(ET.tostring(wortel, encoding="UTF-8", xml_declaration=True))


def _controleer(opdracht: Betaalopdracht, vandaag: date) -> None:
    if not opdracht.regels:
        raise ValidatieFout("Er is niets om te betalen: het betaalbestand heeft geen facturen.")
    if not opdracht.bericht_id or len(opdracht.bericht_id) > _BERICHT_ID_MAX:
        raise ValidatieFout(
            "Het berichtnummer van het betaalbestand is leeg of langer dan 35 tekens."
        )
    if opdracht.gemaakt_op.tzinfo is None:
        raise ValidatieFout("Het tijdstip van het betaalbestand heeft geen tijdzone.")
    if opdracht.uitvoerdatum < vandaag:
        raise ValidatieFout("De uitvoerdatum ligt in het verleden. Kies vandaag of een latere dag.")
    if not is_sepa_iban(opdracht.debiteur_iban):
        raise ValidatieFout("Uw eigen IBAN is niet geldig of ligt niet in de SEPA-zone.")
    gezien: set[int] = set()
    for regel in opdracht.regels:
        if not isinstance(regel.bedrag_cents, int) or isinstance(regel.bedrag_cents, bool):
            raise TypeError(
                "bedrag_cents moet een geheel aantal centen zijn (int), geen float, bool of tekst"
            )
        if regel.bedrag_cents <= 0:
            raise ValidatieFout(
                f"Factuur {regel.factuurnummer}: het bedrag moet groter zijn dan nul."
            )
        if not is_sepa_iban(regel.iban):
            raise ValidatieFout(
                f"Factuur {regel.factuurnummer}: het IBAN van de leverancier is niet geldig of ligt niet in de SEPA-zone."
            )
        if regel.payable_id in gezien:
            raise ValidatieFout(
                f"Factuur {regel.factuurnummer} staat twee keer in het betaalbestand."
            )
        gezien.add(regel.payable_id)


def _naam(naam: str, omschrijving: str) -> str:
    schoon = maak_tekst(naam, _NAAM_MAX)
    if not schoon:
        raise ValidatieFout(
            f"De naam van {omschrijving} bevat geen tekens die in een SEPA-bericht mogen."
        )
    return schoon


def _bedrag(cents: int) -> str:
    euro, rest = divmod(cents, 100)
    return f"{euro}.{rest:02d}"


def _kind(ouder: ET.Element, naam: str) -> ET.Element:
    return ET.SubElement(ouder, naam)


def _tekst(ouder: ET.Element, naam: str, waarde: str) -> ET.Element:
    element = ET.SubElement(ouder, naam)
    element.text = waarde
    return element
