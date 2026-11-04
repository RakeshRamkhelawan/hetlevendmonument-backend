"""De toolbroker voert geen shell-commando's uit (ADR-036 OP-126).

**De bevinding, gemeten door de blinde ronde van 2026-08-10 en door mij laten liggen.**
`LocalToolRegistry._tool_run_shell` combineerde twee dingen die samen een omzeiling opleveren:

    return any(command.startswith(allowed) for allowed in allowed_commands)   # :317
    process = await asyncio.create_subprocess_shell(command, ...)             # :178

`"df -h; env"` begint met het toegestane `"df -h"`, dus de prefix-controle liet het door, en de
SHELL voerde daarna `env` uit. Het kindproces kreeg bovendien de volledige `os.environ` mee --
dezelfde secret-dump als OP-125, langs een andere deur. De HITL-goedkeurder ziet `df -h; env` en
dat leest als een schijfcontrole.

Het commentaar boven de aanroep zei `# Direct execution for whitelisted commands (Safe because of
whitelist)`. De sandbox-tak eronder was een lege `pass`, dus die veiligheid bestond niet.

**Waarom verwijderen en niet hardenen (besluit Rakesh 2026-08-11).** De tool was gevaarlijk EN
dood: gemeten staat GEEN ENKELE `local__`-tool in `config/tool_permissions.yml`, dus
`is_tool_allowed("", ...)` weigert al voordat de HITL-poort in beeld komt. Hardenen zou code
toevoegen aan iets dat niets kan aanroepen.

**Wat deze guard bewaakt.** Niet dat de tool weg is -- dat is een momentopname -- maar dat er
geen SHELL-uitvoering terugkomt in de toolbroker. Een nieuwe tool met dezelfde vorm wordt
geblokkeerd, ongeacht hoe hij heet.

**Mutatietest (2026-08-11, beide richtingen):** een `create_subprocess_shell` toegevoegd aan een
bestand in `src/core/tool_broker/` -> ROOD. De naam in een comment of docstring zetten -> GROEN
(het is een AST-toets op de AANROEP, geen tekstzoektocht). `create_subprocess_exec` gebruiken ->
GROEN, want de array-vorm interpreteert geen shell-metatekens.

**2026-09-07 (ADR-036 OP-127 GESLOTEN).** `src/core/orchestrator/shell_orchestrator.py` en
`scripts/shell_orchestrator_cli.py` zijn verwijderd na GO van Rakesh; `KNOWN_SHELL_EXECUTION`
is daarmee leeg. Bij die wijziging is een gat in `test_known_shell_execution_is_not_stale`
gevonden en gedicht -- zie de docstring van die test. Mutatieproef van die dag, opnieuw in
beide richtingen:
  - `create_subprocess_shell` toevoegen aan een bestaand bestand in `src/core/tool_broker/`
        -> test_the_tool_broker_never_spawns_a_shell ROOD
  - dezelfde mutatie als `create_subprocess_exec` -> GROEN (de array-vorm is de bedoelde vorm)
  - de naam alleen in een comment -> GROEN (AST, geen tekst)
  - een sleutel naar een bestaand bestand waarvan de map geen shell aanroept
        -> test_known_shell_execution_is_not_stale ROOD
  - een sleutel naar een NIET-BESTAAND pad -> ROOD onder de nieuwe tak. Diezelfde mutatie was
    GROEN voordat die tak bestond; dat is het bewijs dat het gat er zat.
  - `_BROKER` naar een niet-bestaande map -> test_the_scan_reads_the_broker_at_all ROOD
  - alles ongewijzigd -> GROEN
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_BROKER = REPO_ROOT / "src/core/tool_broker"

#: Shell-uitvoering die BEWUST blijft staan, met datum en reden per regel.
#:
#: LEEG sinds 2026-09-07. De enige regel was `src/core/orchestrator/shell_orchestrator.py`
#: (ADR-036 OP-127): `create_subprocess_shell(task.command)` met NUL validatie. Die module en
#: zijn enige aanroeper `scripts/shell_orchestrator_cli.py` zijn op die dag verwijderd na GO van
#: Rakesh, omdat het gemeten oppervlak nul was -- geen HTTP-route, geen agent-pad, geen import
#: vanuit `src/`, geen test, en geen CI-stap, Makefile-doel of npm-script dat de CLI aanriep.
KNOWN_SHELL_EXECUTION: dict[str, str] = {}


#: Namen die op zichzelf een shell starten.
_SHELL_NAMEN = frozenset({"create_subprocess_shell", "system", "popen", "spawn"})

#: Namen die een shell starten ZODRA `shell=True` meegaat.
_SHELL_ALS_KWARG = frozenset({"run", "Popen", "call", "check_call", "check_output"})

#: Programma's die zelf een shell zijn. `create_subprocess_exec("/bin/sh", "-c", cmd)` is
#: een shell-aanroep in de array-vorm die deze guard juist aanbeveelt -- de aanbeveling is
#: dus zelf te misbruiken, en dat is precies het gat dat de blinde review van 2026-09-07
#: benoemde.
_SHELL_PROGRAMMAS = frozenset({"sh", "bash", "zsh", "dash", "cmd", "cmd.exe", "powershell",
                               "powershell.exe", "pwsh"})


def _is_shell_programma(waarde: object) -> bool:
    if not isinstance(waarde, str):
        return False
    laatste = waarde.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return laatste in _SHELL_PROGRAMMAS


def _start_een_shell(knoop: ast.Call) -> bool:
    """Start deze aanroep een shell? Structureel getoetst, niet op naam alleen."""
    doel = knoop.func
    naam = doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", "")

    if naam in _SHELL_NAMEN:
        return True

    if naam in _SHELL_ALS_KWARG:
        for kw in knoop.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                return True

    # De array-vorm met een shell als programma: exec("/bin/sh", "-c", cmd), run(["bash", ...]).
    kandidaten: list[ast.expr] = list(knoop.args[:1])
    if kandidaten and isinstance(kandidaten[0], (ast.List, ast.Tuple)):
        kandidaten = list(kandidaten[0].elts[:1])
    for arg in kandidaten:
        if isinstance(arg, ast.Constant) and _is_shell_programma(arg.value):
            return True

    return False


def _shell_aanroepen(map_: Path) -> list[str]:
    """Bestanden in deze map die een SHELL starten -- in welke vorm dan ook.

    Bewust de AST en niet een tekstzoektocht: `ast.dump()` en een kale `grep` vinden de naam ook
    in een docstring of comment. Deze guardfamilie is in dit project al drie keer betrapt op
    precies die fout -- een naam in een toelichting hield hem groen terwijl de aanroep er nog
    stond (ADR-036 OP-101/OP-102).

    **Verbreed 2026-09-07 na de blinde Gate 2-review op de OP-127-sluiting.** De vorige versie
    toetste twee namen (`create_subprocess_shell`, `system`). De reviewer noemde vier vormen die
    daar ongestraft doorheen liepen en hetzelfde doen: `subprocess.run(cmd, shell=True)`,
    `os.popen(cmd)`, `pty.spawn`, en -- de pijnlijkste -- `create_subprocess_exec("/bin/sh",
    "-c", cmd)`, de array-vorm die de foutmelding van deze guard zelf aanbeveelt. Alle vier
    worden nu structureel getoetst; gemeten op 2026-09-07 leverde die verbreding NUL nieuwe
    overtreders op in `src/core/tool_broker` (26 bestanden), dus dit is puur oppervlak erbij.

    **Een onparseerbaar bestand FAALT nu**, in plaats van stil te worden overgeslagen. Een
    `except: continue` maakt van een kapot bestand een schoon bestand, en "geen samenvatting is
    niet groen" geldt hier woordelijk. De boombrede parseerguard (OP-203) dekt de repo, maar
    deze scan mag niet stil leeglopen als hij toch iets tegenkomt.
    """
    gevonden: list[str] = []
    for pad in sorted(map_.rglob("*.py")):
        try:
            boom = ast.parse(pad.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise AssertionError(
                "%s is niet te parseren (%s: %s). Deze scan mag daar niet stil overheen: "
                "een bestand dat niet parseert wordt anders als schoon geteld."
                % (pad.relative_to(REPO_ROOT).as_posix(), type(exc).__name__, exc)
            ) from exc
        for knoop in ast.walk(boom):
            if isinstance(knoop, ast.Call) and _start_een_shell(knoop):
                gevonden.append(pad.relative_to(REPO_ROOT).as_posix())
                break
    return gevonden


#: Wat op 2026-09-07 is verwijderd toen ADR-036 OP-127 sloot. Deze paden horen NIET terug te
#: komen, en de scan hierboven kan dat niet zien: hij leest `src/core/tool_broker` en deze
#: module stond in `src/core/orchestrator`. Dat gat was de kern van een blocker in de blinde
#: Gate 2-review -- de rij citeerde een guard die het gesloten geval per constructie niet zag.
_VERWIJDERD_MET_OP127 = (
    "src/core/orchestrator/shell_orchestrator.py",
    "scripts/shell_orchestrator_cli.py",
)


def test_the_removed_shell_orchestrator_stays_removed() -> None:
    """`shell_orchestrator.py` en zijn CLI blijven weg (ADR-036 OP-127, GO Rakesh 2026-09-07).

    Die module deed `create_subprocess_shell(task.command)` met NUL validatie -- geen allowlist,
    geen shlex -- en het kindproces kreeg de volledige omgeving mee. De CLI bouwde die taken
    rechtstreeks uit een JSON-bestand. Gemeten oppervlak voor de verwijdering was nul: geen
    import vanuit `src/`, geen HTTP-route, geen agent-pad, geen test, en geen CI-stap,
    Makefile-doel of npm-script dat de CLI aanriep.

    Rood te maken door een van de twee bestanden terug te zetten.

    Mutatiebewijs (uitgevoerd 2026-09-07, beide richtingen): een leeg bestand op elk van de twee
    paden aanmaken -> ROOD, per pad apart gemeten; ongemuteerd -> GROEN.
    """
    terug = [pad for pad in _VERWIJDERD_MET_OP127 if (REPO_ROOT / pad).exists()]

    assert not terug, (
        "Deze bestanden zijn op 2026-09-07 verwijderd met ADR-036 OP-127 en staan er weer: "
        f"{terug}.\n\nZe voerden shellcommando's uit zonder enige validatie. Komt er opnieuw "
        "behoefte aan zoiets, gebruik dan `asyncio.create_subprocess_exec(*shlex.split(cmd))` "
        "met een EXPLICIETE minimale omgeving, en zet de bevinding als registerrij neer voordat "
        "je hem bouwt."
    )


def test_the_scan_reads_the_broker_at_all() -> None:
    """Vangnet: loopt de scan leeg, dan bewaakt de test hieronder niets."""
    bestanden = list(_BROKER.rglob("*.py"))

    assert len(bestanden) >= 5, (
        f"Slechts {len(bestanden)} python-bestanden gevonden in {_BROKER}. Is de map verplaatst? "
        "Zolang dit leegloopt zegt de test hieronder niets."
    )


def test_the_tool_broker_never_spawns_a_shell() -> None:
    """Een shell interpreteert `;`, `&&` en `$()` -- dan is elke allowlist een prefix-spel."""
    overtreders = _shell_aanroepen(_BROKER)

    assert not overtreders, (
        f"Deze bestanden in de toolbroker roepen een SHELL aan: {overtreders}.\n\n"
        "Met een shell is elke commando-allowlist te omzeilen: `df -h; env` begint met een "
        "toegestaan prefix en de shell voert daarna alles uit. Gebruik "
        "`asyncio.create_subprocess_exec(*shlex.split(cmd))` -- de array-vorm interpreteert geen "
        "metatekens -- en geef een EXPLICIETE minimale omgeving mee (ADR-036 OP-125/OP-126)."
    )


def test_the_removed_shell_tool_has_not_returned() -> None:
    """Specifiek `local__run_shell`, verwijderd op 2026-08-11.

    Los van de heuristiek hierboven: dit soort tools komt makkelijk terug via een oude branch of
    een hersteld bestand.
    """
    registry = REPO_ROOT / "src/core/tool_broker/local_registry.py"
    if not registry.exists():
        return

    boom = ast.parse(registry.read_text(encoding="utf-8"))
    namen = {
        knoop.value
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Constant) and isinstance(knoop.value, str)
    }
    functies = {
        knoop.name
        for knoop in ast.walk(boom)
        if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "local__run_shell" not in namen, (
        "`local__run_shell` staat weer in de registry. Die tool is op 2026-08-11 verwijderd "
        "omdat een prefix-controle plus een shell samen elke allowlist waardeloos maken."
    )
    assert "_tool_run_shell" not in functies, (
        "`_tool_run_shell` is terug. Zie de docstring van dit bestand voor waarom hij weg is."
    )


def test_known_shell_execution_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET eruit, anders rot de lijst dicht.

    **Gat dat hier op 2026-09-07 is gedicht, en het is het geval waar de commit die het vond
    zelf op stond (ADR-036 OP-127).** De eerste voorwaarde was `(REPO_ROOT / naam).exists()`.
    Een uitzondering waarvan het BESTAND is verwijderd viel daardoor uit de lijstbegrip, en de
    test bleef GROEN met een dode regel erin -- precies wat het gedateerde-uitzonderingspatroon
    in `quality-gates.md` belooft dat niet kan. Toen OP-127 werd gesloten DOOR het bestand te
    verwijderen, was dat geen theoretisch geval meer.

    Nu zijn er twee soorten stale: het bestand bestaat niet meer, of het bestaat wel en roept
    geen shell meer aan. Beide horen uit de lijst.
    """
    verdwenen = [naam for naam in KNOWN_SHELL_EXECUTION if not (REPO_ROOT / naam).exists()]
    opgelost = [
        naam
        for naam in KNOWN_SHELL_EXECUTION
        if (REPO_ROOT / naam).exists() and not _shell_aanroepen((REPO_ROOT / naam).parent)
    ]

    assert not verdwenen, (
        f"Deze bestanden staan in KNOWN_SHELL_EXECUTION maar BESTAAN NIET MEER: {verdwenen}. "
        "Haal ze uit de lijst; een uitzondering voor een verwijderd bestand suggereert een "
        "risico dat er niet is, en niets anders in deze guard betrapt hem."
    )
    assert not opgelost, (
        f"Deze bestanden staan in KNOWN_SHELL_EXECUTION maar roepen geen shell meer aan: "
        f"{opgelost}. Haal ze uit de lijst; anders suggereert die lijst een risico dat er niet "
        "meer is."
    )


