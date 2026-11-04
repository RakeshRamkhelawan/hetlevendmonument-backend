"""Stuur de 24 testbonnen als opdrachten naar de bonlezer-worker en tel de uitslag per veld (dag 2).

Draait IN een container op hetzelfde interne netwerk als Redis en de worker
(`scripts/bonlezer/meet_worker.sh`). Per document: `lees_bon.send(tenant, bestand_id)`, wachten op het
resultaat in Redis (de resultaatopslag van Dramatiq, geen tabel), de velden terug omzetten en scoren met
dezelfde telregels als de meting van dag 1 (`src/core/als/bonlezer/meting.py`).

Daarnaast een paar NEGATIEVE opdrachten, om te zien dat de worker weigert wat hij moet weigeren:
dezelfde bestandsnaam onder een andere tenant, een pad met `..` en een verzonnen nummer.

Gebruik (in de container; `/uploads` is de uploadmap zoals de worker die ziet, `/repo` de repo, alleen lezen):
    PYTHONPATH=/app python /repo/scripts/bonlezer_worker_meting.py --tenant 1 --uit /uit/worker-verslag.md
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.core.als.bonlezer.meting import (
    VELDEN,
    DocumentUitslag,
    beoordeel,
    onverwachte_tarieven,
    tel,
)
from src.core.als.bonlezer.veldenlaag import BonVelden
from src.core.als.bonlezer.worker import haal_resultaat, lees_bon

SET = Path("/repo/tests/fixtures/bonnen")
KAART = Path("/uploads/kaart.json")
WACHT_MS = 300_000


def als_velden(uitkomst: dict[str, object]) -> BonVelden:
    """Zet de JSON-velden van de worker terug in een `BonVelden`, voor dezelfde telregels."""
    v = uitkomst.get("velden") or {}
    assert isinstance(v, dict)
    btw = v.get("btw") or {}
    return BonVelden(
        leverancier=v.get("leverancier"),
        datum=date.fromisoformat(v["datum"]) if v.get("datum") else None,
        totaal=Decimal(v["totaal"]) if v.get("totaal") is not None else None,
        factuurnummer=v.get("factuurnummer"),
        btw={int(t): Decimal(b) for t, b in btw.items()},
        btw_nummer=v.get("btw_nummer"),
        kvk_nummer=v.get("kvk_nummer"),
    )


def stuur(tenant: int, bestand_id: str) -> tuple[dict[str, object], float]:
    start = time.perf_counter()
    bericht = lees_bon.send(tenant, bestand_id)
    uitkomst = haal_resultaat(bericht, wacht_ms=WACHT_MS)
    return uitkomst, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser(description="Meet de bonlezer-worker over de testset")
    parser.add_argument("--tenant", type=int, default=1)
    parser.add_argument("--uit", type=Path, required=True)
    argumenten = parser.parse_args()

    kaart: dict[str, str] = json.loads(KAART.read_text(encoding="utf-8"))
    uitslagen: list[DocumentUitslag] = []
    fouten: list[str] = []
    tijden: list[float] = []
    for naam in sorted(kaart):
        antwoorden = json.loads((SET / f"{naam}.json").read_text(encoding="utf-8"))
        uitkomst, duur = stuur(argumenten.tenant, kaart[naam])
        tijden.append(duur)
        print(f"{naam}: {uitkomst['status']} in {duur:.1f} s", flush=True)
        if uitkomst["status"] != "gelezen":
            fouten.append(f"{naam}: {uitkomst['status']} ({uitkomst['reden']})")
            continue
        velden = als_velden(uitkomst)
        uitslagen.append(
            DocumentUitslag(
                naam,
                str(antwoorden["soort"]),
                beoordeel(velden, antwoorden),
                onverwachte_tarieven(velden, antwoorden),
            )
        )

    negatief: list[str] = []
    eerste = sorted(kaart.values())[0]
    for omschrijving, tenant, bestand_id in (
        ("zelfde bestandsnaam, andere tenant", argumenten.tenant + 1, eerste),
        ("pad met ..", argumenten.tenant, f"../{argumenten.tenant + 1}/{eerste}"),
        ("verzonnen nummer", argumenten.tenant, "0" * 32 + ".pdf"),
    ):
        uitkomst, _ = stuur(tenant, bestand_id)
        negatief.append(f"| {omschrijving} | {uitkomst['status']} | {uitkomst['reden']} |")

    geteld = tel(uitslagen)
    regels = [
        f"# Meting bonlezer-worker dag 2, {date.today().isoformat()}",
        "",
        f"- Documenten via de worker gelezen: {len(uitslagen)} van {len(kaart)}",
        f"- Wachttijd per opdracht (versturen tot resultaat): gemiddeld "
        f"{sum(tijden) / len(tijden):.1f} s, langste {max(tijden):.1f} s, totaal {sum(tijden):.0f} s",
        "",
        "| Veld | via de worker (regels) |",
        "| --- | --- |",
    ]
    for veld in VELDEN:
        goed, totaal = geteld[veld]
        procent = f" ({100 * goed // totaal}%)" if totaal else ""
        regels.append(f"| {veld} | {goed}/{totaal}{procent} |")
    regels += ["", "## Niet gelezen", "", *(fouten or ["Geen."])]
    regels += [
        "",
        "## Negatieve opdrachten",
        "",
        "| Opdracht | Status | Reden |",
        "| --- | --- | --- |",
        *negatief,
        "",
    ]
    tekst = "\n".join(regels)
    print(tekst)
    argumenten.uit.write_text(tekst, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
