"""De deploygate ROEPT de schematoets aan -- hij noemt hem niet alleen (ADR-036 OP-227).

**Waarom deze guard bestaat.** `scripts/pre-deploy-check.sh` zei tot 2026-09-18 in een
comment dat `tests/integration/database/test_the_chain_builds_the_whole_schema.py` "tegen
een echte database draait en blokkerend hoort te zijn". Gemeten met
`grep -n "test_the_chain_builds_the_whole_schema" scripts/pre-deploy-check.sh`: precies EEN
treffer, die comment zelf. Er was dus geen enkele poort die een deploy tegenhield als de
migratieketen op een echte database een kapot schema opleverde -- en sinds het
GitHub-abonnement is opgezegd (2026-09-14) draait die test ook nergens anders automatisch.

**Waarom deze guard geen tekst doorzoekt.** `.claude/rules/quality-gates.md` documenteert
twee gemeten manieren waarop precies deze guard hol wordt, en dit geval heeft ze allebei:

- "Zocht een naam ergens in een shellscript" -- de naam in een `#`-comment laten staan hield
  de guard groen. Hier STOND de naam al in een comment, dus een substring-toets was vanaf
  regel een betekenisloos geweest.
- "Negeerde de returncode van een subproces" -- een test aanroepen en zijn uitkomst
  weggooien is precies het soort poort dat groen meldt terwijl hij niets tegenhoudt.

Daarom wordt het script eerst ONTDAAN van commentaar (met een scanner die aanhalingstekens
bijhoudt, want een `#` binnen een string is geen commentaar), worden backslash-vervolgregels
samengevoegd, worden eenvoudige variabelen ingevuld, en wordt daarna op COMMANDO's getoetst
in plaats van op regels of op tekst. `test_de_commentaarstripper_haalt_de_naam_echt_weg`
bewijst die eerste stap apart; zonder die zelftoets zou deze guard een tekstzoeker kunnen
zijn zonder dat iemand het ziet.

**Mutatiebewijs (2026-09-18), een regel per bewaakt element en in beide richtingen. Terugweg
via een KOPIE van het script, nooit via `git checkout --` (dat gooit ongecommit werk weg):**

    1. aanroep weggehaald, naam blijft
       in de comment                           -> 4 failed, 2 passed
       (..._roept_de_schematoets_aan, ..._telt_mee, ..._geen_ontsnapping,
        ..._wordt_altijd_opgeruimd -- de laatste drie hangen aan element 1 en vallen mee)
    2. aanroep uitgecommentarieerd             -> 4 failed, 2 passed (dezelfde vier)
    3. aanroep BLIJFT staan, `if ...; then ok;
       else fail; fi` vervangen door
       `pytest ... || true`                    -> 2 failed, 4 passed
       (..._telt_mee en ..._geen_ontsnapping; element 1 blijft GROEN)
    4. `trap _schema_db_opruimen EXIT` weg     -> 1 failed, 5 passed
       (..._wordt_altijd_opgeruimd, en alleen die)
    5. pytest vervangen door `echo`, met BEIDE
       tokens (`pytest` en het testpad) nog
       aanwezig in het commando               -> 4 failed, 2 passed
    6. ongemuteerd en hersteld                 -> 6 passed

**Mutatie 5 stond hier NIET in de eerste versie, en die versie liet hem GROEN passeren.** De
Gate 2-code-review van 2026-09-18 vond dat: `_is_pytest_aanroep` (nu `_voert_pytest_uit`)
toetste of de tokens `pytest` en het testpad ergens in het commando voorkwamen, niet of pytest
het uitgevoerde PROGRAMMA was. `if echo pytest <pad>` voldeed daaraan, `echo` slaagt altijd, en
de deploygate meldde OK terwijl de schematoets nooit draaide -- met alle vier de bewaakte
elementen groen. Dat is dezelfde "tekst waar structuur hoort"-fout die deze guard moest
vangen, een niveau dieper, en hij stond in de functie die het hele bestand draagt. De les die
daarbij hoort: een guard die een faalvorm bestrijdt, kan die faalvorm zelf hebben, en alleen
een mutatie die de VORM nabootst in plaats van de bedoeling vindt dat.

Mutatie 3 is de belangrijkste, en de uitslag zegt precies waarom: de aanroep BLIJFT staan,
dus element 1 meldt groen. Een guard die alleen daarop toetst -- de voor de hand liggende
eerste versie -- had deze mutatie doorgelaten terwijl de poort niets meer tegenhoudt.
Mutatie 4 raakt omgekeerd alleen element 4, wat laat zien dat de vier elementen niet
allemaal aan dezelfde assertie hangen.

Uitgevoerd met `scripts/mutation_harness.py` (kopie, atomair herstel, en `verify_red`
weigert een uitslag waarin geen enkele test is uitgevoerd -- zonder dat leest een
sowieso-falend commando als bewijs).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOYGATE = REPO_ROOT / "scripts" / "pre-deploy-check.sh"

#: Het testbestand dat de deploygate blokkerend moet draaien.
SCHEMATOETS = "tests/integration/database/test_the_chain_builds_the_whole_schema.py"

#: Wat deze guard bewaakt, expliciet benoemd zodat het mutatiebewijs hierboven een regel
#: PER ELEMENT kan hebben in plaats van een vage "de poort deugt". Een guard die zijn eigen
#: oppervlakte niet opschrijft, laat niet zien welk deel ongetest is
#: (quality-gates.md, aanscherping 2026-08-14).
BEWAAKTE_ELEMENTEN = ("aanroep", "foutafhandeling", "geen_ontsnapping", "opruiming")

#: Vormen waarmee een uitkomst wordt weggegooid. `continue-on-error` staat erbij omdat die
#: vlag in deze repo in drie afzonderlijke ronden juist is WEGGEHAALD (ci-feature.yml,
#: 15 en 31 juli 2026) en niet via een shellscript mag terugkomen.
ONTSNAPPINGEN = (r"\|\|\s*true\b", r"\|\|\s*:", r"continue-on-error")


def _strip_regels(tekst: str) -> str:
    """Haal commentaar weg, regel voor regel, met de quote-staat over regels heen.

    Per regel scannen is niet genoeg (een string kan over regels lopen), daarom draagt
    deze functie de staat mee.
    """
    uit: list[str] = []
    enkel = dubbel = False
    for regel in tekst.splitlines():
        schoon: list[str] = []
        ontsnapt = False
        vorige_was_witruimte = True
        for teken in regel:
            if ontsnapt:
                schoon.append(teken)
                ontsnapt = False
                vorige_was_witruimte = False
                continue
            if teken == "\\" and not enkel:
                schoon.append(teken)
                ontsnapt = True
                vorige_was_witruimte = False
                continue
            if teken == "'" and not dubbel:
                enkel = not enkel
            elif teken == '"' and not enkel:
                dubbel = not dubbel
            elif teken == "#" and not enkel and not dubbel and vorige_was_witruimte:
                break
            schoon.append(teken)
            vorige_was_witruimte = teken in " \t"
        uit.append("".join(schoon))
    return "\n".join(uit)


def _logische_regels(tekst: str) -> list[str]:
    """Plak backslash-vervolgregels aan elkaar.

    Zonder dit ziet een tokenizer het tweede deel van de pytest-aanroep niet en meet deze
    guard te weinig terwijl hij groen meldt -- dezelfde valkuil als in
    `test_de_voorgeschreven_poort_is_de_afgedwongen_poort.py`.
    """
    return re.sub(r"\\\s*\n\s*", " ", tekst).splitlines()


def _toewijzingen(tekst: str) -> dict[str, str]:
    """Eenvoudige `NAAM=waarde`-toekenningen uit het script.

    Bestaat zodat de guard de aanroep ook herkent als het pad via een variabele wordt
    doorgegeven. Een guard die eist dat je alles letterlijk uitschrijft, schrijft stijl
    voor in plaats van gedrag te bewaken.
    """
    alle: dict[str, set[str]] = {}
    for regel in _logische_regels(tekst):
        overeenkomst = re.match(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)=(\"([^\"]*)\"|'([^']*)'|([^\s;|&]*))\s*$", regel
        )
        if overeenkomst:
            waarde = next((deel for deel in overeenkomst.groups()[2:] if deel is not None), "")
            alle.setdefault(overeenkomst.group(1), set()).add(waarde)
    # Alleen een variabele met PRECIES EEN waarde is een constante en mag worden ingevuld.
    # `PYTHON_BIN` krijgt er twee (`""` als beginwaarde en `"$kandidaat"` in de zoeklus), dus
    # die wordt NIET ingevuld en blijft als `$PYTHON_BIN` staan. Dat is geen tekortkoming maar
    # het juiste antwoord: de naam is het enige dat nog zegt dat daar een python-interpreter
    # komt, en `_voert_pytest_uit` leunt daarop. Zou hij wel worden ingevuld, dan verdween het
    # programma uit het commando en vond deze guard de aanroep niet meer -- gemeten
    # 2026-09-18 bij het repareren van de HIGH-bevinding uit de Gate 2-code-review.
    return {naam: next(iter(waarden)) for naam, waarden in alle.items() if len(waarden) == 1}


def _expandeer(waarde: str, toewijzingen: dict[str, str]) -> str:
    """Vul `$NAAM` en `${NAAM}` in, begrensd zodat een cyclus niet blijft draaien."""
    for _ in range(4):
        nieuw = re.sub(
            r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
            lambda m: toewijzingen.get(m.group(1), m.group(0)),
            waarde,
        )
        if nieuw == waarde:
            break
        waarde = nieuw
    return waarde


def _commandos(regel: str, toewijzingen: dict[str, str]) -> list[list[str]]:
    """De losse commando's op een logische regel, elk als token-lijst.

    Knipt op `;`, `&&`, `||`, `|` en `&` zodat de toets per COMMANDO gaat en niet per
    STAP -- de gemeten valkuil waarbij de ene tak een woord hield en de andere het verloor.
    """
    zonder_omleiding = re.sub(r"\d?>>?&?\s*\S+", " ", regel)
    uit: list[list[str]] = []
    for stuk in re.split(r"\|\||&&|;|\||&", zonder_omleiding):
        stuk = stuk.strip()
        if not stuk:
            continue
        try:
            tokens = shlex.split(_expandeer(stuk, toewijzingen), posix=True)
        except ValueError:
            continue
        if tokens:
            uit.append(tokens)
    return uit


def _functies(tekst: str) -> dict[str, str]:
    """De shellfuncties uit het script, als `naam -> lichaam`.

    Regelgebaseerd en niet met een DOTALL-regex: `ok() { echo ...; }` staat in dit script op
    EEN regel, en een niet-gulzige `.*?^\\}` laat dat lichaam doorlopen tot de eerste
    sluitende accolade die WEL alleen op een regel staat. Gemeten 2026-09-18: `ok` slokte
    zo 140 regels op inclusief `_schema_db_opruimen`, waarna die functie nooit werd
    gevonden en `test_de_meetdatabase_wordt_altijd_opgeruimd` faalde op een bestaande,
    correcte opruiming. Deze guard betrapte daarmee zijn eigen eerste versie.
    """
    gevonden: dict[str, str] = {}
    huidige: str | None = None
    lichaam: list[str] = []
    for regel in _strip_regels(tekst).splitlines():
        if huidige is None:
            op_een_regel = re.match(r"\s*(\w+)\s*\(\)\s*\{(.*)\}\s*$", regel)
            if op_een_regel:
                gevonden[op_een_regel.group(1)] = op_een_regel.group(2)
                continue
            begin = re.match(r"\s*(\w+)\s*\(\)\s*\{\s*$", regel)
            if begin:
                huidige, lichaam = begin.group(1), []
            continue
        if regel.strip() == "}":
            gevonden[huidige] = "\n".join(lichaam)
            huidige = None
            continue
        lichaam.append(regel)
    return gevonden


#: Shell-sleutelwoorden die voor het eigenlijke commando kunnen staan. `if` staat hier omdat
#: de aanroep bewust in een `if`-conditie hoort (element 2), dus `if` is altijd het eerste
#: token van dat commando.
VOORVOEGSELS = ("if", "elif", "while", "until", "then", "do", "!", "command", "exec")

#: Hoe een python-interpreter eruitziet in dit script. Een variabele telt alleen mee als haar
#: NAAM naar python verwijst (`$PYTHON_BIN`); dat is wat `pre-deploy-check.sh` gebruikt.
INTERPRETER = re.compile(r"^(python|python3|python3\.\d+|py)(\.exe)?$|^\$\{?[A-Za-z_]*PYTHON", re.I)


def _argv(tokens: list[str]) -> list[str]:
    """Het uit te voeren commando: zonder shell-sleutelwoorden en `NAAM=waarde`-voorvoegsels.

    Bash laat een commando voorafgaan door omgevingstoekenningen
    (`FOO=bar python -m pytest ...`); die horen niet bij argv en mogen het programma niet
    verbergen.
    """
    argv = list(tokens)
    while argv and (argv[0] in VOORVOEGSELS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0])):
        argv.pop(0)
    return argv


def _voert_pytest_uit(tokens: list[str]) -> bool:
    """Is pytest het PROGRAMMA dat dit commando uitvoert?

    **Dit heette `_is_pytest_aanroep` en toetste of de tokens `pytest` en het testpad ergens
    in het commando voorkwamen. Dat was fout, en de Gate 2-code-review betrapte het
    (2026-09-18).** Gemeten tegenvoorbeeld:

        if echo pytest tests/integration/database/test_the_chain_builds_the_whole_schema.py

    Daarop gaf de oude versie True: beide tokens staan er. `echo` slaagt altijd, dus de
    deploygate meldde `OK` terwijl pytest nooit draaide -- en alle vier de bewaakte elementen
    bleven groen. Een guard die op AANWEZIGHEID van tokens toetst in plaats van op de POSITIE
    die het programma bepaalt, is dezelfde "tekst waar structuur hoort"-fout als het geval dat
    hij moest vangen, een niveau dieper.

    Nu geldt: pytest is het programma (`pytest ...`), of een python-interpreter draait de
    module (`<python> -m pytest ...`, met `-m pytest` direct achter de interpreter). Bij
    `echo` is argv[0] geen interpreter en staat `-m` niet op positie 1, dus beide takken
    weigeren.
    """
    argv = _argv(tokens)
    if not argv:
        return False
    programma = argv[0].replace("\\", "/").rsplit("/", 1)[-1]
    draait_pytest = programma in {"pytest", "pytest.exe"} or (
        len(argv) >= 3
        and bool(INTERPRETER.match(argv[0]))
        and argv[1] == "-m"
        and argv[2] == "pytest"
    )
    noemt_de_toets = any(token.replace("\\", "/").endswith(SCHEMATOETS) for token in argv[1:])
    return draait_pytest and noemt_de_toets


def _schoon_script() -> tuple[list[str], dict[str, str]]:
    ruw = DEPLOYGATE.read_text(encoding="utf-8")
    zonder = _strip_regels(ruw)
    return _logische_regels(zonder), _toewijzingen(zonder)


def _regel_van_de_aanroep() -> int:
    """De index van de logische regel die pytest op de schematoets aanroept."""
    regels, toewijzingen = _schoon_script()
    for index, regel in enumerate(regels):
        if any(_voert_pytest_uit(tokens) for tokens in _commandos(regel, toewijzingen)):
            return index
    return -1


def _blok_rond(index: int, regels: list[str]) -> list[str]:
    """De regels van het `if`-blok waar regel `index` in begint, tot en met zijn `fi`."""
    diepte = 0
    blok: list[str] = []
    for regel in regels[index:]:
        eerste = regel.strip().split(" ")[0] if regel.strip() else ""
        if eerste == "if":
            diepte += 1
        blok.append(regel)
        if eerste == "fi":
            diepte -= 1
            if diepte <= 0:
                break
    return blok


def test_de_deploygate_roept_de_schematoets_aan() -> None:
    """Element 1: er is een COMMANDO dat pytest op de schematoets draait."""
    assert DEPLOYGATE.exists(), f"{DEPLOYGATE} bestaat niet -- deze guard meet dan niets."
    index = _regel_van_de_aanroep()
    assert index >= 0, (
        f"{DEPLOYGATE.name} draait `{SCHEMATOETS}` NERGENS. De naam noemen in een comment "
        "telt niet: deze guard strip commentaar voordat hij kijkt, juist omdat die naam "
        "hier tot 2026-09-18 alleen in een comment stond terwijl er geen poort was "
        "(ADR-036 OP-227). Zonder deze aanroep houdt niets een deploy tegen als de "
        "migratieketen op een echte database een kapot schema oplevert."
    )


def test_de_uitkomst_van_de_schematoets_telt_mee() -> None:
    """Element 2: de returncode wordt gebruikt, en een rode toets zet `fail`.

    Zonder deze toets is "roep hem aan en gooi het resultaat weg" een geldige oplossing
    voor de test hierboven -- precies de gemeten valkuil "negeerde de returncode van een
    subproces".
    """
    regels, _ = _schoon_script()
    index = _regel_van_de_aanroep()
    assert index >= 0, "geen aanroep gevonden -- zie test_de_deploygate_roept_de_schematoets_aan"

    assert regels[index].strip().startswith("if "), (
        f"De aanroep van {SCHEMATOETS} staat niet in een `if`-conditie:\n"
        f"  {regels[index].strip()}\n"
        "De uitkomst wordt dan niet gebruikt en de poort meldt groen ongeacht wat de "
        "schematoets vindt."
    )

    blok = _blok_rond(index, regels)
    _, toewijzingen = _schoon_script()
    heeft_fail = any(
        tokens and tokens[0] == "fail"
        for regel in blok
        for tokens in _commandos(regel, toewijzingen)
    )
    assert heeft_fail, (
        "Het if-blok rond de schematoets roept nergens `fail` aan, dus een rode toets "
        "verhoogt de foutenteller niet en `pre-deploy-check.sh` eindigt met exitcode 0:\n"
        + "\n".join(blok)
    )


def test_de_schematoets_heeft_geen_ontsnapping() -> None:
    """Element 3: geen `|| true`, `|| :` of `continue-on-error` rond de schematoets."""
    regels, _ = _schoon_script()
    index = _regel_van_de_aanroep()
    assert index >= 0, "geen aanroep gevonden -- zie test_de_deploygate_roept_de_schematoets_aan"

    blok_tekst = "\n".join(_blok_rond(index, regels))
    for patroon in ONTSNAPPINGEN:
        assert not re.search(patroon, blok_tekst), (
            f"Rond de schematoets staat een ontsnapping die op {patroon!r} past. Daarmee "
            "blokkeert een kapot schema de deploy niet meer. Deze repo heeft "
            "`continue-on-error` in drie afzonderlijke, goedgekeurde ronden juist "
            f"weggehaald:\n{blok_tekst}"
        )


def test_de_meetdatabase_wordt_altijd_opgeruimd() -> None:
    """Element 4: een `trap ... EXIT` ruimt de container op, ook bij een fout.

    Zonder dit blijft er bij elke gefaalde deploy een PostgreSQL achter. Dat is geen
    theorie: op 2026-09-14 liet een achtergebleven container de integratiesuite tegen de
    verkeerde database meten zonder dat iets dat meldde (ADR-036 OP-243).
    """
    regels, toewijzingen = _schoon_script()
    index = _regel_van_de_aanroep()
    assert index >= 0, "geen aanroep gevonden -- zie test_de_deploygate_roept_de_schematoets_aan"

    functies = _functies(DEPLOYGATE.read_text(encoding="utf-8"))

    traps_voor_de_aanroep = [
        tokens
        for regelnummer, regel in enumerate(regels[:index])
        for tokens in _commandos(regel, toewijzingen)
        if tokens and tokens[0] == "trap" and "EXIT" in tokens and regelnummer < index
    ]
    assert traps_voor_de_aanroep, (
        "Er staat geen `trap ... EXIT` VOOR de aanroep van de schematoets, dus de "
        "meetdatabase valt buiten het bereik van de opruiming. Breekt het script daarna "
        "af, dan blijft de container draaien."
    )

    ruimt_op = False
    for tokens in traps_voor_de_aanroep:
        handler = tokens[1] if len(tokens) > 1 else ""
        lichaam = functies.get(handler, handler)
        ruimt_op = ruimt_op or bool(re.search(r"docker\s+(rm|stop)\b", lichaam))
    assert ruimt_op, (
        "De `trap ... EXIT` verwijdert geen container (`docker rm`/`docker stop`). Een "
        "trap die niets opruimt is geen opruiming."
    )


def test_de_commentaarstripper_haalt_de_naam_echt_weg() -> None:
    """De tegenrichting: een naam die ALLEEN in commentaar staat telt niet mee.

    Dit is de belangrijkste zelftoets van dit bestand. Zonder hem zou deze guard stilletjes
    een tekstzoeker kunnen zijn -- en de naam van de schematoets stond in
    `pre-deploy-check.sh` al in een comment voordat er een poort was, dus dat verschil is
    hier het hele punt.
    """
    alleen_commentaar = f"# de echte schematoets is `{SCHEMATOETS}` en hoort te draaien\n"
    geschoond = _strip_regels(alleen_commentaar)
    assert SCHEMATOETS not in geschoond, (
        "De commentaarstripper laat een naam uit een `#`-regel staan. Elke toets hieronder "
        "meet dan tekst in plaats van gedrag."
    )

    echt = f'if python -m pytest "{SCHEMATOETS}" -q; then ok x; else fail y; fi\n'
    behouden = _strip_regels(echt)
    assert SCHEMATOETS in behouden, (
        "De stripper haalt ook een ECHTE aanroep weg. Dan zou 'verwijder alles' een geldige "
        "oplossing zijn en zou deze guard nooit groen kunnen staan."
    )

    quote_regel = 'echo "# dit is geen commentaar"\n'
    assert "geen commentaar" in _strip_regels(quote_regel), (
        "Een `#` BINNEN een string is geen commentaar; de stripper mag die regel niet halveren."
    )


def test_de_guard_meet_iets() -> None:
    """Een lege of onleesbare parse maakt alles hierboven trivially groen."""
    regels, toewijzingen = _schoon_script()
    aantal = sum(len(_commandos(regel, toewijzingen)) for regel in regels)
    assert aantal >= 40, (
        f"Slechts {aantal} commando's herkend in {DEPLOYGATE.name}. Op 2026-09-18 waren het "
        "er ruim honderd. Is de parse stuk, of is het script leeggelopen?"
    )
    assert len(BEWAAKTE_ELEMENTEN) == 4, (
        "BEWAAKTE_ELEMENTEN staat hier zodat het mutatiebewijs in de docstring een regel "
        "per element heeft; wijzig je de verzameling, werk dan dat bewijs bij."
    )
