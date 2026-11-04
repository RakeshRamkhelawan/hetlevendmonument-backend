"""Gemeten inventarisatie van src/: wat bestaat er, wat is bereikbaar, wat doet niets.

Waarom dit een SCRIPT is en geen rapport
----------------------------------------
De auditrapporten van 2026-07-03 waren binnen twee maanden onbruikbaar als
werkdocument: ze beschreven een toestand die verlopen was. Een meting die je
opnieuw kunt draaien verloopt niet. Draai dit wekelijks en vergelijk het getal.

Wat het WEL bewijst
-------------------
- Welke modules er zijn, hoe groot, en wie ze importeert (AST, geen tekstzoekopdracht).
- Of een module bereikbaar is vanaf een echt startpunt (FastAPI-app, Dramatiq-taken),
  inclusief de dynamische ``importlib.import_module("...")``-route die de
  ADR-033-registries gebruiken. Zonder die stap meet je de halve app als dood.
- Welke functies succes melden zonder werk te doen -- de faalvorm die een jaar lang
  onzichtbaar bleef omdat er nooit iets rood werd (23 afdelingsagents met
  ``act() -> success=True``, ChiefOrchestrator met status "delegated", de retentietaak
  met "completed, 0 verwijderd").
- Welke modules door tests worden aangeraakt, en welke symbolen tests WEGMOCKEN.
  Een module die alleen in gemockte vorm voorkomt is niet getest maar nagebootst;
  dat is precies hoe ``_resolve_agent`` jaren onzichtbaar kapot kon zijn.

Wat het NIET bewijst
--------------------
- Niet dat bereikbare code correct is. Bereikbaar is geen synoniem voor werkend.
- Niet dat onbereikbare code weg kan. ``department_orchestrator.py`` heeft geen
  levende klasse-aanroeper maar levert wel de ``Department``-enum aan 13 modules.
- Niets over de frontend. Dit meet uitsluitend ``src/``.

Gebruik
-------
    python scripts/codebase_inventory.py
    python scripts/codebase_inventory.py --out C:/tmp/inventory.csv
    python scripts/codebase_inventory.py --list-hollow
    python scripts/codebase_inventory.py --list-unreachable --top 40
"""

from __future__ import annotations

import argparse
import ast
import csv
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Startpunten: elk proces dat in een compose-bestand of Dockerfile daadwerkelijk wordt
# gestart. Wie hier iets vergeet, boekt draaiende code als dood -- en gooit hem daarna
# mogelijk weg. Gemeten 2026-09-26: met alleen de eerste drie stond `src/workers/scheduler.py`
# (662 regels, eigen container in docker-compose.yml en docker-compose.prod.yml, nul tests)
# als ONBEREIKBAAR geboekt. Het toevoegen van de vijf regels hieronder bracht 859 -> 825.
#
# Per regel de vindplaats, zodat een volgende lezer kan narekenen dat hij nog klopt:
#   src.main                    gunicorn/uvicorn in scripts/entrypoint-prod.sh:76 en -dev.sh:65
#   src.core.app_factory        bouwt de app
#   src.core.app_lifespan       draait bij opstarten
#   src.workers.workflow_worker dramatiq-broker, docker-compose.yml:224 + Dockerfile:168
#   src.workers.actors          dramatiq-actormodule, zelfde regel
#   src.workers.scheduler       python -m, docker-compose.yml:268 + .prod.yml:195
#   src.core.learning.worker    dramatiq-broker, docker-compose.yml:405, .dev.yml:136, .prod.yml:140
#   src.core.als.bonlezer.worker  dramatiq-broker, docker-compose.yml (dienst bonlezer-worker)
#   src.alembic.env             alembic upgrade head in beide entrypoint-scripts
#
# Bewaakt door tests/architecture/test_de_startpunten_dekken_wat_er_echt_draait.py.
ROOTS = [
    "src.main",
    "src.core.app_factory",
    "src.core.app_lifespan",
    "src.workers.workflow_worker",
    "src.workers.actors",
    "src.workers.scheduler",
    "src.core.learning.worker",
    "src.core.als.bonlezer.worker",
    "src.alembic.env",
    # Nachtelijke job levendmonument-opschonen (infra/main-levendmonument-prod.bicep):
    # python -m src.core.services.foundation_leerlingantwoorden (BE-EP-055, BE-EP-056).
    "src.core.services.foundation_leerlingantwoorden",
]
ROOT_PREFIXES = ["src.core.tasks."]

