"""
Architecture test: kritieke router-bestanden moeten success/data-wrapper retourneren.
RED voor de fix, GREEN zodra alle non-conformante endpoints gefixed zijn.
CI-blokkering BP-001 -- SP-SEC-002.

FA-001 fix: scant alleen @router.* handlers via AST -- null-objects, dependency
factories en private helpers worden niet meer als false positives opgepikt.
"""

import ast
from pathlib import Path


# Kritieke API-bestanden met bekende non-conformant responses (audit 2026-06-30)
# Voeg bestanden toe als ze gefixed zijn en verwijder uit deze lijst.
# TODO(SP-SEC-002): Alle bestanden in deze lijst moeten gecorrigeerd worden.
ROUTER_FILES_SCOPE = [
    "src/core/api/v1/agents/agent_crud_router.py",
    "src/core/api/v1/company/external_agent_router.py",
    "src/core/api/v1/notifications/router.py",
    "src/core/api/v1/workflow/router.py",
]

CONFORMANT_PATTERNS = [
    '"success"',
    "'success'",
    "success=",
    "JSONResponse",
    "StreamingResponse",
    "RedirectResponse",
    "Response(",
    "FileResponse",
]

EXCLUDED_RETURN_KEYWORDS = [
    "redirect",
    "none",
    "response",  # pass-through
]


def _is_route_handler(node: ast.AST) -> bool:
    """True als de functie gedecoreerd is met @router.get/post/put/delete/patch."""
    if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        return False
    for decorator in node.decorator_list:
        # @router.get("...") of @router.post("/") etc.
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "router":
                return True
    return False


def _find_non_conformant_returns(source: str, path_str: str) -> list[str]:
    """Scant alleen @router.* route-handlers op non-conformante returns.

    Null-objects, dependency factories en private helpers worden niet gescand (FA-001).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [f"PARSE ERROR in {path_str}"]

    lines = source.splitlines()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not _is_route_handler(node):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Return) or child.value is None:
                continue
            # Het volledige return-statement kan meerdere regels beslaan (bijv. een
            # dict-literal met "success" pas op de TWEEDE regel) -- alleen de eerste
            # regel toetsen mist die en meldt een conformante return als overtreding.
            end = child.end_lineno or child.lineno
            full_span = "\n".join(lines[child.lineno - 1 : end])
            first_line = lines[child.lineno - 1].strip()
            if any(pat in full_span for pat in CONFORMANT_PATTERNS):
                continue
            if any(exc in full_span.lower() for exc in EXCLUDED_RETURN_KEYWORDS):
                continue
            violations.append(f"L{child.lineno}: {first_line[:80]}")

    return violations


def test_router_files_scope_paths_exist() -> None:
    """Vangnet: een hernoemd bestand mag ROUTER_FILES_SCOPE niet stilzwijgend vacuum maken.

    test_critical_routers_use_success_wrapper slaat een pad in ROUTER_FILES_SCOPE stil
    over als het niet bestaat (`if not path.exists(): continue`). Zonder dit vangnet zou
    een hernoemd bestand -- met de non-conformante returns nog intact -- de guard
    permanent en onopgemerkt laten slagen.
    """
    missing = [p for p in ROUTER_FILES_SCOPE if not Path(p).exists()]
    assert not missing, (
        f"Deze paden in ROUTER_FILES_SCOPE bestaan niet: {missing}. Hernoemd of "
        "verplaatst? Werk de lijst bij -- anders controleert de guard hierboven niets "
        "meer voor dat bestand."
    )


def test_critical_routers_use_success_wrapper() -> None:
    """Kritieke routers moeten success/data-wrapper gebruiken -- BP-001 CI-blokkering.

    Huidig: meerdere non-conformant return statements per bestand.
    Doel: 0 non-conformant statements per bestand.
    Alleen @router.* handlers worden gescand (FA-001 fix -- geen false positives).
    """
    all_violations: dict[str, list[str]] = {}

    for path_str in ROUTER_FILES_SCOPE:
        path = Path(path_str)
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8-sig", errors="ignore")
        violations = _find_non_conformant_returns(source, path_str)
        if violations:
            all_violations[path_str] = violations

    assert not all_violations, (
        "BP-001: non-conformant return statements gevonden in @router.* handlers.\n"
        "Fix: voeg success/data-wrapper toe (backend-patterns pattern 7).\n"
        + "\n".join(
            f"\n  {f}:\n" + "\n".join(f"    {v}" for v in vs) for f, vs in all_violations.items()
        )
    )
