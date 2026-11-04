"""Veldenlaag: haal uit de TEKST van een bon of factuur de velden (bonlezer dag 1).

De lezer (`lezer.py`) zet een bestand om in tekst. Dit bestand doet de stap daarna, met vaste
regels en zonder netwerk of model: bedragen, datums, btw per tarief, totaal, factuurnummer,
btw-nummer, KvK-nummer en leverancier.

Eerlijk over wat dit is. Het zijn regels, geen begrip. Ze zijn gemaakt en getoetst op de
zelfgemaakte testset (`tests/fixtures/bonnen/`) en op Nederlandse schrijfwijzen die in die set
voorkomen. Een bon met een ongebruikelijke opmaak kan een veld leeg laten of verkeerd lezen;
`docs/evidence/bonlezer-meting-*.md` zegt per veld hoe vaak dat gebeurt. Een veld dat niet te lezen
is, blijft `None` of ontbreekt in `btw`: de veldenlaag raadt niet.

Bedragen zijn `Decimal`, nooit `float`: een btw-bedrag op de cent nauwkeurig is het hele punt.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

#: De btw-tarieven die op een Nederlandse bon voorkomen. 6% is het oude lage tarief tot 2019.
TARIEVEN = (0, 6, 9, 21)

#: Hoeveel een btw-bedrag mag afwijken van netto x tarief voordat we denken dat het een ander
#: getal op dezelfde regel is. Afronding per regel en per groep geeft hooguit enkele centen.
BTW_MARGE = Decimal("0.03")

#: Grenzen tegen vijandige of kapotte invoer (Gate 2, gemeten: een regel van 40.000 spaties kostte
#: 20 s). Wat langer is, wordt afgekapt: de velden die we zoeken staan niet in regel 501.
MAX_TEKST = 200_000
MAX_REGEL = 500
MAX_BEDRAGEN_PER_REGEL = 20

MAANDEN = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}  # fmt: skip
_AFKORTINGEN = {
    "jan": 1, "feb": 2, "mrt": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sept": 9, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_ALLE_MAANDEN = {**MAANDEN, **_AFKORTINGEN}


@dataclass(frozen=True)
class BonVelden:
    """Wat uit een bon of factuur is gelezen. `None` of een ontbrekend tarief = niet gevonden."""

    leverancier: str | None = None
    datum: date | None = None
    totaal: Decimal | None = None
    factuurnummer: str | None = None
    btw: dict[int, Decimal] = field(default_factory=dict)
    btw_nummer: str | None = None
    kvk_nummer: str | None = None
    # Alleen voor een inkoopfactuur (crediteuren dag 2); bij een bon blijven ze `None`.
    iban: str | None = None
    vervaldatum: date | None = None
    valuta: str | None = None


# -- bedragen ---------------------------------------------------------------------------------

_BEDRAGTOKEN = re.compile(r"(?<![\d.,])-?\d[\d.,]*\d|(?<![\d.,])\d")
_DUIZENDTAL_NA_SPATIE = re.compile(r"(?:^|\s)\d{1,3} $")
_DRIE_CIJFERS_EN_BREUK = re.compile(r"-?\d{3}[.,]\d{1,2}")
_VALUTA = re.compile(r"(?i)\beur\b|\u20ac")
_GROEPEN_VAN_DRIE = re.compile(r"\d{1,3}([.,]\d{3})+")


def _normaliseer_met_twee_tekens(token: str) -> str | None:
    """`1.234,56` of `1,234.56`: het laatste teken is het decimaalteken, het andere de duizendtallen."""
    decimaal = "," if token.rfind(",") > token.rfind(".") else "."
    duizend = "." if decimaal == "," else ","
    geheel, _, breuk = token.rpartition(decimaal)
    if duizend in breuk:
        return None
    if not re.fullmatch(rf"\d{{1,3}}(?:{re.escape(duizend)}\d{{3}})+", geheel):
        return None
    return geheel.replace(duizend, "") + "." + breuk


def _normaliseer_met_een_teken(token: str) -> str | None:
    """Alleen komma's of alleen punten. `1.234` is 1234 (duizendtal), `12.50` en `12,50` zijn 12,5."""
    teken = "," if "," in token else "."
    if token.count(teken) > 1:
        return token.replace(teken, "") if _GROEPEN_VAN_DRIE.fullmatch(token) else None
    geheel, _, breuk = token.partition(teken)
    if teken == "." and len(breuk) == 3 and 1 <= len(geheel) <= 3:
        return geheel + breuk
    return geheel + "." + breuk