SUCCESS_KEYS = ("success", "ok")
SUCCESS_STATUSES = ("delegated", "completed", "success", "klaar")


@dataclass
class ModuleInfo:
    module: str
    path: str
    loc: int = 0
    parse_error: str = ""
    imports: set = field(default_factory=set)
    dynamic_imports: set = field(default_factory=set)
    n_functions: int = 0
    hollow: list = field(default_factory=list)
    success_no_work: list = field(default_factory=list)


def git_files(pattern: str) -> list:
    """Bestandslijst uit git, niet van schijf.

    `.git/info/exclude` verborg eerder 1816 GETRACKTE bestanden voor een
    tekstzoekopdracht. git ls-files is de enige bron die dat niet overkomt.
    """
    out = subprocess.run(
        ["git", "ls-files", pattern],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line.endswith(".py")]


def to_module(path: str) -> str:
    stem = path[:-3]
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return stem.replace("/", ".")


def resolve_relative(current: str, node: ast.ImportFrom, is_pkg: bool) -> str:
    """`from .x import y` oplossen naar een absolute modulenaam."""
    parts = current.split(".")
    base = parts if is_pkg else parts[:-1]
    up = node.level - 1
    if up:
        base = base[:-up] if up <= len(base) else []
    if node.module:
        return ".".join(list(base) + [node.module])
    return ".".join(base)


def strip_docstring(body: list) -> list:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            return body[1:]
    return body


def is_empty_value(node) -> bool:
    """Geeft deze return-waarde aantoonbaar niets terug?"""
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return node.value is None or node.value == ""
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return not node.elts
    return False


def claims_success(node) -> bool:
    """`return X(success=True)` of `return {"status": "success"}` als volledige functie-inhoud.

    Dit is de faalvorm die niet opvalt: geen fout, geen rode test, geen logregel.
    Een stub die NotImplementedError gooit wordt in een dag gevonden; deze niet.
    """
    if isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant):
                if k.value in SUCCESS_KEYS and isinstance(v, ast.Constant) and v.value is True:
                    return True
                if (
                    k.value == "status"
                    and isinstance(v, ast.Constant)
                    and str(v.value).lower() in SUCCESS_STATUSES
                ):
                    return True
        return False
    if not isinstance(node, ast.Call):
        return False
    for kw in node.keywords:
        if kw.arg in SUCCESS_KEYS and isinstance(kw.value, ast.Constant):
            if kw.value.value is True:
                return True
        if kw.arg == "status" and isinstance(kw.value, ast.Constant):
            if str(kw.value.value).lower() in SUCCESS_STATUSES:
                return True
    return False


def is_abstract_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        name = ""
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Attribute):
            name = dec.attr
        if name in ("abstractmethod", "overload"):
            return True
    return False


def is_protocol_or_abc_class(class_node: ast.ClassDef) -> bool:
    if class_node.name.endswith("Protocol"):
        return True
    for base in class_node.bases:
        name = ""
        if isinstance(base, ast.Name):
            name = base.id
        elif isinstance(base, ast.Attribute):
            name = base.attr
        if name in ("Protocol", "ABC"):
            return True
    return False


def is_base_template_class(class_node: ast.ClassDef) -> bool:
    name = class_node.name
    return (
        name.startswith("Base")
        or name.startswith("Stub")
        or name.startswith("Dummy")
        or name.endswith("Strategy")
        or name.endswith("Supervisor")
        or name.endswith("Agent")
        or name.endswith("Manager")
        or name.endswith("CEO")
        or name.endswith("Monitor")
        or name.endswith("Provider")
    )


