"""Architecture test: importeren van een module mag de globale Dramatiq-broker niet kapen.

Achtergrond (2026-08-01, ADR-036 Fase B dag 1):
`src/core/learning/worker.py` riep op module-niveau `dramatiq.set_broker(_broker)` aan.
Omdat `@dramatiq.actor` bij DECORATIE bindt aan `get_broker()`, bepaalde daarmee de
IMPORTVOLGORDE op welke broker actors terechtkwamen -- in productie net zo goed als in
tests. `src/workers/actors.py` documenteerde dat zelfs als load-bearing regel:

    "IMPORTANT: this must come BEFORE the actor side-effect imports below,
     because workflow_worker calls dramatiq.set_broker() at import time.
     Any actor module imported BEFORE this line may register on the wrong broker."

Correctheid die afhangt van de volgorde van import-statements is per definitie niet
toekomstbestendig. Het werd zichtbaar toen tests/core onder de CI-gate kwam: het
importeren van de learning-worker maakte 4 tests in drie andere bestanden rood. In
productie is het gevaarlijker dan een rode test -- achtergrondtaken kunnen op een broker
landen die niemand uitleest, en dan gebeurt er stilletjes niets.

De oplossing in learning/worker.py: elke actor bindt EXPLICIET (`@dramatiq.actor(
broker=_broker, ...)`) en de entrypoint benoemt de broker bij naam
(`dramatiq src.core.learning.worker:_broker`). Geen globale staat, geen volgorde-effect.
"""

import ast
import re
from functools import lru_cache
from pathlib import Path

SRC_ROOT = Path("src")
REPO_ROOT = Path(".")

# Modules die vandaag nog wel op module-niveau set_broker() aanroepen. Leeg sinds ADR-036 OP-13 (2026-10-21):
# `src/workers/workflow_worker.py` zet geen procesbrede broker meer; de actors binden expliciet aan
# `workflow_broker` (src/core/tasks/dramatiq_broker.py). Zie ook test_geen_procesbrede_broker.py.
KNOWN_SET_BROKER_AT_IMPORT: set[str] = set()


def _module_level_set_broker_calls(tree: ast.Module) -> list[int]:
    """Regelnummers van set_broker()-aanroepen die BIJ IMPORT worden uitgevoerd.

    Wel meegeteld: alles op module-niveau, ook binnen een `if`/`try`/`with`/`for` --
    die blokken draaien immers gewoon bij import.
    Niet meegeteld: aanroepen in een functie- of klasse-body; die zijn lazy.

    NB: een eerdere versie liep per top-level node met ast.walk en sloeg het hele blok
    over zodra daar ergens een functie in stond. Daardoor miste hij precies het patroon
    in workflow_worker.py (`if _DRAMATIQ_AVAILABLE:` met zowel een set_broker-aanroep
    als een geneste functie) en was de guard op dat punt vacuum.
    """
    hits: list[int] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue  # lazy: draait pas bij aanroep
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "set_broker"
            ):
                hits.append(child.lineno)
            visit(child)

    visit(tree)
    return hits


