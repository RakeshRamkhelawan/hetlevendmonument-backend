"""Het btw-overzicht per kwartaal uit BEVESTIGDE bonnen (btw-overzicht, 2026-10-19).

Per kwartaal de VOORBELASTING (rubriek 5b van de aangifte) per tarief, uit alleen de bonnen die een medewerker
heeft bevestigd (`<bon>.bevestigd.json` naast de bon, geen tabel). Wat dit NIET is: geen omzetbelasting (die
komt niet uit bonnen), geen indiening, geen advies; de klant controleert het overzicht en neemt het zelf op.

- **Het kwartaal volgt de bondatum**, niet het moment van bevestigen.
- **Alleen bevestigd telt.** Een bon met alleen een leesresultaat telt nooit mee.
- **Dezelfde bon telt een keer.** Twee bevestigingen met dezelfde `sha256` (dezelfde bon twee keer geupload en
  bevestigd) tellen als een: de LAATSTE bevestiging telt (wie een fout ziet en opnieuw bevestigt, verbetert zich;
  besluit regie 2026-10-19), de rest wordt als `aantal_dubbel` gemeld (Gate 2,
  security: anders valt de voorbelasting te hoog uit). Zonder `sha256` is er niets om op te vergelijken.
- **Bedragen zijn `Decimal`.** Elk tarief wordt als som van de exacte bedragen op de cent afgerond (half omhoog,
  van nul af); het totaal is de som van de afgeronde delen, zodat het scherm optelt (besluit van de bouwer). Een
  uitkomst van min nul komt nooit als `-0.00` naar buiten.
- **Tarieven:** 9 en 21 afzonderlijk (ook als `09` of `021` is geschreven), elk ander tarief (bijvoorbeeld 0 of 6)
  onder `overig`.
- **De tenant komt van de aanroeper** (de JWT), nooit uit een bestandsnaam of invoer; het pad is
  `<uploadmap>/<tenantnummer>/`. Wat niet aan het schema voldoet (kapot, geen getal, onbekend veld) wordt als
  bon overgeslagen en nooit geraden.
- **Het antwoord bevat geen namen en geen bestandsnamen**; de CSV wel de leverancier, veilig gemaakt zoals de
  bevestigde-bonnen-export (stuurtekens eruit, apostrof voor een cel die als formule kan worden gelezen).
"""

from __future__ import annotations

import calendar
import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from src.core.als.bonlezer.bevestiging import (
    BonBevestiging,
    _getal,
    _tekst,
    moet_gecontroleerd,
)
from src.core.als.bonlezer.upload import _DECIMAAL, _toets_velden

_LABEL = re.compile(r"([0-9]{4})-Q([1-4])")
_DATUM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CENT = Decimal("0.01")
_EERSTE_JAAR = 2000
_LAATSTE_JAAR = 2100
_TARIEVEN = ("9", "21")
RUBRIEK = "5b"
RUBRIEK_NAAM = "Voorbelasting"

_KOLOMMEN = (
    "datum",
    "leverancier",
    "factuurnummer",
    "totaal",
    "btw_9",
    "btw_21",
    "btw_overig",
    "controleren",
)