def _prefix_padcontroles() -> list[str]:
    """Plekken die een PAD-toelaatlijst met `startswith` toetsen.

    `startswith` op strings kent geen mapgrenzen: `/app/src/core_secrets/x` begint met
    `/app/src/core`, dus een zustermap met een langere naam passeert een allowlist-regel waar hij
    niet onder valt. `Path.is_relative_to` toetst de mapgrens wel.

    Bewust de AST: de naam `startswith` komt ook in comments en docstrings voor.
    """
    doelen = [
        "src/core/tool_broker/local_registry.py",
        "src/core/agents/cva_file_manager.py",
    ]
    gevonden: list[str] = []
    for pad in doelen:
        bestand = REPO_ROOT / pad
        if not bestand.exists():
            continue
        boom = ast.parse(bestand.read_text(encoding="utf-8"))
        for knoop in ast.walk(boom):
            if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "path" not in knoop.name.lower():
                continue
            for binnen in ast.walk(knoop):
                if (
                    isinstance(binnen, ast.Call)
                    and isinstance(binnen.func, ast.Attribute)
                    and binnen.func.attr == "startswith"
                ):
                    gevonden.append(f"{pad}::{knoop.name}")
                    break
    return gevonden


def test_path_allowlist_targets_still_exist() -> None:
    """Vangnet: worden beide doelbestanden van `_prefix_padcontroles()` hernoemd terwijl
    het mapgrens-defect erin blijft staan, dan meet die functie permanent nul overtreders
    -- de `if not bestand.exists(): continue` daarbinnen heeft geen eigen bestaanscheck.
    """
    doelen = [
        "src/core/tool_broker/local_registry.py",
        "src/core/agents/cva_file_manager.py",
    ]
    ontbrekend = [pad for pad in doelen if not (REPO_ROOT / pad).exists()]
    assert not ontbrekend, (
        f"Deze doelbestanden van de startswith-padcontrole bestaan niet meer: {ontbrekend}. "
        "Hernoemd of verplaatst? Werk de lijst in _prefix_padcontroles() bij -- anders "
        "controleert test_path_allowlists_respect_directory_boundaries niets meer voor "
        "dat bestand."
    )


def test_path_allowlists_respect_directory_boundaries() -> None:
    """Een zustermap met een langere naam mag niet door een pad-allowlist glippen.

    Gemeten vorm: allowlist-regel `src/core`, aanvraag `src/core_secrets/x`. Met `startswith` is
    dat een treffer. Met `Path.is_relative_to` niet.

    Mutatie (2026-08-11, beide richtingen): `is_relative_to` terugveranderd naar `startswith`
    -> ROOD. Een legitiem pad BINNEN de allowlist blijft toegestaan -- dat wordt getoetst door
    `tests/test_tool_broker_local.py::test_tool_broker_local_read_file`.
    """
    overtreders = _prefix_padcontroles()

    assert not overtreders, (
        f"Deze pad-allowlists gebruiken `startswith` en kennen dus geen mapgrens: "
        f"{overtreders}.\n\n"
        "Een allowlist-regel `src/core` laat daarmee ook `src/core_secrets` door. Gebruik "
        "`Path(kandidaat).resolve().is_relative_to(Path(toegestaan).resolve())`."
    )