def classify_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    in_interface_contract: bool = False,
    in_base_template: bool = False,
) -> str:
    """'hollow', 'success_no_work' of '' voor een functiedefinitie."""
    body = strip_docstring(node.body)
    if not body:
        return "" if in_interface_contract else "hollow"
    if len(body) != 1:
        return ""
    stmt = body[0]
    # PEP 492 / PEP 343: Context manager exit (__exit__ and __aexit__) with pass or
    # returning False/None is standard semantics for no-op cleanup with exception propagation.
    if node.name in ("__exit__", "__aexit__"):
        if isinstance(stmt, ast.Pass):
            return ""
        if isinstance(stmt, ast.Return) and (
            is_empty_value(stmt.value) or (isinstance(stmt.value, ast.Constant) and stmt.value.value is False)
        ):
            return ""

    # Property setters with pass (e.g. read-only proxies like _LazyProxy)
    is_setter = any(
        isinstance(dec, ast.Attribute) and dec.attr == "setter"
        for dec in node.decorator_list
    )
    if is_setter and isinstance(stmt, ast.Pass):
        return ""

    if isinstance(stmt, ast.Pass):
        return "" if in_interface_contract else "hollow"
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        if stmt.value.value is Ellipsis:
            return "" if in_interface_contract else "hollow"
        return ""
    if isinstance(stmt, ast.Return):
        if is_empty_value(stmt.value):
            return "" if in_interface_contract else "hollow"
        if claims_success(stmt.value):
            return "success_no_work"
        return ""
    if isinstance(stmt, ast.Raise):
        exc = stmt.exc
        name = ""
        if isinstance(exc, ast.Name):
            name = exc.id
        elif isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            name = exc.func.id
        if name == "NotImplementedError":
            return "" if (in_interface_contract or in_base_template) else "hollow"
    return ""


