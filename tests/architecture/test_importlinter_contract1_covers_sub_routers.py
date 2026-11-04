"""AUDIT-ARCH-2026-07-02 Groep 7 -- ARCH-003 (root cause van Groep 7).

`.importlinter` Contract 1 ("API routers mogen niet direct domeinlogica
importeren") dekt alleen bestanden die exact `router.py` heten
(source_modules glob `src.core.api.v1.*.router`). De ~151 `*_router.py`
sub-routers (bijv. `board_router.py`, `gatekeeper_hitl_router.py`,
`catalog_router.py`) vallen buiten die dekking en zijn dus nooit gecontroleerd.

import-linter ondersteunt GEEN partiele-segment-wildcards (`*_router`) --
"A wildcard can only replace a whole module" (empirisch geverifieerd: elke
poging tot `src.core.api.v1.*.*_router` in `.importlinter` faalt met exact die
foutmelding). Contract 1 zelf kan dus niet verbreed worden; deze AST-scan is de
enige haalbare manier om dezelfde ADR-033-regel (`router.py`/`*_router.py`
mogen alleen via `*.dependencies` domeinlogica bereiken, nooit direct) ook op
de sub-routers te handhaven.
"""

import ast
from pathlib import Path

SRC_ROOT = Path("src/core/api").resolve()

# Zelfde forbidden_modules-lijst als .importlinter Contract 1.
FORBIDDEN_MODULES = (
    "src.core.database",
    "src.core.governance",
    "src.core.learning",
    "src.core.agents",
    "src.core.workflow",
    "src.core.llm",
    "src.core.services",
    "src.core.ml",
    "src.core.als",
    "src.core.semantic_router",
)

# Bekende, nog niet gefixte violations (SP-ARCH-ARCH-3 backlog) -- elke entry hier
# is een <bestand>:<geimporteerde-module>-paar dat via deze test zichtbaar blijft
# totdat het naar de *.dependencies-facade is verplaatst.
KNOWN_VIOLATIONS: dict[str, set[str]] = {}


def _iter_sub_router_files() -> list[Path]:
    """Alle *_router.py-bestanden onder src/core/api, exclusief letterlijk 'router.py'
    (dat al gedekt wordt door .importlinter Contract 1's eigen glob)."""
    return sorted(
        p
        for p in SRC_ROOT.rglob("*_router.py")
        if p.name != "router.py" and "dependencies" not in p.name
    )


def _package_of(py_file: Path) -> list[str]:
    """Dotted package-segmenten van de map waarin py_file staat (repo-root-relatief)."""
    repo_root = SRC_ROOT.parent.parent.parent
    return list(py_file.relative_to(repo_root).parent.parts)


def _resolve_relative_import(node: ast.ImportFrom, package: list[str]) -> str | None:
    """Zet `from ..agents import X` (level=2) om naar 'src.core.agents' -- absolute
    resolutie is nodig omdat een relative import evengoed een forbidden module kan
    bereiken (bijv. vanuit een diep-geneste sub-router)."""
    if node.level == 0:
        return node.module
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
    if node.level > len(package) + 1:
        return (
            None  # relative import gaat boven de repo-root uit -- kan niet gebeuren in geldige code
        )
    return ".".join(base + ([node.module] if node.module else []))


def _direct_forbidden_imports(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8-sig"), filename=str(py_file))
    package = _package_of(py_file)
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                if module_name and any(
                    module_name == m or module_name.startswith(m + ".") for m in FORBIDDEN_MODULES
                ):
                    violations.add(module_name)
        elif isinstance(node, ast.ImportFrom):
            module_name = _resolve_relative_import(node, package)
            if not module_name:
                continue
            if module_name.endswith(".dependencies") or ".dependencies." in module_name:
                continue
            if any(module_name == m or module_name.startswith(m + ".") for m in FORBIDDEN_MODULES):
                violations.add(module_name)
    return violations


def test_sub_routers_do_not_directly_import_domain_logic() -> None:
    """*_router.py-bestanden mogen domeinlogica alleen via *.dependencies bereiken,
    nooit direct -- zelfde regel als .importlinter Contract 1, nu ook op sub-routers."""
    unexpected: dict[str, set[str]] = {}
    for py_file in _iter_sub_router_files():
        rel_path = str(py_file.relative_to(SRC_ROOT.parent.parent.parent))
        violations = _direct_forbidden_imports(py_file)
        known = KNOWN_VIOLATIONS.get(rel_path, set())
        new_violations = violations - known
        if new_violations:
            unexpected[rel_path] = new_violations

    assert not unexpected, (
        "Nieuwe directe domeinlogica-imports gevonden in *_router.py-bestanden "
        f"(ADR-033 facade-bypass): {unexpected}. Gebruik een Depends()-provider in "
        "de bijbehorende dependencies.py in plaats van het domein rechtstreeks te "
        "importeren."
    )


def test_known_violations_list_stays_accurate() -> None:
    """KNOWN_VIOLATIONS mag geen entries bevatten die al gefixed zijn (voorkomt dat de
    allowlist stilzwijgend een gefixed item blijft afdekken)."""
    stale = []
    for rel_path, known_modules in KNOWN_VIOLATIONS.items():
        py_file = Path(rel_path).resolve()
        if not py_file.exists():
            stale.append(rel_path)
            continue
        actual = _direct_forbidden_imports(py_file)
        if not (known_modules & actual):
            stale.append(rel_path)

    assert not stale, (
        f"KNOWN_VIOLATIONS bevat verouderde entries die al gefixed zijn: {stale}. "
        "Verwijder ze uit de allowlist."
    )
