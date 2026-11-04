"""Architecture test: `current_user` moet correct geannoteerd zijn per dependency.

Achtergrond (OP-11 vervolgbevinding, 2026-07-31):
Deze codebase heeft TWEE soorten `current_user`, en dat is legitiem:

1. `src/core/auth/api_deps.get_current_user_dependency` (ook geimporteerd als
   `get_current_user`) geeft een **UserResponse** terug -- een Pydantic-model met
   attributen `id`, `email`, `tenant_id`. Dat model heeft GEEN `.get()`.
2. `src/core/api/dependencies.get_current_user` geeft een **ruwe JWT-payload dict**
   terug. Daar is `.get("user_id")` juist correct.

Het probleem: drie routermodules annoteerden `current_user: dict[str, Any]` terwijl ze
variant 1 als dependency gebruikten, en deden vervolgens `current_user.get("id")`. Dat
gooit op runtime een AttributeError. In `analytics_ingest/events_router.py` zat die call
in een `logger.info(extra=...)` binnen een `try`, met een generieke
`except Exception -> HTTP 500`: elke geslaagde analytics-batch eindigde dus in
"Failed to process event batch". Twee unit-tests stonden daarom al rood -- niet omdat ze
verouderd waren, maar omdat ze een live bug aanwezen die niemand oppakte.

Waarom deze test bestaat terwijl pyright de `.get()` zelf al vindt: pyright kan dat
alleen als de annotatie klopt. Zolang er `dict[str, Any]` staat, is `.get()` volgens de
types correct en zwijgt pyright. Deze test bewaakt dus de voorwaarde waaronder de
type-checker zijn werk kan doen.
"""

import ast
from pathlib import Path

SRC_ROOT = Path("src")

# Facades die de UserResponse-variant doorgeven. Wie hieruit importeert, krijgt een
# Pydantic-model -- geen dict.
USERRESPONSE_FACADES = {
    "src.core.auth.api_deps",
    "src.core.auth.dependencies",
    "src.core.api.v1.analytics_ingest.dependencies",
}

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _userresponse_dep_names(tree: ast.AST) -> set[str]:
    """Lokale namen waaronder een UserResponse-dependency is geimporteerd."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module not in USERRESPONSE_FACADES:
            continue
        for alias in node.names:
            if alias.name in {"get_current_user", "get_current_user_dependency"}:
                names.add(alias.asname or alias.name)
    return names


def _depends_target(default: ast.expr | None) -> str | None:
    """Naam van de dependency in `= Depends(<naam>)`."""
    if not isinstance(default, ast.Call):
        return None
    func = default.func
    is_depends = (isinstance(func, ast.Name) and func.id == "Depends") or (
        isinstance(func, ast.Attribute) and func.attr == "Depends"
    )
    if not is_depends or not default.args:
        return None
    arg = default.args[0]
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    return None


def _mismatches(path: Path, tree: ast.AST) -> list[str]:
    dep_names = _userresponse_dep_names(tree)
    if not dep_names:
        return []

    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        defaults: list[ast.expr | None] = [None] * (
            len(all_args) - len(args.defaults) - len(args.kwonlyargs)
        )
        defaults += list(args.defaults) + list(args.kw_defaults)

        for arg, default in zip(all_args, defaults, strict=False):
            if arg.arg != "current_user":
                continue
            if _depends_target(default) not in dep_names:
                continue
            annotation = ast.unparse(arg.annotation) if arg.annotation else "<geen>"
            if "dict" in annotation:
                problems.append(
                    f"{path.as_posix()}:{node.lineno} {node.name}: "
                    f"`current_user: {annotation}` maar de dependency geeft een "
                    "UserResponse (Pydantic, geen .get())"
                )
    return problems


def _index() -> tuple[list[tuple[Path, ast.AST]], list[str]]:
    """(bestand+AST-paren, paden die niet gelezen/geparsed konden worden)."""
    bomen: list[tuple[Path, ast.AST]] = []
    fouten: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{path.as_posix()}: {exc}")
            continue
        bomen.append((path, tree))
    return bomen, fouten


def test_all_src_files_parse_for_current_user_scan() -> None:
    """Vangnet: een onleesbaar bestand mag deze guard niet stilzwijgend blind maken.

    De totaaldrempel op test_scan_finds_userresponse_dependency_users (>=5 modules)
    beschermt alleen tegen een lege scan -- die drempel wordt door de gezonde modules
    gehaald, dus het ene overgeslagen bestand met precies het defect dat deze guard moet
    vangen blijft daaronder onzichtbaar. Dit vangnet toetst per bestand.
    """
    _, fouten = _index()
    assert not fouten, (
        "Deze bestanden onder src/ konden niet gelezen/geparsed worden en zijn NIET "
        "gecontroleerd op een verkeerd geannoteerde current_user:\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )


def test_current_user_is_not_annotated_as_dict_when_dependency_returns_a_model() -> None:
    """Een UserResponse-dependency mag niet als dict geannoteerd worden."""
    bomen, _fouten = _index()
    violations: list[str] = []
    for path, tree in bomen:
        violations.extend(_mismatches(path, tree))

    assert not violations, (
        "`current_user` verkeerd geannoteerd: de dependency geeft een UserResponse, geen "
        "dict. Met een dict-annotatie ziet pyright een `.get()`-aanroep als correct, "
        "terwijl die op runtime een AttributeError geeft:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_scan_finds_userresponse_dependency_users() -> None:
    """Vangnet tegen een vacuum-pass als de facade-namen veranderen."""
    bomen, _fouten = _index()
    modules_using_dep = sum(1 for _, tree in bomen if _userresponse_dep_names(tree))

    assert modules_using_dep >= 5, (
        f"Verwacht minimaal 5 modules die een UserResponse-dependency importeren, "
        f"gevonden {modules_using_dep} -- de facade-lijst in deze test is verouderd."
    )
