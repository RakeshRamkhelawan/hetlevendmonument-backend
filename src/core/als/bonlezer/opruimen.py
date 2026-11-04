"""De opruiming van geuploade bonnen na 30 dagen (bonlezer dag 4).

Besluit Rakesh 2026-10-17: "30 dagen bewaren en zijn daarmee lezer". Dat akkoord (interlock 1) geldt voor
PRECIES dit en niets anders: een geuploade bon en zijn metabestand, 30 dagen na de upload. Daarom is deze
module bewust smal:

- Na 30 dagen worden alleen bestanden met EEN van deze namen verwijderd, en alleen direct onder
  `<uploadmap>/<tenantnummer>/`: de bon (`<32 hex>.<pdf|png|jpg|jpeg|tif|tiff>`), zijn metabestand
  (`<bon>.meta.json`), het vastgelegde leesresultaat (`<bon>.resultaat.json`, acceptatie dag 4: valt onder de
  30 dagen van de bon) en hun achtergebleven tijdelijke bestanden (`<naam>.<8 hex>.tmp`).
- De bevestigde velden (`<bon>.bevestigd.json`, alleen cijfers) volgen een EIGEN termijn (besluit Rakesh
  2026-10-17, "optie 2"): bewaard tot het einde van het kwartaal van de bondatum plus 3 maanden, daarna
  verwijderd door `ruim_bevestigd_op`. Zonder leesbare bondatum blijft het bestand staan.
- NIET: elk bestand met een andere naam, een map die geen tenantnummer is, en alles dat een symlink is (er
  wordt nooit een koppeling gevolgd; wat via een koppeling buiten de uploadmap wijst blijft staan).
- De leeftijd telt vanaf de UPLOAD: de wijzigingstijd van de bon. Het metabestand wordt bij elke
  statusvraag opnieuw geschreven en zegt daar niets over; ontbreekt de bon, dan telt het oudste bestand van de
  groep.
- Een bestand dat niet weg kan (rechten, schijf) stopt de rest niet; het blijft staan en wordt de volgende
  dag opnieuw geprobeerd.
- Het log noemt per tenant alleen het AANTAL bonnen: geen bestandsnamen en geen inhoud.
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: Het besluit van Rakesh (2026-10-17): 30 dagen.
BEWAARDAGEN = 30


def upload_map() -> Path:
    """De uploadmap zoals het proces die ziet (`BONLEZER_UPLOAD_ROOT`, standaard `/data/bonnen`)."""
    return Path(os.environ.get("BONLEZER_UPLOAD_ROOT", "/data/bonnen"))


_TENANT_MAP = re.compile(r"[1-9][0-9]*")
_BESTAND = re.compile(
    r"(?P<id>[0-9a-f]{32}\.(?:pdf|png|jpg|jpeg|tif|tiff))"
    r"(?P<soort>|\.meta\.json|\.meta\.json\.[0-9a-f]{8}\.tmp"
    r"|\.resultaat\.json|\.resultaat\.json\.[0-9a-f]{8}\.tmp"
    r"|\.factuur\.json|\.factuur\.json\.[0-9a-f]{8}\.tmp)"
)
_BEVESTIGD = re.compile(r"[0-9a-f]{32}\.(?:pdf|png|jpg|jpeg|tif|tiff)\.bevestigd\.json")
_ISO_DATUM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
#: Een bevestiging is een paar velden; veel groter is geen bevestiging en wordt niet gelezen.
_MAX_BEVESTIGING_BYTES = 64 * 1024


def _tenantmappen(root: Path) -> list[os.DirEntry[str]]:
    try:
        return [
            entry
            for entry in os.scandir(root)
            if _TENANT_MAP.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False)
        ]
    except (FileNotFoundError, NotADirectoryError):
        return []


def ruim_op(root: Path, *, nu: datetime | None = None, dagen: int = BEWAARDAGEN) -> dict[int, int]:
    """Verwijder bonnen ouder dan `dagen`; geef per tenant het aantal verwijderde bonnen terug."""
    grens = (nu or datetime.now(timezone.utc)).timestamp() - dagen * 86400
    resultaat: dict[int, int] = {}
    for tenantmap in _tenantmappen(root):
        try:
            aantal = _ruim_tenant_op(Path(tenantmap.path), grens)
        except OSError as fout:
            # Een map die niet te lezen is mag de andere tenants niet blokkeren; morgen opnieuw.
            logger.warning("bonlezer opruimen: een tenantmap kon niet worden gelezen (%s)", type(fout).__name__)
            continue
        if aantal:
            resultaat[int(tenantmap.name)] = aantal
            logger.info("bonlezer opruimen: tenant=%s bonnen=%d", tenantmap.name, aantal)
    return resultaat


def bewaar_tot(datum: object) -> date | None:
    """De laatste dag dat een bevestiging bewaard blijft: einde van het kwartaal van `datum` plus 3 maanden.

    Bondatum 2026-02-26 valt in kwartaal 1 (einde 2026-03-31), dus tot en met 2026-06-30. Geen leesbare
    datum (`JJJJ-MM-DD`, bestaande dag) betekent `None`: dan wordt er niets verwijderd.
    """
    if not isinstance(datum, str) or _ISO_DATUM.fullmatch(datum) is None:
        return None
    try:
        dag = date.fromisoformat(datum)
    except ValueError:
        return None
    maand = 3 * ((dag.month - 1) // 3 + 1) + 3
    jaar = dag.year + (maand - 1) // 12
    maand = (maand - 1) % 12 + 1
    if jaar > date.max.year:
        # De bondatum is invoer van een gebruiker (`9999-10-01` is geldig); een termijn voorbij het einde van
        # de kalender bestaat niet en mag de run niet laten crashen. `ruim_bevestigd_op` begrenst hem.
        return date.max
    return date(jaar, maand, calendar.monthrange(jaar, maand)[1])


#: De termijn begint nooit eerder dan zoveel dagen na het bevestigen, en duurt nooit langer dan zoveel jaar
#: daarna (security-review dag 4: de bondatum kiest de gebruiker zelf; een datum ver in het verleden mag de
#: bevestiging niet meteen laten verdwijnen, een datum ver in de toekomst mag hem niet eeuwig laten staan).
_MIN_NA_BEVESTIGEN_DAGEN = 30
_MAX_NA_BEVESTIGEN_JAREN = 10


def _bevestigd_op(waarde: object) -> date | None:
    if not isinstance(waarde, str):
        return None
    try:
        return datetime.fromisoformat(waarde).date()
    except ValueError:
        return None


def _termijn_einde(velden: object, bevestigd_op: object) -> date | None:
    """De laatste bewaardag van een bevestiging, of `None` (dan wordt er niets verwijderd)."""
    eind = bewaar_tot(velden.get("datum") if isinstance(velden, dict) else None)
    if eind is None:
        return None
    bevestigd = _bevestigd_op(bevestigd_op)
    if bevestigd is None:
        return eind
    try:
        eind = max(eind, bevestigd + timedelta(days=_MIN_NA_BEVESTIGEN_DAGEN))
    except OverflowError:
        return date.max
    try:
        plafond = bevestigd.replace(year=bevestigd.year + _MAX_NA_BEVESTIGEN_JAREN)
    except ValueError:
        # 29 februari in een jaar zonder 29 februari, of voorbij het einde van de kalender.
        try:
            plafond = bevestigd.replace(
                year=bevestigd.year + _MAX_NA_BEVESTIGEN_JAREN, month=2, day=28
            )
        except ValueError:
            plafond = date.max
    return min(eind, plafond)


def ruim_bevestigd_op(root: Path, *, nu: datetime | None = None) -> dict[int, int]:
    """Verwijder bevestigde velden waarvan de bewaartermijn voorbij is; het aantal per tenant."""
    vandaag = (nu or datetime.now(timezone.utc)).date()
    resultaat: dict[int, int] = {}
    for tenantmap in _tenantmappen(root):
        try:
            aantal = _ruim_tenant_bevestigd_op(Path(tenantmap.path), vandaag)
        except OSError as fout:
            logger.warning(
                "bonlezer opruimen: een tenantmap kon niet worden gelezen (%s)", type(fout).__name__
            )
            continue
        if aantal:
            resultaat[int(tenantmap.name)] = aantal
            logger.info("bonlezer opruimen: tenant=%s bevestigingen=%d", tenantmap.name, aantal)
    return resultaat


def _ruim_tenant_bevestigd_op(tenantmap: Path, vandaag: date) -> int:
    verwijderd = 0
    for entry in os.scandir(tenantmap):
        if _BEVESTIGD.fullmatch(entry.name) is None:
            continue
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            if entry.stat(follow_symlinks=False).st_size > _MAX_BEVESTIGING_BYTES:
                continue
            with open(entry.path, "rb") as bron:
                record = json.loads(bron.read())
        except (OSError, ValueError, RecursionError):
            # Verdwenen, onleesbaar, geen JSON of te diep genest: blijven staan, nooit raden.
            continue
        if not isinstance(record, dict):
            continue
        eind = _termijn_einde(record.get("velden"), record.get("bevestigd_op"))
        if eind is not None and vandaag > eind:
            verwijderd += _verwijder(Path(entry.path))
    return verwijderd


def _ruim_tenant_op(tenantmap: Path, grens: float) -> int:
    groepen: dict[str, list[tuple[Path, str, float]]] = defaultdict(list)
    for entry in os.scandir(tenantmap):
        treffer = _BESTAND.fullmatch(entry.name)
        if treffer is None:
            continue
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            tijd = entry.stat(follow_symlinks=False).st_mtime
        except OSError:
            # Het bestand verdween tijdens de run (bijvoorbeeld een mislukte upload die zichzelf opruimt).
            continue
        groepen[treffer["id"]].append((Path(entry.path), treffer["soort"], tijd))
    verwijderd = 0
    for bestanden in groepen.values():
        if _upload_tijd(bestanden) >= grens:
            continue
        if sum(_verwijder(pad) for pad, _, _ in bestanden):
            verwijderd += 1
    return verwijderd


def _upload_tijd(bestanden: list[tuple[Path, str, float]]) -> float:
    """De wijzigingstijd van de bon; zonder bon het oudste bestand van de groep."""
    for _, soort, tijd in bestanden:
        if soort == "":
            return tijd
    return min(tijd for _, _, tijd in bestanden)


def _verwijder(pad: Path) -> int:
    try:
        os.unlink(pad)
    except OSError as fout:
        logger.warning("bonlezer opruimen: een bestand kon niet weg (%s)", type(fout).__name__)
        return 0
    return 1