@dataclass(frozen=True)
class Kwartaal:
    jaar: int
    nummer: int

    @classmethod
    def van(cls, dag: date) -> Kwartaal:
        return cls(dag.year, (dag.month - 1) // 3 + 1)

    def label(self) -> str:
        return f"{self.jaar}-Q{self.nummer}"

    def eerste_dag(self) -> date:
        return date(self.jaar, 3 * (self.nummer - 1) + 1, 1)

    def laatste_dag(self) -> date:
        maand = 3 * self.nummer
        return date(self.jaar, maand, calendar.monthrange(self.jaar, maand)[1])


def huidig_kwartaal(nu: datetime) -> Kwartaal:
    """Het kwartaal van `nu` (de dag in UTC)."""
    return Kwartaal.van(nu.date())


def vorig_kwartaal(nu: datetime) -> Kwartaal:
    """Het laatst AFGESLOTEN kwartaal (de dag van `nu` in UTC): aangifte doe je achteraf."""
    huidig = huidig_kwartaal(nu)
    if huidig.nummer == 1:
        return Kwartaal(huidig.jaar - 1, 4)
    return Kwartaal(huidig.jaar, huidig.nummer - 1)


def kwartaal_uit_pakketinvoer(invoer: object, nu: datetime) -> tuple[Kwartaal | None, str | None]:
    """Het kwartaal voor een pakketstap, of een foutmelding; stap 1 en stap 2 delen deze ene regel.

    Alleen de sleutel `kwartaal` (gekozen in het venster Uitvoeren) bepaalt het kwartaal. Zonder die sleutel is het
    het vorige afgesloten kwartaal. Vrije tekst in `invoer` bepaalt het kwartaal NOOIT: dezelfde invoer gaat naar elke
    stap van het pakket en een tekst als "het derde kwartaal" laat zich niet betrouwbaar lezen.
    """
    if isinstance(invoer, dict) and "kwartaal" in invoer:
        gevonden = parse_kwartaal(invoer["kwartaal"])
        if gevonden is None:
            return None, "Dit kwartaal is niet geldig. Kies een kwartaal zoals 2026-Q3."
        return gevonden, None
    return vorig_kwartaal(nu), None


def parse_kwartaal(tekst: object) -> Kwartaal | None:
    """`2026-Q3` als `Kwartaal`; alles anders (ook een andere schrijfwijze) is `None`."""
    if not isinstance(tekst, str):
        return None
    treffer = _LABEL.fullmatch(tekst)
    if treffer is None:
        return None
    jaar = int(treffer.group(1))
    if not _EERSTE_JAAR <= jaar <= _LAATSTE_JAAR:
        return None
    return Kwartaal(jaar, int(treffer.group(2)))


def _dag(waarde: object) -> date | None:
    if not isinstance(waarde, str) or _DATUM.fullmatch(waarde) is None:
        return None
    try:
        return date.fromisoformat(waarde)
    except ValueError:
        return None


def _bedrag(waarde: object) -> Decimal:
    """Een bevestigd bedrag; alles wat geen geldig getal is telt als 0 (nooit raden)."""
    if isinstance(waarde, str) and _DECIMAAL.fullmatch(waarde) is not None:
        return Decimal(waarde)
    return Decimal("0")


def _sleutel(tarief: object) -> str:
    """`9` en `21` (ook als `09` of `021` is geschreven) houden hun eigen regel; elk ander tarief is `overig`."""
    tekst = str(tarief)
    if tekst.isdigit() and str(int(tekst)) in _TARIEVEN:
        return str(int(tekst))
    return "overig"


def _per_tarief(velden: dict[str, object]) -> dict[str, Decimal]:
    """De exacte btw per tarief van een bon; alleen de tarieven die op de bon staan."""
    uit: dict[str, Decimal] = {}
    btw = velden.get("btw")
    if isinstance(btw, dict):
        for tarief, bedrag in btw.items():
            sleutel = _sleutel(tarief)
            uit[sleutel] = uit.get(sleutel, Decimal("0")) + _bedrag(bedrag)
    return uit


def _afronden(bedrag: Decimal) -> Decimal:
    """Op de cent, half omhoog (van nul af); nooit `-0.00`."""
    afgerond = bedrag.quantize(_CENT, rounding=ROUND_HALF_UP)
    return afgerond if afgerond != 0 else Decimal("0.00")


def _afgerond_per_tarief(velden: list[dict[str, object]]) -> dict[str, Decimal]:
    """De voorbelasting per tarief (9, 21, overig): de exacte som van alle bonnen, daarna op de cent."""
    som = {"9": Decimal("0"), "21": Decimal("0"), "overig": Decimal("0")}
    for bon in velden:
        for sleutel, bedrag in _per_tarief(bon).items():
            som[sleutel] += bedrag
    return {sleutel: _afronden(bedrag) for sleutel, bedrag in som.items()}


class BtwOverzicht:
    def __init__(self, root: Path) -> None:
        self._bonnen = BonBevestiging(root)

    def overzicht(self, tenant_id: int, kwartaal: Kwartaal) -> dict[str, object]:
        """De voorbelasting van het kwartaal uit de bevestigde bonnen van DEZE tenant."""
        velden, dubbel = self._gevonden(tenant_id, kwartaal)
        return self._bereken(kwartaal, velden, dubbel)

    def bonnen_samenvatting(self, tenant_id: int, kwartaal: Kwartaal) -> dict[str, object]:
        """Aantal, totaalbedrag en btw per tarief van de bevestigde bonnen van het kwartaal (stap 1 van het pakket).

        Dezelfde bonnen als `overzicht` (zelfde kwartaal, zelfde ontdubbeling), zodat stap 1 en stap 2 elkaar niet
        tegenspreken. Alleen de tarieven die op de bonnen staan komen erin.
        """
        velden, _ = self._gevonden(tenant_id, kwartaal)
        totaal = sum((_bedrag(bon.get("totaal")) for bon in velden), Decimal("0"))
        som: dict[str, Decimal] = {}
        for bon in velden:
            for sleutel, bedrag in _per_tarief(bon).items():
                som[sleutel] = som.get(sleutel, Decimal("0")) + bedrag
        volgorde = {"9": 0, "21": 1, "overig": 2}
        return {
            "kwartaal": kwartaal.label(),
            "aantal": len(velden),
            "totaal": str(_afronden(totaal)),
            "btw": {
                sleutel: str(_afronden(bedrag))
                for sleutel, bedrag in sorted(som.items(), key=lambda kv: volgorde[kv[0]])
            },
        }

    def csv_export(self, tenant_id: int, kwartaal: Kwartaal) -> str:
        """De bonnen van het kwartaal als CSV, met onderaan de totalen; formules zijn onschadelijk gemaakt."""
        velden, _ = self._gevonden(tenant_id, kwartaal)
        uit = io.StringIO()
        schrijver = csv.writer(uit, lineterminator="\r\n")
        schrijver.writerow(_KOLOMMEN)
        for bon in sorted(velden, key=lambda v: (str(v.get("datum")), str(v.get("leverancier")))):
            per = _per_tarief(bon)
            schrijver.writerow(
                [
                    _tekst(bon.get("datum")),
                    _tekst(bon.get("leverancier")),
                    _tekst(bon.get("factuurnummer")),
                    _getal(bon.get("totaal")),
                    str(per["9"]) if "9" in per else "",
                    str(per["21"]) if "21" in per else "",
                    str(per["overig"]) if "overig" in per else "",
                    "ja" if moet_gecontroleerd(bon) else "nee",
                ]
            )
        afgerond = _afgerond_per_tarief(velden)
        schrijver.writerow(
            [
                f"Totaal voorbelasting rubriek {RUBRIEK} kwartaal {kwartaal.label()}",
                "",
                "",
                "",
                str(afgerond["9"]),
                str(afgerond["21"]),
                str(afgerond["overig"]),
                "",
            ]
        )
        return uit.getvalue()

    @staticmethod
    def _bereken(
        kwartaal: Kwartaal, velden: list[dict[str, object]], dubbel: int
    ) -> dict[str, object]:
        aantal_controleren = sum(1 for bon in velden if moet_gecontroleerd(bon))
        afgerond = _afgerond_per_tarief(velden)
        totaal = _afronden(sum(afgerond.values(), Decimal("0")))
        return {
            "kwartaal": kwartaal.label(),
            "van": kwartaal.eerste_dag().isoformat(),
            "tot": kwartaal.laatste_dag().isoformat(),
            "rubriek": RUBRIEK,
            "rubriek_naam": RUBRIEK_NAAM,
            "aantal": len(velden),
            "aantal_dubbel": dubbel,
            "aantal_controleren": aantal_controleren,
            "voorbelasting": {sleutel: str(bedrag) for sleutel, bedrag in afgerond.items()},
            "totaal": str(totaal),
        }

    def _gevonden(self, tenant_id: int, kwartaal: Kwartaal) -> tuple[list[dict[str, object]], int]:
        """De velden van de bevestigde bonnen van het kwartaal, en hoeveel dubbele bevestigingen zijn overgeslagen.

        Een bon die niet aan het schema voldoet (aangepast bestand: geen getal, onbekend veld) wordt overgeslagen.
        De bevestigingen komen op volgorde van bevestigen; we lopen terug, dus bij dezelfde `sha256` telt de laatste.
        """
        eerste, laatste = kwartaal.eerste_dag(), kwartaal.laatste_dag()
        gezien: set[str] = set()
        gevonden: list[dict[str, object]] = []
        dubbel = 0
        for bon in reversed(self._bonnen.bevestigde_bonnen(tenant_id)):
            velden = _toets_velden(bon.get("velden"))
            if velden is None:
                continue
            dag = _dag(velden.get("datum"))
            if dag is None or not eerste <= dag <= laatste:
                continue
            sha = bon.get("sha256")
            if isinstance(sha, str) and sha:
                if sha in gezien:
                    dubbel += 1
                    continue
                gezien.add(sha)
            gevonden.append(velden)
        return gevonden, dubbel
