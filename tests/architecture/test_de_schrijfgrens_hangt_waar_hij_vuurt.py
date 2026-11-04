"""De schrijfgrens hangt in settings.json, want daar vuurt hij -- in een rolkop niet.

**De duurste les van 2026-09-28, en hij is twee keer eerder gemaakt.**

`rol-schrijfgrens.sh` hing in de KOP van elk rolbestand (`hooks:` in de frontmatter). Het
script was in beide richtingen mutatie-getest: 21 gevallen, 0 afwijkend. Op grond daarvan is
aan Rakesh gemeld dat de rolgrenzen "afgedwongen" waren.

Dat was onwaar. Gemeten met een ECHTE subagent in de rol verkenner:

    Write -> src/core/PROEF-SCHRIJFGRENS-WEGWERP.py
    "File created successfully at: ...\\src\\core\\PROEF-SCHRIJFGRENS-WEGWERP.py"

Geen weigering. Hooks uit een rolkop vuren niet wanneer die rol als subagent draait.
`disallowedTools` in diezelfde kop had evenmin effect. Het mutatiebewijs bewees dus dat het
SCRIPT klopte, niet dat het AANGESLOTEN was -- exact de fout die dit project op 2026-09-27
al bij `auto-test.sh` maakte, en die in CLAUDE.md met zoveel woorden benoemd staat: "een
hook kan in `.claude/hooks/` staan zonder in settings.json aangesloten te zijn, en dan
draait hij nooit."

Wat WEL vuurt bij een subagent is een hook uit `.claude/settings.json`. Gemeten in dezelfde
ronde: `protect-files.sh` weigerde daar netjes een `*.gen.ts`. En de invoer van zo'n hook
draagt de rol mee (`"agent_type":"verkenner"`), dus hij kan zelf uitzoeken wie er schrijft.

Na de ombouw, opnieuw live met een subagent gemeten:

    src/core/...     -> "ROL 'verkenner' MAG HIER NIET SCHRIJVEN"
    docs/meetlat.md  -> "NIEMAND WIJZIGT DE MEETLAT"
    docs/gewoon.md   -> aangemaakt (de controlevraag: het is geen "weiger alles")

**Deze test bewaakt de BEDRADING, niet het gedrag.** Het gedrag staat in het
mutatieharnas; wat hier stond te gebeuren is dat iemand de hook uit settings.json haalt of
hernoemt en denkt dat de rolkop het overneemt. Dat denken was de fout.

Mutatiebewijs (2026-09-28), beide richtingen, 4 gevallen, 0 afwijkend:

    de hook uit settings.json halen          -> ROOD
    de matcher terug naar "Edit|Write"       -> ROOD  (NotebookEdit valt dan buiten)
    het scriptbestand hernoemen              -> ROOD
    de boom zoals hij is                     -> GROEN
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
GRENS = ".claude/hooks/rol-schrijfgrens.sh"
BASH_BEWAKER = ".claude/hooks/block-dangerous-commands.sh"

# De schrijfgereedschappen die langs de grens MOETEN. NotebookEdit stond er aanvankelijk
# niet bij en is een echte ontsnappingsroute: het schrijft bestanden zoals Write dat doet.
VERPLICHTE_MATCHERS = frozenset({"Edit", "Write", "NotebookEdit"})

# Alle vijftien rolnamen die in de zonetabel van rol-schrijfgrens.sh moeten staan.
# Een rol die er niet in staat, valt door naar de *)-arm en wordt stilletjes doorgelaten.
BEKENDE_ROLLEN = frozenset(
    {
        "regie",
        "testspecialist",
        "bouwer",
        "acceptant",
        "beoordelaar",
        "verkenner",
        "architect",
        "schrijver",
        "database",
        "code-reviewer",
        "quality-reviewer",
        "security-reviewer",
        "doc-reviewer",
        "performance-reviewer",
        "frontend-designer",
    }
)

# De vijf review-rollen die alleen Bash hebben (geen Write of Edit).
# Hun enige schrijfroute via Bash moet in block-dangerous-commands.sh geblokkeerd worden.
REVIEWER_ROLLEN = frozenset(
    {
        "code-reviewer",
        "quality-reviewer",
        "security-reviewer",
        "doc-reviewer",
        "performance-reviewer",
    }
)

# De zeven bouwende rollen die WEL Bash-schrijftoegang hebben, maar uitsluitend binnen
# hun zone. Hun Bash-schrijfgrens loopt via _is_bouwende_rol + _pad_geblokkeerd in
# block-dangerous-commands.sh (gedelegeerd aan rol-schrijfgrens.sh).
BOUWENDE_ROLLEN = frozenset(
    {
        "testspecialist",
        "bouwer",
        "database",
        "schrijver",
        "architect",
        "frontend-designer",
        "regie",
    }
)


def _pretooluse_blokken() -> list[dict]:
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    blokken = data.get("hooks", {}).get("PreToolUse", [])
    assert blokken, "settings.json heeft geen PreToolUse-hooks -- dan meet deze test niets"
    return blokken


def test_de_schrijfgrens_is_aangesloten_in_settings_json() -> None:
    """Een hook die alleen in een rolkop staat, vuurt niet bij een subagent."""
    aangesloten = [
        blok
        for blok in _pretooluse_blokken()
        if any(GRENS in h.get("command", "") for h in blok.get("hooks", []))
    ]
    assert aangesloten, (
        "%s hangt nergens in settings.json onder PreToolUse. Een hook in de KOP van een "
        "rolbestand vuurt NIET wanneer die rol als subagent draait -- gemeten 2026-09-28, "
        "een verkenner schreef toen ongehinderd naar src/core/." % GRENS
    )


def test_de_grens_dekt_elk_schrijvend_gereedschap() -> None:
    """Edit en Write dekken niet alles: NotebookEdit schrijft net zo goed bestanden."""
    gedekt: set[str] = set()
    for blok in _pretooluse_blokken():
        if not any(GRENS in h.get("command", "") for h in blok.get("hooks", [])):
            continue
        gedekt |= {deel.strip() for deel in blok.get("matcher", "").split("|") if deel.strip()}

    ontbreekt = sorted(VERPLICHTE_MATCHERS - gedekt)
    assert not ontbreekt, (
        "de schrijfgrens hangt niet op %s -- dat is een open route langs de rolgrens "
        "(gedekt: %s)" % (", ".join(ontbreekt), ", ".join(sorted(gedekt)) or "niets")
    )


def test_het_script_waar_settings_json_naar_wijst_bestaat_echt() -> None:
    """Een verwijzing naar een verdwenen script faalt stil: de hook draait dan nooit."""
    assert (REPO_ROOT / GRENS).exists(), (
        "settings.json wijst naar %s, maar dat bestand bestaat niet" % GRENS
    )


def test_alle_rollen_in_de_zonetabel() -> None:
    """Elke bekende rol heeft een arm in de zonetabel -- geen onbekende rol die stilletjes doorloopt.

    Mutatiebewijs (beide richtingen):
    - verwijder een arm uit de case-tabel -> ROOD (rol ontbreekt in patroon)
    - voeg een nieuwe rol toe aan BEKENDE_ROLLEN EN aan de shell-tabel -> GROEN
    """
    inhoud = (REPO_ROOT / GRENS).read_text(encoding="utf-8")
    # Rol kan op een eigen regel staan ("  code-reviewer)") OF midden in een
    # gecombineerde arm ("|quality-reviewer|"). Beide vormen zijn geldig shell-syntax.
    ontbreekt = [
        r
        for r in sorted(BEKENDE_ROLLEN)
        if not re.search(r"(?:\n\s+|\|)" + re.escape(r) + r"[)|]", inhoud)
    ]
    assert not ontbreekt, (
        "deze rollen hebben geen arm in de zonetabel van %s: %s -- een onbekende rol "
        "wordt stilletjes doorgelaten (exit 0, met alleen een stderr-melding)"
        % (
            GRENS,
            ", ".join(ontbreekt),
        )
    )


def test_bash_bewaker_kent_alle_reviewer_rollen() -> None:
    """block-dangerous-commands.sh bevat alle reviewer-rolnamen -- anders is Bash een open schrijfroute.

    Mutatiebewijs (beide richtingen):
    - verwijder een reviewer-rolnaam uit block-dangerous-commands.sh -> ROOD
    - voeg een naam toe aan REVIEWER_ROLLEN zonder hem in het script te zetten -> ROOD
    - voeg hem in BEIDE toe -> GROEN
    """
    inhoud = (REPO_ROOT / BASH_BEWAKER).read_text(encoding="utf-8")
    # Controleer dat de rol in een case-arm staat ("|rolnaam[)|]" of "\n  rolnaam[)|]"),
    # niet alleen ergens in een commentaarregel -- een commentaar blokkeert niets.
    ontbreekt = [
        r
        for r in sorted(REVIEWER_ROLLEN)
        if not re.search(r"(?:\n\s+|\|)" + re.escape(r) + r"[)|]", inhoud)
    ]
    assert not ontbreekt, (
        "%s bevat geen rolcontrole voor: %s -- die rollen kunnen onbeperkt naar "
        "bestanden schrijven via Bash-commando's (redirects, tee, sed -i)"
        % (
            BASH_BEWAKER,
            ", ".join(ontbreekt),
        )
    )


def _bash() -> str:
    """Het pad naar Git Bash -- nooit de kale naam, want dat wint WSL-bash op sommige machines.

    Gemeten op de machine van rsram-5b: shutil.which("bash") geeft WSL-bash terug, die
    faalt met execvpe(/bin/bash) failed en exitcode 1. Alle 14 gevallen leken dan te slagen
    terwijl de bewaker niet draaide -- dezelfde faalvorm als beschreven in rol-schrijfgrens.sh
    regel 59-62. Oplossing: zoek expliciet Git Bash, shutil.which alleen als noodval.
    """
    for kandidaat in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/bin/bash",
    ):
        if os.path.exists(kandidaat):
            return kandidaat
    gevonden = shutil.which("bash")
    if gevonden is None:
        pytest.skip("geen bash gevonden om de bewaker mee te draaien")
    return gevonden


# De bewaker draait als los proces en kost zelf tijd, niet de start van bash. Gemeten 2026-10-10
# op een rustige machine (Git Bash, Windows): `bash -c true` 0,06 s; een aanroep van
# block-dangerous-commands.sh 1,3 tot 2,8 s. Daarvan zit ongeveer 1 s in zo'n 30 kleine processen
# die het script zelf start (`jq`, `grep`, `sed`, `printf` in subshells; een fork kost op Windows
# 15 tot 50 ms) en 0,65 s in de geneste aanroep van rol-schrijfgrens.sh. De bewaker mag hier niet
# worden aangepast; wat deze test wel kan is de aanroepen NIET na elkaar te draaien.
#
# Per aanroep: 90 s. Dat is geen "hoger getal ter geruststelling": het is een hangdetectie met
# ruimte voor een machine die ruim 30x trager is dan gemeten (90 / 2,8 s = 32x). Eerder stond hier
# 15 s, ruim onder de 2 s x de vertraging van een volle testronde (`-n 4` plus builds).
BEWAKER_TIMEOUT = 90
# Gelijktijdige bewakerprocessen. De gevallen zijn onafhankelijk van elkaar (elk een eigen proces
# met eigen invoer); vier tegelijk haalt de duur van 14 aanroepen van ~30 s serieel terug naar
# ongeveer een derde, zonder de machine met tientallen processen te overspoelen.
GELIJKTIJDIG = 4
# De duur van een hele bash-test, voor `@pytest.mark.timeout`. De testpoort draait met
# `--timeout=60` en `timeout_method = "thread"` (pyproject.toml): op Windows breekt dat het hele
# WERKPROCES af ("worker crashed") en geeft het geen gewone fout. Serieel kost een test ~30 s op een
# rustige machine. Een test is 14 aanroepen met 4 tegelijk = 4 rondes; bij een machine die zo traag
# is dat elke aanroep tegen BEWAKER_TIMEOUT aanloopt zijn dat 4 x 90 = 360 s, en 450 s laat daar
# nog ruimte boven, zodat eerst de leesbare fout van de bewaker komt en niet de afbreking.
BASH_TEST_TIMEOUT = 450


def _run_bash_bewaker(commando: str, rol: str) -> int:
    """Draai block-dangerous-commands.sh met een synthetisch commando en een roldnaam.

    Geeft de exitcode terug: 0 = toegestaan, 2 = geblokkeerd, anders script-fout.
    Drie uitkomsten: een rc die noch 0 noch 2 is wijst op een mis-lopend script,
    niet op doorlating. Zie rol-schrijfgrens.sh regel 58-62 voor dezelfde les.
    CLAUDE_PROJECT_DIR wordt meegegeven zodat rol-schrijfgrens.sh de repo-root vindt
    zonder git rev-parse te hoeven aanroepen.

    Een bewaker die te lang duurt geeft een GEWONE, leesbare fout (rol en commando erin) en niet
    een kale `TimeoutExpired`.
    """
    invoer = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": commando},
            "agent_type": rol,
        }
    )
    omgeving = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT).replace("\\", "/")}
    try:
        uitvoer = subprocess.run(
            [_bash(), str(REPO_ROOT / BASH_BEWAKER).replace("\\", "/")],
            input=invoer,
            text=True,
            capture_output=True,
            env=omgeving,
            cwd=str(REPO_ROOT),
            timeout=BEWAKER_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "de bewaker draaide langer dan %d s voor rol %r + %r. Gemeten op een rustige machine: "
            "1,3 tot 2,8 s. Is de machine overbelast, of hangt %s?"
            % (BEWAKER_TIMEOUT, rol, commando, BASH_BEWAKER)
        )
    return uitvoer.returncode


def _run_bewaker_gevallen(gevallen: list[tuple[str, str]]) -> list[int]:
    """Draai (rol, commando)-paren tegelijk; de uitkomsten staan in de volgorde van de invoer.

    Elk geval is een eigen proces met eigen invoer, dus de volgorde van uitvoeren doet er niet
    toe. Faalt er een (te trage bewaker), dan start er daarna GEEN nieuw geval meer: anders loopt
    de test alsnog tegen de timeout van de testpoort aan. Een stopvlag en niet `Future.cancel()`:
    gemeten 2026-10-10 met een hangende bewaker, een thread die vrijkomt pakt het volgende geval
    nog op voordat de hoofddraad annuleert (209 s in plaats van de verwachte ~90 s).
    """
    gestopt = threading.Event()

    def taak(rol: str, commando: str) -> int:
        if gestopt.is_set():
            return -1
        try:
            return _run_bash_bewaker(commando, rol)
        except BaseException:
            gestopt.set()
            raise

    with ThreadPoolExecutor(max_workers=GELIJKTIJDIG) as pool:
        futures = [pool.submit(taak, rol, cmd) for rol, cmd in gevallen]
        return [f.result() for f in futures]


def test_block_dangerous_verwijst_naar_bestaand_rol_script() -> None:
    """block-dangerous-commands.sh delegeert aan rol-schrijfgrens.sh via _pad_geblokkeerd().

    Die delegatie is fail-closed: als rol-schrijfgrens.sh ontbreekt terwijl de projectroot
    wel is opgelost, blokkeert _pad_geblokkeerd() de hele Bash-actie. Een verwijzing naar
    een verdwenen script mocht vroeger stil doorgaan (fail-open) -- hetzelfde patroon als
    auto-test.sh op 2026-09-27. Deze test bewaart de vereiste dat het gerefereerde script
    aantoonbaar bestaat.

    Mutatiebewijs (beide richtingen, 2026-09-30):
    Richting 1: verwijder bash "$GRENS" aanroep in uitvoerbare code -> assertion 1 ROOD
      (naam staat nog 7x in commentaar maar commentaar blokkeert niets)
    Richting 2: hernoem rol-schrijfgrens.sh -> assertion 2 ROOD
    Richting 3: beide aanwezig en aanroep in code -> GROEN
    Uitgevoerd door daadwerkelijk verwijderen/hernoemen (copy als terugweg).
    """
    inhoud = (REPO_ROOT / BASH_BEWAKER).read_text(encoding="utf-8")
    # "rol-schrijfgrens.sh" staat 7x in het bestand, 5x in commentaarregels.
    # Toets de daadwerkelijke bash-aanroep in uitvoerbare code, niet tekstaanwezigheid.
    code_regels = [r for r in inhoud.splitlines() if not r.lstrip().startswith("#")]
    code = "\n".join(code_regels)
    assert re.search(r"\bbash\b[^\n]*\$GRENS", code), (
        "%s roept rol-schrijfgrens.sh niet aan in uitvoerbare code -- "
        "de naam staat wel in commentaar maar commentaar blokkeert niets; "
        'de aanroep in _pad_geblokkeerd() is: bash "$GRENS" "$ROL"' % BASH_BEWAKER
    )
    assert (REPO_ROOT / GRENS).exists(), (
        "rol-schrijfgrens.sh bestaat niet op %s -- block-dangerous-commands.sh verwijst "
        "ernaar in _pad_geblokkeerd(). Die functie is fail-closed: als het script weg is, "
        "blokkeert de Bash-grens alle schrijfacties voor bouwende rollen. "
        "Herstel de werkkopie." % (REPO_ROOT / GRENS)
    )


@pytest.mark.timeout(BASH_TEST_TIMEOUT)
def test_bash_schrijf_geblokkeerd_voor_bouwende_rollen() -> None:
    """Zone-gebaseerde Bash-grens blokkeert schrijfacties buiten de rol-zone.

    Mutatiebewijs (beide richtingen, 2026-09-30), een gevalsregel per rol:
      testspecialist    echo > src/core/x.py          GEWEIGERD (src/ is geblokkeerd)
      testspecialist    echo > tests/unit/test_x.py   TOEGESTAAN
      bouwer            echo > tests/unit/test_x.py   GEWEIGERD (tests/ is geblokkeerd)
      bouwer            echo > src/core/x.py          TOEGESTAAN
      regie             echo > src/core/x.py          GEWEIGERD
      regie             echo > docs/besluit.md        TOEGESTAAN
      schrijver         echo > src/core/x.py          GEWEIGERD
      schrijver         echo > docs/handleiding.md    TOEGESTAAN
      database          echo > frontend/src/App.tsx   GEWEIGERD
      database          echo > alembic/versions/x.py  TOEGESTAAN
      architect         echo > src/core/x.py          GEWEIGERD
      architect         echo > docs/adr/x.md          TOEGESTAAN
      frontend-designer echo > src/core/x.py          GEWEIGERD
      frontend-designer echo > frontend/src/App.tsx   TOEGESTAAN

    Richting 2 (TOEGESTAAN-gevallen) is de controle-groep: weiger-alles is geen oplossing.
    """
    gevallen: list[tuple[str, str, int]] = [
        # (rol, commando, verwacht: 2=geblokkeerd, 0=toegestaan)
        ("testspecialist", "echo foo > src/core/x.py", 2),
        ("testspecialist", "echo foo > tests/unit/test_x.py", 0),
        ("bouwer", "echo foo > tests/unit/test_x.py", 2),
        ("bouwer", "echo foo > src/core/x.py", 0),
        ("regie", "echo foo > src/core/x.py", 2),
        ("regie", "echo foo > docs/besluit.md", 0),
        ("schrijver", "echo foo > src/core/x.py", 2),
        ("schrijver", "echo foo > docs/handleiding.md", 0),
        ("database", "echo foo > frontend/src/App.tsx", 2),
        ("database", "echo foo > alembic/versions/x.py", 0),
        ("architect", "echo foo > src/core/x.py", 2),
        ("architect", "echo foo > docs/adr/x.md", 0),
        ("frontend-designer", "echo foo > src/core/x.py", 2),
        ("frontend-designer", "echo foo > frontend/src/App.tsx", 0),
    ]
    uitkomsten = _run_bewaker_gevallen([(rol, cmd) for rol, cmd, _ in gevallen])
    fouten = [
        "rol %r + %r: verwacht exit %d, kreeg %d" % (rol, cmd, verwacht, uitkomst)
        for (rol, cmd, verwacht), uitkomst in zip(gevallen, uitkomsten, strict=True)
        if uitkomst != verwacht
    ]
    assert not fouten, "Zone-gebaseerde Bash-grens klopt niet voor:\n" + "\n".join(fouten)


@pytest.mark.timeout(BASH_TEST_TIMEOUT)
def test_meetlat_geblokkeerd_via_bash_voor_bouwende_rollen() -> None:
    """docs/meetlat.md is universeel geblokkeerd voor alle bouwende rollen via Bash.

    Mutatiebewijs (beide richtingen, 2026-09-30):
    Richting 1: elke bouwende rol + redirect naar docs/meetlat.md -> GEWEIGERD
    Richting 2: elke bouwende rol + redirect naar docs/gewoon.md  -> TOEGESTAAN
    Richting 2 bewijst dat de meetlat-blokkade niet alles blokkeert.
    """
    rollen = sorted(BOUWENDE_ROLLEN)
    # Richting 1: meetlat geblokkeerd. Richting 2: gewoon docs-bestand toegestaan. BEIDE in een
    # aanroep, zodat richting 2 ook loopt (en gemeld wordt) als richting 1 faalt.
    uitkomsten = _run_bewaker_gevallen(
        [(rol, "echo foo > docs/meetlat.md") for rol in rollen]
        + [(rol, "echo foo > docs/gewoon.md") for rol in rollen]
    )
    meetlat, gewoon = uitkomsten[: len(rollen)], uitkomsten[len(rollen) :]
    fouten = [
        "rol %r: 'echo > docs/meetlat.md' niet geblokkeerd (exit %d)" % (rol, uitkomst)
        for rol, uitkomst in zip(rollen, meetlat, strict=True)
        if uitkomst != 2
    ] + [
        "rol %r: 'echo > docs/gewoon.md' onterecht geblokkeerd (exit %d) "
        "-- weiger-alles is geen oplossing" % (rol, uitkomst)
        for rol, uitkomst in zip(rollen, gewoon, strict=True)
        if uitkomst != 0
    ]
    assert not fouten, "\n".join(fouten)
