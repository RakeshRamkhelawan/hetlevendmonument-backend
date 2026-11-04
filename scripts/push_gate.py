"""Gedeelde push-goedkeuring voor `origin/develop`, over alle sessies heen (2026-09-10).

**Aanleiding.** Rakesh wil dat elke sessie zelf naar `origin/develop` kan pushen, maar
dat een DOOR HEM AANGEWEZEN sessie ("de regie") de daadwerkelijke push-momenten
coordineert -- zodat pushes niet willekeurig door elkaar heen gebeuren, elke push
tegen een bekende, recent geverifieerde stand gebeurt, en er altijd een duidelijk
antwoord is op "is dit al gepusht, en door wie goedgekeurd".

**Hoe dit samenwerkt met `scripts/hooks/pre-push`.** Die hook draait al de volledige
poort bij elke push naar `develop`. Dit bestand voegt een TWEEDE, aanvullende
voorwaarde toe: de hook weigert een push naar `develop` als de exacte commit die
gepusht wordt geen goedgekeurde vermelding heeft. Beide voorwaarden moeten slagen.

**Wat dit WEL en NIET afdwingt.** Net als `claim_op.py`: de state leeft in de
GEDEELDE `.git`-map (`git rev-parse --git-common-dir`), dus zichtbaar voor elke
worktree zonder commit. Dat maakt de hook-check betrouwbaar voor een sessie die
zich aan het protocol houdt. Het is GEEN ijzeren slot: elke sessie heeft dezelfde
Bash-toegang tot dit bestand en zou in theorie zelf `approve` kunnen aanroepen. De
afdwinging zit in het PROTOCOL (CLAUDE.md: vraag de regie-sessie om goedkeuring
voor je pusht), dit script maakt naleven daarvan een kwestie van een commando in
plaats van een erewoord zonder enige controle.

Gebruik:
    python scripts/push_gate.py whois                              # wie is nu de regie-sessie?
    python scripts/push_gate.py set-coordinator --session <naam>   # alleen Rakesh/de regie zelf wijzigt dit
    python scripts/push_gate.py approve --sha <sha> --by <naam> [--note "..."]
    python scripts/push_gate.py check <sha>                        # exit 0 = goedgekeurd, 1 = niet
    python scripts/push_gate.py status
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _git_common_dir() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(completed.stdout.strip())
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


GATE_PATH = _git_common_dir() / "sanskritisetu-push-gate.json"
LOCK_PATH = GATE_PATH.with_suffix(".lock")


@contextmanager
def _locked(timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Kon de lock niet krijgen binnen {timeout}s -- {LOCK_PATH} "
                    "bestaat al. Verwijder hem handmatig als een eerdere aanroep "
                    "is gecrasht."
                ) from None
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        LOCK_PATH.unlink(missing_ok=True)


def _read() -> dict:
    if not GATE_PATH.exists():
        return {"coordinator": None, "approved": {}}
    return json.loads(GATE_PATH.read_text(encoding="utf-8"))


def _write(data: dict) -> None:
    GATE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_sha(rev: str) -> str:
    """Volledige sha, zodat een prefix-match nooit per ongeluk een andere commit goedkeurt."""
    return subprocess.run(
        ["git", "rev-parse", rev], capture_output=True, text=True, check=True
    ).stdout.strip()


#: Hoe lang een goedkeuring mag blijven liggen voor hij wordt gemeld. Een uur, want een
#: push met de volledige poort duurt een kwartier: korter geeft ruis op elke normale push,
#: langer laat een vergeten goedkeuring een halve werkdag onzichtbaar.
WAARSCHUW_NA = timedelta(hours=1)

#: Een goedkeuringsrij uit het gatebestand. Bewust `object` en geen `Any`: de waarden zijn
#: str of bool (`by`, `approved_at`, `note`, `by_human`, `worktree`), en met `object` blijft
#: de Any-gate schoon zonder dat er iets wordt verzwegen.
Goedkeuring = dict[str, object]


def _lokale_develop() -> str | None:
    """De sha waar de LOKALE `origin/develop`-ref op staat, of None.

    BEWUST de lokale ref en niet `git ls-remote`, en de reden is de faalRICHTING:

    - lokale ref verouderd -> een GELANDE sha wordt alsnog gemeld. Vals alarm, luid,
      en de lezer ziet meteen waartegen is gemeten want dat staat in de uitvoer.
    - `ls-remote` bij een haperend netwerk -> geen uitspraak, dus GEEN waarschuwing, en
      precies dan mis je de sha die een dag blijft liggen.

    `status` en `whois` staan in de openingsronde van elke sessie; die mag niet
    netwerkafhankelijk worden. Een controle hoort luid te falen en niet stil.
    """
    resultaat = subprocess.run(  # nosec B603 B607: vaste argumenten, geen invoer
        ["git", "rev-parse", "refs/remotes/origin/develop"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultaat.returncode != 0:
        return None
    return resultaat.stdout.strip() or None


def _landingsstatussen(shas: list[str], basis: str | None) -> dict[str, bool | None]:
    """Per sha: True = geland, False = blijft liggen, None = niet vast te stellen.

    None is een eigen antwoord en geen variant van False. Een sha die lokaal niet bestaat
    -- goedgekeurd in een andere worktree en nooit gefetcht -- als "blijft liggen" tonen is
    een bewering die je niet kunt waarmaken.

    **Waarom dit in TWEE git-aanroepen gebeurt en niet in twee PER SHA.** De eerste versie
    draaide `cat-file -e` plus `merge-base --is-ancestor` per sha. Gemeten op het echte
    gatebestand: 83 goedgekeurde shas, 167 subprocessen, **14 seconden** voor een enkele
    `push_gate.py status`. Dat commando staat in de openingsronde van ELKE sessie, dus dat
    is veertien seconden op elke start -- voor een waarschuwing die meestal niets te melden
    heeft. Een controle die zo duur is, wordt op een dag dat het druk is uit de
    openingsronde gehaald, en dan is hij er niet meer op de ochtend dat hij nodig is.
    Nu: een `cat-file --batch-check` voor het bestaan, en een `rev-list ... --not <basis>`
    die in EEN keer teruggeeft welke shas NIET in de basis zitten.

    Let op dat hier VOLLEDIGE shas in gaan. Afgekorte shas zijn dubbelzinnig: in dit
    gatebestand staat `2dbc58d9d16a...`, terwijl `2dbc58d9` in deze repo naar een heel
    andere commit (`2dbc58d90531...`) resolvet. Op een afkorting toetsen zou die sha ten
    onrechte als GELAND aanmerken.
    """
    if basis is None or not shas:
        return {sha: None for sha in shas}

    bestaan = subprocess.run(  # nosec B603 B607: vaste argumenten, shas uit ons eigen bestand
        ["git", "cat-file", "--batch-check"],
        input="\n".join(shas) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    aanwezig = {
        regel.split()[0]
        for regel in bestaan.stdout.splitlines()
        if len(regel.split()) >= 2 and regel.split()[1] == "commit"
    }
    if not aanwezig:
        return {sha: None for sha in shas}

    niet_geland = subprocess.run(  # nosec B603 B607: vaste argumenten, shas uit ons eigen bestand
        ["git", "rev-list", "--no-walk", *sorted(aanwezig), "--not", basis],
        capture_output=True,
        text=True,
        check=False,
    )
    if niet_geland.returncode != 0:
        # Kan de vraag niet beantwoorden. Dan zeggen we dat, in plaats van te gokken dat
        # alles geland is -- dat laatste zou de waarschuwing stil uitzetten.
        return {sha: (None if sha not in aanwezig else None) for sha in shas}
    achter = set(niet_geland.stdout.split())
    return {sha: (None if sha not in aanwezig else sha not in achter) for sha in shas}


def _blijft_liggen(
    data: dict[str, object], status_fn: Callable[[str], bool | None]
) -> tuple[list[tuple[str, Goedkeuring]], list[tuple[str, Goedkeuring, str]]]:
    """(blijft_liggen, onbepaald) -- goedgekeurd, ouder dan `WAARSCHUW_NA`, niet geland.

    `onbepaald` bevat drietallen `(sha, entry, reden)`: er zijn TWEE manieren waarop deze
    controle geen uitspraak kan doen, en ze vragen een ander vervolg. Een sha die lokaal
    niet bestaat los je op met `git fetch`; een onleesbare timestamp los je op door het
    gatebestand te repareren.

    **Een onleesbare of ontbrekende `approved_at` wordt GEMELD en niet overgeslagen.** De
    eerste versie deed `continue` bij een lege of onparseerbare waarde. Dat is precies het
    tegenovergestelde van waarvoor deze controle bestaat: de rij verdween dan zonder enige
    uitvoer, en dat is stil falen op de plek die stil falen moest opvangen. Gevonden door
    de Gate 2-code-review. Het gatebestand is gedeeld JSON dat met de hand bewerkt wordt,
    dus dit is geen theoretisch pad.
    """
    nu = datetime.now(timezone.utc)
    liggen: list[tuple[str, Goedkeuring]] = []
    onbepaald: list[tuple[str, Goedkeuring, str]] = []
    # Een gatebestand met een kapotte `approved` is geen reden om te crashen en al helemaal
    # niet om te zwijgen: dan valt de controle weg op precies het moment dat het bestand
    # aandacht nodig heeft. Hij wordt hier expliciet afgevangen.
    approved = data.get("approved", {})
    if not isinstance(approved, dict):
        return [], []
    for sha, entry in sorted(
        approved.items(), key=lambda kv: str(kv[1].get("approved_at", ""))
    ):
        rauw = entry.get("approved_at")
        if not rauw:
            onbepaald.append((sha, entry, "geen approved_at in het gatebestand"))
            continue
        try:
            wanneer = datetime.fromisoformat(str(rauw))
        except ValueError:
            onbepaald.append((sha, entry, f"approved_at is onleesbaar: {rauw!r}"))
            continue
        if wanneer.tzinfo is None:
            wanneer = wanneer.replace(tzinfo=timezone.utc)
        if nu - wanneer < WAARSCHUW_NA:
            continue
        status = status_fn(sha)
        if status is True:
            continue
        if status is False:
            liggen.append((sha, entry))
        else:
            onbepaald.append((sha, entry, "bestaat hier niet lokaal"))
    return liggen, onbepaald


def _toon_blijft_liggen() -> None:
    """De waarschuwing, BOVENAAN `status` en `whois`.

    Waarom bovenaan en met een rand: beide commando's drukken al veel af, en een rustige
    regel tussen de rest wordt overgeslagen op precies de ochtend dat het ertoe doet.
    Waarom GEEN exitcode: aanroepers rekenen op 0, en dan wordt de waarschuwing een
    storing in plaats van een signaal.

    Aanleiding: `839d98e1` stond een dag goedgekeurd en ongepusht. Dat kwam alleen aan het
    licht doordat een sessie bij ANDER werk de commitlijst natelde.
    """
    basis = _lokale_develop()
    data = _read()
    statussen = _landingsstatussen(list(data.get("approved", {})), basis)
    liggen, onbepaald = _blijft_liggen(data, statussen.get)
    if not liggen and not onbepaald:
        return

    # De kop draagt de boodschap ZELF, en staat op de eerste regel. Een losse streepjesrand
    # als eerste regel is visueel onderscheidend maar zegt niets; wie de uitvoer afkapt of
    # alleen de eerste regel logt, ziet dan een rand en geen waarschuwing.
    if liggen:
        print(
            f"=== !! BLIJFT LIGGEN: {len(liggen)} goedgekeurde commit(s) staan niet op develop ==="
        )
        for sha, entry in liggen:
            print(f"     {sha[:12]}  goedgekeurd door {entry.get('by')}  op {entry['approved_at']}")
    if onbepaald:
        print(f"=== ?? NIET VAST TE STELLEN: {len(onbepaald)} goedkeuring(en) ===")
        print("     Dit is GEEN vastgestelde achterstand, maar ook geen schone uitslag.")
        for sha, entry, reden in onbepaald:
            wanneer = entry.get("approved_at", "(geen datum)")
            print(f"     {sha[:12]}  door {entry.get('by')}  op {wanneer}")
            print(f"                   reden: {reden}")
    gemeten = basis[:12] if basis else "(geen lokale origin/develop-ref)"
    print(f"   Gemeten tegen de LOKALE origin/develop: {gemeten}")
    print("   Is die verouderd, dan kan een gelande commit hier alsnog staan: git fetch origin.")
    print("=" * 78)


def cmd_whois(_args: argparse.Namespace) -> int:
    _toon_blijft_liggen()
    data = _read()
    coordinator = data.get("coordinator")
    if not coordinator:
        print("Geen regie-sessie ingesteld.")
        return 1
    print(f"Regie: {coordinator['session']} (ingesteld {coordinator['since']})")
    # Dit bestand overleeft een herstart van de machine, een sessienaam niet. Op 2026-09-14
    # stond hier een naam van twee dagen oud waarvan de sessie allang weg was; iedereen die
    # wilde pushen liep vast op een dode naam zonder dat iets dat meldde. Dit script kan
    # ListAgents niet aanroepen, dus het kan de vraag alleen STELLEN -- beantwoorden doet de
    # sessie die het commando draait. Zie CLAUDE.md, "Werken met meerdere sessies tegelijk".
    print(
        "CONTROLEER dit tegen ListAgents voordat je deze naam om goedkeuring vraagt.\n"
        "Staat de naam daar niet bij, dan is de sessie weg en is de regie vervallen:\n"
        "Rakesh wijst dan een nieuwe aan (dat is zijn keuze, niet iets dat een sessie\n"
        "zichzelf toe-eigent), waarna die sessie `set-coordinator` draait."
    )
    return 0


def cmd_set_coordinator(args: argparse.Namespace) -> int:
    with _locked():
        data = _read()
        data["coordinator"] = {
            "session": args.session,
            "since": datetime.now(timezone.utc).isoformat(),
        }
        _write(data)
    print(f"Regie ingesteld op: {args.session}")
    return 0


def _werkmap() -> str:
    """De werkmap van de AANROEPENDE sessie -- de identiteit die wel klopt.

    Een sessienaam is geen identiteit: bij een resume krijgt dezelfde sessie een andere
    naam (gemeten 2026-09-15: `org-93` kwam terug als `org-03`). De worktree waarin
    gewerkt wordt verandert niet. `claim_op.py` gebruikt sinds die meting dezelfde
    identiteit; dit script doet het daarom ook.
    """
    return str(Path.cwd().resolve())


def cmd_request(args: argparse.Namespace) -> int:
    """Meld je aan als AUTEUR van een commit, voordat je er goedkeuring voor vraagt.

    **Waarom dit bestaat (2026-09-18).** `approve` kon niet controleren of de goedkeurder
    iemand anders was dan de schrijver, om een simpele reden: er was geen enkel FEIT
    waaraan dat te zien was. Gemeten op die dag: een goedkeuringsrij bevatte alleen
    `{approved_at, by, note}`, en git kan de sessies niet onderscheiden -- elke commit in
    deze repo heeft dezelfde auteur (`toets <t@t.t>`). Zelf-goedkeuring was daarmee alleen
    met een afspraak tegen te houden, en die afspraak is op 2026-09-17/18 acht keer
    genegeerd door de enige sessie die er toen was.

    Dit commando legt het ontbrekende feit vast: welke sessie, vanuit welke werkmap, om
    goedkeuring vraagt voor deze sha. `approve` weigert daarna een goedkeurder met dezelfde
    naam of dezelfde werkmap.
    """
    sha = _resolve_sha(args.sha)
    with _locked():
        data = _read()
        data.setdefault("requested", {})[sha] = {
            "session": args.session,
            "worktree": _werkmap(),
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        _write(data)
    print(f"Goedkeuring aangevraagd voor {sha} door {args.session} ({_werkmap()})")
    print("Een ANDERE sessie keurt deze commit goed; je kunt dat niet zelf doen.")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    sha = _resolve_sha(args.sha)
    with _locked():
        data = _read()

        # Zelf-goedkeuring is geen goedkeuring (2026-09-18). De auto-mode-classifier
        # verwoordt het waarom in een zin: "Self-approval defeats the two-party review
        # requirement". Dit is de technische kant daarvan; de afspraak alleen bleek niet
        # genoeg. Zie `cmd_request` voor waarom het feit waarop dit rust eerst moest
        # ontstaan.
        aanvraag = data.get("requested", {}).get(sha)
        if aanvraag is None:
            print(f"GEWEIGERD: geen aanvraag bekend voor {sha}.")
            print("De schrijvende sessie draait eerst:")
            print(f"    python scripts/push_gate.py request --sha {sha} --session <naam>")
            print(
                "Zonder dat feit is niet vast te stellen WIE deze commit schreef, "
                "en kan deze controle niets afdwingen."
            )
            return 1
        # `--human` is de uitzondering voor een MENS die aan de permissieprompt goedkeurt.
        # Die prompt is de tweede partij: het commando draait weliswaar vanuit de werkmap
        # van de auteur, maar de toestemming komt van iemand anders. Zonder deze uitzondering
        # kan een enkele sessie helemaal niet meer pushen -- ook niet met Rakesh erbij -- en
        # dat zou de regel van een controle in een blokkade veranderen.
        # Let op: de aanvraag-eis hierboven blijft WEL gelden, zodat ook hier vastligt wie
        # de commit schreef.
        if not args.human and (
            args.by == aanvraag["session"] or _werkmap() == aanvraag["worktree"]
        ):
            print(
                f"GEWEIGERD: {args.by} is de auteur van {sha}, of keurt goed vanuit "
                f"dezelfde werkmap ({aanvraag['worktree']})."
            )
            print(
                "Een tweede handtekening van dezelfde hand is geen tweede handtekening. "
                "Vraag een ANDERE sessie, of -- als je de enige bent -- vraag Rakesh."
            )
            print(f"Aangevraagd door: {aanvraag['session']} op {aanvraag['requested_at']}")
            return 1

        data.setdefault("approved", {})[sha] = {
            "by": args.by,
            # De werkmap van de GOEDKEURDER, naast die van de aanvrager (SP-WF-001 dag 2).
            # De controle hierboven VERGELIJKT de twee en weigert bij gelijkheid, maar tot
            # 2026-09-19 werd alleen de naam bewaard. Het record toonde dus wie tekende,
            # niet dat die onafhankelijk was -- en dat laatste is wat de handtekening
            # geldig maakt. Bij `--human` is de werkmap bewust GELIJK aan die van de
            # auteur (het commando draait nu eenmaal daar); `by_human` zegt dan waarom.
            "worktree": _werkmap(),
            "authored_by": aanvraag["session"],
            "by_human": bool(args.human),
            "note": args.note or "",
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        _write(data)
    print(
        f"Goedgekeurd om te pushen: {sha} (door {args.by}, geschreven door {aanvraag['session']})"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    sha = _resolve_sha(args.sha[0])
    data = _read()
    entry = data.get("approved", {}).get(sha)
    if entry:
        print(f"GOEDGEKEURD: {sha} door {entry['by']} op {entry['approved_at']}")
        return 0
    print(f"NIET GOEDGEKEURD: {sha}")
    coordinator = data.get("coordinator")
    if coordinator:
        print(f"Vraag goedkeuring aan de regie-sessie: {coordinator['session']}")
    else:
        print("Geen regie-sessie ingesteld -- vraag Rakesh wie dat nu is.")
    return 1


def cmd_verify(_args: argparse.Namespace) -> int:
    """Staat op `origin/develop` wat er is goedgekeurd? Draai dit NA elke push.

    Waarom dit bestaat -- gemeten 2026-09-17, en het is geen theoretisch geval.

    `git push origin HEAD:develop` leest `HEAD` niet alleen bij het starten maar OPNIEUW
    bij het verzenden, en daartussen zit de pre-push hook met de volledige poort van elf
    minuten. Wie in die elf minuten committeert, duwt die commits mee. Gemeten verloop:

        14:21  push gestart, HEAD = 7108f721 (de goedgekeurde commit)
        14:23  poort draait op die inhoud
        14:34  poort GROEN
        14:38  commit 5fdaf315   <- binnen het venster
        14:40  commit e8d5ff12   <- binnen het venster
        14:46  push klaar; git meldt "4d61b292..7108f721"
               `git ls-remote origin develop` zegt e8d5ff12

    Twee commits stonden dus op `develop` zonder goedkeuring en zonder poort, terwijl de
    uitvoer van `git push` het tegendeel meldde. Die uitvoer is daarmee GEEN bewijs van wat
    er is geland; alleen de remote is dat.

    Twee dingen die dit voorkomen, en gebruik ze allebei:

    1. Push een EXPLICIETE sha in plaats van `HEAD`: `git push origin <sha>:develop`.
       Dan valt er niets opnieuw uit te lezen.
    2. Draai `push_gate.py verify` na afloop. Dit vergelijkt de remote met de
       goedkeuringen en meldt het verschil.
    """
    remote = subprocess.run(  # nosec B603 B607: vaste argumenten, geen invoer
        ["git", "ls-remote", "origin", "refs/heads/develop"],
        capture_output=True,
        text=True,
        check=False,
    )
    if remote.returncode != 0 or not remote.stdout.strip():
        print("Kan `origin/develop` niet uitlezen -- geen netwerk of geen remote.")
        print(remote.stderr.strip()[:300])
        return 1

    sha = remote.stdout.split()[0]
    entry = _read().get("approved", {}).get(sha)
    if entry:
        print(f"OK: origin/develop staat op {sha}, goedgekeurd door {entry['by']}")
        return 0

    print(f"NIET GOEDGEKEURD: origin/develop staat op {sha}, en die sha is nooit goedgekeurd.")
    print("Dit is precies het venster uit de docstring van `cmd_verify`: committeer je")
    print("terwijl een push loopt, dan gaan die commits mee zonder poort en zonder")
    print("goedkeuring. Draai de volledige poort ALSNOG op deze sha en meld het.")
    return 1


def _toon_geparkeerd(data: dict) -> None:
    """De aanvragen die op een handtekening wachten.

    **Waarom dit bestaat (2026-09-28, besluit Rakesh).** De afspraak is dat een sessie na
    het aanvragen van een pushgoedkeuring DRIE MINUTEN wacht en daarna doorgaat met de
    volgende taak. Anders staat een sessie uren stil omdat Rakesh er net niet is.

    Dat doorgaan mag alleen als de aanvraag ergens zichtbaar blijft. Gemeten op die dag:
    `status` toonde uitsluitend goedkeuringen (114 rijen), terwijl het bestand ook 56
    aanvragen bijhield. Een geparkeerde push was dus wel opgeslagen maar door niets te
    zien -- en parkeren zonder plek om het te onthouden is hetzelfde als vergeten.

    Een aanvraag telt als geparkeerd wanneer er geen goedkeuring bij staat EN de sha nog
    niet op `origin/develop` zit. Die tweede voorwaarde weert de aanvragen die allang
    geland zijn langs een andere weg; zonder die voorwaarde groeit deze lijst tot niemand
    hem meer leest, en dan is hij net zo blind als geen lijst.
    """
    aangevraagd = data.get("requested", {})
    goedgekeurd = data.get("approved", {})
    open_aanvragen = {
        sha: rij for sha, rij in aangevraagd.items() if sha not in goedgekeurd
    }
    if not open_aanvragen:
        return

    # Via `_landingsstatussen` en niet met twee git-aanroepen per sha. Die vorm is hier al
    # een keer gemeten: 83 shas gaven 167 subprocessen en 14 seconden op een commando dat
    # in de openingsronde van elke sessie staat. True = geland, False = nog niet,
    # None = geen uitspraak (sha bestaat hier niet, of er is geen basis).
    basis = _lokale_develop()
    statussen = _landingsstatussen(sorted(open_aanvragen), basis)
    lege_merges = _merges_zonder_eigen_inhoud(
        [sha for sha in open_aanvragen if statussen.get(sha) is False], basis
    )
    geparkeerd = [
        (sha, rij)
        for sha, rij in open_aanvragen.items()
        if statussen.get(sha) is False and sha not in lege_merges
    ]
    onbepaald = [(sha, rij) for sha, rij in open_aanvragen.items() if statussen.get(sha) is None]

    def _op_datum(kv: tuple[str, dict]) -> str:
        return str(kv[1].get("requested_at", ""))

    if geparkeerd:
        print("=== GEPARKEERD: wacht op een handtekening ===")
        for sha, rij in sorted(geparkeerd, key=_op_datum):
            print(
                f"  {sha[:12]}  aangevraagd door {rij.get('session', '?')}  "
                f"op {rij.get('requested_at', '?')}  ({_leeftijd(rij.get('requested_at'))})"
            )
        print("     Een ANDERE sessie tekent, of Rakesh met --human.")
        print("=" * 78)
    if onbepaald:
        # Een sha die hier niet te vinden is, is geen geland commit en geen vastgestelde
        # achterstand. Stil weglaten zou een echte geparkeerde push onzichtbaar maken.
        print(f"=== ?? NIET VAST TE STELLEN: {len(onbepaald)} aanvraag/aanvragen ===")
        print("     Sha niet lokaal te vinden (of geen origin/develop-ref): git fetch origin.")
        for sha, rij in sorted(onbepaald, key=_op_datum):
            print(
                f"  {sha[:12]}  aangevraagd door {rij.get('session', '?')}  "
                f"op {rij.get('requested_at', '?')}  ({_leeftijd(rij.get('requested_at'))})"
            )
        print("=" * 78)


def _leeftijd(rauw: object) -> str:
    """Leeftijd van een aanvraag in gewone woorden; '?' bij een onleesbare datum."""
    try:
        wanneer = datetime.fromisoformat(str(rauw))
    except ValueError:
        return "leeftijd onbekend"
    if wanneer.tzinfo is None:
        wanneer = wanneer.replace(tzinfo=timezone.utc)
    minuten = int((datetime.now(timezone.utc) - wanneer).total_seconds() // 60)
    if minuten < 60:
        return f"{max(minuten, 0)} min oud"
    if minuten < 60 * 48:
        return f"{minuten // 60} uur oud"
    return f"{minuten // (60 * 24)} dagen oud"


def _merges_zonder_eigen_inhoud(shas: list[str], basis: str | None) -> set[str]:
    """De shas die een merge zijn zonder eigen inhoud: alle ouders geland en lege diff.

    Een merge van twee gelande lijnen is zelf geen voorouder van develop, maar brengt ook
    niets nieuws. Gemeten 2026-10-01 op cc3bfa3a: `merge-base --is-ancestor` gaf 1 terwijl
    `git diff --stat origin/develop...cc3bfa3a` leeg was. Bereikbaarheid alleen hield zo'n
    aanvraag eeuwig in de wachtrij.

    Alleen aangeroepen voor shas die al als "niet bereikbaar" zijn vastgesteld; gewone
    commits kosten hier dus een enkele `rev-list`.
    """
    if basis is None:
        return set()
    leeg: set[str] = set()
    for sha in shas:
        ouders = subprocess.run(  # nosec B603 B607: vaste argumenten, sha uit ons eigen bestand
            ["git", "rev-list", "--parents", "-n", "1", sha],
            capture_output=True,
            text=True,
            check=False,
        )
        delen = ouders.stdout.split()
        if ouders.returncode != 0 or len(delen) < 3:
            continue  # geen merge (of niet te lezen): bereikbaarheid is het enige criterium
        ouder_status = _landingsstatussen(delen[1:], basis)
        if not all(ouder_status.get(o) is True for o in delen[1:]):
            continue
        verschil = subprocess.run(  # nosec B603 B607: vaste argumenten, sha uit ons eigen bestand
            ["git", "diff", "--quiet", f"{basis}...{sha}"],
            capture_output=True,
            check=False,
        )
        if verschil.returncode == 0:
            leeg.add(sha)
    return leeg


def cmd_wachtrij(_args: argparse.Namespace) -> int:
    """Alleen de geparkeerde aanvragen; voor de sessiestart (snel, geen goedkeuringenlijst)."""
    _toon_geparkeerd(_read())
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    _toon_blijft_liggen()
    data = _read()
    _toon_geparkeerd(data)
    coordinator = data.get("coordinator")
    print(f"Regie: {coordinator['session'] if coordinator else '(niet ingesteld)'}")
    approved = data.get("approved", {})
    if not approved:
        print("Geen goedgekeurde commits.")
        return 0
    for sha, entry in sorted(approved.items(), key=lambda kv: kv[1]["approved_at"]):
        print(
            f"  {sha[:12]}  door {entry['by']}  op {entry['approved_at']}  {entry.get('note', '')}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_whois = sub.add_parser("whois", help="Wie is de huidige regie-sessie?")
    p_whois.set_defaults(func=cmd_whois)

    p_set = sub.add_parser("set-coordinator", help="Wijs de regie-sessie aan")
    p_set.add_argument("--session", required=True)
    p_set.set_defaults(func=cmd_set_coordinator)

    p_approve = sub.add_parser("approve", help="Keur een commit goed om te pushen")
    p_approve.add_argument("--sha", required=True)
    p_approve.add_argument("--by", required=True)
    p_approve.add_argument("--note")
    p_approve.add_argument(
        "--human",
        action="store_true",
        help="Een MENS keurt goed aan de permissieprompt; dan telt de werkmap niet mee",
    )
    p_approve.set_defaults(func=cmd_approve)

    p_request = sub.add_parser(
        "request", help="Meld je aan als AUTEUR van een commit (verplicht voor approve)"
    )
    p_request.add_argument("--sha", required=True)
    p_request.add_argument("--session", required=True)
    p_request.set_defaults(func=cmd_request)

    p_check = sub.add_parser("check", help="Is deze commit goedgekeurd?")
    p_check.add_argument("sha", nargs=1)
    p_check.set_defaults(func=cmd_check)

    p_verify = sub.add_parser(
        "verify", help="Staat op origin/develop wat er is goedgekeurd? Draai dit NA elke push"
    )
    p_verify.set_defaults(func=cmd_verify)

    p_wachtrij = sub.add_parser(
        "wachtrij", help="Alleen de aanvragen die op een handtekening wachten (sessiestart)"
    )
    p_wachtrij.set_defaults(func=cmd_wachtrij)

    p_status = sub.add_parser("status", help="Toon regie + alle goedkeuringen")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
