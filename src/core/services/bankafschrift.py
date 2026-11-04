"""Een bankafschrift (CAMT.053) inlezen en koppelen aan debiteuren (debiteuren vanzelf afronden, 2026-10-20).

Besluit Rakesh 2026-10-20: "als het mogelijk is en niet al te veel werk Ja nu". CAMT.053 is het XML-formaat (ISO 20022)
dat alle Nederlandse banken leveren. Dit bestand doet twee dingen en BEWAART NIETS: een afschrift bevat persoonsgegevens
(namen, rekeningnummers), dus er is geen tabel, geen kopie op schijf en geen log van de inhoud; alleen tellingen.

**Veilig inlezen.** Het bestand komt van de gebruiker. Er komt geen nieuwe dependency bij (de brief liet "defusedxml of
gelijkwaardig" toe): voor het parsen weigert `lees_camt053` elk document met een `<!DOCTYPE` of `<!ENTITY` (een echt
CAMT.053-bestand heeft er nooit een, en zonder die twee zijn miljard-lachen en externe entiteiten onmogelijk), leest
alleen UTF-8 (zo kan een DOCTYPE zich niet in UTF-16 verstoppen), en kent grenzen: 5 MB, 5000 regels en 20 niveaus diep.
Elke weigering is een `BankafschriftFout` met een Nederlandse tekst die NOOIT iets uit het bestand herhaalt.

**Alleen bijschrijvingen.** Afschrijvingen (`DBIT`), terugboekingen (`RvslInd`) en niet-geboekte regels tellen niet. Een
bedrag dat niet te lezen is weigert het HELE bestand: stil overslaan zou een betaling laten verdwijnen.

**Streng koppelen.** `koppel` kiest alleen AFVINKEN bij precies een open, herinnerde of geescaleerde vordering waarvan het
factuurnummer als losse term in de omschrijving of het betalingskenmerk staat EN waarvan bedrag en valuta gelijk zijn. Een
verkeerde afvinking zet een onbetaalde factuur op betaald en stopt de opvolging; dus bij twijfel niet. Een bijschrijving
waarvan precies een BETAALDE vordering matcht is `al_afgevinkt`: zo vinkt hetzelfde afschrift twee keer inlezen niets
dubbel af.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
import xml.etree.ElementTree as ET  # noqa: S405 -- het document is vooraf gecontroleerd op DOCTYPE en ENTITY
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Literal

#: Grenzen tegen misbruik van een upload.
MAX_BYTES = 5 * 1024 * 1024
MAX_TRANSACTIES = 5000
#: Het aantal BIJSCHRIJVINGEN, apart van het aantal regels: een regel (`Ntry`) kan duizenden transacties bevatten (Gate 2).
MAX_BIJSCHRIJVINGEN = 5000
#: Het aantal tags, geteld VOOR het parsen: de boom van een bestand van 5 MB aan lege elementen kost honderden MB (Gate 2).
MAX_TAGS = 200_000
#: Het totale koppelwerk: de som over alle bijschrijvingen van het aantal vorderingen met hetzelfde bedrag en dezelfde
#: valuta. Geweigerd VOORDAT er iets is afgevinkt; zonder dit blokkeert een tenant met duizenden even dure facturen de
#: event loop voor iedereen (Gate 2 ronde 2).
MAX_VERGELIJKINGEN = 500_000
MAX_DIEPTE = 20
#: Zo veel tekens van een omschrijving worden bewaard voor het koppelen en tonen.
MAX_OMSCHRIJVING = 500

_BEDRAG = re.compile(r"[0-9]{1,12}(?:\.[0-9]{1,5})?")
_VALUTA = re.compile(r"[A-Z]{3}")
_DOCTYPE_OF_ENTITY = re.compile(r"<!\s*(?:doctype|entity)", re.IGNORECASE)
_DECLARATIE = re.compile(r"\s*<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_UTF8_NAMEN = frozenset({"utf-8", "utf8"})
_OPEN_STATUSSEN = frozenset({"open", "herinnerd", "geescaleerd"})


class BankafschriftFout(Exception):
    """Een afschrift dat niet kan worden ingelezen; `boodschap` is voor de gebruiker en herhaalt niets uit het bestand."""

    def __init__(self, code: str, boodschap: str, status_code: int = 422) -> None:
        super().__init__(boodschap)
        self.code = code
        self.boodschap = boodschap
        self.status_code = status_code


def _geen_afschrift() -> BankafschriftFout:
    return BankafschriftFout(
        "GEEN_GELDIG_AFSCHRIFT",
        "Dit is geen geldig CAMT.053-bankafschrift. Download het afschrift bij uw bank opnieuw "
        "als CAMT.053 (XML).",
    )


@dataclass(frozen=True)
class Bijschrijving:
    """Een geboekte bijschrijving uit een afschrift. Geen namen en geen rekeningnummers."""

    datum: date | None
    bedrag: Decimal
    valuta: str
    omschrijving: str


@dataclass(frozen=True)
class Lezing:
    bijschrijvingen: list[Bijschrijving]
    #: Aantal regels dat geen geboekte bijschrijving is (afschrijving, terugboeking, niet geboekt).
    overgeslagen: int


@dataclass(frozen=True)
class Vordering:
    """Wat het koppelen van een vordering nodig heeft."""

    id: int
    factuurnummer: str
    bedrag: Decimal
    valuta: str
    status: str


Uitkomst = Literal["afvinken", "al_afgevinkt", "niet_gekoppeld"]


@dataclass(frozen=True)
class Koppeling:
    uitkomst: Uitkomst
    vordering_id: int | None


def _naam(element: ET.Element) -> str:
    """De tagnaam zonder namespace: camt.053.001.02 en .08 verschillen daarin."""
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _kind(element: ET.Element, naam: str) -> ET.Element | None:
    for kind in element:
        if _naam(kind) == naam:
            return kind
    return None


def _nakomelingen(element: ET.Element, naam: str) -> list[ET.Element]:
    return [e for e in element.iter() if e is not element and _naam(e) == naam]


def _diepte_is_ok(wortel: ET.Element) -> bool:
    """Zonder recursie: een diep document mag de interpreter niet laten vastlopen."""
    stapel = [(wortel, 1)]
    while stapel:
        element, diepte = stapel.pop()
        if diepte > MAX_DIEPTE:
            return False
        stapel.extend((kind, diepte + 1) for kind in element)
    return True


def _bedrag(tekst: str | None) -> Decimal:
    schoon = (tekst or "").strip()
    if not _BEDRAG.fullmatch(schoon):
        raise _geen_afschrift()
    bedrag = Decimal(schoon)
    if bedrag <= 0:
        raise _geen_afschrift()
    return bedrag


def _valuta(element: ET.Element) -> str:
    valuta = (element.get("Ccy") or "").strip().upper()
    if not _VALUTA.fullmatch(valuta):
        raise _geen_afschrift()
    return valuta


def _schoon_tekst(tekst: str) -> str:
    return "".join(t for t in tekst if unicodedata.category(t) not in ("Cc", "Cf"))


def _datum(regel: ET.Element) -> date | None:
    """De boekdatum, anders de valutadatum; een datumtijd wordt tot de datum afgekapt; onleesbaar is `None`."""
    for soort in ("BookgDt", "ValDt"):
        kind = _kind(regel, soort)
        if kind is None:
            continue
        for veld in ("Dt", "DtTm"):
            waarde = _kind(kind, veld)
            if waarde is None or not waarde.text:
                continue
            try:
                return date.fromisoformat(waarde.text.strip()[:10])
            except ValueError:
                continue
    return None


def _tekst_van(tx: ET.Element) -> str:
    """De vrije omschrijving en het gestructureerde betalingskenmerk van een transactie."""
    delen: list[str] = []
    for element in tx.iter():
        if _naam(element) == "Ustrd" and element.text:
            delen.append(element.text)
    for kenmerk in _nakomelingen(tx, "CdtrRefInf"):
        verwijzing = _kind(kenmerk, "Ref")
        if verwijzing is not None and verwijzing.text:
            delen.append(verwijzing.text)
    return " ".join(delen)


def _eigen_bedrag(tx: ET.Element) -> ET.Element | None:
    """Het bedrag van een enkele transactie binnen een verzamelboeking (`AmtDtls/TxAmt/Amt`), als dat er is."""
    for details in _nakomelingen(tx, "AmtDtls"):
        for txamt in _nakomelingen(details, "TxAmt"):
            amt = _kind(txamt, "Amt")
            if amt is not None:
                return amt
    return None


def _is_terugboeking(tx: ET.Element) -> bool:
    """Een transactie binnen een verzamelboeking die een retour is (`RtrInf`) of een eigen debetrichting heeft.

    Zo'n transactie is geen betaling van een klant, ook niet als de boeking eromheen een credit is (Gate 2).
    """
    if _nakomelingen(tx, "RtrInf"):
        return True
    richting = _kind(tx, "CdtDbtInd")
    return richting is not None and (richting.text or "").strip().upper() == "DBIT"


def _is_geboekte_bijschrijving(regel: ET.Element) -> bool:
    terug = _kind(regel, "RvslInd")
    if terug is not None and (terug.text or "").strip().lower() in ("true", "1"):
        return False
    status = _kind(regel, "Sts")
    if status is not None:
        waarde = (status.text or "").strip()
        if not waarde:
            code = _kind(status, "Cd")
            waarde = (code.text or "").strip() if code is not None else ""
        if waarde and waarde.upper() != "BOOK":
            return False
    richting = _kind(regel, "CdtDbtInd")
    return richting is not None and (richting.text or "").strip().upper() == "CRDT"


def _bijschrijvingen_van(regel: ET.Element) -> tuple[list[Bijschrijving], int]:
    """De bijschrijvingen van een geboekte creditregel, en hoeveel transacties daarbinnen zijn overgeslagen."""
    amt = _kind(regel, "Amt")
    if amt is None:
        raise _geen_afschrift()
    datum = _datum(regel)
    transacties: list[ET.Element] = []
    for details in _nakomelingen(regel, "NtryDtls"):
        transacties.extend(k for k in details if _naam(k) == "TxDtls")
    eigen = [_eigen_bedrag(tx) for tx in transacties]
    if len(transacties) >= 2 and all(b is not None for b in eigen):
        uit: list[Bijschrijving] = []
        overgeslagen = 0
        for tx, bedrag_element in zip(transacties, eigen, strict=True):
            if bedrag_element is None:
                raise _geen_afschrift()
            if _is_terugboeking(tx):
                overgeslagen += 1
                continue
            tekst = _schoon_tekst(_tekst_van(tx))[:MAX_OMSCHRIJVING].strip()
            uit.append(
                Bijschrijving(datum, _bedrag(bedrag_element.text), _valuta(bedrag_element), tekst)
            )
        return uit, overgeslagen
    if any(_is_terugboeking(tx) for tx in transacties):
        return [], 1
    tekst = _schoon_tekst(" ".join(_tekst_van(tx) for tx in transacties))[:MAX_OMSCHRIJVING].strip()
    return [Bijschrijving(datum, _bedrag(amt.text), _valuta(amt), tekst)], 0


def lees_camt053(data: bytes) -> Lezing:
    """Lees een CAMT.053-bestand; alleen geboekte bijschrijvingen. Weigert met `BankafschriftFout`."""
    if len(data) > MAX_BYTES:
        raise BankafschriftFout(
            "BESTAND_TE_GROOT",
            "Het bestand is te groot. Een bankafschrift mag hoogstens 5 MB zijn.",
            413,
        )
    if not data.strip():
        raise _geen_afschrift()
    try:
        tekst = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _geen_afschrift() from None
    declaratie = _DECLARATIE.match(tekst)
    if declaratie and declaratie.group(1).strip().lower() not in _UTF8_NAMEN:
        raise _geen_afschrift()
    if _DOCTYPE_OF_ENTITY.search(tekst):
        raise _geen_afschrift()
    if tekst.count("<") > MAX_TAGS:
        raise _geen_afschrift()
    try:
        wortel = ET.fromstring(tekst.encode("utf-8"))  # noqa: S314 -- DOCTYPE en ENTITY zijn hierboven geweigerd
    except (ET.ParseError, ValueError):
        raise _geen_afschrift() from None
    if not _diepte_is_ok(wortel):
        raise _geen_afschrift()
    afschriften = [e for e in wortel.iter() if _naam(e) == "Stmt"]
    if not afschriften:
        raise _geen_afschrift()
    regels = [kind for stmt in afschriften for kind in stmt if _naam(kind) == "Ntry"]
    if len(regels) > MAX_TRANSACTIES:
        raise BankafschriftFout(
            "TE_VEEL_TRANSACTIES",
            f"Het afschrift heeft meer dan {MAX_TRANSACTIES} regels. Lees het in delen in.",
        )
    bijschrijvingen: list[Bijschrijving] = []
    overgeslagen = 0
    for regel in regels:
        if not _is_geboekte_bijschrijving(regel):
            overgeslagen += 1
            continue
        nieuw, terug = _bijschrijvingen_van(regel)
        overgeslagen += terug
        bijschrijvingen.extend(nieuw)
        if len(bijschrijvingen) > MAX_BIJSCHRIJVINGEN:
            raise BankafschriftFout(
                "TE_VEEL_TRANSACTIES",
                f"Het afschrift heeft meer dan {MAX_BIJSCHRIJVINGEN} bijschrijvingen. Lees het in delen in.",
            )
    return Lezing(bijschrijvingen=bijschrijvingen, overgeslagen=overgeslagen)


def _komt_voor(factuurnummer: str, omschrijving: str, omschrijving_laag: str | None = None) -> bool:
    """Het factuurnummer als LOSSE term (niet binnen een ander woord of een langer nummer), hoofdletterongevoelig."""
    nummer = factuurnummer.strip()
    if not nummer:
        return False
    # Goedkoop voorfilter: staat het nummer er niet eens als tekst in, dan hoeft er geen patroon te worden gebouwd.
    laag = omschrijving.lower() if omschrijving_laag is None else omschrijving_laag
    if nummer.lower() not in laag:
        return False
    patroon = (
        r"(?<![0-9A-Za-z])(?<![0-9A-Za-z]-)"
        + re.escape(factuurnummer.strip())
        + r"(?![0-9A-Za-z])(?!-[0-9A-Za-z])"
    )
    return re.search(patroon, omschrijving, re.IGNORECASE) is not None


def koppel(bijschrijving: Bijschrijving, vorderingen: Sequence[Vordering]) -> Koppeling:
    """Kies wat er met een bijschrijving gebeurt: afvinken, al afgevinkt, of niet gekoppeld (zie de moduledocstring)."""
    open_: list[Vordering] = []
    betaald: list[Vordering] = []
    # Een keer per bijschrijving, niet per kandidaat: bij duizenden facturen met hetzelfde bedrag scheelt dat de helft van
    # het werk (gerichte review F2).
    laag = bijschrijving.omschrijving.lower()
    for vordering in vorderingen:
        if vordering.valuta != bijschrijving.valuta or vordering.bedrag != bijschrijving.bedrag:
            continue
        if not _komt_voor(vordering.factuurnummer, bijschrijving.omschrijving, laag):
            continue
        if vordering.status in _OPEN_STATUSSEN:
            open_.append(vordering)
        elif vordering.status == "betaald":
            betaald.append(vordering)
    # Past de bijschrijving OOK bij een al betaalde factuur, dan kan het geld voor die factuur zijn: een verkeerde afvinking
    # stopt de opvolging van een onbetaalde factuur, dus bij twijfel niet (acceptatie 2026-10-21, "Facturen F-4 en F-5").
    if len(open_) == 1 and not betaald:
        return Koppeling("afvinken", open_[0].id)
    if not open_ and len(betaald) == 1:
        return Koppeling("al_afgevinkt", betaald[0].id)
    return Koppeling("niet_gekoppeld", None)


@dataclass(frozen=True)
class NietGekoppeld:
    """Een bijschrijving die niet is afgevinkt: de medewerker kiest zelf bij welke factuur hij hoort."""

    datum: date | None
    bedrag: Decimal
    valuta: str
    omschrijving: str


@dataclass
class Verwerking:
    aantal_bijschrijvingen: int
    #: (vordering-id, datum uit het afschrift) van elke vordering die in deze run is afgevinkt.
    afgevinkt: list[tuple[int, date | None]]
    al_afgevinkt: int
    niet_gekoppeld: list[NietGekoppeld]
    overgeslagen: int


VinkAf = Callable[[int, date | None], Awaitable[None]]


def _koppel_alles(
    lezing: Lezing,
    huidig: dict[int, Vordering],
    per_sleutel: dict[tuple[str, Decimal], list[int]],
    verwerking: Verwerking,
) -> dict[int, date | None]:
    """Koppel elke bijschrijving en vul `verwerking`; geeft per af te vinken vordering de datum. Zuiver, geen database."""
    te_vinken: dict[int, date | None] = {}
    for bijschrijving in lezing.bijschrijvingen:
        kandidaten = [
            huidig[rij_id]
            for rij_id in per_sleutel.get((bijschrijving.valuta, bijschrijving.bedrag), [])
        ]
        koppeling = koppel(bijschrijving, kandidaten)
        if koppeling.uitkomst == "afvinken" and koppeling.vordering_id is not None:
            te_vinken[koppeling.vordering_id] = bijschrijving.datum
            huidig[koppeling.vordering_id] = replace(huidig[koppeling.vordering_id], status="betaald")
            verwerking.afgevinkt.append((koppeling.vordering_id, bijschrijving.datum))
        elif koppeling.uitkomst == "al_afgevinkt":
            verwerking.al_afgevinkt += 1
        else:
            verwerking.niet_gekoppeld.append(
                NietGekoppeld(
                    bijschrijving.datum,
                    bijschrijving.bedrag,
                    bijschrijving.valuta,
                    bijschrijving.omschrijving,
                )
            )
    return te_vinken


async def verwerk_afschrift(
    data: bytes, vorderingen: Sequence[Vordering], vink_af: VinkAf
) -> Verwerking:
    """Lees een afschrift, koppel elke bijschrijving en roep per af te vinken vordering `vink_af` aan.

    Weet niets van de database: de aanroeper levert de vorderingen van DE EIGEN tenant en de terugroep die afvinkt. Een
    vordering die in deze run al is afgevinkt telt voor een volgende bijschrijving als betaald (`al_afgevinkt`), zodat
    twee bijschrijvingen voor dezelfde factuur niet twee keer afvinken. Een fout in het bestand komt als
    `BankafschriftFout` naar buiten voordat er iets is afgevinkt.
    """
    # Buiten de event loop: parsen van een groot bestand is zuiver rekenwerk en blokkeert anders alle verzoeken.
    lezing = await asyncio.to_thread(lees_camt053, data)
    huidig = {v.id: v for v in vorderingen}
    verwerking = Verwerking(
        aantal_bijschrijvingen=len(lezing.bijschrijvingen),
        afgevinkt=[],
        al_afgevinkt=0,
        niet_gekoppeld=[],
        overgeslagen=lezing.overgeslagen,
    )
    # Alleen vorderingen met hetzelfde bedrag en dezelfde valuta kunnen matchen: zonder deze index is het werk
    # bijschrijvingen x vorderingen (Gate 2); `koppel` toetst bedrag en valuta zelf ook nog.
    per_sleutel: dict[tuple[str, Decimal], list[int]] = {}
    for vordering in vorderingen:
        per_sleutel.setdefault((vordering.valuta, vordering.bedrag), []).append(vordering.id)
    werk = sum(
        len(per_sleutel.get((b.valuta, b.bedrag), [])) for b in lezing.bijschrijvingen
    )
    if werk > MAX_VERGELIJKINGEN:
        raise BankafschriftFout(
            "TE_VEEL_WERK",
            "Dit afschrift is te groot om in een keer met uw facturen te vergelijken. Lees het in delen in.",
        )
    # Het koppelen zelf is zuiver rekenwerk (tot `MAX_VERGELIJKINGEN` vergelijkingen) en draait buiten de event loop.
    te_vinken = await asyncio.to_thread(_koppel_alles, lezing, huidig, per_sleutel, verwerking)
    # Pas NU afvinken, en in oplopende id-volgorde: twee uploads met dezelfde facturen in een andere bestandsvolgorde
    # zetten elkaar anders met rijsloten in een deadlock (Gate 2 ronde 2).
    for rij_id in sorted(te_vinken):
        await vink_af(rij_id, te_vinken[rij_id])
    return verwerking
