"""Draai de bonlezer over de testset en meet per veld hoe vaak het goed gaat (bonlezer dag 1).

Wat dit doet, per document in `tests/fixtures/bonnen/`:

1. de veldenlaag op de BRONTEKST (`*.tekst.txt`): meet de regels los van het lezen;
2. de lezer (Docling + Tesseract `nld`) op het PDF- of beeldbestand, daarna dezelfde veldenlaag:
   meet het hele pad. Twee teksten uit hetzelfde leesresultaat worden afzonderlijk gemeten:
   de platte export van Docling (die regels tot alinea's samenvoegt) en de regels die de lezer
   uit de celposities opbouwt (`regels_uit_resultaat`, de weg die het product gebruikt).

De uitslag gaat naar `docs/evidence/bonlezer-meting-<datum>.md`: per veld goed/totaal, per soort
document, en elk fout gelezen veld met verwachte en gelezen waarde. Dag 1 heeft geen drempel; het
verslag IS het product.

Gebruik (in de meetcontainer, zonder netwerk):
    python scripts/bonlezer_meting.py --artifacts /modellen --uit docs/evidence/bonlezer-meting-X.md

Zonder lezer (alleen de veldenlaag op brontekst):
    python scripts/bonlezer_meting.py --alleen-brontekst
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import types
from collections.abc import Callable
from datetime import date
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _laad_bonlezer_zonder_applicatie() -> None:
    """Maak `src`, `src.core` en `src.core.als` tot lege pakketten, zodat alleen de bonlezer laadt.

    `src/core/__init__.py` laadt de hele applicatieconfiguratie en -afhankelijkheden. De bonlezer
    heeft daar niets van nodig, en de meetcontainer heeft ze niet. Bewust alleen als `src` nog niet
    geladen is: draait dit script binnen de applicatie, dan blijft alles zoals het was.
    """
    if "src" in sys.modules:
        return
    for naam in ("src", "src.core", "src.core.als"):
        pakket = types.ModuleType(naam)
        pakket.__path__ = [str(REPO.joinpath(*naam.split(".")))]
        sys.modules[naam] = pakket


_laad_bonlezer_zonder_applicatie()

from src.core.als.bonlezer.lezer import BonLezer, regels_uit_resultaat  # noqa: E402
from src.core.als.bonlezer.meting import (  # noqa: E402
    VELDEN,
    DocumentUitslag,
    beoordeel,
    onverwachte_tarieven,
    tel,
)
from src.core.als.bonlezer.veldenlaag import BonVelden, lees_velden  # noqa: E402

SET = REPO / "tests" / "fixtures" / "bonnen"
SOORTEN = ("factuur_pdf", "factuur_scan", "bon_foto")

Documenten = list[tuple[str, Path | None, dict[str, object]]]


def veldwaarde(velden: BonVelden, veld: str) -> str:
    """De gelezen waarde als tekst, voor in het verslag."""
    if veld.startswith("btw_") and veld[4:].isdigit():
        waarde = velden.btw.get(int(veld[4:]))
    elif veld == "datum":
        waarde = velden.datum.isoformat() if velden.datum else None
    else:
        waarde = getattr(velden, veld)
    return "(niets gelezen)" if waarde is None else str(waarde)


def verwacht_waarde(antwoorden: dict[str, object], veld: str) -> str:
    if veld.startswith("btw_") and veld[4:].isdigit():
        btw = antwoorden.get("btw")
        waarde = btw.get(veld[4:]) if isinstance(btw, dict) else None
    else:
        waarde = antwoorden.get(veld)
    return "(geen)" if waarde is None else str(waarde)


def documenten() -> Documenten:
    uit: Documenten = []
    for antwoord in sorted(SET.glob("*.json")):
        naam = antwoord.stem
        bestand = next(
            (SET / f"{naam}{x}" for x in (".pdf", ".jpg") if (SET / f"{naam}{x}").exists()), None
        )
        uit.append((naam, bestand, json.loads(antwoord.read_text(encoding="utf-8"))))
    return uit


def meet(
    tekst_van: Callable[[str], str], docs: Documenten
) -> tuple[list[DocumentUitslag], dict[str, BonVelden]]:
    uitslagen: list[DocumentUitslag] = []
    gelezen: dict[str, BonVelden] = {}
    for naam, _bestand, antwoorden in docs:
        velden = lees_velden(tekst_van(naam))
        gelezen[naam] = velden
        uitslagen.append(
            DocumentUitslag(
                naam,
                str(antwoorden["soort"]),
                beoordeel(velden, antwoorden),
                onverwachte_tarieven(velden, antwoorden),
            )
        )
    return uitslagen, gelezen


def _percentage(goed: int, totaal: int) -> str:
    return f"{goed}/{totaal}" + (f" ({100 * goed // totaal}%)" if totaal else "")


def tabel_per_veld(kolommen: dict[str, list[DocumentUitslag]]) -> list[str]:
    kop = [
        "| Veld | " + " | ".join(kolommen) + " |",
        "| --- | " + " | ".join("---" for _ in kolommen) + " |",
    ]
    geteld = {naam: tel(u) for naam, u in kolommen.items()}
    rijen = [
        f"| {veld} | " + " | ".join(_percentage(*geteld[naam][veld]) for naam in kolommen) + " |"
        for veld in VELDEN
    ]
    return kop + rijen


def tabel_per_soort(uitslagen: list[DocumentUitslag]) -> list[str]:
    kop = [
        "| Veld | " + " | ".join(SOORTEN) + " |",
        "| --- | " + " | ".join("---" for _ in SOORTEN) + " |",
    ]
    per_soort = {s: tel([u for u in uitslagen if u.soort == s]) for s in SOORTEN}
    rijen = [
        f"| {veld} | "
        + " | ".join(f"{per_soort[s][veld][0]}/{per_soort[s][veld][1]}" for s in SOORTEN)
        + " |"
        for veld in VELDEN
    ]
    return kop + rijen


def fouten(
    uitslagen: list[DocumentUitslag],
    gelezen: dict[str, BonVelden],
    antwoorden: dict[str, dict[str, object]],
) -> list[str]:
    regels = ["| Document | Soort | Veld | Verwacht | Gelezen |", "| --- | --- | --- | --- | --- |"]
    aantal = 0
    for u in uitslagen:
        for veld in VELDEN:
            if u.resultaat.get(veld) is False:
                aantal += 1
                verwacht = verwacht_waarde(antwoorden[u.naam], veld).replace("|", "/")
                waarde = veldwaarde(gelezen[u.naam], veld).replace("|", "/")
                regels.append(f"| {u.naam} | {u.soort} | {veld} | {verwacht} | {waarde} |")
    return regels if aantal else ["Geen enkel veld fout gelezen."]


def omgeving() -> list[str]:
    def versie(pakket: str) -> str:
        try:
            return metadata.version(pakket)
        except metadata.PackageNotFoundError:
            return "niet geinstalleerd"

    tesseract = shutil.which("tesseract")
    tesseract_versie = "niet gevonden"
    if tesseract:
        uit = subprocess.run([tesseract, "--version"], capture_output=True, text=True, check=False)
        regels = (uit.stdout or uit.stderr).splitlines()
        tesseract_versie = regels[0] if regels else "onbekend"
    return [
        f"- Python {sys.version.split()[0]}, docling {versie('docling')}, tesseract: {tesseract_versie}",
        f"- Commit van de code: {os.environ.get('BONLEZER_SHA', 'onbekend')}",
        f"- Netwerk tijdens het lezen: {os.environ.get('BONLEZER_NETWERK', 'niet vastgelegd')}",
    ]


def lees_alles(
    docs: Documenten, artifacts: Path | None, cache: Path | None
) -> tuple[dict[str, str], dict[str, str], list[float]]:
    """Lees elk bestand een keer; geef (platte export, regels, tijden) terug."""
    lezer = BonLezer(artifacts_pad=artifacts)
    teksten: dict[str, str] = {}
    regels: dict[str, str] = {}
    tijden: list[float] = []
    for naam, bestand, _ in docs:
        if bestand is None:
            continue
        start = time.perf_counter()
        resultaat = lezer.converteer(bestand)
        tijden.append(time.perf_counter() - start)
        document = getattr(resultaat, "document")
        teksten[naam] = str(document.export_to_text())
        regels[naam] = regels_uit_resultaat(resultaat)
        print(f"{naam}: gelezen in {tijden[-1]:.1f} s", flush=True)
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
            (cache / f"{naam}.txt").write_text(teksten[naam], encoding="utf-8")
            (cache / f"{naam}.regels.txt").write_text(regels[naam], encoding="utf-8")
    return teksten, regels, tijden


def verslag_tekst(
    docs: Documenten,
    kolommen: dict[str, list[DocumentUitslag]],
    gelezen: dict[str, BonVelden],
    tijden: list[float],
) -> str:
    antwoorden = {naam: a for naam, _, a in docs}
    regels = [
        f"# Meting bonlezer dag 1, {date.today().isoformat()}",
        "",
        "## Omgeving",
        "",
        *omgeving(),
    ]
    regels += [
        f"- Testset: {len(docs)} documenten in `tests/fixtures/bonnen/` (zelfgemaakt, verzonnen gegevens)"
    ]
    if tijden:
        regels += [
            f"- Leestijd per document: gemiddeld {sum(tijden) / len(tijden):.1f} s, "
            f"langste {max(tijden):.1f} s, totaal {sum(tijden):.0f} s"
        ]
    regels += ["", "## Uitslag per veld (goed/totaal)", "", *tabel_per_veld(kolommen), ""]
    if gelezen:
        tekst = kolommen["na lezen (regels)"]
        regels += ["## Per soort document (na lezen, regels)", "", *tabel_per_soort(tekst), ""]
        regels += [
            "## Fout gelezen velden (na lezen, regels)",
            "",
            *fouten(tekst, gelezen, antwoorden),
            "",
        ]
        onverwacht = [f"{u.naam}: {list(u.onverwacht)}" for u in tekst if u.onverwacht]
        regels += [
            "## Tarieven gelezen die niet in het antwoord staan",
            "",
            *(onverwacht or ["Geen."]),
            "",
        ]
    regels += [
        "## Wat dit WEL en NIET zegt",
        "",
        "- De set is zelfgemaakt door dezelfde hand als de regels; `op brontekst` is daarom een bovengrens"
        " voor de regels, geen bewijs dat ze op echte bonnen werken.",
        "- De beelden zijn schoon gerenderd met kunstmatige ruis; echte foto's (kreuken, glans, thermisch"
        " papier, schaduw) zijn niet gemeten.",
        "- Een lettertype, een taal (Nederlands), geen handschrift, geen gebogen of gescheurde bonnen.",
        "- Dag 1 stelt geen drempel; de getallen zijn het nulpunt voor dag 2 en verder.",
        "",
    ]
    return "\n".join(regels)


def main() -> int:
    parser = argparse.ArgumentParser(description="Meet de bonlezer over de testset")
    parser.add_argument(
        "--artifacts", type=Path, help="map met de vooraf gedownloade Docling-modellen"
    )
    parser.add_argument("--uit", type=Path, help="schrijf het verslag naar dit bestand")
    parser.add_argument("--cache", type=Path, help="bewaar de gelezen tekst per document hier")
    parser.add_argument(
        "--alleen-brontekst", action="store_true", help="geen lezer, alleen de regels"
    )
    argumenten = parser.parse_args()

    docs = documenten()
    bron, _ = meet(lambda naam: (SET / f"{naam}.tekst.txt").read_text(encoding="utf-8"), docs)
    kolommen: dict[str, list[DocumentUitslag]] = {"op brontekst": bron}
    gelezen: dict[str, BonVelden] = {}
    tijden: list[float] = []

    if not argumenten.alleen_brontekst:
        teksten, regels, tijden = lees_alles(docs, argumenten.artifacts, argumenten.cache)
        kolommen["na lezen (platte export)"], _ = meet(lambda naam: teksten[naam], docs)
        kolommen["na lezen (regels)"], gelezen = meet(lambda naam: regels[naam], docs)

    tekst = verslag_tekst(docs, kolommen, gelezen, tijden)
    print(tekst)
    if argumenten.uit:
        argumenten.uit.parent.mkdir(parents=True, exist_ok=True)
        argumenten.uit.write_text(tekst, encoding="utf-8")
        print(f"verslag geschreven naar {argumenten.uit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
