"""ADR-036 OP-12/ADR031-001, fix-sprint dag 4 nazorg (tweede blinde review, 2026-08-19).

BE-AGT-050's fix (`src/core/agents/cva_autonomous_trigger.py`) leunt volledig op de claim
dat `CVAAutonomousTrigger._execute_breakthrough_session()` vandaag onbereikbaar is in
productie: de enige constructieplek (`cva_trigger = CVAAutonomousTrigger()`) geeft geen
`oversight_gate` mee, dus het governance-blok draait nooit voor die singleton. Zonder een
gate blijft ook de VERDERE keten (`OversightGate.check()` -> `PolicyEngine.validate_action()`
-> `AGENT_ENTRYPOINT_ACTIONS`-classificatie van `"autonomous_breakthrough"`) inert -- het is
EEN keten, geen twee onafhankelijke routes (zie `governance_helper.py::
PolicyEngineAdapter.validate_action`, die `ActionContext(action_name=action, ...)` bouwt uit
precies het `task_action` dat `OversightGate.check()` doorgeeft).

De ADR-036-registerrij voor OP-12 staat daarom bewust op `STATUS=OPEN` (niet GESLOTEN): de
onderliggende conditie (geen autonomieladder gewired) is niet opgelost, alleen bevestigd
inert. Die conclusie moest een eigen guard krijgen -- zonder guard zou een latere wijziging
dit pad stilzwijgend live kunnen maken zonder dat er een test rood gaat.

**Derde blinde review (2026-08-19) vond een BLOCKER in de EERSTE versie van deze guard
zelf**: het genoemde functieverzameling miste `trigger_manual_breakthrough`/
`trigger_manual_cva_breakthrough` -- een pad dat het GOVERNANCE-BLOK HELEMAAL OMZEILT
(`trigger_manual_breakthrough()` roept `_add_trigger()` aan, die bij hoge prioriteit direct
`_process_trigger_queue()` -> `_execute_breakthrough_session()` aanroept, zonder ooit
`self.oversight_gate`-check te passeren omdat die pas IN `_execute_breakthrough_session()`
zit -- maar de singleton heeft toch geen gate, dus dat blok slaat sowieso over). De
historische, dode router (`git show a38fbd09:src/core/api/cva_autonomous_endpoints.py`)
riep dit pad wel degelijk aan (`trigger_manual_cva_breakthrough(request.reason)`,
regel 173) -- een toekomstige partiele restore van ALLEEN die route (zonder de
`start_cva_autonomous()`-aanroep elders in dat bestand) zou dus alsnog een live,
ongouverneerd pad opleveren terwijl deze guard groen bleef. Toegevoegd aan de
functieverzameling; mutatiebewijs per element in de docstrings van de tests.

**Vier MINOR-bevindingen uit dezelfde review, ook gefixt:**
1. De eerste detector keek alleen naar `ast.Assign` -- een `ast.AnnAssign`
   (`cva_trigger: CVAAutonomousTrigger = CVAAutonomousTrigger(oversight_gate=...)`) werd
   gemist. Nu beide typen.
2. De eerste detector gebruikte `ast.iter_child_nodes` (alleen directe module-children) --
   een `if <conditie>: cva_trigger = CVAAutonomousTrigger(oversight_gate=...)` (precies het
   soort feature-flag-constructie die OP-12's eigen mitigatie-advies noemt: "zet een
   feature-flag op die in productie uit staat") werd gemist. Nu een eigen recursieve
   `_iter_import_time_statements()` die WEL afdaalt in `if`/`try`/`with`/`for`/`while`
   op modulniveau, maar NOOIT in een `FunctionDef`/`AsyncFunctionDef`/`ClassDef`-body (die
   voeren niet uit bij import -- exact de valkuil die `ast.walk` op de hele module zou
   introduceren).
3. `_live_python_files()` sloot `__init__.py` uit (huisstijl overgenomen van
   `test_adr018_eventstore_not_wired.py`, maar hier verkeerd: import-time-side-effects
   zitten precies vaak in een package-`__init__.py`) en doorzocht alleen `src/`, niet
   `scripts/`. Nu beide meegenomen.
4. (Documentatie, niet deze guard): het commit-bericht van de vorige ronde overclaimde
   "4 tests met assert_not_called" in `test_cva_breakthrough_fails_closed_without_ticket.py`
   -- het zijn er daadwerkelijk 3 (de vierde test bewijst het GEDRAG anders, niet via een
   herhaalde assertie). Gecorrigeerd in `review-BE-AGT-050.md`.

**Vierde blinde review (2026-08-19), GO met 1 MINOR**: het aanroep-gebaseerde check
(`_external_autonomous_start_callers`) matcht alleen de SYNTAX van een aanroep
(`node.func`), niet elk GEBRUIK. Drie ontsnappingen bleven groen, allemaal zelf
gereproduceerd: (a) een naam als referentie doorgeven zonder hem aan te roepen (bv.
`router.add_api_route("/x", trigger_manual_cva_breakthrough)`), (b) een alias-import
gevolgd door een aanroep op de alias, en (c) een import van `cva_trigger` zelf gevolgd door
een aanroep op een PRIVATE methode (`cva_trigger._add_trigger(...)`, die geen eigen naam in
de functieverzameling heeft maar wel bij `_execute_breakthrough_session()` uitkomt). Alle
drie vereisen EERST een import -- toegevoegd:
`test_nothing_outside_the_module_imports_the_singleton_or_its_start_functions`, die elke
`from ...cva_autonomous_trigger import <cva_trigger of een van de vier namen>` buiten dit
bestand verbiedt en daarmee alle drie ontsnappingen dicht voor die importvorm (bewezen: elk
apart gemuteerd, elk rood, allemaal teruggedraaid).

**Vijfde blinde review (2026-08-19), GO met 1 MINOR, aanbevolen als laatste ronde op deze
guard**: de import-check hierboven dekte alleen `from ...cva_autonomous_trigger import
<naam>` (`ast.ImportFrom`), niet `import ...cva_autonomous_trigger as m` gevolgd door
`m.cva_trigger._add_trigger(...)` (whole-module import + attribuutketen, `ast.Import`) --
zelf gereproduceerd: dit bleef groen terwijl het een levend pad naar
`_execute_breakthrough_session()` opent. De eerdere formulering "dicht alle drie
ontsnappingen" was daardoor een overclaim voor deze tweede importvorm. Toegevoegd: een
`ast.Import`-tak die elke whole-module-import van `cva_autonomous_trigger` zelf als
bevinding markeert (er is vandaag geen legitiem gebruik van een whole-module-import van dit
bestand -- het enige externe gebruik, `TriggerType` in `mode_manager.py`, gaat via de
ImportFrom-vorm en blijft dus terecht ongeraakt). Met beide importvormen gedekt is het
argument "elk gebruik vereist eerst een import, en beide importvormen worden bewaakt"
compleet -- een verdedigbaar stoppunt, in tegenstelling tot "we dekken een van de twee
importvormen".

**Zesde blinde review (2026-08-19)**: de claim "compleet" hierboven was ZELF een overclaim
-- de vorige ronde loste `import ...cva_autonomous_trigger as m` op (`ast.Import`), maar
een whole-module import kan OOK via `ast.ImportFrom` gespeld worden:
`from src.core.agents import cva_autonomous_trigger as m` of de relatieve vorm `from .
import cva_autonomous_trigger as m`. Bij beide is `node.module` het PAKKET
("src.core.agents", of `None` bij de relatieve vorm), niet de string
"cva_autonomous_trigger" -- de oude `"cva_autonomous_trigger" not in node.module`-filter
sloeg deze twee vormen dus onterecht over (en blokkeerde de relatieve vorm zelfs volledig
via `node.module is None`). Zelf gereproduceerd: beide vormen, gevolgd door
`m.cva_trigger._add_trigger(...)`, bleven groen. Gefixt: een aparte check op
`alias.name == "cva_autonomous_trigger"` in de ImportFrom-tak, VOOR de module-string-filter
-- vangt beide resterende vormen. Met nu VIER importvormen gedekt (`import X`, `import X as
m`, `from Y import X as m`, `from . import X as m`) is de eerdere "compleet"-claim nu pas
daadwerkelijk waar. Verdere AST-verfijning op deze guard (dynamische imports via
`importlib`, `getattr`-gebaseerde dispatch, etc.) blijft bewust buiten scope: vijf
opeenvolgende reviewrondes vonden een dalende reeks (twee echte functionele gaten, dan
syntax-randgevallen, dan importvorm-randgevallen) op een pad met nul echte aanroepers
overal in de repo (herhaaldelijk bevestigd) -- verdere verfijning zou geen drift meer
vangen maar alleen opzettelijke omzeiling door iemand met commit-rechten, en daar is geen
AST-guard tegen bestand. Elke toekomstige "compleet"-claim over deze guard moet, geleerd
van deze ronde, EXPLICIET de genoemde verzameling van vormen benoemen in plaats van het
woord "compleet" op zichzelf te gebruiken.

**Zevende blinde review (2026-08-19), GO, nul blokkerende bevindingen -- sluit de
reviewrondes.** Zelf gecontroleerd (niet aangenomen): een VIJFDE spelling bestond al sinds
ronde 3 en stond niet in de opsomming -- `from .cva_autonomous_trigger import <naam>`
(relatieve submodule-import van een naam, `node.module == "cva_autonomous_trigger"`,
`node.level == 1`) -- de ORIGINELE module-string-filter (ronde 3) vangt die al, want de
string staat wel letterlijk in `node.module`. Twee documentatienits, geen codewijziging:
(1) de opsomming hierboven noemt vier vormen, terwijl het er vijf zijn geworden; (2) de
herhaalde formulering "elk gebruik vereist eerst een import" is strikt onwaar -- een
parent-package-import gevolgd door een attribuutketen
(`agents.cva_autonomous_trigger.cva_trigger...`), een publieke-klasse-plus-private-methode
(`CVAAutonomousTrigger()._add_trigger(...)`, want de klasse staat bewust in `__all__`), en
een star-import (structureel onzichtbaar voor deze guard, maar onschadelijk gemaakt door
`__all__` zelf) blijven allemaal groen. De reviewer beoordeelde dit expliciet als de
deliberate-circumventie-kant van de grens die alle rondes al erkennen (niemand schrijft
een vier-diepe attribuutketen door een oudermodule, of construeert de klasse om een
private methode te raken, per ongeluk) en NIET als een achtste bevinding. Precieze
formulering: elk IDIOMATISCH gebruik vereist een import die deze module bij naam noemt, en
alle VIJF spellingen daarvan worden bewaakt (`import X`, `import X as m`, `from Y import X
as m`, `from . import X as m`, `from .X import <naam>`) -- niet "elk gebruik" zonder
kwalificatie.

**Achtste ronde (2026-08-26, ADR-036 OP-12 addendum SS8.2, GEEN blinde review -- bewuste
implementatie): `test_the_module_level_singleton_still_gets_no_oversight_gate` en zijn
helper `_module_level_cva_trigger_call_has_no_args()` zijn VERWIJDERD, niet stilzwijgend.**
De singleton (`cva_trigger = CVAAutonomousTrigger(...)`) krijgt nu een echte
`OversightGate` mee (`PolicyEngineAdapter()`/`AuditServiceAdapter()`, geen I/O bij
constructie -- zelfde patroon als `governance_helper.py`/`swarm_websocket_endpoints.py`),
zodat de zes `BREAKTHROUGH_ACTIONS`-eindoperaties daadwerkelijk getoetst worden zodra dit
pad ooit een aanroeper krijgt. Dat is precies de mutatie die de verwijderde test rood
liet worden -- terecht, want de oude invariant ("geen gate") is een BEWUSTE, geplande
wijziging geworden, geen regressie. **De inertie van dit pad wordt sindsdien uitsluitend
bewezen door de twee resterende tests hieronder** (`test_nothing_outside_the_module_starts_autonomous_operation`,
`test_nothing_outside_the_module_imports_the_singleton_or_its_start_functions`): een
gate hebben is onschadelijk zolang niemand van buitenaf de trigger-functies aanroept of
importeert -- dat blijft het enige dat telt. Beide bevestigd ONGEWIJZIGD correct te
blijven na de wijziging (ze scannen expliciet alles BUITEN `CVA_MODULE_PATH`, regel
224/273 -- een interne constructor-aanroep raakt geen van beide). ADR-036 OP-12 blijft
STATUS=OPEN (de autonomieladder zelf is nog niet gewired), maar het BEWIJS voor inertie
is verschoven van "geen gate" naar "geen externe aanroeper" -- zie de ADR-036-rij zelf
voor de volledige toelichting.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CVA_MODULE_PATH = REPO_ROOT / "src" / "core" / "agents" / "cva_autonomous_trigger.py"
SCAN_ROOTS = (REPO_ROOT / "src", REPO_ROOT / "scripts")

# Elke naam hier start (of omzeilt) het governance-blok richting een autonome/handmatige
# breakthrough-sessie. Zolang niemand ze buiten dit eigen bestand aanroept, kan de singleton
# nooit een echte sessie starten zonder dat het `oversight_gate is not None`-blok ertussen
# staat.
_AUTONOMOUS_START_FUNCTIONS = {
    "start_autonomous_operation",
    "start_cva_autonomous",
    "trigger_manual_breakthrough",
    "trigger_manual_cva_breakthrough",
}

_NON_IMPORT_TIME_BLOCKS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _live_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*.py") if "archive" not in p.parts)
    return files


def _parse(py_file: Path) -> ast.AST | None:
    try:
        return ast.parse(py_file.read_text(encoding="utf-8-sig"), filename=str(py_file))
    except SyntaxError:
        return None


def _iter_import_time_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """Elke statement die bij `import` daadwerkelijk uitvoert: de module-body zelf plus
    geneste `if`/`try`/`with`/`for`/`while`-blokken op modulniveau -- maar NOOIT de body van
    een `def`/`async def`/`class` (die voeren niet uit bij import).

    Dit is bewust GEEN `ast.walk()` op de hele module: die zou ook in functiebodies duiken
    (de precieze valkuil uit `valkuil_ast_walk_duikt_functiebodies_in.md`), en bewust GEEN
    `ast.iter_child_nodes()` (die kijkt alleen naar directe children en mist een
    module-level `if`).
    """
    collected: list[ast.stmt] = []
    for stmt in body:
        collected.append(stmt)
        if isinstance(stmt, _NON_IMPORT_TIME_BLOCKS):
            continue
        if isinstance(stmt, ast.Try):
            collected.extend(_iter_import_time_statements(stmt.body))
            for handler in stmt.handlers:
                collected.extend(_iter_import_time_statements(handler.body))
            collected.extend(_iter_import_time_statements(stmt.orelse))
            collected.extend(_iter_import_time_statements(stmt.finalbody))
        elif isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            collected.extend(_iter_import_time_statements(stmt.body))
            collected.extend(_iter_import_time_statements(stmt.orelse))
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            collected.extend(_iter_import_time_statements(stmt.body))
    return collected


def _external_autonomous_start_callers() -> list[str]:
    """Vindt elke aanroep van een naam in `_AUTONOMOUS_START_FUNCTIONS` BUITEN
    cva_autonomous_trigger.py zelf (zijn eigen interne aanroepen -- zoals de module-level
    wrapper die naar de instance-methode doorverwijst -- en het `__main__`-blok mogen wel)."""
    callers: list[str] = []
    for py_file in _live_python_files():
        if py_file == CVA_MODULE_PATH:
            continue
        tree = _parse(py_file)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in _AUTONOMOUS_START_FUNCTIONS:
                callers.append(f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} ({name})")
    return callers


# Derde blinde review (2026-08-19): het bovenstaande, aanroep-gebaseerde check matcht alleen
# de SYNTAX van een aanroep (`node.func`), niet elk GEBRUIK. Drie ontsnappingen bleven groen:
# een naam als referentie doorgeven (bv. `router.add_api_route("/x", trigger_manual_cva_
# breakthrough)`), een alias-import (`import ... as boot_breakthrough` gevolgd door
# `boot_breakthrough()`), en een aanroep op een GEIMPORTEERDE `cva_trigger`
# (`cva_trigger._add_trigger(...)`, een private methode die evengoed uitkomt bij
# `_execute_breakthrough_session()`). Alle drie vereisen EERST een import van `cva_trigger`
# of een van de vier namen -- een IMPORT-gebaseerde check subsumeert daarom alle drie.
_GOVERNANCE_BYPASSING_NAMES = _AUTONOMOUS_START_FUNCTIONS | {"cva_trigger"}


def _external_importers_of_governance_bypassing_names() -> list[str]:
    """Vindt elke import van `cva_trigger`/een van de vier startfuncties vanuit een ander
    bestand, in alle VIJF idiomatische spellingen (zevende blinde review, 2026-08-19,
    telde ze na en vond dat het er vijf zijn, niet vier):
    1. `from ...cva_autonomous_trigger import <naam>` (met of zonder alias) -- ronde 3.
    2. `from .cva_autonomous_trigger import <naam>` (relatieve submodule-import van een
       naam) -- ook ronde 3, de module-string zit letterlijk in `node.module`.
    3. `import ...cva_autonomous_trigger [as m]` (whole-module) -- ronde 4.
    4. `from <pakket> import cva_autonomous_trigger [as m]` (whole-module gespeld als
       ImportFrom, absoluut) -- ronde 5.
    5. `from . import cva_autonomous_trigger [as m]` (whole-module gespeld als
       ImportFrom, relatief) -- ook ronde 5.
    Spelling 3-5 vlagen de module-import zelf, ongeacht welke attribuutketen er later op
    volgt. Elk IDIOMATISCH gebruik vereist een van deze vijf spellingen -- een
    parent-package-import + attribuutketen, een publieke-klasse-plus-private-methode, of
    een star-import zijn bewust NIET gedekt (deliberate-circumventie-kant van de grens,
    zie moduledocstring, zevende blinde review)."""
    importers: list[str] = []
    for py_file in _live_python_files():
        if py_file == CVA_MODULE_PATH:
            continue
        tree = _parse(py_file)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                # Vijfde blinde review (2026-08-19): `from <package> import
                # cva_autonomous_trigger [as m]` (of de relatieve vorm `from . import
                # cva_autonomous_trigger as m`) is een DERDE spelling van een whole-module
                # import -- het IMPORTEERT DE MODULE ZELF ALS NAAM, via `ast.ImportFrom` in
                # plaats van `ast.Import`. `node.module` bevat dan het PAKKET
                # ("src.core.agents" of niets bij een relatieve import), niet
                # "cva_autonomous_trigger" -- de eerdere `"cva_autonomous_trigger" not in
                # node.module`-filter sloeg deze vorm daarom onterecht over (en een
                # relatieve import heeft `node.module is None`, wat de oude guard-conditie
                # zelfs volledig blokkeerde). Controleer dit EERST, los van `node.module`.
                for alias in node.names:
                    if alias.name == "cva_autonomous_trigger":
                        importers.append(
                            f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} "
                            f"(whole-module import via from-vorm: {alias.name})"
                        )
                if node.module is None or "cva_autonomous_trigger" not in node.module:
                    continue
                for alias in node.names:
                    if alias.name in _GOVERNANCE_BYPASSING_NAMES:
                        importers.append(
                            f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} (import {alias.name})"
                        )
            elif isinstance(node, ast.Import):
                # Vierde blinde review (2026-08-19): `from ... import <naam>` is niet de
                # enige importvorm. `import ...cva_autonomous_trigger as m` gevolgd door
                # `m.cva_trigger._add_trigger(...)` (whole-module import + attribuutketen)
                # ontsnapte aan de ImportFrom-check hierboven. Een whole-module import van
                # DIT bestand heeft vandaag geen legitiem doel (het enige externe gebruik,
                # `TriggerType` in `mode_manager.py`, gaat via `from ... import TriggerType`,
                # dus via de ImportFrom-tak) -- elke `import` van de module zelf is daarom
                # zelf al een bevinding, ongeacht wat ermee gedaan wordt na de import.
                for alias in node.names:
                    if alias.name.endswith("cva_autonomous_trigger"):
                        importers.append(
                            f"{py_file.relative_to(REPO_ROOT)}:{node.lineno} "
                            f"(whole-module import {alias.name})"
                        )
    return importers


def test_the_scan_finds_python_files_at_all() -> None:
    """Vangnet: klapt de padberekening, dan scannen beide tests hieronder nul bestanden en
    zijn beide eisen triviaal waar.

    Na zeven blinde reviewrondes op importvormen ontbrak juist dit eenvoudigste vangnet.
    SCAN_ROOTS verplaatsen, hernoemen, of een lege lijst -- niets hierboven zou dat
    opmerken zonder deze test.
    """
    files = _live_python_files()
    assert len(files) >= 2000, (
        f"Slechts {len(files)} bestanden gevonden onder {SCAN_ROOTS} -- dat lijkt een "
        "(bijna) lege scan. Zijn de paden verplaatst? Beide tests hieronder controleren "
        "dan vrijwel niets."
    )


def test_nothing_outside_the_module_starts_autonomous_operation() -> None:
    """OP-12 blijft alleen terecht OPEN-met-inert-bewijs zolang niemand deze functies
    van buitenaf aanroept om een autonome OF handmatige breakthrough-sessie te starten.

    Mutatiebewijs (2026-08-19, zelf bevestigd, elk apart teruggedraaid), een regel per naam
    in `_AUTONOMOUS_START_FUNCTIONS`:
    - een aanroep naar `start_cva_autonomous()` toevoegen in een ander `src/`-bestand -> rood.
    - een aanroep naar `start_autonomous_operation()` toevoegen -> rood.
    - een aanroep naar `trigger_manual_cva_breakthrough()` toevoegen (het pad dat het
      governance-blok volledig omzeilt) -> rood.
    - een aanroep naar `cva_trigger.trigger_manual_breakthrough()` toevoegen (attribute-vorm)
      -> rood.
    - dezelfde aanroep in een `__init__.py` (voorheen uitgesloten) -> rood.
    - dezelfde aanroep in `scripts/` (voorheen niet doorzocht) -> rood.
    """
    callers = _external_autonomous_start_callers()
    assert not callers, (
        f"Een autonoom- of handmatig-startpad wordt nu van buitenaf aangeroepen: {callers}. "
        "Dat maakt CVAAutonomousTrigger's governance-blok (en de eronder liggende "
        "PolicyEngine.AGENT_ENTRYPOINT_ACTIONS-classificatie van 'autonomous_breakthrough') "
        "mogelijk voor het eerst live. ADR-036 OP-12 moet dan herzien worden VOORDAT dit "
        "gemerged wordt (wire eerst de autonomieladder, of zet een feature-flag die in "
        "productie uit staat)."
    )


def test_nothing_outside_the_module_imports_the_singleton_or_its_start_functions() -> None:
    """Vangt wat het aanroep-gebaseerde check hierboven MIST: een naam als referentie
    doorgeven (bv. aan een routerregistratie), een alias-import, of een aanroep op een
    geimporteerde `cva_trigger` via een private methode (`_add_trigger` e.d.) die evengoed
    bij `_execute_breakthrough_session()` uitkomt. Alle drie vereisen EERST een import.

    Mutatiebewijs (2026-08-19, derde blinde review, zelf bevestigd, elk teruggedraaid):
    - `from ...cva_autonomous_trigger import trigger_manual_cva_breakthrough` in een ander
      bestand, zonder dat die naam ooit als `node.func` van een `Call` voorkomt (bv. alleen
      als argument aan `router.add_api_route(...)` doorgegeven) -> rood.
    - `from ...cva_autonomous_trigger import trigger_manual_cva_breakthrough as
      boot_breakthrough` -> rood (het check kijkt naar `alias.name`, de OORSPRONKELIJKE
      naam, niet de alias).
    - `from ...cva_autonomous_trigger import cva_trigger` in een ander bestand -> rood (dit
      dekt ook de `cva_trigger._add_trigger(...)`-ontsnapping: die aanroep is zelf niet in de
      naamlijst van de aanroep-check, maar de IMPORT die hem mogelijk maakt wel).

    Mutatiebewijs (2026-08-19, vijfde blinde review, zelf bevestigd, elk teruggedraaid):
    - `import ...cva_autonomous_trigger as m` gevolgd door
      `m.cva_trigger._add_trigger(...)` in een ander bestand -> rood (whole-module import,
      de eerdere `ast.ImportFrom`-tak zag dit niet, want er wordt geen naam uit de module
      "from"-geimporteerd).
    - `from ...cva_autonomous_trigger import TriggerType` (het enige echte externe gebruik,
      `mode_manager.py`) blijft GROEN -- `TriggerType` staat niet in
      `_GOVERNANCE_BYPASSING_NAMES` en is geen whole-module-import.

    Mutatiebewijs (2026-08-19, zesde blinde review, zelf bevestigd, elk teruggedraaid) --
    de vorige ronde loste alleen `import ...cva_autonomous_trigger as m` op; een
    whole-module import kan ook via `ast.ImportFrom` gespeld worden:
    - `from src.core.agents import cva_autonomous_trigger as m` gevolgd door
      `m.cva_trigger._add_trigger(...)` -> rood (pakket-relatieve whole-module-import).
    - `from . import cva_autonomous_trigger as m` gevolgd door
      `m.cva_trigger._add_trigger(...)` -> rood (relatieve whole-module-import;
      `node.module is None` voor deze vorm, dus de oude module-string-filter blokkeerde
      hem sowieso al voordat hij zelfs maar bij de naamcheck kwam).
    - `from ...cva_autonomous_trigger import TriggerType` blijft GROEN (opnieuw bevestigd
      na de fix -- `alias.name` is `"TriggerType"`, niet `"cva_autonomous_trigger"`).
    """
    importers = _external_importers_of_governance_bypassing_names()
    assert not importers, (
        f"cva_trigger of een van de vier startfuncties wordt nu elders geimporteerd: "
        f"{importers}. Elk gebruik van deze namen (rechtstreeks, via alias, of als "
        "referentie doorgegeven) vereist eerst een import -- deze import zelf is dus het "
        "vroegste, meest robuuste punt om te bewaken. ADR-036 OP-12 moet herzien worden "
        "VOORDAT dit gemerged wordt."
    )