@lru_cache(maxsize=1)
def _scan_src_for_set_broker() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(violations, fouten) over alle bestanden onder SRC_ROOT.

    Voorheen ving dit een stille except (SyntaxError, UnicodeDecodeError): continue
    ZONDER enige telling of vloer -- in tegenstelling tot de andere test in dit bestand
    (test_compose_entrypoints_name_an_existing_broker, die wel `assert checked >= 1`
    heeft). Een verplaatste SRC_ROOT of een overgeslagen bestand met een nieuwe,
    ongeoorloofde module-level set_broker()-aanroep zou hier onopgemerkt blijven.
    """
    violations: list[str] = []
    fouten: list[str] = []

    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{path}: {exc}")
            continue
        posix = path.as_posix()
        for lineno in _module_level_set_broker_calls(tree):
            if posix in KNOWN_SET_BROKER_AT_IMPORT:
                continue
            violations.append(f"{posix}:{lineno}")

    return tuple(violations), tuple(fouten)


def test_no_source_file_is_silently_unreadable_or_unparseable() -> None:
    """Vangnet: een overgeslagen bestand mag hier niet stil verdwijnen."""
    _, fouten = _scan_src_for_set_broker()
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd "
        "op een module-level set_broker()-aanroep:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_the_scan_actually_scans_files() -> None:
    """Vangnet: een verplaatste/hernoemde SRC_ROOT zou de scan stil laten leeglopen."""
    aantal = len(list(SRC_ROOT.rglob("*.py")))
    assert aantal >= 1500, (
        f"Slechts {aantal} bestanden gevonden onder {SRC_ROOT} (verwacht >= 1500). Is "
        "SRC_ROOT verplaatst of hernoemd? Dan controleert deze guard niets meer."
    )


def test_no_new_module_level_set_broker() -> None:
    """Een module mag bij import de procesbrede broker niet vervangen."""
    violations, _ = _scan_src_for_set_broker()

    assert not violations, (
        "set_broker() op module-niveau vervangt de procesbrede Dramatiq-broker zodra de "
        "module wordt geimporteerd; welke actors waar landen hangt dan af van de "
        "importvolgorde:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nBind actors in plaats daarvan expliciet: @dramatiq.actor(broker=<broker>, ...) "
        "en laat de entrypoint de broker benoemen (`dramatiq module:broker`)."
    )


def test_known_exceptions_still_exist() -> None:
    """Een uitzondering die niet meer bestaat moet uit de lijst -- anders rot hij dicht."""
    missing = [p for p in KNOWN_SET_BROKER_AT_IMPORT if not Path(p).exists()]
    assert not missing, f"KNOWN_SET_BROKER_AT_IMPORT noemt niet-bestaande bestanden: {missing}"

    stale = []
    for posix in KNOWN_SET_BROKER_AT_IMPORT:
        tree = ast.parse(Path(posix).read_text(encoding="utf-8"))
        if not _module_level_set_broker_calls(tree):
            stale.append(posix)
    assert not stale, (
        f"Deze bestanden staan als uitzondering maar roepen set_broker() niet meer aan op "
        f"module-niveau: {stale}. Haal ze uit KNOWN_SET_BROKER_AT_IMPORT."
    )


def test_learning_worker_actors_bind_to_their_own_broker() -> None:
    """Alle actors in de learning-worker binden expliciet, niet via globale staat."""
    path = SRC_ROOT / "core" / "learning" / "worker.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    unbound: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            target = dec.func
            if not (isinstance(target, ast.Attribute) and target.attr == "actor"):
                continue
            if not any(kw.arg == "broker" for kw in dec.keywords):
                unbound.append(f"{node.name}:{node.lineno}")

    assert not unbound, (
        "Deze actors binden aan de GLOBALE broker in plaats van aan _broker; daarmee komt "
        f"de importvolgorde weer terug: {unbound}"
    )


def test_compose_entrypoints_name_an_existing_broker() -> None:
    """`dramatiq module:attr` in compose moet een bestaand Broker-attribuut noemen.

    Zonder deze koppeling kan de code de broker hernoemen terwijl de deployment het oude
    pad blijft aanroepen -- de CLI valt dan stil terug op get_broker() en de worker leest
    van de verkeerde broker.
    """
    pattern = re.compile(r'"dramatiq",\s*"([a-zA-Z0-9_.]+):([a-zA-Z0-9_]+)"')
    checked = 0
    problems: list[str] = []

    for compose in sorted(REPO_ROOT.glob("docker-compose*.yml")):
        text = compose.read_text(encoding="utf-8")
        for module_path, attr in pattern.findall(text):
            checked += 1
            rel = Path(module_path.replace(".", "/") + ".py")
            if not rel.exists():
                problems.append(f"{compose.name}: module {module_path} bestaat niet")
                continue
            tree = ast.parse(rel.read_text(encoding="utf-8"))
            names = {
                t.id
                for node in tree.body
                if isinstance(node, ast.Assign)
                for t in node.targets
                if isinstance(t, ast.Name)
            }
            if attr not in names:
                problems.append(
                    f"{compose.name}: {module_path} definieert geen module-level `{attr}`"
                )

    assert not problems, "Compose-entrypoints wijzen naar een niet-bestaande broker:\n" + "\n".join(
        f"  - {p}" for p in problems
    )
    assert checked >= 1, (
        "Geen enkele `dramatiq module:attr`-entrypoint gevonden in docker-compose*.yml -- "
        "de scan matcht het patroon niet meer."
    )