def _normaliseer(token: str) -> str | None:
    """Zet een getal met scheidingstekens om in `1234.56`; None als de schrijfwijze dubbelzinnig is."""
    if "," in token and "." in token:
        return _normaliseer_met_twee_tekens(token)
    if "," in token or "." in token:
        return _normaliseer_met_een_teken(token)
    return token


def parse_bedrag(tekst: str) -> Decimal | None:
    """Lees een bedrag als `1.234,56`, `EUR 12,50`, `12.50` of `1,234.56`; None als het er geen is."""
    schoon = _VALUTA.sub(" ", tekst).strip()
    if not re.fullmatch(r"-?\d[\d.,]*", schoon):
        return None
    genormaliseerd = _normaliseer(schoon.lstrip("-"))
    if genormaliseerd is None:
        return None
    try:
        waarde = Decimal(genormaliseerd)
    except InvalidOperation:
        return None
    return -waarde if schoon.startswith("-") else waarde


def _bedragen_in(regel: str) -> list[Decimal]:
    """Alle bedragen met een decimaalteken in een regel, zonder percentages en zonder losse gehelen."""
    gevonden: list[Decimal] = []
    for treffer in _BEDRAGTOKEN.finditer(regel):
        token = treffer.group()
        if "," not in token and "." not in token:
            continue
        if re.match(r"\s*%", regel[treffer.end() :]):
            continue
        # `1 234,56`: een spatie als duizendtal is niet te onderscheiden van twee kolommen. Liever
        # niets dan het restant (`234,56`) als bedrag (Gate 2, gemeten).
        if _DRIE_CIJFERS_EN_BREUK.fullmatch(token) and _DUIZENDTAL_NA_SPATIE.search(
            regel[: treffer.start()]
        ):
            continue
        waarde = parse_bedrag(token)
        if waarde is not None:
            gevonden.append(waarde)
            if len(gevonden) >= MAX_BEDRAGEN_PER_REGEL:
                break
    return gevonden


# -- datums -----------------------------------------------------------------------------------

_MAANDNAMEN = "|".join(sorted(_ALLE_MAANDEN, key=len, reverse=True))
_DATUMPATRONEN: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?!\d)"),
    re.compile(rf"(?<!\d)(\d{{1,2}})\s+({_MAANDNAMEN})\.?\s+(\d{{4}})(?!\d)", re.IGNORECASE),
)


def _maak_datum(dag: int, maand: int, jaar: int) -> date | None:
    if jaar < 100:
        jaar += 2000
    try:
        return date(jaar, maand, dag)
    except ValueError:
        return None


def _datum_uit_treffer(index: int, a: str, b: str, c: str) -> date | None:
    if index == 0:
        return _maak_datum(int(c), int(b), int(a))
    if index == 1:
        return _maak_datum(int(a), int(b), int(c))
    return _maak_datum(int(a), _ALLE_MAANDEN[b.casefold()], int(c))


def _datums_in(tekst: str) -> list[tuple[int, date | None]]:
    """(positie, datum of None) voor elke datumachtige reeks, op volgorde van voorkomen."""
    uit: list[tuple[int, date | None]] = []
    for index, patroon in enumerate(_DATUMPATRONEN):
        for treffer in patroon.finditer(tekst):
            a, b, c = treffer.groups()
            uit.append((treffer.start(), _datum_uit_treffer(index, a, b, c)))
    return sorted(uit, key=lambda paar: paar[0])


def parse_datum(tekst: str) -> date | None:
    """De eerste geldige datum in de tekst, in een van de gangbare Nederlandse schrijfwijzen."""
    for _, datum in _datums_in(tekst):
        if datum is not None:
            return datum
    return None


# -- totaal -----------------------------------------------------------------------------------

_GEEN_TOTAAL = re.compile(
    r"(?i)sub\s*totaal|excl|totaal\s+btw|btw\s+totaal|totaal\s+korting"
    r"|nog\s+te|reeds|openstaand|resterend"
)
_TOTAALTIERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)te\s+betalen|totaal\s*incl|totaalbedrag"),
    re.compile(r"(?i)^totaal\b"),
    re.compile(r"(?i)totaal"),
)


def _bedrag_bij_regel(regels: list[str], index: int) -> Decimal | None:
    """Het laatste bedrag op de regel; staat er geen, dan het eerste op de eerstvolgende regels."""
    eigen = _bedragen_in(regels[index])
    if eigen:
        return eigen[-1]
    if re.search(r"\d", regels[index]):
        return None  # een regel met een ander getal (`Totaal artikelen 3`) leent niets van de volgende
    for volgende in regels[index + 1 : index + 3]:
        bedragen = _bedragen_in(volgende)
        if bedragen:
            return bedragen[0]
    return None


