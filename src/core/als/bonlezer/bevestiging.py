"""Velden van een bon controleren, bevestigen, tonen en exporteren (bonlezer dag 4).

Alles wat uit een bon komt is ONBETROUWBAAR: de worker leest hem met een parser die vijandige invoer krijgt.
Daarom:

- **Controleren.** Leverancier, datum en totaal zijn verplicht; een btw-nummer (`NL` + 9 cijfers + `B` + 2
  cijfers) en een KvK-nummer (8 cijfers) moeten strak kloppen of leeg zijn. Wat niet klopt is "controleren",
  nooit stil goed. Een bevestiging met zo'n veld wordt geweigerd (422).
- **Schoon.** Stuurtekens en onzichtbare opmaaktekens (categorie `Cc` en `Cf`, ook de richtingstekens die tekst
  omkeren) worden uit alle tekstvelden gehaald. HTML blijft gewone tekst: het scherm toont tekst, nooit HTML.
- **CSV.** Een cel die met `=`, `+`, `-` of `@` begint krijgt een apostrof ervoor (formule-injectie in Excel);
  gevalideerde getallen blijven getallen, ook een negatief totaal.
- **Een mens bevestigt.** De medewerker ziet de velden, corrigeert ze en bevestigt. Alleen bevestigde velden
  gaan verder (de samenvatting voor het pakket en de export).

Opslag zonder tabel: `<uploadmap>/<tenant_id>/<bestand_id>.bevestigd.json` naast de bon, met de velden, wie
bevestigde (`door`), wanneer (`bevestigd_op`) en de `sha256` van de bon. De opruiming na 30 dagen verwijdert de
bon en zijn metabestand (`opruimen.py`) maar NIET dit bestand: de bevestigde velden zijn het enige dat een
latere stap (btw) nodig heeft. Hoe lang die bevestigde gegevens bewaard blijven (fiscaal) is een besluit voor
Rakesh, niet van deze module.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import secrets
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.als.bonlezer.upload import (
    _BESTAND_ID,
    _DECIMAAL,
    VERLOOP_SECONDEN,
    BonNietGevonden,
    UploadFout,
    _lees_json,
    _schrijf_nieuw,
    _toets_velden,
    lees_vastgelegd_resultaat,
)

logger = logging.getLogger(__name__)

_BTW_NUMMER = re.compile(r"NL[0-9]{9}B[0-9]{2}")
_KVK_NUMMER = re.compile(r"[0-9]{8}")
_VERPLICHT = ("leverancier", "datum", "totaal")
_FORMULETEKENS = ("=", "+", "-", "@")
_KOLOMMEN = (
    "bestandsnaam",
    "datum",
    "leverancier",
    "factuurnummer",
    "totaal",
    "btw_9",
    "btw_21",
    "btw_overig",
    "btw_nummer",
    "kvk_nummer",
    "bevestigd_op",
    # De unieke sleutel van de bon: een bestandsnaam is niet uniek, en bevestigingen van voor 2026-10-19 hebben
    # geen naam bewaard (Gate 2).
    "bestand_id",
)
_CENT = Decimal("0.01")

#: Zo veel bonnen per lijstaanroep krijgen alsnog hun resultaat opgehaald (bonnen die niemand heeft geopend).
MAX_VERVERS = 20
#: Zo veel tekens van de leverancier tonen we in de lijst.
_MAX_LEVERANCIER_LIJST = 120


def schoon_tekst(tekst: str) -> str:
    """De tekst zonder stuurtekens en onzichtbare opmaaktekens (`Cc` en `Cf`, ook richtingstekens)."""
    return "".join(teken for teken in tekst if unicodedata.category(teken) not in ("Cc", "Cf"))


def csv_veilig(waarde: str) -> str:
    """De celwaarde voor een CSV: schoon, en met een apostrof ervoor als hij als formule kan worden gelezen."""
    tekst = schoon_tekst(waarde)
    return f"'{tekst}" if tekst.startswith(_FORMULETEKENS) else tekst


def _leeg(waarde: object) -> bool:
    return waarde is None or (isinstance(waarde, str) and not waarde.strip())


def controleer_velden(velden: dict[str, object]) -> dict[str, str]:
    """Per veld dat niet klopt `controleren`; een leeg resultaat betekent dat alles klopt."""
    meldingen: dict[str, str] = {}
    for veld in _VERPLICHT:
        if _leeg(velden.get(veld)):
            meldingen[veld] = "controleren"
    for veld, patroon in (("btw_nummer", _BTW_NUMMER), ("kvk_nummer", _KVK_NUMMER)):
        waarde = velden.get(veld)
        if not _leeg(waarde) and not (isinstance(waarde, str) and patroon.fullmatch(waarde)):
            meldingen[veld] = "controleren"
    return meldingen


def moet_gecontroleerd(velden: dict[str, object]) -> dict[str, str]:
    """Per veld waar de medewerker op moet letten: `controleren` (alleen een AANWIJZING, geen blokkade).

    Alles wat `controleer_velden` afkeurt, plus een leeg btw-nummer of KvK-nummer (acceptatie dag 4: bon_12 gaf
    een foute leverancier en lege nummers zonder waarschuwing) en btw die samen groter is dan het totaal. Een
    kassabon zonder KvK-nummer mag na controle gewoon bevestigd worden: alleen `controleer_velden` blokkeert.
    """
    meldingen = controleer_velden(velden)
    for veld in ("btw_nummer", "kvk_nummer"):
        if _leeg(velden.get(veld)):
            meldingen.setdefault(veld, "controleren")
    btw = velden.get("btw")
    if isinstance(btw, dict) and btw:
        som = sum((_decimaal(bedrag) for bedrag in btw.values()), Decimal("0"))
        # Absolute waarden: bij een creditnota (totaal -121, btw -21) is -21 anders "groter" dan -121.
        if abs(som) > abs(_decimaal(velden.get("totaal"))):
            meldingen.setdefault("totaal", "controleren")
    return meldingen


def _stop_na_eerste_fout(
    ververs: Callable[[str], None] | None, tenant_id: int
) -> Callable[[str], None] | None:
    """Een kapotte Redis mag de lijst niet slopen of traag maken: na de eerste fout slaan we de rest over."""
    if ververs is None:
        return None
    gestopt = False

    def _aanroep(bestand_id: str) -> None:
        nonlocal gestopt
        if gestopt:
            return
        try:
            ververs(bestand_id)
        except Exception as fout:  # noqa: BLE001 -- de lijst blijft heel, het fouttype gaat in het log
            gestopt = True
            logger.warning(
                "bonlezer lijst verversen mislukt: tenant=%s fouttype=%s",
                tenant_id,
                type(fout).__name__,
            )

    return _aanroep


#: Ruis die de bonlezer voor of achter een leverancier leest (`_Jumbo_`, `- Jumbo -`). Een punt ACHTERAAN blijft
#: staan: "B.V." eindigt erop. Haakjes en procenttekens blijven staan: die kunnen bij een naam horen.
_RUIS_VOOR = " \t_-|*~#/\\.,;:"
_RUIS_ACHTER = " \t_-|*~#/\\,;:"


def _knip_leverancier(tekst: str) -> str:
    return tekst.lstrip(_RUIS_VOOR).rstrip(_RUIS_ACHTER)


def _maak_schoon(velden: dict[str, object]) -> dict[str, object]:
    schoon = {
        sleutel: schoon_tekst(waarde).strip() if isinstance(waarde, str) else waarde
        for sleutel, waarde in velden.items()
    }
    leverancier = schoon.get("leverancier")
    if isinstance(leverancier, str):
        schoon["leverancier"] = _knip_leverancier(leverancier)
    return schoon


def _tekst(waarde: object) -> str:
    return csv_veilig(str(waarde)) if waarde is not None else ""


def _getal(waarde: object) -> str:
    """Een gevalideerd getal blijft een getal (ook negatief); alles anders gaat door de CSV-beveiliging."""
    if waarde is None:
        return ""
    tekst = str(waarde)
    return tekst if _DECIMAAL.fullmatch(tekst) else csv_veilig(tekst)


def _decimaal(waarde: object) -> Decimal:
    try:
        return Decimal(str(waarde)) if waarde is not None else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _op_tarief(onderdeel: tuple[str, Decimal]) -> tuple[int, str]:
    tarief = onderdeel[0]
    return (int(tarief) if tarief.isdigit() else 999, tarief)


def _geldige_tenant(tenant_id: object) -> bool:
    return isinstance(tenant_id, int) and not isinstance(tenant_id, bool) and tenant_id > 0


def _geldig(tenant_id: object, bestand_id: object) -> bool:
    return (
        _geldige_tenant(tenant_id)
        and isinstance(bestand_id, str)
        and _BESTAND_ID.fullmatch(bestand_id) is not None
    )


def _nederlandse_tijd(waarde: object) -> str:
    """Een ISO-tijd als Nederlandse tijd met tijdzone (`2026-10-17 11:00:00+02:00`); onleesbaar is een lege cel.

    Een tijd zonder tijdzone geldt als UTC (zo schrijft `bevestig` hem altijd). Is de tijdzonedatabase niet
    beschikbaar, dan blijft de tijd in UTC staan, met `+00:00` erbij: nooit een tijd zonder zone.
    """
    if not isinstance(waarde, str):
        return ""
    try:
        tijd = datetime.fromisoformat(waarde)
    except ValueError:
        return ""
    if tijd.tzinfo is None:
        tijd = tijd.replace(tzinfo=timezone.utc)
    try:
        tijd = tijd.astimezone(ZoneInfo("Europe/Amsterdam"))
    except ZoneInfoNotFoundError:
        tijd = tijd.astimezone(timezone.utc)
    return tijd.isoformat(sep=" ", timespec="seconds")


def _rij(
    naam: object, velden: dict[str, object], bevestigd_op: object, bestand_id: str
) -> list[str]:
    btw = velden.get("btw")
    tarieven: dict[str, object] = btw if isinstance(btw, dict) else {}
    overig = ";".join(f"{t}:{b}" for t, b in tarieven.items() if str(t) not in ("9", "21"))
    return [
        _tekst(naam),
        _tekst(velden.get("datum")),
        _tekst(velden.get("leverancier")),
        _tekst(velden.get("factuurnummer")),
        _getal(velden.get("totaal")),
        _getal(tarieven.get("9")),
        _getal(tarieven.get("21")),
        csv_veilig(overig),
        _tekst(velden.get("btw_nummer")),
        _tekst(velden.get("kvk_nummer")),
        _nederlandse_tijd(bevestigd_op),
        bestand_id,
    ]


class BonBevestiging:
    def __init__(self, root: Path, *, nu: Callable[[], datetime] | None = None) -> None:
        self._root = root
        self._nu = nu or (lambda: datetime.now(timezone.utc))

    # -- bevestigen ---------------------------------------------------------------------------------

    def bevestig(
        self, tenant_id: int, bestand_id: str, velden: object, *, gebruiker_id: int
    ) -> dict[str, object]:
        """Leg de (gecorrigeerde) velden van een bon van DEZE tenant vast als bevestigd."""
        meta = self._meta(tenant_id, bestand_id)
        getoetst = _toets_velden(velden)
        if getoetst is None:
            raise UploadFout(422, "VELDEN_ONGELDIG", "De velden zijn niet geldig.")
        schoon = _maak_schoon(getoetst)
        meldingen = controleer_velden(schoon)
        if meldingen:
            raise UploadFout(
                422,
                "VELDEN_CONTROLEREN",
                "Controleer deze velden: " + ", ".join(sorted(meldingen)) + ".",
            )
        record: dict[str, object] = {
            "velden": schoon,
            "door": gebruiker_id,
            "bevestigd_op": self._nu().isoformat(),
            "sha256": meta.get("sha256", ""),
            "aangemaakt": meta.get("aangemaakt", ""),
            # De naam die de server bij de upload al schoonmaakte; het metabestand verdwijnt na 30 dagen, de
            # bevestiging blijft, en de CSV wil de naam ook dan nog tonen.
            "naam": meta.get("naam", ""),
        }
        doel = self._pad(tenant_id, f"{bestand_id}.bevestigd.json")
        tijdelijk = doel.with_name(f"{doel.name}.{secrets.token_hex(4)}.tmp")
        try:
            _schrijf_nieuw(tijdelijk, json.dumps(record).encode("utf-8"))
            os.replace(tijdelijk, doel)
        except OSError:
            # Het tijdelijke bestand bevat de bevestigde velden; de opruiming herkent zijn naam niet.
            tijdelijk.unlink(missing_ok=True)
            raise
        self._markeer_afgerond(tenant_id, bestand_id, meta)
        logger.info("bonlezer bevestigd: tenant=%s bestand_id=%s", tenant_id, bestand_id)
        return record

    def bevestigd(self, tenant_id: int, bestand_id: str) -> dict[str, object] | None:
        """De bevestiging van deze bon, of `None` (ook voor een bon van een andere tenant)."""
        if not _geldig(tenant_id, bestand_id):
            return None
        return _lees_json(self._pad(tenant_id, f"{bestand_id}.bevestigd.json"))

    def verrijk(
        self, tenant_id: int, bestand_id: str, status: dict[str, object]
    ) -> dict[str, object]:
        """De statusvraag aangevuld met wat de medewerker moet zien.

        Gelezen velden worden van stuurtekens ontdaan en krijgen een lijst `controleren`; de bevestigde
        velden (die ook na het verlopen van het resultaat bestaan) staan onder `bevestigd`.
        """
        uit = dict(status)
        velden = uit.get("velden")
        if uit.get("status") == "gelezen" and isinstance(velden, dict):
            schoon = _maak_schoon(velden)
            uit["velden"] = schoon
            uit["controleren"] = moet_gecontroleerd(schoon)
        record = self.bevestigd(tenant_id, bestand_id)
        uit["bevestigd"] = (
            {"velden": record.get("velden"), "bevestigd_op": record.get("bevestigd_op")}
            if record is not None
            else None
        )
        return uit

    # -- lijst, export, samenvatting ----------------------------------------------------------------

    def lijst(
        self,
        tenant_id: int,
        *,
        limit: int,
        offset: int,
        ververs: Callable[[str], None] | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        """De bonnen van deze tenant, nieuwste eerst: (de gevraagde pagina, het totaal).

        Per bon: de oorspronkelijke bestandsnaam (al schoongemaakt bij de upload), de leverancier (uit de
        bevestiging, anders uit het leesresultaat), de stand en of er gecontroleerd moet worden. Een bon
        zonder vastgelegd resultaat wordt via `ververs` (hooguit `MAX_VERVERS` per aanroep) alsnog opgehaald;
        een fout daarin laat de lijst heel.
        """
        if not _geldige_tenant(tenant_id):
            return [], 0
        items: list[dict[str, object]] = []
        metas: dict[str, dict[str, object]] = {}
        for pad in (self._root / str(tenant_id)).glob("*.meta.json"):
            bestand_id = pad.name.removesuffix(".meta.json")
            meta = _lees_json(pad)
            if meta is None or not _BESTAND_ID.fullmatch(bestand_id):
                continue
            metas[bestand_id] = meta
            naam = meta.get("naam")
            items.append(
                {
                    "bestand_id": bestand_id,
                    "aangemaakt": str(meta.get("aangemaakt", "")),
                    "bevestigd": self._pad(tenant_id, f"{bestand_id}.bevestigd.json").exists(),
                    "naam": naam if isinstance(naam, str) and naam else None,
                }
            )
        items.sort(key=lambda i: (str(i["aangemaakt"]), str(i["bestand_id"])), reverse=True)
        pagina = items[offset : offset + limit]
        ververs = _stop_na_eerste_fout(ververs, tenant_id)
        budget = MAX_VERVERS
        for item in pagina:
            budget -= self._vul_aan(
                tenant_id, item, metas[str(item["bestand_id"])], ververs, budget
            )
        return pagina, len(items)

    def _vul_aan(
        self,
        tenant_id: int,
        item: dict[str, object],
        meta: dict[str, object],
        ververs: Callable[[str], None] | None,
        budget: int,
    ) -> int:
        """Vul `status`, `leverancier` en `controleren` aan; geef terug hoeveel keer er is ververst."""
        bestand_id = str(item["bestand_id"])
        bevestigd = bool(item["bevestigd"])
        resultaat_pad = self._pad(tenant_id, f"{bestand_id}.resultaat.json")
        resultaat = lees_vastgelegd_resultaat(resultaat_pad, bestand_id)
        verlopen = self._leeftijd_seconden(meta) > VERLOOP_SECONDEN
        ververst = 0
        if (
            resultaat is None
            and not bevestigd
            and meta.get("message_id")
            and ververs is not None
            and budget > 0
        ):
            ververst = 1
            ververs(bestand_id)
            resultaat = lees_vastgelegd_resultaat(resultaat_pad, bestand_id)
        if resultaat is not None:
            item["status"] = str(resultaat["status"])
        else:
            item["status"] = "verlopen" if verlopen else "wachten"
        velden: object = None
        if bevestigd:
            record = self.bevestigd(tenant_id, bestand_id)
            velden = record.get("velden") if record is not None else None
        elif resultaat is not None and resultaat["status"] == "gelezen":
            velden = resultaat.get("velden")
        schoon = _maak_schoon(velden) if isinstance(velden, dict) else {}
        leverancier = schoon.get("leverancier")
        item["leverancier"] = (
            leverancier[:_MAX_LEVERANCIER_LIJST]
            if isinstance(leverancier, str) and leverancier
            else None
        )
        item["controleren"] = (not bevestigd) and bool(schoon) and bool(moet_gecontroleerd(schoon))
        return ververst

    def _leeftijd_seconden(self, meta: dict[str, object]) -> float:
        try:
            aangemaakt = datetime.fromisoformat(str(meta["aangemaakt"]))
        except (KeyError, ValueError):
            return 0.0
        return (self._nu() - aangemaakt).total_seconds()

    def bevestigde_bonnen(self, tenant_id: int) -> list[dict[str, object]]:
        """Alle bevestigingen van deze tenant, ook van bonnen die na 30 dagen zijn verwijderd."""
        if not _geldige_tenant(tenant_id):
            return []
        bonnen: list[dict[str, object]] = []
        for pad in (self._root / str(tenant_id)).glob("*.bevestigd.json"):
            bestand_id = pad.name.removesuffix(".bevestigd.json")
            record = _lees_json(pad)
            if record is not None and _BESTAND_ID.fullmatch(bestand_id):
                bonnen.append({**record, "bestand_id": bestand_id})
        bonnen.sort(key=lambda b: (str(b.get("bevestigd_op", "")), str(b["bestand_id"])))
        return bonnen

    def csv_export(self, tenant_id: int) -> str:
        """De bevestigde bonnen van deze tenant als CSV; formules zijn onschadelijk gemaakt."""
        uit = io.StringIO()
        schrijver = csv.writer(uit, lineterminator="\r\n")
        schrijver.writerow(_KOLOMMEN)
        for bon in self.bevestigde_bonnen(tenant_id):
            velden = bon.get("velden")
            if isinstance(velden, dict):
                schrijver.writerow(
                    _rij(bon.get("naam"), velden, bon.get("bevestigd_op"), str(bon["bestand_id"]))
                )
        return uit.getvalue()

    def samenvatting(self, tenant_id: int) -> dict[str, object]:
        """Aantal, totaalbedrag en btw per tarief van de BEVESTIGDE bonnen (voor het pakket)."""
        totaal = Decimal("0")
        btw: dict[str, Decimal] = {}
        aantal = 0
        for bon in self.bevestigde_bonnen(tenant_id):
            velden = bon.get("velden")
            if not isinstance(velden, dict):
                continue
            aantal += 1
            totaal += _decimaal(velden.get("totaal"))
            bedragen = velden.get("btw")
            if isinstance(bedragen, dict):
                for tarief, bedrag in bedragen.items():
                    btw[str(tarief)] = btw.get(str(tarief), Decimal("0")) + _decimaal(bedrag)
        return {
            "aantal": aantal,
            "totaal": str(totaal.quantize(_CENT)),
            "btw": {
                tarief: str(bedrag.quantize(_CENT))
                for tarief, bedrag in sorted(btw.items(), key=_op_tarief)
            },
        }

    # -- intern -------------------------------------------------------------------------------------

    def _pad(self, tenant_id: int, naam: str) -> Path:
        return self._root / str(tenant_id) / naam

    def _markeer_afgerond(self, tenant_id: int, bestand_id: str, meta: dict[str, object]) -> None:
        """Een bevestigde bon is klaar: de status wordt `verlopen` (niet `wachten`) als het resultaat weg is."""
        if meta.get("afgerond"):
            return
        doel = self._pad(tenant_id, f"{bestand_id}.meta.json")
        if not doel.exists():
            # De opruiming nam de bon net weg: geen wees-metabestand terugschrijven dat nog 30 dagen blijft staan.
            return
        tijdelijk = doel.with_name(f"{doel.name}.{secrets.token_hex(4)}.tmp")
        _schrijf_nieuw(tijdelijk, json.dumps({**meta, "afgerond": True}).encode("utf-8"))
        os.replace(tijdelijk, doel)

    def _meta(self, tenant_id: int, bestand_id: str) -> dict[str, object]:
        meta = (
            _lees_json(self._pad(tenant_id, f"{bestand_id}.meta.json"))
            if _geldig(tenant_id, bestand_id)
            else None
        )
        if meta is None:
            raise BonNietGevonden(bestand_id)
        return meta
