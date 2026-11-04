"""Preventie-test: Dramatiq dict-payload actors valideren tenant_id (ADR-003).

AUDIT-SINGLE-TENANT-DB01 S7 -- regressie-guard voor TI-004 (execute_workflow_step
verwerkte task_data zonder tenant_id-validatie, cross-tenant bypass mogelijk).

Twee categorien actors bestaan in deze codebase:

1. Expliciet getypeerde parameters (bijv. `async def foo(agent_id: str, tenant_id: int)`).
   Deze categorie is AL veilig: Python's type-systeem dwingt af dat elke .send()
   caller tenant_id meegeeft (TypeError bij ontbrekend argument). Geen aparte
   test nodig -- dit is de meerderheid van de actors in src/workers/actors.py,
   src/core/workflow/worker.py, etc.

2. Dict-payload parameters (bijv. `def foo(task_data: dict[str, object])`).
   Hier is er GEEN taalgarantie -- een dict kan altijd een sleutel missen.
   Deze actors MOETEN zelf (of via een direct aangeroepen collaborator-module)
   tenant_id valideren en falen (raise/log+return) als die ontbreekt.

Deze test scant de bekende dict-payload-actor-modules op het validatiepatroon EN
scant de rest van src/ op NIEUWE dict-payload actors die nog niet in de bekende
lijst staan (zodat een toekomstige actor niet ongemerkt de garantie omzeilt).

Guard-detectie is AST-gekoppeld (_has_tenant_id_guard): een `if`-statement wiens
conditie tenant_id (of een lokale naam afgeleid van `.get("tenant_id")`/
`["tenant_id"]`) toetst EN wiens body raise/return bevat. Een guard-string in
een comment, docstring, of dode/ongebruikte functie telt NIET mee -- alleen
code die daadwerkelijk in het controlepad zit (S7 review-fix: was voorheen een
lexicale substring-check over de volledige module-source).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path("src")

# (actor-module, [collaborator-modules die de daadwerkelijke validatie uitvoeren])
# Actor-modules die zelf geen guard hebben omdat ze delegeren naar een
# service-laag die wel valideert, moeten hun collaborator hier opnemen --
# anders faalt de test terecht.
_DICT_PAYLOAD_ACTOR_MODULES: list[tuple[Path, list[Path]]] = [
    (SRC_ROOT / "core" / "tasks" / "workflow_tasks.py", []),
    (SRC_ROOT / "core" / "tasks" / "cva_tasks.py", []),
    (SRC_ROOT / "core" / "learning" / "worker.py", [SRC_ROOT / "core" / "learning" / "service.py"]),
]


def _is_actor_decorator(decorator: ast.expr) -> bool:
    # `workflow_actor` is de wrapper die de actor aan de workflowbroker bindt (ADR-036 OP-13); hij telt als actor.
    if isinstance(decorator, ast.Attribute):
        return decorator.attr in ("actor", "workflow_actor")
    if isinstance(decorator, ast.Call):
        return _is_actor_decorator(decorator.func)
    if isinstance(decorator, ast.Name):
        return decorator.id in ("actor", "workflow_actor")
    return False


def _has_dict_payload_param(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True als de actor een dict-typed parameter heeft EN geen aparte, expliciet
    getypeerde (niet-dict) tenant_id-parameter -- die laatste plaatst de actor al in
    categorie 1 (type-systeem-afgedwongen), ongeacht andere dict-typed hulpvelden
    (bijv. `details: dict`) elders in de signature. AUDIT-ARCH-2026-07-02 Groep 2:
    write_audit_log_task(tenant_id: int, ..., details: dict | None) is zo'n geval.
    """
    has_dict_param = False
    has_typed_tenant_id_param = False
    for arg in node.args.args:
        if arg.annotation is None:
            continue
        dump = ast.dump(arg.annotation).lower()
        if "dict" in dump:
            has_dict_param = True
        elif arg.arg == "tenant_id":
            has_typed_tenant_id_param = True
    return has_dict_param and not has_typed_tenant_id_param