def _lees_totaal(regels: list[str]) -> Decimal | None:
    for patroon in _TOTAALTIERS:
        kandidaten = [
            i for i, r in enumerate(regels) if patroon.search(r) and not _GEEN_TOTAAL.search(r)
        ]
        bedragen = [b for b in (_bedrag_bij_regel(regels, i) for i in kandidaten) if b is not None]
        if bedragen:
            return bedragen[-1]
    return None


# -- btw ---------------------------------------------------------------------------------------

_BTW_WOORD = re.compile(r"(?i)\bbtw(?![a-z])|b\.t\.w|omzetbelasting")
_TARIEF = re.compile(r"(?<!\d)(\d{1,2})(?:[.,]\d+)?\s*%")
_REGEL_BEGINT_MET_TARIEF = re.compile(r"^\s*\d{1,2}(?:[.,]\d+)?\s*%")


def _kies_btwbedrag(tarief: int, bedragen: list[Decimal], tabelrij: bool) -> Decimal | None:
    """Welk van de bedragen op de regel is het btw-bedrag? None als dat niet vast te stellen is.

    Een regel kan `netto btw` of `netto btw bruto` hebben. Het btw-bedrag is het getal dat bij een
    eerder getal op de regel past als netto x tarief. Past er geen paar, dan alleen een regel met
    EEN bedrag die niet de rij van een tabel is (`BTW 9%  1,33`). Twee of meer bedragen zonder
    passend paar, of een tabelrij met een bedrag (de rest is door OCR weggevallen), geven None:
    de veldenlaag raadt niet (Gate 2: eerder kwam daar het BRUTO bedrag uit).
    """
    if not bedragen:
        return None
    for i, netto in enumerate(bedragen[:-1]):
        for kandidaat in bedragen[i + 1 :]:
            if abs(netto * tarief / 100 - kandidaat) <= BTW_MARGE:
                return kandidaat
    if len(bedragen) == 1 and not tabelrij:
        return bedragen[0]
    return None


def _lees_btw(regels: Iterable[str]) -> dict[int, Decimal]:
    uit: dict[int, Decimal] = {}
    for regel in regels:
        tabelrij = bool(_REGEL_BEGINT_MET_TARIEF.match(regel)) and not _BTW_WOORD.search(regel)
        if not (_BTW_WOORD.search(regel) or tabelrij) or re.search(r"(?i)totaal", regel):
            continue
        tarief_treffer = _TARIEF.search(regel)
        if tarief_treffer is None or int(tarief_treffer.group(1)) not in TARIEVEN:
            continue
        tarief = int(tarief_treffer.group(1))
        achter_tarief = regel[tarief_treffer.end() :]
        # `BTW 21% over 100,00`: het bedrag erachter is de GRONDSLAG; zonder het btw-bedrag erbij is
        # het geen btw (Gate 2 ronde 2, gemeten: het netto bedrag werd als btw ingeboekt).
        alleen_paar = tabelrij or bool(re.match(r"\s*(?:over|netto|grondslag)\b", achter_tarief, re.I))
        bedrag = _kies_btwbedrag(tarief, _bedragen_in(achter_tarief), alleen_paar)
        if bedrag is not None and not (tarief == 0 and bedrag != 0):
            uit[tarief] = bedrag
    return uit


# -- datum, nummers, leverancier ---------------------------------------------------------------

_DATUMREGEL_NEGEREN = re.compile(r"(?i)verval|betaal|uiterlijk|geldig|expir|due")
# Alle herhalingen zijn begrensd: `\s*` achter elkaar gaf kwadratische rekentijd op een regel spaties.
_FACTUURNUMMER = re.compile(
    r"(?i)(?:factuur\s{0,2}(?:nummer|nr|no)|invoice\s{0,2}(?:number|no|nr))\.?\s{0,3}[:#]?\s{0,3}"
    r"([A-Za-z0-9][A-Za-z0-9\-/]{0,40})"
)
# OCR zet soms een spatie midden in het nummer (`NL811 160913B03`); die laten we toe en halen we weg.
_BTWNUMMER = re.compile(r"\bNL\s?((?:\d\s?){9})B\s?(\d{2})\b")
_KVKNUMMER = re.compile(r"(?i)\bkvk(?:[-\s]{0,3}(?:nummer|nr\.?))?\s{0,3}[:#]?\s{0,3}(\d{8})\b")
_NIET_LEVERANCIER = re.compile(
    r"(?i)^(?:factuur|kassabon|bon|datum|tel|telefoon|www|http|kvk|btw|iban|pagina|invoice)\b"
)
_POSTCODE = re.compile(r"\b\d{4}\s?[A-Z]{2}\b")


