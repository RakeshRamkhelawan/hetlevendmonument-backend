"""Het open-punten-register van ADR-036 moet machinaal na te lezen zijn.

Aanleiding (SP-OP-TRIAGE-001, 2026-08-14). Paragraaf 10 van ADR-036 telt 135 rijen en is de
enige planbron voor de rest van die ADR. De status van een rij stond in vrije tekst: 62
rijen begonnen met "GESLOTEN", 18 met "OPEN", en 50 met een gewone zin waaruit de status
alleen door lezen bleek. Gevolg, gemeten: een parse telde 60 open punten terwijl OP-33,
OP-43, OP-128 en OP-129 in hun eigen tekst al gesloten waren, en OP-64 en OP-65 hadden een
omschrijvingskolom die "gesloten" zei naast een statuskolom die "OPEN -- BLOKKEREND" zei.
Er is toen werk ingepland op cijfers die niet klopten.

Deze guard dwingt drie dingen af:

1. elke rij draagt STATUS= uit een vaste woordenlijst;
2. het bewijs bij die status is machinaal te controleren -- geen vrije tekst;
3. paden die in het BEWIJS-veld staan bestaan nog.

Punt 3 kijkt bewust alleen naar het bewijsveld en niet naar de hele rij. Gemeten
2026-08-14: over de hele rij leverde dat 113 meldingen op, en na het uitfilteren van kale
bestandsnamen en verkorte paden nog 4 -- waarvan er een (OP-18) een pad noemt dat het
VOORSTELT aan te maken (`tests/unit/conftest.py`). Een guard die voorstellen als kapotte
verwijzingen meldt, leert je hem te negeren.

Waarom punt 2 zo streng is: een guard die alleen eist DAT er iets in BEWIJS= staat, is
tevreden met "BEWIJS=ja". Dan meet hij vorm in plaats van waarheid, en dat is precies het
patroon dat in deze ADR tien keer is misgegaan (tekst doorzoeken waar structuur getoetst
moet worden). Daarom zijn er vier toegestane bewijsvormen die deze test zelf naloopt: een
pytest node-id, een bestaand testbestand dat het OP-nummer noemt, een commit-hash die echt in
de objectdatabase zit, en een pad:regel dat bestaat. Een commando telt alleen voor een OPEN
rij, nooit voor een sluiting.

MUTATIE-BEWIJS (daadwerkelijk uitgevoerd 2026-08-14, een regel per bewaakt element):

Een regel per bewaakt element, en per status uit VALID_STATUSES.

| Mutatie | Element | Uitkomst |
| --- | --- | --- |
| STATUS= weggehaald bij OP-100 | status aanwezig | ROOD |
| GEVERIFIEERD= weggehaald bij een GESLOTEN-rij | datum aanwezig | ROOD |
| BEWIJS= weggehaald bij OP-100 | bewijs aanwezig | ROOD |
| hash van OP-23 (`396a0eb4`) vervangen door `deadbee1234` | GESLOTEN via hash | ROOD |
| testpad van OP-100 vervangen door een niet-bestaand bestand | GESLOTEN via test | ROOD |
| bewijs van OP-84 -> `tests/architecture/test_no_naive_datetime.py` (bestaat, noemt OP-84 niet) | GESLOTEN moet OVER de bevinding gaan | ROOD (was GROEN voor de review van 2026-08-14) |
| markertekst van een ONGEVERIFIEERD-rij vervangen door "komt nog" | ONGEVERIFIEERD-marker | ROOD |
| het woord ONGEVERIFIEERD in de proza van een OPEN-rij | plafond telt de STATUS, niet de tekst | GROEN (was ROOD: vals positief, gemeld door de review) |
| een extra rij op ONGEVERIFIEERD (95 tegen plafond 94) | plafond | ROOD |
| OP-nummer uit het bewijsveld van de DUPLICAAT-rij | DUPLICAAT | ROOD |
| verzonnen pad in het bewijsveld van OP-100 | paden bestaan | ROOD |
| TEGENRICHTING: ongemuteerd register | alle zes tests | GROEN |

Twee keer leek een mutatie GROEN terwijl de guard niets mankeerde; beide keren deugde de
MUTATIE niet. Eerst de hash-mutatie: OP-100 droeg een testpad als bewijs en geen hash, dus de
vervanging greep nergens op aan. Daarna de ongerelateerd-testbestand-mutatie: als vervanger
koos ik DIT bestand, en de tabel hierboven noemt "OP-84" -- waardoor het bestand aan de eis
voldeed die het moest breken. Een mutatie die niets verandert bewijst niets, en een mutatie
die per ongeluk aan de eis voldoet ook niet. Controleer altijd dat de regel daadwerkelijk
anders is (`assert regel != voor`) EN dat de vervanger niet toevallig aan de eis voldoet.

De uitzonderingslijst KNOWN_UNPROVEN_CLOSURES is voor rijen die aantoonbaar gesloten zijn
maar waarvan het bewijs niet meer te reconstrueren is. Die lijst heeft een reden per regel
en een staleness-test, volgens het patroon van
tests/architecture/test_audit_chain_verification_backlog.py.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Gesplitst op 2026-09-19 (instructie Rakesh): het register staat sindsdien in TWEE bestanden.
# ADR-036 houdt zijn eigen open rijen; al het afgeronde werk en alles wat niet over de
# agentlaag gaat, staat in het tweede bestand. BEIDE moeten machinaal na te lezen blijven --
# anders verplaatst een splitsing het probleem in plaats van het op te lossen, en dat is
# precies de vorm waar deze guard voor bestaat.
ADR = REPO_ROOT / "docs" / "adr" / "036-agentic-organizational-hierarchy-governance-reuse.md"
OVERIG = REPO_ROOT / "docs" / "adr" / "036-REGISTER-OVERIG-EN-AFGEROND.md"
REGISTERS = (ADR, OVERIG)

VALID_STATUSES = ("GESLOTEN", "OPEN", "DUPLICAAT", "ONGEVERIFIEERD")

#: Precies deze tekst hoort achter BEWIJS= bij een ONGEVERIFIEERD-rij. Een vrije toelichting
#: zou de rij laten lijken op iets dat is nagekeken.
UNVERIFIED_MARKER = "niet nagemeten in SP-OP-TRIAGE-001"

#: Zoveel rijen mogen nog op STATUS=ONGEVERIFIEERD staan. Dit getal mag alleen OMLAAG. Wie een
#: rij nameet, verlaagt het; wie een rij toevoegt zonder hem na te meten, loopt hier vast.
#: Zonder dit plafond is ONGEVERIFIEERD een gratis uitweg en meet de guard niets meer.
#: 2026-08-14: 80. 2026-08-31: 0 -- de laatste 74 zijn nagemeten, zie
#: docs/reports/ADR-036_NAMETING_74_RIJEN_2026-08-31.md. Vanaf hier is elke nieuwe rij op
#: ONGEVERIFIEERD een harde fout, want er is geen achterstand meer om achter te schuilen.
MAX_UNVERIFIED = 0

ROW = re.compile(r"^\|\s*(OP-\d+)\s*\|")
STATUS_FIELD = re.compile(r"\bSTATUS=([A-Z-]+)")
VERIFIED_FIELD = re.compile(r"\bGEVERIFIEERD=(\d{4}-\d{2}-\d{2})")
EVIDENCE_FIELD = re.compile(r"\bBEWIJS=(.+?)(?:\s+--\s|\s*\|$|$)")

HASH = re.compile(r"\b([0-9a-f]{7,40})\b")
NODE_ID = re.compile(r"(tests/[\w/]+\.py)::(\w+)")
PATH_LINE = re.compile(r"([\w./-]+\.(?:py|md|yml|yaml|bicep|ts|tsx|sh)):(\d+)")
# Alleen paden MET een map ervoor. Een kale bestandsnaam (`hybrid_search.py`) is in deze
# ADR een verwijzing in lopende tekst, geen repo-pad; die als pad behandelen leverde 113
# valse meldingen op (gemeten 2026-08-14, tegenrichting van de mutatietest).
BACKTICK_PATH = re.compile(r"`([\w.-]+(?:/[\w.-]+)+\.(?:py|yml|yaml|bicep|sh))`")
# Een commando telt alleen als bewijs met minstens een argument erachter. Zonder die eis is
# "BEWIJS=git" genoeg om deze guard te bevredigen, en dan meet hij een woord in plaats van
# een handeling.
COMMAND = re.compile(r"\b(git|pytest|python|az|docker|grep|awk|alembic|npm)\s+\S+")
# Een bestaand testbestand zonder functienaam is zwakker bewijs dan een node-id, maar nog
# steeds machinaal te controleren: het bestand bestaat en bevat minstens een test.
TEST_FILE = re.compile(r"\b(tests/[\w/.-]+\.py)\b")

# Rijen die aantoonbaar gesloten zijn maar waarvan het bewijs niet meer te reconstrueren
# is. Reden per regel, gedateerd. De staleness-test hieronder haalt een regel weg zodra hij
# alsnog bewijs draagt.
KNOWN_UNPROVEN_CLOSURES: dict[str, str] = {
    "OP-237": (
        "2026-09-11: de sluiting rust op een wijziging in `.git/config` (`core.bare` van "
        "`true` naar `false`), en git-config staat niet in versiebeheer. Er is dus geen "
        "commit die dit repareert en geen test die het kan vastleggen -- alleen meten. "
        "Gemeten in dezelfde worktree voor en na: `git rev-parse --is-inside-work-tree` ging "
        "van `false` naar `true`, `git grep` van rc=128 naar treffers, en de drie zwaarst "
        "getroffen guardbestanden van rood naar 15 passed. Wie de instelling heeft omgezet "
        "is niet vast te stellen."
    ),
    "OP-11": (
        "2026-08-14: `pytest tests/integration` tegen een echte backend geeft 1759 passed / "
        "0 failed / 177 skipped in 911s. De 34 failures uit de rij (meting 2026-07-31) zijn "
        "weg. WELKE commits ze wegnamen is niet vastgesteld."
    ),
    "OP-140": (
        "2026-08-31: de sluiting rust op een EENMALIGE meting tegen een live database -- 109 "
        "revisies volledig uitgevoerd tegen een verse Azure PostgreSQL 16 (2026-08-27) en "
        "`alembic check` erna (2026-08-30). Daar hoort geen commit bij, want er is niets "
        "gerepareerd: er is gemeten. Reproduceren vraagt opnieuw een database, en dat is geen "
        "bewijsvorm die deze guard kent. De kant die WEL open bleef (schema-gelijkheid met "
        "Base.metadata: 516 verschillen) staat onder OP-150. Deze rij kwam pas boven toen de "
        "guard op 2026-08-31 de LAATSTE STATUS ging lezen in plaats van de eerste; daarvoor "
        "gold ze als OPEN en werd haar bewijs nooit op sluitingsstrengheid getoetst."
    ),
    "OP-57": (
        "2026-08-14: `python -m pyright` geeft 0 errors / 54 warnings, dus de 6 fouten uit "
        "de rij zijn niet meer te reproduceren. WELKE commit ze wegnam is niet vastgesteld: "
        "er is sinds 2026-08-05 niets aan `pyright-baseline.json` of `security_manager.py` "
        "gewijzigd. Sluiting dus gemeten, oorzaak niet."
    ),
}

# Paden die in een rij genoemd worden maar bewust niet meer bestaan (bijv. een module die
# is verwijderd, en dat verwijderen IS de sluiting). Reden per regel.
KNOWN_REMOVED_PATHS: dict[str, str] = {
    "src/core/workflow/worker_simple.py": (
        "verwijderd in AUDIT-DB01 S7 -- het verwijderen zelf is de sluiting (2026-07-02)"
    ),
}


def _rows() -> list[tuple[int, str, str]]:
    """(regelnummer, OP-id, volledige regel) voor elke registerrij."""
    rows = []
    regels: list[str] = []
    for pad in REGISTERS:
        regels.extend(pad.read_text(encoding="utf-8").splitlines())
    for number, line in enumerate(regels, start=1):
        match = ROW.match(line)
        if match:
            rows.append((number, match.group(1), line))
    return rows


def _status(line: str) -> str | None:
    """De GELDENDE status van een rij: de LAATSTE `STATUS=`-waarde.

    De leeswijzer boven het register schrijft dit al sinds 2026-08-14 voor -- de derde
    kolom is append-only, dus een latere meting staat ACHTER een eerdere en vervangt hem.
    Deze functie las tot 2026-08-31 de EERSTE waarde, en dat verschil was niet theoretisch:
    OP-24, OP-64, OP-140 en OP-164 dragen allevier eerst `STATUS=OPEN` en daarna
    `STATUS=GESLOTEN`. De guard hield ze dus voor open, en sloeg daarmee precies de strengste
    controle over die er is (`_closure_evidence_is_strong` draait alleen op GESLOTEN). Het
    verschil zat dus in de PERMISSIEVE richting: vier sluitingen zijn nooit op hun bewijs
    getoetst. Bij het rechttrekken bleek OP-64 een verkort pad te dragen dat de guard niet
    kon vinden, en OP-140 een sluiting die op een eenmalige meting tegen een live database
    rust -- die staat nu met reden in KNOWN_UNPROVEN_CLOSURES.
    """
    matches = STATUS_FIELD.findall(line)
    return matches[-1] if matches else None


def _evidence(line: str) -> str | None:
    """Het GELDENDE bewijs van een rij: het LAATSTE `BEWIJS=`-veld, om dezelfde reden."""
    matches = [match.group(1) for match in EVIDENCE_FIELD.finditer(line)]
    return matches[-1] if matches else None


def _existing_objects(hashes: set[str]) -> set[str]:
    """Welke van deze hashes bestaan in de git-objectdatabase (een aanroep, niet N)."""
    if not hashes:
        return set()
    payload = "\n".join(sorted(hashes)) + "\n"
    result = subprocess.run(
        ["git", "cat-file", "--batch-check"],
        cwd=REPO_ROOT,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "git cat-file gaf returncode %s -- deze guard kan zonder git niets bewijzen: %s"
            % (result.returncode, result.stderr.strip())
        )
    found = set()
    for asked, answer in zip(sorted(hashes), result.stdout.splitlines()):
        if " missing" not in answer:
            found.add(asked)
    return found


def _evidence_is_checkable(evidence: str, known_objects: set[str]) -> str | None:
    """None als het bewijs klopt, anders de reden waarom niet."""
    node = NODE_ID.search(evidence)
    if node:
        test_file = REPO_ROOT / node.group(1)
        if not test_file.exists():
            return "testbestand %s bestaat niet" % node.group(1)
        if ("def %s" % node.group(2)) not in test_file.read_text(encoding="utf-8"):
            return "testbestand %s bevat geen %s" % (node.group(1), node.group(2))
        return None

    path_line = PATH_LINE.search(evidence)
    if path_line:
        target = REPO_ROOT / path_line.group(1)
        if not target.exists():
            return "pad %s bestaat niet" % path_line.group(1)
        line_count = len(target.read_text(encoding="utf-8", errors="ignore").splitlines())
        if int(path_line.group(2)) > line_count:
            return "%s heeft maar %d regels" % (path_line.group(1), line_count)
        return None

    test_file = TEST_FILE.search(evidence)
    if test_file:
        target = REPO_ROOT / test_file.group(1)
        if not target.exists():
            return "testbestand %s bestaat niet" % test_file.group(1)
        if "def test_" not in target.read_text(encoding="utf-8", errors="ignore"):
            return "%s bevat geen enkele test" % test_file.group(1)
        return None

    for candidate in HASH.findall(evidence):
        if candidate in known_objects:
            return None
    if HASH.search(evidence):
        return "genoemde hash bestaat niet in de objectdatabase"

    if COMMAND.search(evidence):
        return None

    return "geen node-id, geen bestaande hash, geen pad:regel en geen commando"


def _file_fingerprint() -> str:
    """Wat deze test daadwerkelijk heeft ingelezen.

    Aanleiding: op 2026-08-14 viel deze guard EEN keer om in een volledige suite-run en
    daarna nooit meer, ook niet in twee identiek geordende runs (pytest-randomly is hier
    niet eens geinstalleerd, dus de volgorde was alle keren gelijk). De melding stond onder
    `--tb=line` en was daarmee weg: geen bestandsgrootte, geen rijaantal, geen enkele
    aanwijzing. Zonder die gegevens is een herhaling opnieuw niet te duiden. Daarom horen ze
    voortaan in de melding zelf.
    """
    try:
        stat = ADR.stat()
        return "gelezen bestand: %s, %d bytes, mtime %d, %d registerrijen gevonden" % (
            ADR,
            stat.st_size,
            int(stat.st_mtime),
            len(_rows()),
        )
    except OSError as error:  # pragma: no cover -- alleen bij een onleesbaar bestand
        return "bestand niet leesbaar: %s" % error


def _closure_evidence_is_strong(evidence: str, op_id: str, known_objects: set[str]) -> bool:
    """Bewijs dat een SLUITING draagt, en dat aantoonbaar OVER DEZE bevinding gaat.

    Een commando telt hier bewust niet. "Ik heb het gedraaid en zag niets" bewijst dat het
    gat vandaag niet zichtbaar is, niet dat het dicht is gemaakt en dicht blijft.

    Een kaal testbestand telde eerder wel, en dat was een gat: de blinde review van
    2026-08-14 zette bij OP-84 een volstrekt ongerelateerd testbestand neer en de guard bleef
    GROEN. Veertien van de vijfendertig GESLOTEN-rijen rustten daarop. Een testbestand telt nu
    alleen als het OP-nummer erin voorkomt -- dan is er een aantoonbare band tussen de test en
    de bevinding, en niet alleen tussen de test en de mappenstructuur.
    """
    if any(h in known_objects for h in HASH.findall(evidence)):
        return True
    node = NODE_ID.search(evidence)
    if node:
        target = REPO_ROOT / node.group(1)
        return target.exists() and op_id in target.read_text(encoding="utf-8", errors="ignore")
    bare = TEST_FILE.search(evidence)
    if bare:
        target = REPO_ROOT / bare.group(1)
        return target.exists() and op_id in target.read_text(encoding="utf-8", errors="ignore")
    return False


def test_geen_enkele_registerrij_is_over_meerdere_regels_gebroken() -> None:
    """Een registerrij staat op EEN regel -- anders leest de helft als losse tekst.

    **Waarom deze toets bestaat.** Op 2026-09-16 heb ik zelf een rij gebroken door er tekst
    met echte regeleinden in te zetten (een codeblokje in de toelichting bij OP-151). De
    markdown-tabel viel daarmee uiteen: `| OP-151 | ...` eindigde niet meer op een `|`, en de
    rest van de toelichting stond als losse alinea's onder de tabel.

    Geen van de bestaande toetsen in dit bestand merkte dat, en dat is het gevaarlijke deel:
    `_rows()` pakt alleen regels die met `| OP-NNN |` beginnen, dus alles achter de breuk --
    inclusief het `STATUS=`-veld dat de GELDENDE status bepaalt -- valt stil buiten beeld. Een
    rij kan daardoor als OPEN blijven lezen terwijl hij gesloten is, of andersom, en de hele
    open-telling van dit project hangt aan dat veld.

    Rood te maken door in een rij een echte newline te zetten.
    """
    regels = ADR.read_text(encoding="utf-8").splitlines()
    gebroken = [
        (nummer, regel[:80])
        for nummer, regel in enumerate(regels, start=1)
        if ROW.match(regel) and not regel.rstrip().endswith("|")
    ]
    assert not gebroken, (
        "Deze registerrijen lopen door op de volgende regel:"
        + "".join(chr(10) + f"  regel {n}: {t}..." for n, t in gebroken)
        + chr(10) * 2
        + "Een rij hoort op EEN regel te staan en op `|` te eindigen. Alles achter de breuk "
        "valt buiten `_rows()`, dus ook het `STATUS=`-veld dat de geldende status bepaalt."
    )


def test_every_row_has_a_status_from_the_vocabulary() -> None:
    """Elke rij draagt STATUS= uit de woordenlijst plus een verificatiedatum.

    Rood te maken door STATUS= bij een rij weg te halen.
    """
    missing_status = []
    wrong_value = []
    missing_date = []
    for number, op_id, line in _rows():
        status = _status(line)
        if not status:
            missing_status.append("%s (regel %d)" % (op_id, number))
            continue
        if status not in VALID_STATUSES:
            wrong_value.append("%s heeft STATUS=%s" % (op_id, status))
        # ONGEVERIFIEERD draagt met opzet GEEN datum: een verificatiedatum bij een rij die
        # niet is nagemeten, beweert een controle die niet heeft plaatsgevonden.
        if status != "ONGEVERIFIEERD" and not VERIFIED_FIELD.search(line):
            missing_date.append("%s (regel %d)" % (op_id, number))

    problems = []
    if missing_status:
        problems.append("zonder STATUS= (%d): %s" % (len(missing_status), missing_status))
    if wrong_value:
        problems.append("STATUS buiten de woordenlijst: %s" % wrong_value)
    if missing_date:
        problems.append("zonder GEVERIFIEERD= (%d): %s" % (len(missing_date), missing_date))

    assert not problems, (
        "ADR-036 par. 10 is niet machinaal te lezen. Toegestaan: %s. Zie SP-OP-TRIAGE-001.\n"
        "%s\n%s" % (", ".join(VALID_STATUSES), "\n".join(problems), _file_fingerprint())
    )


def test_every_row_has_machine_checkable_evidence() -> None:
    """Het bewijsveld is een node-id, een bestaande commit-hash of een pad:regel.

    Rood te maken door BEWIJS= weg te halen, of door er een verzonnen hash of testnaam in
    te zetten. Vrije tekst als bewijs is bewust niet toegestaan: een guard die alleen eist
    DAT er iets staat, is tevreden met "BEWIJS=ja".
    """
    rows = _rows()
    hashes = {h for _, _, line in rows for h in HASH.findall(line)}
    known_objects = _existing_objects(hashes)

    problems = []
    for number, op_id, line in rows:
        value = _status(line)
        if not value:
            continue  # de andere test meldt dit al

        if value == "ONGEVERIFIEERD":
            marker_field = _evidence(line)
            if marker_field is None or marker_field.strip() != UNVERIFIED_MARKER:
                problems.append(
                    "%s (regel %d): ONGEVERIFIEERD hoort exact 'BEWIJS=%s' te dragen"
                    % (op_id, number, UNVERIFIED_MARKER)
                )
            continue

        if value == "DUPLICAAT":
            dup_field = _evidence(line)
            if dup_field is None or not re.search(r"OP-\d+", dup_field):
                problems.append("%s (regel %d): DUPLICAAT zonder OP-nummer" % (op_id, number))
            continue

        if value == "BESLISSING-RAKESH":
            if "?" not in line:
                problems.append(
                    "%s (regel %d): BESLISSING-RAKESH zonder de vraag die beantwoord moet worden"
                    % (op_id, number)
                )
            continue

        if op_id in KNOWN_UNPROVEN_CLOSURES:
            continue

        evidence = _evidence(line)
        if evidence is None:
            problems.append("%s (regel %d): geen BEWIJS=" % (op_id, number))
            continue

        reason = _evidence_is_checkable(evidence, known_objects)
        if reason:
            problems.append("%s (regel %d): %s" % (op_id, number, reason))
            continue

        # Een commando is genoeg bewijs voor OPEN ("ik heb dit gedraaid en het gat is er
        # nog"), maar niet voor GESLOTEN. Een sluiting die niemand kan terugvinden in de
        # geschiedenis is geen sluiting; die hoort met reden in KNOWN_UNPROVEN_CLOSURES.
        if value == "GESLOTEN" and not _closure_evidence_is_strong(evidence, op_id, known_objects):
            problems.append(
                "%s (regel %d): GESLOTEN zonder commit-hash of test -- zet hem met reden in "
                "KNOWN_UNPROVEN_CLOSURES" % (op_id, number)
            )

    assert not problems, "Bewijsvelden in ADR-036 par. 10 zijn niet te controleren (%d):\n%s" % (
        len(problems),
        "\n".join(problems),
    )


def test_referenced_paths_still_exist() -> None:
    """Een rij die naar een verdwenen bestand wijst, is niet meer na te meten.

    Rood te maken door een verzonnen pad tussen backticks in een rij te zetten.
    """
    dangling = []
    for number, op_id, line in _rows():
        evidence = _evidence(line)
        if evidence is None:
            continue
        for path in BACKTICK_PATH.findall(evidence):
            if path in KNOWN_REMOVED_PATHS:
                continue
            # De ADR schrijft paden vaak verkort ("tool_broker/service.py" voor
            # "src/core/tool_broker/service.py"). Die verkorting is geen fout; alleen een
            # pad dat onder GEEN van deze wortels bestaat is echt verdwenen.
            if not any((REPO_ROOT / prefix / path).exists() for prefix in ("", "src/core", "src")):
                dangling.append("%s (regel %d) noemt %s" % (op_id, number, path))

    assert not dangling, "Deze rijen verwijzen naar bestanden die niet meer bestaan (%d):\n%s" % (
        len(dangling),
        "\n".join(dangling),
    )


def test_unverified_rows_do_not_grow() -> None:
    """Het aantal nog-niet-nagemeten rijen mag alleen omlaag.

    Rood te maken door een rij op ONGEVERIFIEERD te zetten zonder MAX_UNVERIFIED te
    verlagen -- of, andersom, door rijen na te meten zonder het plafond mee te laten
    zakken (dan meldt deze test dat het plafond te ruim staat).
    """
    # De STATUS-WAARDE telt, niet het voorkomen van het woord ergens in de rij. Dat was tot
    # 2026-08-31 anders, en dat was een fout: de mutatietabel hierboven noteert al sinds
    # 2026-08-14 dat "het woord ONGEVERIFIEERD in de proza van een OPEN-rij" GROEN hoort te
    # geven, maar de code telde die rij toch mee. Gemeten op 2026-08-31: OP-20 en OP-146
    # noemen het woord in hun toelichting terwijl ze allebei STATUS=OPEN dragen; met de oude
    # telling zou het plafond nooit onder 2 kunnen zakken zonder die toelichtingen te
    # verminken.
    unverified = [op_id for _, op_id, line in _rows() if _status(line) == "ONGEVERIFIEERD"]
    assert len(unverified) <= MAX_UNVERIFIED, (
        "Er zijn %d ONGEVERIFIEERD-rijen, het plafond staat op %d. Een rij toevoegen zonder "
        "hem na te meten mag niet: %s" % (len(unverified), MAX_UNVERIFIED, sorted(unverified))
    )
    assert len(unverified) >= MAX_UNVERIFIED - 5, (
        "Er zijn nog maar %d ONGEVERIFIEERD-rijen terwijl het plafond op %d staat. Verlaag "
        "MAX_UNVERIFIED naar %d, anders zakt de druk weg."
        % (len(unverified), MAX_UNVERIFIED, len(unverified))
    )


def test_known_unproven_closures_is_not_stale() -> None:
    """Een uitzondering die alsnog bewijs draagt, MOET uit de lijst.

    Zonder deze test rot de uitzonderingslijst dicht en dekt hij op den duur rijen die al
    lang in orde zijn.
    """
    rows = {op_id: line for _, op_id, line in _rows()}
    hashes = {h for line in rows.values() for h in HASH.findall(line)}
    known_objects = _existing_objects(hashes)

    stale = []
    for op_id, reason in KNOWN_UNPROVEN_CLOSURES.items():
        line = rows.get(op_id)
        if line is None:
            stale.append("%s staat niet meer in het register (%s)" % (op_id, reason))
            continue
        evidence = _evidence(line)
        # Dezelfde strengheid als de GESLOTEN-regel: een commando is hier GEEN bewijs, want
        # dat is nu juist waarom de rij op deze lijst staat.
        if evidence is not None and _closure_evidence_is_strong(evidence, op_id, known_objects):
            stale.append("%s draagt nu wel een commit-hash of test" % op_id)

    assert not stale, "Haal deze uitzonderingen uit KNOWN_UNPROVEN_CLOSURES:\n%s" % "\n".join(stale)


def test_known_removed_paths_is_not_stale() -> None:
    """Een pad dat weer bestaat, hoort niet meer in KNOWN_REMOVED_PATHS."""
    resurrected = [p for p in KNOWN_REMOVED_PATHS if (REPO_ROOT / p).exists()]
    assert not resurrected, (
        "Deze paden bestaan weer en horen niet meer in de uitzonderingslijst: %s" % resurrected
    )


# ============================================================================
# Prioriteit -- een expliciet veld, want lopende tekst noemt prioriteiten
# ============================================================================

PRIO_FIELD = re.compile(r"\bPRIO=(P0|P1|P2|P3|ONBEPAALD)")

#: Rijen die NOOIT een prioriteit hebben gekregen. Gedateerd 2026-09-18; dit zijn de oudste
#: registerrijen, van voor het moment dat `Fase X, Pn` de gewoonte werd.
#:
#: Deze lijst mag alleen KRIMPEN. Hij staat er niet om het gat te vergoelijken maar om het
#: zichtbaar te houden: zolang een rij hier staat, weet niemand hoe zwaar hij weegt, en dan
#: geeft het register die werkelijkheid ook zo weer in plaats van een prioriteit te
#: suggereren die nooit is bepaald.
KNOWN_ZONDER_PRIORITEIT: frozenset[str] = frozenset(
    {
        "OP-01", "OP-02", "OP-03", "OP-04", "OP-05", "OP-06", "OP-07", "OP-08",
        "OP-10", "OP-11", "OP-12", "OP-13", "OP-14", "OP-15", "OP-16", "OP-19", "OP-21",
        "OP-22", "OP-23", "OP-24", "OP-25", "OP-26", "OP-30", "OP-31", "OP-32", "OP-35",
        "OP-39", "OP-45", "OP-121", "OP-173", "OP-178", "OP-226", "OP-238", "OP-239",
        "OP-240", "OP-241", "OP-242", "OP-243", "OP-244", "OP-245",
    }
)


def _prio(line: str) -> str | None:
    """De GELDENDE prioriteit van een rij: de LAATSTE `PRIO=`-waarde.

    Zelfde regel als bij `STATUS=`, en om dezelfde reden: een rij mag zijn eigen
    geschiedenis citeren, en dan telt wat er nu geldt.
    """
    treffers = PRIO_FIELD.findall(line)
    return treffers[-1] if treffers else None


def test_elke_registerrij_heeft_precies_een_prioriteitsveld() -> None:
    """Zonder expliciet veld raadt het gereedschap, en dan liegt het register.

    **Waarom deze toets bestaat (2026-09-18).** `list_adr036_open_items.py` leidde de
    prioriteit af uit de eerste losse `P0`/`P1`-aanduiding in de regel. Rijen NOEMEN
    prioriteiten in hun lopende tekst ("het bewust omheinde P0-autorisatiecluster", "een
    zijdelingse P0-vondst", "vier verweesde P0-claims"), dus dat las een verwijzing als
    classificatie. Gemeten die dag: OP-254 werd als P0 gemeld terwijl hij P1 is, en met de
    omgekeerde regel werden OP-13, OP-196 en OP-243 ten onrechte P0 -- vier van de tachtig
    open rijen fout, in beide richtingen.

    Rakesh heeft die dag als harde eis vastgelegd dat het register te allen tijde de
    werkelijkheid weergeeft. Een afgeleide prioriteit kan dat niet garanderen; een expliciet
    veld wel.
    """
    zonder = [f"{op} (regel {nummer})" for nummer, op, regel in _rows() if _prio(regel) is None]

    assert not zonder, (
        f"Deze {len(zonder)} registerrijen hebben geen `PRIO=`-veld:\n  "
        + "\n  ".join(zonder)
        + "\n\nZet `PRIO=P0|P1|P2|P3` achter het `STATUS=`-veld. Is de prioriteit nooit "
        "bepaald, gebruik dan `PRIO=ONBEPAALD` en zet het OP-nummer in "
        "KNOWN_ZONDER_PRIORITEIT -- dan staat er wat waar is in plaats van een gok."
    )


def test_alleen_oude_rijen_mogen_zonder_prioriteit_staan() -> None:
    """Een NIEUWE rij zonder prioriteit is geblokkeerd; de oude lijst mag alleen krimpen."""
    onbepaald = {op for _nummer, op, regel in _rows() if _prio(regel) == "ONBEPAALD"}
    nieuw = sorted(onbepaald - KNOWN_ZONDER_PRIORITEIT)

    assert not nieuw, (
        f"Deze rijen staan op `PRIO=ONBEPAALD` zonder in KNOWN_ZONDER_PRIORITEIT te staan: "
        f"{nieuw}. Een nieuwe bevinding hoort een prioriteit te krijgen op het moment dat je "
        "hem opschrijft -- dat is precies het moment waarop je de meting nog vers hebt."
    )


def test_de_lijst_zonder_prioriteit_is_niet_verouderd() -> None:
    """Een rij die inmiddels WEL een prioriteit heeft MOET uit de lijst."""
    onbepaald = {op for _nummer, op, regel in _rows() if _prio(regel) == "ONBEPAALD"}
    bestaande = {op for _nummer, op, _regel in _rows()}
    opgelost = sorted((KNOWN_ZONDER_PRIORITEIT & bestaande) - onbepaald)

    assert not opgelost, (
        f"Deze rijen hebben inmiddels een echte prioriteit: {opgelost}. Haal ze uit "
        "KNOWN_ZONDER_PRIORITEIT, anders rot die lijst dicht en verbergt hij het moment "
        "waarop dit gat daadwerkelijk kleiner werd."
    )