def analyse_tree(tree: ast.AST, module: str, path: str) -> ModuleInfo:
    info = ModuleInfo(module=module, path=path)
    is_pkg = path.endswith("/__init__.py")
    is_protocol_file = (
        path.endswith("protocol.py")
        or path.endswith("protocols.py")
        or "/typing/" in path.replace("\\", "/")
    )

    class InventoryVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.current_classes: list[ast.ClassDef] = []
            self.in_import_error: bool = False

        def visit_Try(self, node: ast.Try) -> None:
            for stmt in node.body:
                self.visit(stmt)
            for handler in node.handlers:
                is_import_err = False
                if handler.type:
                    if isinstance(handler.type, ast.Name) and handler.type.id in (
                        "ImportError",
                        "ModuleNotFoundError",
                    ):
                        is_import_err = True
                    elif isinstance(handler.type, ast.Tuple):
                        for elt in handler.type.elts:
                            if isinstance(elt, ast.Name) and elt.id in (
                                "ImportError",
                                "ModuleNotFoundError",
                            ):
                                is_import_err = True
                prev = self.in_import_error
                if is_import_err:
                    self.in_import_error = True
                for stmt in handler.body:
                    self.visit(stmt)
                self.in_import_error = prev
            for stmt in node.orelse:
                self.visit(stmt)
            for stmt in node.finalbody:
                self.visit(stmt)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.current_classes.append(node)
            self.generic_visit(node)
            self.current_classes.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._handle_func(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._handle_func(node)
            self.generic_visit(node)

        def _handle_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            if self.in_import_error:
                # Fallback stub classes inside except ImportError (CLAUDE.md rule 105)
                # are stubs to prevent import crashes and never executed if package is present.
                return

            info.n_functions += 1
            in_interface = False
            in_base_template = False
            if is_protocol_file or is_abstract_function(node):
                in_interface = True
            elif self.current_classes:
                current_cls = self.current_classes[-1]
                if is_protocol_or_abc_class(current_cls):
                    in_interface = True
                elif is_base_template_class(current_cls):
                    in_base_template = True

            verdict = classify_function(
                node, in_interface_contract=in_interface, in_base_template=in_base_template
            )
            if verdict == "hollow":
                info.hollow.append(node.name)
            elif verdict == "success_no_work":
                info.success_no_work.append(node.name)

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                info.imports.add(alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.level:
                base = resolve_relative(info.module, node, is_pkg)
            else:
                base = node.module or ""
            if not base:
                return
            info.imports.add(base)
            for alias in node.names:
                if alias.name != "*":
                    info.imports.add(f"{base}.{alias.name}")

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "import_module" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    info.dynamic_imports.add(arg.value)
            self.generic_visit(node)

        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str):
                if node.value.startswith("src.") and " " not in node.value:
                    info.dynamic_imports.add(node.value)

    visitor = InventoryVisitor()
    visitor.visit(tree)
    return info


def analyse(path: str) -> ModuleInfo:
    info = ModuleInfo(module=to_module(path), path=path)
    try:
        text = (REPO / path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        info.parse_error = "read: {}".format(exc)
        return info
    info.loc = text.count("\n")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        info.parse_error = "syntax: regel {}".format(exc.lineno)
        return info

    parsed_info = analyse_tree(tree, info.module, path)
    parsed_info.loc = info.loc
    return parsed_info


def build_graph(mods: dict):
    """Importgraaf plus de verzameling die vanaf een startpunt bereikbaar is."""
    edges = defaultdict(set)
    known = set(mods)
    for mod, info in mods.items():
        for target in info.imports | info.dynamic_imports:
            if target in known:
                edges[mod].add(target)
            else:
                parent = target.rsplit(".", 1)[0]
                if parent in known:
                    edges[mod].add(parent)

    roots = set(r for r in ROOTS if r in mods)
    for mod in mods:
        if any(mod.startswith(prefix) for prefix in ROOT_PREFIXES):
            roots.add(mod)

    seen = set()
    queue = deque(roots)
    while queue:
        cur = queue.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        queue.extend(edges[cur] - seen)
    return edges, seen, roots


def test_signals():
    """Welke modules raken tests aan, en welke symbolen mocken ze weg?"""
    touched = defaultdict(int)
    mocked = defaultdict(int)
    for path in git_files("tests"):
        try:
            tree = ast.parse((REPO / path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("src."):
                    touched[node.module] += 1
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in ("patch", "patch_object") and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value.startswith("src."):
                            mocked[arg.value.rsplit(".", 1)[0]] += 1
    return touched, mocked


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemeten inventarisatie van src/")
    parser.add_argument("--out", help="schrijf de volledige tabel naar dit CSV-bestand")
    parser.add_argument("--list-hollow", action="store_true")
    parser.add_argument("--list-unreachable", action="store_true")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args()

    mods = {}
    for path in git_files("src"):
        info = analyse(path)
        mods[info.module] = info

    edges, reachable, roots = build_graph(mods)
    in_degree = defaultdict(int)
    for targets in edges.values():
        for target in targets:
            in_degree[target] += 1

    touched, mocked = test_signals()

    rows = []
    for mod, info in sorted(mods.items()):
        rows.append(
            {
                "module": mod,
                "path": info.path,
                "loc": info.loc,
                "imported_by": in_degree[mod],
                "reachable": int(mod in reachable),
                "functions": info.n_functions,
                "hollow": len(info.hollow),
                "success_no_work": len(info.success_no_work),
                "test_imports": touched.get(mod, 0),
                "mock_targets": mocked.get(mod, 0),
                "parse_error": info.parse_error,
            }
        )

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print("geschreven: {} ({} modules)".format(args.out, len(rows)))

    total = max(len(rows), 1)
    unreachable = [r for r in rows if not r["reachable"]]
    untested = [r for r in rows if r["test_imports"] == 0]
    mocked_only = [r for r in rows if r["mock_targets"] > 0 and r["test_imports"] == 0]
    parse_errors = [r for r in rows if r["parse_error"]]

    print("")
    print("=== INVENTARISATIE src/ ===")
    print("startpunten                     {}".format(len(roots)))
    print("modules                         {}".format(len(rows)))
    print("regels totaal                   {}".format(sum(r["loc"] for r in rows)))
    print(
        "NIET bereikbaar vanaf start     {}  ({}%)".format(
            len(unreachable), 100 * len(unreachable) // total
        )
    )
    print(
        "geen enkele test importeert     {}  ({}%)".format(
            len(untested), 100 * len(untested) // total
        )
    )
    print("alleen weggemockt, nooit echt   {}".format(len(mocked_only)))
    print("holle functies                  {}".format(sum(r["hollow"] for r in rows)))
    print("succes-zonder-werk functies     {}".format(sum(r["success_no_work"] for r in rows)))
    if parse_errors:
        print("niet te parsen                  {}".format(len(parse_errors)))

    if args.list_hollow:
        print("")
        print("=== SUCCES ZONDER WERK (de onzichtbare faalvorm) ===")
        for mod, info in sorted(mods.items()):
            for fn in info.success_no_work:
                print("  {}::{}".format(info.path, fn))

    if args.list_unreachable:
        print("")
        print("=== ONBEREIKBAAR, grootste {} ===".format(args.top))
        ranked = sorted(unreachable, key=lambda r: -r["loc"])[: args.top]
        for row in ranked:
            print(
                "  {:>5} regels  imported_by={:<3} {}".format(
                    row["loc"], row["imported_by"], row["path"]
                )
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