# `[A-Z0-9]` met spaties erdoor (OCR en facturen groeperen per vier); de controlesom beslist, niet de vorm.
_IBAN = re.compile(r"\b([A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?)\b")
_VERVALREGEL = re.compile(r"(?i)vervaldatum|verval\s*datum|uiterlijk|due\s*date|betaal\w*\s+voor")


def _iban_klopt(compact: str) -> bool:
    """ISO 13616: de controlesom (mod 97) op de verplaatste en omgezette tekens moet 1 zijn."""
    if not 15 <= len(compact) <= 34:
        return False
    omgezet = "".join(str(int(teken, 36)) for teken in compact[4:] + compact[:4])
    return int(omgezet) % 97 == 1


def _lees_iban(tekst: str) -> str | None:
    for treffer in _IBAN.finditer(tekst):
        compact = re.sub(r"\s", "", treffer.group(1))
        if _iban_klopt(compact):
            return compact
    return None


def _lees_vervaldatum(regels: list[str]) -> date | None:
    for regel in regels:
        treffer = _VERVALREGEL.search(regel)
        if treffer is not None:
            # De datum NA het label: op `Factuurdatum 01-10-2026 Vervaldatum 31-10-2026` is de eerste datum op de regel de
            # factuurdatum (Gate 2: dan is de vervaldatum gelijk aan de factuurdatum en lijkt de factuur schoon).
            datum = parse_datum(regel[treffer.end() :])
            if datum is not None:
                return datum
    return None


_VALUTATEKENS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EUR", _VALUTA),
    ("USD", re.compile(r"(?i)\busd\b|\$")),
    ("GBP", re.compile(r"(?i)\bgbp\b|\u00a3")),
)


def _lees_valuta(tekst: str) -> str | None:
    """De valuta als er precies EEN soort valutateken in de tekst staat; anders `None` (onzeker, de veldenlaag raadt niet).

    Een USD-factuur met `EUR` in een voetnoot (een wisselkoers) is geen euro-factuur: twee soorten tekens betekent onzeker.
    """
    gevonden = [code for code, patroon in _VALUTATEKENS if patroon.search(tekst)]
    return gevonden[0] if len(gevonden) == 1 else None


def _lees_datum(regels: list[str]) -> date | None:
    for regel in regels:
        if re.search(r"(?i)datum|date", regel) and not _DATUMREGEL_NEGEREN.search(regel):
            datum = parse_datum(regel)
            if datum is not None:
                return datum
    return parse_datum("\n".join(regels))


def _lees_factuurnummer(tekst: str) -> str | None:
    for treffer in _FACTUURNUMMER.finditer(tekst):
        kandidaat = treffer.group(1).rstrip("-/")
        if any(teken.isdigit() for teken in kandidaat):
            return kandidaat
    return None


def _lees_leverancier(regels: list[str]) -> str | None:
    for regel in [r for r in regels if r][:6]:
        letters = sum(teken.isalpha() for teken in regel)
        if letters < 3 or letters < len(regel) / 2:
            continue
        if _NIET_LEVERANCIER.match(regel) or _POSTCODE.search(regel):
            continue
        return regel
    return None


def _btwnummer_van(treffer: re.Match[str] | None) -> str | None:
    if treffer is None:
        return None
    return "NL" + re.sub(r"\s", "", treffer.group(1)) + "B" + treffer.group(2)


def lees_velden(tekst: str) -> BonVelden:
    """Haal de velden uit de tekst van een bon of factuur."""
    regels = [regel.strip()[:MAX_REGEL] for regel in tekst[:MAX_TEKST].splitlines()]
    tekst = "\n".join(regels)
    btw_treffer = _BTWNUMMER.search(tekst)
    kvk_treffer = _KVKNUMMER.search(tekst)
    return BonVelden(
        leverancier=_lees_leverancier(regels),
        datum=_lees_datum(regels),
        totaal=_lees_totaal(regels),
        factuurnummer=_lees_factuurnummer(tekst),
        btw=_lees_btw(regels),
        btw_nummer=_btwnummer_van(btw_treffer),
        kvk_nummer=kvk_treffer.group(1) if kvk_treffer else None,
        iban=_lees_iban(tekst),
        vervaldatum=_lees_vervaldatum(regels),
        valuta=_lees_valuta(tekst),
    )
