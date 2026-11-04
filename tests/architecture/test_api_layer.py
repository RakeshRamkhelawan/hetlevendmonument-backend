"""
Architectural fitness functions — structuurregels die import-linter niet dekt.
Bij elke commit gecontroleerd. Falen = bouw stopt.

Copied verbatim from docs/plans/api-layer-grade-a-plus-plan.md Deel 3B.
"""

import ast
from pathlib import Path

import pytest


def _collect_router_defining_modules(root: Path) -> list[Path]:
    """
    Gebruik AST om bestanden te vinden die een APIRouter-instantie
    toewijzen aan een module-level naam. Betrouwbaarder dan string-search:
    vangt ook `router = APIRouter(prefix=...)` en aliassen.

    Alleen bestanden genaamd `router.py` worden beschouwd als domein-entry-points
    die geregistreerd moeten worden. Bestanden met de suffix `_router.py`
    (bijv. rules_router.py, analytics_router.py) zijn sub-routers die intern
    door de domein-router worden samengesteld — deze hoeven NIET direct in
    een registry te staan.
    """
    results = []
    for py_file in root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        # Sub-routers zijn intern aan het domein; alleen router.py is een entry-point.
        if py_file.name != "router.py" and py_file.name.endswith("_router.py"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # Zoek: <name> = APIRouter(...) op module-niveau (col_offset == 0)
            if (
                isinstance(node, ast.Assign)
                and node.col_offset == 0
                and isinstance(node.value, ast.Call)
            ):
                func = node.value.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                if name == "APIRouter":
                    results.append(py_file)
                    break
    return results


def test_no_orphan_routers() -> None:
    """
    Elk bestand met een module-level APIRouter-instantie moet
    geïmporteerd worden door de registry (direct of via registries/).
    """
    src = Path("src/core/api")
    # Verzamel alle import-statements in de registry-bestanden
    registry_imports: set[str] = set()
    registry_files = [src / "router_registry.py"] + list(
        (src / "registries").glob("*.py") if (src / "registries").exists() else []
    )
    for reg_file in registry_files:
        if not reg_file.exists():
            continue
        try:
            tree = ast.parse(reg_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                registry_imports.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    registry_imports.add(alias.name)

    router_files = _collect_router_defining_modules(src)
    orphans = []
    for py_file in router_files:
        # Vertaal bestandspad naar module-pad
        rel = py_file.relative_to(Path("."))
        module = str(rel).replace("\\", "/").replace("/", ".").replace(".py", "")
        # Controleer of de module of een parent wordt geïmporteerd
        imported = any(
            module == imp or module.startswith(imp + ".") or imp.startswith(module)
            for imp in registry_imports
        )
        # Uitzondering: copilot/api en scheduling/api zijn correct geïsoleerde bounded contexts
        is_exempt = (
            "copilot/api" in str(py_file)
            or "scheduling/api" in str(py_file)
            or "# orphan:exempt" in py_file.read_text(encoding="utf-8", errors="ignore")
        )
        if not imported and not is_exempt:
            orphans.append(str(py_file))

    assert not orphans, (
        "Orphan router-bestanden gevonden (niet geregistreerd in registry):\n"
        + "\n".join(f"  - {f}" for f in orphans)
        + "\nVoeg toe aan src/core/api/registries/<domein>.py of verwijder het bestand."
        + "\nUitzonderingen: voeg `# orphan:exempt` toe aan het bestand."
    )


def test_no_router_files_over_200_lines() -> None:
    """
    router.py bestanden mogen niet groter zijn dan 200 regels.
    Groter = business logica in de route handler (verkeerd).
    Bestanden met `# orphan:exempt` zijn vrijgesteld (tijdelijk, pending split).
    Sub-routers (*_router.py) zijn interne domein-componenten zonder size-limiet.
    """
    violations = []
    for py_file in Path("src/core/api/v1").rglob("router.py"):
        content = py_file.read_text(encoding="utf-8")
        if "# orphan:exempt" in content:
            continue
        lines = len(content.splitlines())
        if lines > 200:
            violations.append(f"{py_file} ({lines} regels)")
    assert not violations, "Router bestanden te groot (max 200 regels):\n" + "\n".join(
        f"  - {v}" for v in violations
    )


def test_registry_files_under_80_lines() -> None:
    """
    Domeinregistry bestanden mogen niet groter zijn dan 80 regels.
    Groter = te veel verantwoordelijkheid per registry.
    """
    reg_dir = Path("src/core/api/registries")
    if not reg_dir.exists():
        pytest.skip("registries/ nog niet aangemaakt — na Deel 2 actief")
    violations = []
    for reg_file in reg_dir.glob("*.py"):
        if reg_file.name.startswith("_"):
            continue
        lines = len(reg_file.read_text(encoding="utf-8").splitlines())
        if lines > 80:
            violations.append(f"{reg_file} ({lines} regels)")
    assert not violations, "Registry bestanden te groot (max 80 regels):\n" + "\n".join(
        f"  - {v}" for v in violations
    )


def test_no_eager_imports_in_setup_registry() -> None:
    """
    setup/router_registry.py mag geen module-level imports van
    endpoint-bestanden bevatten (eager import anti-patroon).
    Na Stap 0A moet deze test groen zijn.
    """
    setup_registry = Path("src/core/api/setup/router_registry.py")
    assert setup_registry.exists(), (
        f"{setup_registry} bestaat niet meer. Hernoemd of verplaatst? Deze test controleert "
        "dan NIETS meer -- werk het pad hierboven bij in plaats van de test te laten slagen."
    )

    tree = ast.parse(setup_registry.read_text(encoding="utf-8"))

    # Verzamel TYPE_CHECKING guard-lijnen — die zijn geen runtime imports
    type_checking_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if is_tc:
                for child in ast.walk(node):
                    if hasattr(child, "lineno"):
                        type_checking_lines.add(child.lineno)  # type: ignore[attr-defined]

    eager_imports = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node.lineno in type_checking_lines:
            continue
        if getattr(node, "col_offset", 1) != 0:
            continue  # inspringing > 0 = binnen functie (lazy) — correct
        if isinstance(node, ast.ImportFrom) and node.module:
            if "endpoints" in node.module or node.module.endswith(".router"):
                eager_imports.append(f"  Lijn {node.lineno}: from {node.module} import ...")

    assert not eager_imports, (
        "Eager imports gevonden in setup/router_registry.py:\n"
        + "\n".join(eager_imports)
        + "\nVerplaats naar functie-body (lazy import patroon) — zie Stap 0A."
    )