def _find_dict_payload_actors(
    tree: ast.Module,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Vind functies gedecoreerd met @dramatiq.actor die een dict-typed parameter hebben."""
    actors = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_actor_decorator(d) for d in node.decorator_list):
            continue
        if _has_dict_payload_param(node):
            actors.append(node)
    return actors


def _tenant_id_bound_names(func: ast.AST) -> set[str]:
    """Vind lokale namen toegekend via `.get("tenant_id")` of `["tenant_id"]`.

    Bijv. `_tid_raw = task_data_dict.get("tenant_id")` -> {"_tid_raw"}.
    """
    names: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        is_tenant_source = False
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "get"
            and value.args
            and isinstance(value.args[0], ast.Constant)
            and value.args[0].value == "tenant_id"
        ):
            is_tenant_source = True
        if (
            isinstance(value, ast.Subscript)
            and isinstance(value.slice, ast.Constant)
            and value.slice.value == "tenant_id"
        ):
            is_tenant_source = True
        if is_tenant_source:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _if_body_fails_closed(if_node: ast.If) -> bool:
    """True als de if-body een Raise of Return bevat (fail-closed controlepad)."""
    for stmt in if_node.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, (ast.Raise, ast.Return)):
                return True
    return False


def _has_tenant_id_guard(tree: ast.Module) -> bool:
    """AST-gekoppelde guard-detectie: een `if`-statement wiens conditie tenant_id
    (of een lokale naam afgeleid van `.get("tenant_id")`/`["tenant_id"]`) toetst
    EN wiens body faalt (raise/return). Dit is gekoppeld aan het daadwerkelijke
    controlepad -- een guard-string in een comment, docstring, of dode functie
    telt NIET mee, want die zit niet in een `ast.If.test`.
    """
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tenant_names = _tenant_id_bound_names(func) | {"tenant_id"}
        for node in ast.walk(func):
            if not isinstance(node, ast.If):
                continue
            test_dump = ast.dump(node.test)
            if any(name in test_dump for name in tenant_names) and _if_body_fails_closed(node):
                return True
    return False


def test_dict_payload_dramatiq_actors_validate_tenant_id() -> None:
    """Elke bekende dict-payload Dramatiq actor moet tenant_id valideren (ADR-003)."""
    violations = []

    for module_path, collaborators in _DICT_PAYLOAD_ACTOR_MODULES:
        assert module_path.exists(), f"{module_path}: bestand bestaat niet -- test-lijst verouderd"

        module_source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(module_source)
        actors = _find_dict_payload_actors(tree)
        assert actors, (
            f"{module_path}: geen dict-payload actor meer gevonden -- "
            "verwijder uit _DICT_PAYLOAD_ACTOR_MODULES of controleer of de actor hernoemd is."
        )

        trees = [tree]
        for collaborator in collaborators:
            assert collaborator.exists(), f"{collaborator}: collaborator-bestand bestaat niet"
            trees.append(ast.parse(collaborator.read_text(encoding="utf-8")))

        if not any(_has_tenant_id_guard(t) for t in trees):
            violations.append(
                f"{module_path}: dict-payload actor zonder aantoonbare tenant_id-validatie "
                f"(AST-gekoppelde guard-scan in module + collaborators {[str(c) for c in collaborators]})"
            )

    assert not violations, "Dramatiq dict-payload actors zonder tenant_id-validatie:\n" + "\n".join(
        violations
    )


def test_no_unregistered_dict_payload_dramatiq_actors() -> None:
    """Nieuwe dict-payload actors moeten expliciet in _DICT_PAYLOAD_ACTOR_MODULES staan.

    Voorkomt dat een toekomstige actor met een dict-payload (dus zonder
    type-systeem-garantie voor tenant_id) ongemerkt wordt toegevoegd zonder
    door de validatie-check hierboven gecontroleerd te worden.
    """
    known = {module_path for module_path, _ in _DICT_PAYLOAD_ACTOR_MODULES}
    unregistered = []
    parsefouten = []
    scanned = 0

    for py_file in SRC_ROOT.rglob("*.py"):
        if py_file in known:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as exc:
            parsefouten.append(f"{py_file}: {exc}")
            continue
        scanned += 1
        if _find_dict_payload_actors(tree):
            unregistered.append(str(py_file))

    assert scanned >= 1500, (
        f"Slechts {scanned} bestanden gescand onder {SRC_ROOT} -- dat lijkt een (bijna) "
        "lege boom. Verkeerd pad? Deze guard controleert dan vrijwel niets."
    )
    assert not parsefouten, (
        "Deze bestanden parseren niet en zijn NIET gecontroleerd op een niet-geregistreerde "
        "dict-payload actor:\n" + "\n".join(f"  - {f}" for f in parsefouten)
    )
    assert not unregistered, (
        "Nieuwe dict-payload Dramatiq actor(s) buiten _DICT_PAYLOAD_ACTOR_MODULES:\n"
        + "\n".join(unregistered)
        + "\nVoeg toe aan de lijst in dit testbestand en controleer tenant_id-validatie."
    )
