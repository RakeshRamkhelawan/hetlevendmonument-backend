"""Een test draait git nooit tegen een ANDERE repo zonder de omgeving te schrobben (OP-245).

**Waarom deze guard bestaat, gemeten en niet bedacht (2026-09-16).** `core.bare = true` brak
vier keer op rij de gedeelde `.git/config`, waardoor `git status`, `git grep` en
`git rev-parse` faalden in de hoofdmap EN in alle vier de `iter/`-worktrees. Elke pre-push
poort naar `develop` liep daarop vast, van wie dan ook.

De keten, in een wegwerp-repo nagebouwd:

1. `git push` vanuit een GELINKTE worktree zet `GIT_DIR=<repo>/.git/worktrees/<naam>` in de
   omgeving van zijn hooks. Vanuit een gewone repo blijft `GIT_DIR` leeg -- dat onderscheid
   is de hele zaak en werd bij het eerste nameten bijna gemist.
2. De pre-push hook start pytest; pytest erft `GIT_DIR`.
3. Een test draait `git init` met `cwd=<tmp_path>`. `GIT_DIR` WINT VAN `cwd`, altijd. Git
   herinitialiseert dus de echte repo en de tijdelijke map blijft leeg.
4. Omdat `GIT_DIR` naar een worktree-gitdir wijst, schrijft git `core.bare = true` in de
   GEDEELDE config.

Gemeten bewijs van stap 3/4:

    cd <lege map>; GIT_DIR=<repo>/.git/worktrees/<naam> git init -q
    -> core.bare false -> TRUE, hoofdmap en gelinkte worktree allebei stuk
    idem met GIT_*-variabelen geschrobd
    -> core.bare blijft false, en de lege map krijgt eindelijk zijn eigen .git

**Waarom de regel aan de SOORT uitdrukking hangt en niet aan een naam.** Het eerste ontwerp
van deze guard eiste dat `cwd` een constante met de naam `REPO_ROOT` was. Gemeten heten de
constantes in deze boom `REPO_ROOT` (13x), `_REPO_ROOT`, `_REPO`, `WORTEL` en een kale `"."`.
Die regel had DRIE werkende guards rood gezet. Daarom verzamelt deze guard per bestand de
namen die op MODULENIVEAU zijn toegekend, en toetst hij of de `cwd`-uitdrukking daaruit komt
-- er staat geen enkele repo-naam in deze code.

**De verzameling die hij bewaakt, expliciet (AST-telling 2026-09-17): 21 git-aanroepen in 18
bestanden.** 16 lezend tegen de echte repo (`grep`, `ls-files`, `cat-file`, `log`), 2
`rev-parse` tegen een tijdelijke repo, 3 met een statisch onleesbaar subcommando (`*args`).
Eerdere tekstmetingen gaven 1 en daarna 16; elke verfijning van het instrument gaf een hoger
getal, en dat is de reden dat deze guard op de AST werkt en niet op tekst.

**Wat hij NIET ziet, gemeten en niet vermoed.**

- Alleen GETRACKTE bestanden (`git ls-files`). Een vers, nog niet toegevoegd testbestand valt
  erbuiten. Dat is hier voldoende: de schade treedt op tijdens `git push`, en wat gepusht wordt
  is per definitie getrackt. Het mutatiebewijs hieronder registreert zijn wegwerpbestanden
  daarom met `git add -N`; zonder die stap bleef de guard groen en leek hij hol.
- Een argv in een variabele (`cmd = ["git", "init"]; subprocess.run(cmd)`), `os.system`, of een
  helper in `tests/fixtures/`. De detectie eist een letterlijke lijst als eerste argument.
  Gemeten op 2026-09-17: nul zulke aanroepen in `tests/`.
- `asyncio.create_subprocess_exec("git", ...)` geeft losse argumenten door in plaats van een
  lijst. Gemeten op 2026-09-17: nul zulke aanroepen in `tests/`.
- Een moduleconstante die naar een tijdelijk pad wijst (`TMP = Path(tempfile.mkdtemp())`).
  Clausule 2 kijkt naar de SOORT uitdrukking, niet naar de waarde.
- Alles BUITEN `tests/`. Het incident had twee daders: dit soort test en
  `mcp-server/tools/coordination.py`. Gemeten op 2026-09-17: 11 git-aanroepen buiten `tests/`,
  waarvan 10 zonder `env=`, allemaal lezend (`rev-parse`, `diff`, `ls-files`) in
  `scripts/push_gate.py`, `scripts/claim_op.py`, `scripts/scan_any_usage.py`,
  `scripts/run_righttyper.py` en `mcp-server/store.py`. Vandaag ongevaarlijk; niets houdt
  tegen dat daar een schrijvend commando verschijnt, en twee ervan draaien in het push-pad.

**Mutatiebewijs -- beide richtingen, gedraaid 2026-09-17 met `scripts/mutation_harness.py`,
17 controles, 0 fouten:**

| Mutatie | Verwacht | Gemeten |
| --- | --- | --- |
| ongemuteerde boom | GROEN | GROEN |
| `env=` weg bij de twee `_git`-helpers (clausule 2) | ROOD | ROOD |
| `env=` weg bij alle vier, incl. de twee `rev-parse` | ROOD | ROOD |
| nieuw bestand `git init` ZONDER `cwd` (clausule 1) | ROOD | ROOD |
| nieuw bestand `git *args` zonder `cwd` (clausule 3) | ROOD | ROOD |
| nieuw bestand `git *args` MET moduleconstante als `cwd` (clausule 3) | ROOD | ROOD |
| `env=os.environ.copy()` -- het idioom dat de melding uitlokt | ROOD | ROOD |
| `env=None` -- letterlijk de default | ROOD | ROOD |
| een `env` die WEL schrobt | GROEN | GROEN |
| nieuw bestand `git ls-files` met `cwd=<moduleconstante>` | GROEN | GROEN |
| nieuw bestand `git grep` met `cwd="."` | GROEN | GROEN |
| `git grep` in deze guard laten falen | ROOD | ROOD |
| `"init"` toevoegen aan ALLEEN_LEZEND | ROOD | ROOD |

Twee daarvan verdienen een aantekening. De laatste is roder dan ontworpen: de repo-scan vindt
dan geen overtreding meer, maar de vorm-assertie onderaan dit bestand valt om -- de guard
bewaakt dus zijn eigen leesverzameling. En de wegwerpbestanden worden met `git add -N` in de
index gezet; zonder die stap bleef de guard groen en LEEK het bewijs te kloppen, want
`git ls-files` toont geen ongetrackt bestand.

**Wat de review van 2026-09-17 eruit haalde, want het zegt iets over de vorm van deze fout.**
Twee onafhankelijke reviewers vonden dezelfde HIGH: `env=` werd op AANWEZIGHEID getoetst, niet
op inhoud. `env=os.environ.copy()` -- precies wat iemand typt die deze melding rood ziet --
gaf GROEN terwijl `GIT_DIR` gewoon werd doorgegeven. Dat is de faalvorm "de guard toetst de
VERANTWOORDING in plaats van de HANDELING", en hij zat in de guard die er juist tegen moest
beschermen. Daarnaast draaide de guard zijn eigen `git ls-files` ZONDER schone omgeving: met
een geerfde `GIT_DIR` van een andere worktree mat hij 2061 in plaats van 2079 bestanden en
sloeg hij er 18 stil over.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# De enige subcommando's die de gedeelde config niet kunnen schrijven. Bewust een
# LEESverzameling en geen schrijfverzameling: een onbekend commando hoort de eis te krijgen,
# niet de vrijstelling. Wie hier iets aan toevoegt, voegt een bewering toe.
ALLEEN_LEZEND = frozenset({"grep", "ls-files", "cat-file", "rev-parse", "log"})

_SUBPROCESS_FUNCTIES = frozenset({"run", "Popen", "check_output", "check_call", "call"})

# Vlaggen waarvan het VOLGENDE argument een waarde is en dus geen subcommando.
VLAG_MET_WAARDE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})


def schone_git_omgeving() -> dict[str, str]:
    """De omgeving zonder `GIT_*`, zodat git de repo uit `cwd` kiest en niet uit `GIT_DIR`.

    Deze guard volgt zijn eigen regel, ook al is `ls-files` lezend. Gemeten in deze worktree:
    `git ls-files -- "tests/*.py"` geeft 2079 paden, maar met een geerfde
    `GIT_DIR=<.git/worktrees/ss-netiso>` geeft hetzelfde commando er 2061 -- de index van een
    ANDERE boom. De guard zou dan 18 bestanden van deze boom stil overslaan.
    """
    return {
        sleutel: waarde for sleutel, waarde in os.environ.items() if not sleutel.startswith("GIT_")
    }


def _kandidaatbestanden() -> list[Path]:
    """Getrackte `.py` onder `tests/` die de tekst `git` bevatten. Faalt luid zonder git.

    `git grep -l` in plaats van alle 2079 bestanden zelf openen: gemeten 0.20s tegen
    0.82s alleen, en in de volledige poort (`-n 4`) telde deze test 26.9s tegen een
    `--timeout=60` -- te weinig marge voor een test die iedereen blokkeert. Beide vormen
    leveren exact dezelfde 169 kandidaten op (gemeten 2026-09-17; het symmetrisch
    verschil tussen beide verzamelingen was leeg).

    Het is een filter op de TEKST `git`, geen wiskundige superset: een AST-constante die
    via impliciete concatenatie of een escape is opgebouwd ontsnapt eraan. Gemeten
    2026-09-17: nul zulke gevallen. Verbreedt iemand de detectie, dan moet dit filter mee.
    """
    resultaat = subprocess.run(
        ["git", "grep", "-l", "-I", "-F", "--", "git", "--", "tests/*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=schone_git_omgeving(),
    )
    if resultaat.returncode != 0:
        raise AssertionError(
            "`git grep` faalde met returncode "
            f"{resultaat.returncode}: {resultaat.stderr.strip()!r}. Zonder git kan deze guard "
            "niets bewijzen; hij hoort dan te falen en niet stil nul bestanden te meten."
        )
    paden = [pad for pad in resultaat.stdout.splitlines() if pad]
    paden.extend(_ongetrackte_testbestanden())
    return [REPO_ROOT / pad for pad in dict.fromkeys(paden)]


def _ongetrackte_testbestanden() -> list[str]:
    """Nog niet toegevoegde `.py` onder `tests/` die de tekst `git` bevatten.

    WAAROM DIT ERBIJ MOET, en waarom het geen detail is. `git grep` kent alleen wat git
    kent. Pytest verzamelt op PAD. Een half afgemaakt testbestand dat nog niet is
    toegevoegd, DOET dus wel mee in de lokale testpoort maar was voor deze guard
    onzichtbaar -- en dat is precies het scenario waarin de schade ontstaat: iemand
    schrijft een nieuwe test met `git init`, draait de testpoort, en sloopt de gedeelde
    `.git/config`.

    Dat is op 2026-09-17 ook echt gebeurd, bij sessie `sanskritisetu-org-bf`: een
    ongetrackte, half afgemaakte guard in `tests/architecture/` haalde hun pushronde
    onderuit terwijl zij dachten dat hij niet meedeed. De oorspronkelijke schrijver van
    deze guard (`sanskritisetu-org-39`) had dit gat zelf gemeld en de reparatie
    voorbereid; die sessie is gesloten voor het zover kwam.

    Kosten: gemeten 2026-09-17 leverde dit nul extra bestanden op, dus de guard wordt er
    niet trager van. Hij dekt alleen het geval dat er ooit wel een is.
    """
    resultaat = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "tests/*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=schone_git_omgeving(),
    )
    if resultaat.returncode != 0:
        raise AssertionError(
            "`git ls-files --others` faalde met returncode "
            f"{resultaat.returncode}: {resultaat.stderr.strip()!r}. Stil nul ongetrackte "
            "bestanden meten is hier het gevaarlijke antwoord."
        )
    # Zelf lezen: `git grep` kan niet in bestanden zoeken die git niet kent, en de
    # tekstfilter moet hetzelfde blijven als hierboven.
    uit: list[str] = []
    for pad in resultaat.stdout.splitlines():
        if not pad:
            continue
        volledig = REPO_ROOT / pad
        try:
            if "git" in volledig.read_text(encoding="utf-8", errors="ignore"):
                uit.append(pad)
        except OSError:
            continue  # net verwijderd tussen de opsomming en het lezen
    return uit


def _moduleniveau_namen(module: ast.Module) -> set[str]:
    """Namen die op MODULENIVEAU worden toegekend -- expliciet, zonder ast.walk.

    `ast.walk()` over een module duikt ook functiebodies in; dan zou een lokale `repo = ...`
    als moduleconstante gelden en precies de dader vrijstellen. Daarom dalen we WEL af in
    moduleniveau-blokken (`try`, `if TYPE_CHECKING:`, `with`, `for`) en NOOIT in een
    `FunctionDef`/`AsyncFunctionDef`/`ClassDef`. Zonder die afdaling meldde de guard bij een
    constante uit een `try/except` een oorzaak die onwaar was.
    """
    namen: set[str] = set()

    def loop(statements: list[ast.stmt]) -> None:
        for stat in statements:
            doelen: list[ast.expr] = []
            if isinstance(stat, ast.Assign):
                doelen = list(stat.targets)
            elif isinstance(stat, (ast.AnnAssign, ast.AugAssign)):
                doelen = [stat.target]
            for doel in doelen:
                if isinstance(doel, ast.Name):
                    namen.add(doel.id)
            if isinstance(stat, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                loop(list(getattr(stat, "body", [])))
                loop(list(getattr(stat, "orelse", [])))
                loop(list(getattr(stat, "finalbody", [])))
                for handler in getattr(stat, "handlers", []):
                    loop(list(handler.body))

    loop(module.body)
    return namen


def _git_aanroepen(knoop: ast.AST) -> list[ast.Call]:
    """Elke Call waarvan het eerste argument een lijst is die begint met "git"."""
    treffers: list[ast.Call] = []
    for kind in ast.walk(knoop):
        if not isinstance(kind, ast.Call) or not kind.args:
            continue
        functie = kind.func
        naam = functie.attr if isinstance(functie, ast.Attribute) else getattr(functie, "id", None)
        if naam not in _SUBPROCESS_FUNCTIES:
            continue
        eerste = kind.args[0]
        if (
            isinstance(eerste, ast.List)
            and eerste.elts
            and isinstance(eerste.elts[0], ast.Constant)
            and eerste.elts[0].value == "git"
        ):
            treffers.append(kind)
    return treffers


def _subcommando(aanroep: ast.Call) -> str | None:
    """Het eerste niet-vlag-argument, of None als het statisch onleesbaar is.

    `VLAG_MET_WAARDE` bestaat omdat het argument NA zo'n vlag geen subcommando is. Zonder die
    lijst las `["git", "-C", "/tmp/x", "log"]` als subcommando `/tmp/x` en meldde de guard
    "`git /tmp/x` kan schrijven" -- fail-secure, maar onbegrijpelijk voor wie hem rood ziet.
    """
    argv = aanroep.args[0]
    assert isinstance(argv, ast.List)
    sla_over = False
    for element in argv.elts[1:]:
        if sla_over:
            sla_over = False
            continue
        if isinstance(element, ast.Starred):
            return None
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            if element.value in VLAG_MET_WAARDE:
                sla_over = True
                continue
            if element.value.startswith("-"):
                continue
            return element.value
        return None
    return None


def _env_erft_de_git_variabelen(aanroep: ast.Call) -> bool:
    """True als de `env=`-waarde AANTOONBAAR de git-variabelen doorgeeft.

    Toetsen op de AANWEZIGHEID van `env=` bewaakt de verantwoording en niet de handeling:
    `env=os.environ.copy()` is precies wat iemand schrijft die een variabele wil TOEVOEGEN,
    en dan erft het kindproces GIT_DIR onverkort. Alleen aantoonbaar ervende vormen worden
    afgewezen; al het overige gaat door, want de guard kan niet uitrekenen wat een
    willekeurige uitdrukking oplevert.
    """
    waarde = next((k.value for k in aanroep.keywords if k.arg == "env"), None)
    if waarde is None:
        return False
    if isinstance(waarde, ast.Constant) and waarde.value is None:  # env=None is de default
        return True
    uitdrukking = ast.unparse(waarde).replace(" ", "")
    return uitdrukking in {
        "os.environ",
        "environ",
        "os.environ.copy()",
        "environ.copy()",
        "dict(os.environ)",
        "dict(environ)",
        "{**os.environ}",
        "{**environ}",
    }


def _eist_schone_omgeving(aanroep: ast.Call, moduleconstantes: set[str]) -> str | None:
    """Waarom deze aanroep moet schrobben, of None als hij dat niet hoeft."""
    sub = _subcommando(aanroep)
    cwd = next((k.value for k in aanroep.keywords if k.arg == "cwd"), None)

    if sub is not None and sub not in ALLEEN_LEZEND:
        return f"`git {sub}` kan schrijven"

    if sub is None:
        # Bewust ONGEACHT cwd. Gemeten in een wegwerp-repo: met GIT_DIR naar een
        # worktree-gitdir zet `git init` core.bare=true ook met cwd=<de ECHTE repo>
        # (hoofdmap STUK, gelinkte worktree STUK). cwd beschermt hier dus niets, en juist
        # bij *args is het subcommando niet te lezen.
        return "subcommando statisch onleesbaar (*args), dus niet vast te stellen of het schrijft"

    if cwd is not None:
        vaste_cwd = (isinstance(cwd, ast.Constant) and isinstance(cwd.value, str)) or (
            isinstance(cwd, ast.Name) and cwd.id in moduleconstantes
        )
        if not vaste_cwd:
            return (
                f"cwd={ast.unparse(cwd)} is geen moduleniveau-constante en geen letterlijke "
                "string, dus statisch niet vast te stellen dat dit tegen de echte repo draait"
            )

    return None


def _overtreding_reden(aanroep: ast.Call, moduleconstantes: set[str]) -> str | None:
    """De reden waarom deze aanroep een overtreding is, of None. Een pad voor iedereen.

    De vorm-assertie onderaan dit bestand gebruikt deze functie, niet een eigen kopie van de
    regels -- anders kunnen de guard en zijn eigen bewijs uit elkaar lopen zonder dat iets
    rood wordt.
    """
    reden = _eist_schone_omgeving(aanroep, moduleconstantes)
    if reden is None:
        return None
    heeft_env = any(k.arg == "env" for k in aanroep.keywords)
    if heeft_env and not _env_erft_de_git_variabelen(aanroep):
        return None
    if heeft_env:
        return (
            f"de meegegeven env geeft de git-variabelen door ({reden}). Zie _git_omgeving() "
            "in tests/unit/mcp_server/test_de_poort_meet_de_echte_wijzigingen.py"
        )
    return reden


def _scan() -> tuple[list[str], int]:
    """(overtredingen, aantal daadwerkelijk geparseerde bestanden)."""
    gevonden: list[str] = []
    geparseerd = 0
    for pad in _kandidaatbestanden():
        try:
            bron = pad.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            module = ast.parse(bron)
        except (SyntaxError, ValueError):
            continue
        geparseerd += 1
        constantes = _moduleniveau_namen(module)
        for aanroep in _git_aanroepen(module):
            reden = _overtreding_reden(aanroep, constantes)
            if reden is None:
                continue
            relatief = pad.relative_to(REPO_ROOT).as_posix()
            gevonden.append(f"{relatief}:{aanroep.lineno} -- {reden}")
    return gevonden, geparseerd


def test_geen_git_aanroep_erft_de_omgeving_van_de_hook() -> None:
    """Elke git-aanroep die kan schrijven of tegen een tijdelijke repo draait, schrobt."""
    overtredingen, _ = _scan()
    assert not overtredingen, (
        "Deze git-aanroep(en) erven GIT_DIR van de pre-push hook en draaien daardoor tegen de "
        "ECHTE repo in plaats van tegen de bedoelde:\n  "
        + "\n  ".join(overtredingen)
        + "\n\nGeef `env=` mee met een omgeving zonder GIT_*-sleutels."
    )


def test_de_guard_parseert_werkelijk_bestanden() -> None:
    """Zonder deze toets is 'nul overtredingen' niet te onderscheiden van 'nul bestanden'.

    Telt bewust de bestanden die daadwerkelijk zijn GEPARSEERD, niet de paden die
    `git ls-files` teruggaf. Een pad dat wel in de index staat maar hier niet bestaat, wordt
    in `_overtredingen` stil overgeslagen; die stilte hoort hier zichtbaar te worden.
    """
    _, geparseerd = _scan()
    assert geparseerd > 100, f"verwacht honderden geparseerde kandidaatbestanden, kreeg er {geparseerd}"


@pytest.mark.parametrize(
    ("bron", "moet_vallen"),
    [
        ('subprocess.run(["git", "init"], cwd=tmp)', True),
        ('subprocess.run(["git", "init"])', True),
        ('subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo)', True),
        ('subprocess.run(["git", *args])', True),
        ('subprocess.run(["git", *args], cwd=WORTEL)', True),
        ('subprocess.run(["git", "-C", doel, "init"], cwd=WORTEL)', True),
        ('subprocess.run(["git", "init"], cwd=tmp, env=os.environ)', True),
        ('subprocess.run(["git", "init"], cwd=tmp, env=os.environ.copy())', True),
        ('subprocess.run(["git", "init"], cwd=tmp, env=None)', True),
        ('subprocess.run(["git", "ls-files"], cwd=WORTEL)', False),
        ('subprocess.run(["git", "grep", "-n", "x"], cwd=".")', False),
        ('subprocess.run(["git", "-C", "/tmp/x", "log"], cwd=WORTEL)', False),
        ('subprocess.run(["git", "init"], cwd=tmp, env=schoon())', False),
    ],
)
def test_de_regel_scheidt_de_vormen_die_vandaag_in_de_boom_staan(
    bron: str, moet_vallen: bool
) -> None:
    """Elke vorm uit de gemeten verzameling, beide richtingen, in een regel per vorm."""
    module = ast.parse(f"WORTEL = 1\n{bron}\n")
    constantes = _moduleniveau_namen(module)
    aanroep = _git_aanroepen(module)[0]
    valt = _overtreding_reden(aanroep, constantes) is not None
    assert valt is moet_vallen, f"{bron!r}: verwacht vallen={moet_vallen}, kreeg {valt}"
