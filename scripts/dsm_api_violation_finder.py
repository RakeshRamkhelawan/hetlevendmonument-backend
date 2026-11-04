"""Find real API-layer violations of ADR-033.

Scans src/core/api/ for files that directly import forbidden modules,
instead of using the sanctioned *.dependencies.py facade pattern.

Exempt:
- files named dependencies.py
- legacy flat *_endpoints.py files
- imports from shared foundation modules
- imports from auth/tenancy dependencies
- imports to the file's own domain dependencies
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
API_DIR = REPO_ROOT / "src" / "core" / "api"

# Modules that API-layer files may import directly (ADR-033 facade boundary)
FORBIDDEN_MODULES = {
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
    "src.core.copilot",
}

# Allowed direct imports for API-layer files
ALLOWED_PREFIXES = {
    "src.core.shared",
    "src.core.governance.models",  # reclassified as shared (MODULE_MAP commit 0cc54e93)
    "src.core.exceptions",
    "src.core.schemas",
    "src.core.base",
    "src.core.typing",
    "src.core.contracts",
    "src.core.utils",
    "src.core.logging",
    "src.core.templates",
    "src.core.protocol",
    "src.core.middleware",
    "src.core.ratelimit",
    "src.core.auth.dependencies",
    "src.core.api.dependencies",
    "src.core.api.router_registry",
    "src.core.api.setup",
    "src.core.api.main",
    "src.core.api.auth.router",
}


# Bestanden die buiten ADR-033 router-laag vallen en niet gescand worden:
# - main.py / lifecycle.py: app entry/startup, geen v1/-domein (SP-DSM-002 Dag 3)
# - _prana_contracts_cache.py: ALS infra-cache; circular import vereist aparte ADR-beslissing
#   (pending design review -- niet als bootstrap, maar als tijdelijke uitzondering gelabeld)
_BOOTSTRAP_EXEMPT: frozenset[str] = frozenset(
    {"main.py", "lifecycle.py", "_prana_contracts_cache.py"}
)


def is_api_layer_file(path: Path) -> bool:
    """True for non-dependency, non-legacy API files."""
    if path.name == "dependencies.py":
        return False
    if path.name.endswith("_dependencies.py"):
        return False
    if path.name.endswith("_endpoints.py"):
        return False
    if path.name in _BOOTSTRAP_EXEMPT:
        return False
    try:
        first_line = path.read_text(encoding="utf-8", errors="ignore").split("\n", 1)[0]
        if "dsm:exempt" in first_line:
            return False
    except OSError:
        pass
    return True


def is_allowed_target(module: str, source_domain: str | None) -> bool:
    """Check if an import target is allowed for an API-layer file."""
    # Own domain dependencies are allowed
    if source_domain and module.startswith(f"src.core.api.v1.{source_domain}."):
        return True

    # General API dependencies
    for prefix in ALLOWED_PREFIXES:
        if module == prefix or module.startswith(prefix + "."):
            return True

    return False


def extract_domain(path: Path) -> str | None:
    """Extract domain from src/core/api/v1/<domain>/router.py paths."""
    rel = str(path.relative_to(API_DIR)).replace("\\", "/")
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "v1":
        return parts[1]
    return None


def find_violations() -> list[tuple[Path, str, int]]:
    """Return list of (file_path, imported_module, line_number)."""
    violations: list[tuple[Path, str, int]] = []

    for path in API_DIR.rglob("*.py"):
        if not is_api_layer_file(path):
            continue

        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue

        source_domain = extract_domain(path)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            module = node.module

            # Only check project-internal imports
            if not module.startswith("src."):
                continue

            # Is it a forbidden module?
            forbidden = False
            for forbidden_mod in FORBIDDEN_MODULES:
                if module == forbidden_mod or module.startswith(forbidden_mod + "."):
                    forbidden = True
                    break
            if not forbidden:
                continue

            # Is it allowed anyway?
            if is_allowed_target(module, source_domain):
                continue

            violations.append((path, module, node.lineno or 0))

    return violations


def main() -> None:
    violations = find_violations()

    print("=" * 80)
    print("ADR-033 API-LAYER VIOLATION FINDER")
    print("=" * 80)
    print(f"Total violations found: {len(violations)}")
    print()

    # Group by file
    by_file: dict[Path, list[tuple[str, int]]] = {}
    for path, module, lineno in violations:
        by_file.setdefault(path, []).append((module, lineno))

    for path in sorted(by_file):
        rel = path.relative_to(REPO_ROOT)
        print(f"\n{rel}")
        for module, lineno in sorted(by_file[path], key=lambda x: x[1]):
            print(f"  line {lineno:>4}: {module}")

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Files with violations: {len(by_file)}")
    print(f"Total violation imports: {len(violations)}")
    print()
    print("Fix pattern: move these imports to the domain's dependencies.py")


if __name__ == "__main__":
    main()
