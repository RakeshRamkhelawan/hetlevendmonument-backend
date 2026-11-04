"""Vult tekst die een medewerker in een workflowstap schrijft veilig in met de context van de uitvoering.

Waarom niet `str.format`: dat laat attributen en indexen lezen (`{input_json.__class__}`, `{x.__init__.__globals__}`) en
faalt op accolades in gewone tekst (een JSON-voorbeeld in een opdracht). Hier geldt alleen `{naam}` en
`{naam.veld.veld}`: de eerste naam moet in de context staan, elk volgend deel moet een sleutel van een woordenboek zijn.
Al het andere (onbekende naam, onbekend veld, attribuut, index, opmaakspecificatie, dubbele accolades) blijft letterlijk
staan. Er is geen `eval` en geen sjabloonbibliotheek.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

# De klant van de uitvoering is geen invulwaarde: die komt uit de uitvoering zelf, niet uit de tekst van een medewerker.
_NIET_INVULBAAR = frozenset({"tenant_id"})

#: Een ingevulde waarde en de hele tekst zijn begrensd: een uitkomst van een eerdere stap kan groot zijn en een medewerker
#: kan een verwijzing honderden keren herhalen; de prompt (en de rekening van het taalmodel) groeit dan met het product.
MAX_LENGTE_WAARDE = 20_000
MAX_LENGTE_TOTAAL = 200_000
#: De tekst die een medewerker schrijft is zelf ook begrensd. Het uitvoerbudget dekt dat niet: verwijzingen die leeg oplossen
#: kosten niets aan uitvoer maar wel CPU (gemeten 8,5 s bij 3 miljoen), en een open `{a.a.a...` zonder sluiting gaf 730 MB in
#: de regex (hertoets Gate 2 security).
MAX_LENGTE_INVOER = 200_000
INGEKORT = " [ingekort]"

_VERWIJZING = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\}(?!\})")


def _veilig_str(waarde: object) -> str:
    """`str()` zonder fout: Python weigert een geheel getal van meer dan 4300 cijfers (ValueError) en een te diepe structuur."""
    try:
        return str(waarde)
    except (ValueError, RecursionError):
        return "[te groot om te tonen]"


def _als_tekst(waarde: object) -> str:
    """Een woordenboek of lijst als JSON (leesbaar en door een volgende stap te lezen); de rest met `str`."""
    if isinstance(waarde, (dict, list)):
        try:
            tekst = json.dumps(waarde, ensure_ascii=False, default=str)
        except (TypeError, ValueError, RecursionError):
            # Cyclisch (ValueError) of extreem diep (RecursionError): dan geen JSON maar de korte weergave.
            tekst = _veilig_str(waarde)
    else:
        tekst = _veilig_str(waarde)
    if len(tekst) > MAX_LENGTE_WAARDE:
        return tekst[:MAX_LENGTE_WAARDE] + INGEKORT
    return tekst


def _zoek(pad: str, context: Mapping[str, object]) -> str | None:
    delen = pad.split(".")
    # Elk deel, niet alleen het eerste: `{stap.tenant_id}` mag de klant van een uitvoering ook niet laten zien.
    if any(deel in _NIET_INVULBAAR for deel in delen) or delen[0] not in context:
        return None
    waarde: object = context[delen[0]]
    for veld in delen[1:]:
        if not isinstance(waarde, dict) or veld not in waarde:
            return None
        waarde = waarde[veld]
    return _als_tekst(waarde)


def vul_in(tekst: str, context: Mapping[str, object]) -> str:
    """De tekst met alle toegestane verwijzingen ingevuld; al het andere blijft staan zoals getypt.

    De invoer is begrensd op `MAX_LENGTE_INVOER` en de uitkomst op `MAX_LENGTE_TOTAAL`; daarboven eindigt de tekst op een
    duidelijke aanduiding. Het uitvoerbudget loopt MEE tijdens het opbouwen (zie `_vul_in`).
    """
    if len(tekst) > MAX_LENGTE_INVOER:
        uitkomst = _vul_in(tekst[:MAX_LENGTE_INVOER], context)
        # Haalde de vulling zelf ook het uitvoerbudget, dan staat de aanduiding er al: niet twee keer.
        return uitkomst if uitkomst.endswith(INGEKORT) else uitkomst + INGEKORT
    return _vul_in(tekst, context)


def _vul_in(tekst: str, context: Mapping[str, object]) -> str:
    """De tekst met alle toegestane verwijzingen ingevuld; al het andere blijft staan zoals getypt.

    De uitkomst is begrensd op `MAX_LENGTE_TOTAAL`. Het budget loopt MEE tijdens het opbouwen: een tekst met tienduizenden
    verwijzingen naar een grote waarde mag nooit eerst volledig in het geheugen komen (gemeten: circa 800 MB piek). Zodra
    het budget op is, stopt het invullen en eindigt de tekst op een duidelijke aanduiding. Dezelfde verwijzing wordt
    binnen een aanroep maar een keer omgezet.
    """
    omgezet: dict[str, str | None] = {}
    delen: list[str] = []
    lengte = 0
    laatste = 0

    for treffer in _VERWIJZING.finditer(tekst):
        pad = treffer.group(1)
        if pad not in omgezet:
            omgezet[pad] = _zoek(pad, context)
        gevonden = omgezet[pad]
        voor = tekst[laatste : treffer.start()]
        invulling = treffer.group(0) if gevonden is None else gevonden
        if lengte + len(voor) + len(invulling) > MAX_LENGTE_TOTAAL:
            rest = max(0, MAX_LENGTE_TOTAAL - lengte)
            delen.append((voor + invulling)[:rest] + INGEKORT)
            return "".join(delen)
        delen.append(voor)
        delen.append(invulling)
        lengte += len(voor) + len(invulling)
        laatste = treffer.end()

    staart = tekst[laatste:]
    if lengte + len(staart) > MAX_LENGTE_TOTAAL:
        return "".join(delen) + staart[: max(0, MAX_LENGTE_TOTAAL - lengte)] + INGEKORT
    return "".join(delen) + staart
