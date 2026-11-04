"""Lijst de echte open OP-punten uit het ADR-036-register (docs/adr/036-...md).

Bestaat omdat een tekst-zoekende extractie (bijv. `grep STATUS=OPEN`) op dit
bestand systematisch fout gaat: sommige rijen citeren hun EIGEN geschiedenis en
bevatten daardoor meerdere `STATUS=`-velden in dezelfde regel (bijv. OP-24: "...
STATUS=OPEN ... [later in dezelfde rij] ... STATUS=GESLOTEN"). De vastgestelde
regel van dit register -- ook gehandhaafd door
`tests/architecture/test_adr036_register_is_parseable.py` -- is dat het LAATSTE
`STATUS=`-veld op een rij geldt. Gemeten 2026-09-06: een naieve extractie
(eerste treffer) miste OP-202 en OP-205 (echt open) en nam OP-24 (al gesloten)
ten onrechte mee.

Gebruik:
    python scripts/list_adr036_open_items.py                       # lijst + telling
    python scripts/list_adr036_open_items.py --count                # alleen de telling
    python scripts/list_adr036_open_items.py --write-snapshot PAD   # leg open-set vast
    python scripts/list_adr036_open_items.py --diff-against PAD     # delta t.o.v. snapshot
    python scripts/list_adr036_open_items.py --triage-table         # sprint-triagetabel

**Waarom --triage-table bestaat.** Gemeten 2026-09-09:
`docs/agent-briefs/ADR036-BACKLOG-MASTERPROMPT.md` (2026-09-07) bevatte een met de hand
getypte tabel van alle open rijen. Twee dagen later was die tabel al fout: hij toonde 69
rijen en zette OP-139/OP-141 als open terwijl die al gesloten waren, en miste
OP-175/176/177/179/210/212/213 die er sindsdien bij waren gekomen. Een bevroren tabel op een
register dat continu verandert is binnen dagen misleidend. Deze modus trekt de tabel vers uit
het register in plaats van hem met de hand te onderhouden. De Vlag-kolom (vraagt dit Rakesh /
is dit onomkeerbaar / is dit al eerder bewust uitgesteld) blijft BEWUST leeg -- dat is een
oordeel dat vraagt om de rij zelf te lezen, en een keyword-classifier daarop zou dezelfde fout
herhalen als de guards die op FORMULERING matchen in plaats van op de handeling (zie
`.claude/skills/valkuilen/SKILL.md`). Vul de Vlag-kolom handmatig in bij het lezen van elke
rij, zoals de masterprompt dat ook altijd al voorschreef.

**Waarom --write-snapshot/--diff-against bestaan.** Gemeten 2026-09-09: een sessie ADR-036-
guardwerk sloot af met MEER open rijen dan bij aanvang (66 -> 71), ondanks dat het doel was
gaten te dichten. De regel "meet het aantal open rijen bij begin en eind van een iteratie"
stond al als richtlijn in WORKING-CONTEXT.md, maar een richtlijn die je uit het geheugen moet
ophalen tijdens een lange mechanische taak wordt gemist. Deze twee vlaggen maken de delta een
commando met tekstuele output in plaats van een herinnering. Zie docs/AUDIT-TO-FIX-WORKFLOW.md
Fase 0 (--write-snapshot bij de start) en Fase 5 (--diff-against bij de afsluiting, output
letterlijk in de sprint-afsluiting/brief). Er is bewust GEEN blokkerende exit-code op een
toename: het register moet een echte nieuwe ontdekking (zoals het P0-autorisatiecluster) juist
kunnen tonen -- blokkeren zou aanzetten tot verzwijgen. Het doel is dat de delta ONMOGELIJK te
missen is, niet dat hij verboden is.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
# Sinds de splitsing van 2026-09-19 staat het register in TWEE bestanden: ADR-036 houdt zijn
# eigen open rijen, de rest (afgerond plus alles buiten de agentlaag) staat ernaast. Beide
# worden gelezen, want de open-telling en de --diff-against-discipline gaan over het HELE werk
# en niet over een van de twee documenten.
REGISTERS = (
    REPO_ROOT / "docs" / "adr" / "036-agentic-organizational-hierarchy-governance-reuse.md",
    REPO_ROOT / "docs" / "adr" / "036-REGISTER-OVERIG-EN-AFGEROND.md",
)


def _registertekst() -> str:
    """De twee registerbestanden achter elkaar, als een tekst."""
    return chr(10).join(pad.read_text(encoding="utf-8") for pad in REGISTERS)


ROW = re.compile(r"^\|\s*(OP-\d+)\s*\|")
STATUS_FIELD = re.compile(r"\bSTATUS=([A-Z-]+)")


def open_items() -> list[str]:
    """OP-nummers waarvan het LAATSTE STATUS=-veld op de rij OPEN is."""
    text = _registertekst()
    gevonden: list[str] = []
    for line in text.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        statuses = STATUS_FIELD.findall(line)
        if statuses and statuses[-1] == "OPEN":
            gevonden.append(match.group(1))
    return gevonden


def write_snapshot(path: Path, items: list[str]) -> None:
    """Leg de huidige open OP-set vast, voor een latere --diff-against."""
    inhoud = {
        "_toelichting": (
            "Snapshot van de open OP-nummers in het ADR-036-register op een moment in de "
            "tijd. Gebruikt door --diff-against om de delta tussen begin en eind van een "
            "sessie onmisbaar te maken. Zie docs/AUDIT-TO-FIX-WORKFLOW.md Fase 0/5."
        ),
        "vastgelegd": datetime.now(timezone.utc).isoformat(),
        "open_items": items,
        "totaal": len(items),
    }
    path.write_text(json.dumps(inhoud, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Snapshot geschreven: {len(items)} open OP-nummers -> {path}")


def diff_against(path: Path, huidige_items: list[str]) -> None:
    """Print wat er is dichtgegaan en wat er nieuw open is sinds de snapshot op PATH."""
    if not path.exists():
        raise SystemExit(
            f"Snapshot {path} ontbreekt. Leg hem eerst vast met --write-snapshot {path}."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    oud = set(data["open_items"])
    nieuw = set(huidige_items)

    dichtgegaan = sorted(oud - nieuw, key=lambda op: int(op.split("-")[1]))
    nieuw_open = sorted(nieuw - oud, key=lambda op: int(op.split("-")[1]))
    netto = len(nieuw) - len(oud)

    print(f"Snapshot van {data.get('vastgelegd', '?')}: {len(oud)} open OP-nummers.")
    print(f"Nu: {len(nieuw)} open OP-nummers.")
    print()
    if dichtgegaan:
        print(f"Dichtgegaan sinds snapshot ({len(dichtgegaan)}): {', '.join(dichtgegaan)}")
    else:
        print("Dichtgegaan sinds snapshot: geen.")
    if nieuw_open:
        print(f"Nieuw open sinds snapshot ({len(nieuw_open)}): {', '.join(nieuw_open)}")
    else:
        print("Nieuw open sinds snapshot: geen.")
    print()
    teken = "+" if netto > 0 else ""
    print(f"Netto: {teken}{netto} (was {len(oud)}, nu {len(nieuw)}).")
    if netto > 0:
        print(
            "\nEen toename is niet per definitie fout -- een echte nieuwe ontdekking hoort "
            "in dit register. Noem in de afsluitende samenvatting EXPLICIET of elke nieuwe "
            "rij een aantoonbare nieuwe vondst is, of een gevolg van een eigen review-lus "
            "(zie .claude/rules/quality-gates.md Gate 2 -- ronde-cap op eigen "
            "meta-artefacten)."
        )


#: Het PRIORITEITSVELD van een rij. Zelfde vorm en zelfde regel als `STATUS=`: het LAATSTE
#: veld op de rij geldt, want rijen citeren hun eigen geschiedenis.
#:
#: **Waarom dit een expliciet veld is (2026-09-18).** Hier stond een zoekpatroon op de eerste
#: losse P-aanduiding ergens in de regel. Dat gaat systematisch fout, want rijen NOEMEN
#: prioriteiten in hun lopende tekst: "het bewust omheinde P0-autorisatiecluster", "een
#: zijdelingse P0-vondst", "vier verweesde P0-claims". Gemeten die dag: de triagetabel meldde
#: OP-254 als P0 terwijl die rij P1 is, en met de omgekeerde regel (laatste losse treffer)
#: werden OP-13, OP-196 en OP-243 ten onrechte P0. Vier van de tachtig open rijen kregen dus
#: een verkeerde prioriteit, in beide richtingen -- en daarmee gaf het register niet de
#: werkelijkheid weer, terwijl dat een harde eis van dit project is.
#:
#: Een expliciet veld kan geen verwijzing in lopende tekst zijn.
#: `tests/architecture/test_adr036_register_is_parseable.py` bewaakt dat elke rij er precies
#: een heeft.
PRIO_FIELD = re.compile(r"PRIO=(P0|P1|P2|P3|ONBEPAALD)")
BOLD_TITLE = re.compile(r"\*\*(.+?)\*\*")
_PRIO_ORDE = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "ONBEPAALD": 4, "?": 5}


def _titel(regel: str) -> str:
    """Korte titel voor een registerrij: de vetgedrukte kopzin van KOLOM 2, of anders de
    eerste tekst van kolom 2.

    Gemeten 2026-09-09: een eerdere versie zocht de eerste `**...**`-match in de hele rest
    van de regel (kolom 2 EN 3 samen). Oudere rijen (OP-01 e.d.) beginnen hun omschrijving
    NIET vetgedrukt -- de eerste bold-match zat dan in kolom 3 (bijv. een datumstempel als
    "**Nameting 2026-08-31 (bron: ...)**"), en de tabel toonde een datumstempel als titel in
    plaats van het probleem. Fix: isoleer expliciet kolom 2 via een volledige `split("|")`
    (index 0 = leeg voor de eerste pipe, index 1 = het OP-nummer, index 2 = de omschrijving).
    """
    segmenten = regel.split("|")
    kolom2 = segmenten[2] if len(segmenten) > 2 else regel
    bold = BOLD_TITLE.search(kolom2)
    snippet = bold.group(1) if bold else kolom2.strip()
    snippet = " ".join(snippet.split())
    if len(snippet) > 100:
        snippet = snippet[:97].rsplit(" ", 1)[0] + "..."
    return snippet


def triage_table() -> str:
    """Genereer de sprint-triagetabel (OP/Prio/Vlag/Titel) vers uit het register.

    Alleen OPEN rijen (zelfde `open_items()`-logica als --count/--diff-against, dus
    consistent met de rest van dit script). Vlag blijft leeg, zie de moduledocstring.
    """
    text = _registertekst()
    rijen: list[tuple[str, str, str]] = []
    for regel in text.splitlines():
        match = ROW.match(regel)
        if not match:
            continue
        statuses = STATUS_FIELD.findall(regel)
        if not (statuses and statuses[-1] == "OPEN"):
            continue
        op = match.group(1)
        # Laatste veld wint, zoals bij STATUS=. Geen veld -> "?" en dat is zichtbaar in de
        # tabel; raden zou het register onwaar maken.
        prio_velden = PRIO_FIELD.findall(regel)
        prio = prio_velden[-1] if prio_velden else "?"
        rijen.append((op, prio, _titel(regel)))

    rijen.sort(key=lambda r: (_PRIO_ORDE.get(r[1], 4), int(r[0].split("-")[1])))

    uitvoer = ["| OP | Prio | Vlag | Titel (verkort) |", "|----|------|------|------------------|"]
    for op, prio, titel in rijen:
        uitvoer.append(f"| {op} | {prio} | | {titel} |")
    return "\n".join(uitvoer)


def main() -> None:
    # Sommige oudere registerrijen bevatten non-ASCII tekens (bijv. een em-dash) die
    # pre-existing zijn en hier bewust niet worden aangepast. Op Windows is de
    # stdout-encoding bij een redirect naar een bestand niet gegarandeerd UTF-8 (vaak
    # cp1252), en dat verminkt zo'n teken stil tot een vraagteken-symbool. Reconfigure
    # expliciet, anders corrumpeert `--triage-table > bestand.md` de titel-tekst.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", action="store_true", help="Print alleen de telling")
    parser.add_argument(
        "--write-snapshot",
        metavar="PAD",
        help="Schrijf de huidige open OP-set als JSON-snapshot naar PAD",
    )
    parser.add_argument(
        "--diff-against",
        metavar="PAD",
        help="Vergelijk de huidige open OP-set met een eerder met --write-snapshot vastgelegd PAD",
    )
    parser.add_argument(
        "--triage-table",
        action="store_true",
        help="Print de sprint-triagetabel (OP/Prio/Vlag/Titel), gesorteerd op prioriteit",
    )
    args = parser.parse_args()

    items = sorted(open_items(), key=lambda op: int(op.split("-")[1]))

    if args.write_snapshot:
        write_snapshot(Path(args.write_snapshot), items)
        return
    if args.diff_against:
        diff_against(Path(args.diff_against), items)
        return
    if args.triage_table:
        print(triage_table())
        return
    if args.count:
        print(len(items))
        return
    for op in items:
        print(op)
    print(f"\nTotaal open: {len(items)}")


if __name__ == "__main__":
    main()
