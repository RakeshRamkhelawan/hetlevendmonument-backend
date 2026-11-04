"""Beoordeel gelezen velden tegen de juiste antwoorden, per veld (bonlezer dag 1).

Puur rekenwerk zonder OCR, zodat de telregels zelf getest kunnen worden
(`tests/unit/bonlezer/test_meting.py`). `scripts/bonlezer_meting.py` draait de lezer over de
testset en gebruikt dit om de uitslag per veld te tellen.

Wat telt als goed:

- `leverancier`: gelijk na kleine letters en zonder leestekens of spaties (OCR schrijft "&" en
  hoofdletters niet altijd gelijk; een andere naam blijft fout).
- `datum`, `totaal`, `factuurnummer`, `btw_nummer`, `kvk_nummer`: exact gelijk. Een totaal dat
  een cent afwijkt is fout.
- `btw_9`, `btw_21`: alleen beoordeeld als het antwoord dat tarief heeft (anders `None`, niet van
  toepassing). Een tarief dat de lezer vindt terwijl het niet in het antwoord staat, telt apart als
  `onverwacht`; het maakt geen goed antwoord fout, maar het staat in het verslag.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from src.core.als.bonlezer.veldenlaag import BonVelden

VELDEN = (
    "leverancier",
    "datum",
    "totaal",
    "factuurnummer",
    "btw_9",
    "btw_21",
    "btw_nummer",
    "kvk_nummer",
)
BEOORDEELDE_TARIEVEN = (9, 21)


@dataclass(frozen=True)
class DocumentUitslag:
    naam: str
    soort: str
    resultaat: Mapping[str, bool | None]
    onverwacht: Sequence[int]


def _naam(tekst: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(tekst or "").casefold())


def _btw_antwoord(antwoorden: Mapping[str, object]) -> dict[int, Decimal]:
    btw = antwoorden.get("btw")
    if not isinstance(btw, Mapping):
        return {}
    return {int(tarief): Decimal(str(bedrag)) for tarief, bedrag in btw.items()}


def _beoordeel_factuurnummer(gelezen: str | None, verwacht: object) -> bool | None:
    """Een kassabon heeft geen factuurnummer: dan telt alleen een VALS nummer, anders niet van toepassing."""
    if verwacht is None:
        return False if gelezen is not None else None
    return gelezen == verwacht


def beoordeel(velden: BonVelden, antwoorden: Mapping[str, object]) -> dict[str, bool | None]:
    """Per veld True (goed), False (fout) of None (niet van toepassing)."""
    gelezen_datum = velden.datum.isoformat() if velden.datum else None
    verwacht_totaal = antwoorden.get("totaal")
    uit: dict[str, bool | None] = {
        "leverancier": _naam(velden.leverancier) == _naam(antwoorden.get("leverancier")),
        "datum": gelezen_datum == antwoorden.get("datum"),
        "totaal": velden.totaal is not None
        and verwacht_totaal is not None
        and velden.totaal == Decimal(str(verwacht_totaal)),
        "factuurnummer": _beoordeel_factuurnummer(velden.factuurnummer, antwoorden.get("factuurnummer")),
        "btw_nummer": velden.btw_nummer == antwoorden.get("btw_nummer"),
        "kvk_nummer": velden.kvk_nummer == antwoorden.get("kvk_nummer"),
    }
    verwacht_btw = _btw_antwoord(antwoorden)
    for tarief in BEOORDEELDE_TARIEVEN:
        uit[f"btw_{tarief}"] = (
            velden.btw.get(tarief) == verwacht_btw[tarief] if tarief in verwacht_btw else None
        )
    return uit


def onverwachte_tarieven(velden: BonVelden, antwoorden: Mapping[str, object]) -> list[int]:
    """Tarieven die de lezer vond maar die niet in het antwoord staan."""
    verwacht = _btw_antwoord(antwoorden)
    return sorted(t for t in velden.btw if t not in verwacht)


def tel(uitslagen: Sequence[DocumentUitslag]) -> dict[str, tuple[int, int]]:
    """Per veld (goed, totaal), zonder de documenten waar het veld niet van toepassing is."""
    uit: dict[str, tuple[int, int]] = {}
    for veld in VELDEN:
        beoordeeld = [u.resultaat[veld] for u in uitslagen if u.resultaat.get(veld) is not None]
        uit[veld] = (sum(1 for b in beoordeeld if b), len(beoordeeld))
    return uit
