"""Contract-aware DSM analysis.

Uitbreiding op scripts/dsm_full_analysis.py die rekening houdt met:
- .importlinter ignore_imports (allowed-by-design facade imports)
- legacy flat *_endpoints.py bestanden (exempt van Contract 1)
- echte violations (niet toegestane imports)

Doel: voorkomen van misleidende KRITIEK-labels in DSM-rapporten.
"""

from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path

from scripts.dsm_full_analysis import (
    MODULE_MAP,
    SOURCE_DIRS,
    MODULES,
    classify,
    scan_module,
)

REPO_ROOT = Path(__file__).parent.parent
IMPORTLINTER_CFG = REPO_ROOT / ".importlinter"

# Legacy flat endpoints zijn exempt van Contract 1 tot Strangler Fig migratie.
LEGACY_FLAT_ENDPOINTS = re.compile(r"src[\\/]core[\\/]api[\\/][^\\/]+_endpoints\.py$")


def parse_ignore_imports(path: Path) -> set[tuple[str, str]]:
    """Parse .importlinter ignore_imports entries into (source_module, target_module) pairs.

    Import-linter config is INI-like, but multi-line values with indentation.
    We use a custom parser because configparser strips newlines.
    """
    allowed: set[tuple[str, str]] = set()
    if not path.exists():
        return allowed

    text = path.read_text(encoding="utf-8")
    in_ignore = False
    current_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()

        # Start of a contract
        if stripped.startswith("[importlinter:contract:"):
            in_ignore = False
            current_key = None
            continue

        # Detect ignore_imports key
        if stripped.startswith("ignore_imports") and "=" in stripped:
            in_ignore = True
            # Value may be on the same line after =
            after_eq = stripped.split("=", 1)[1].strip()
            if after_eq:
                _parse_ignore_line(after_eq, allowed)
            continue

        if in_ignore:
            # Continuation lines are indented and contain "src.x -> src.y"
            if not stripped:
                # Empty line ends the multi-line value
                in_ignore = False
                continue
            if stripped.startswith("#"):
                continue
            # If line is a new key (not indented and has =), stop parsing ignore_imports
            if not line.startswith(" ") and not line.startswith("\t") and "=" in stripped:
                in_ignore = False
                continue
            _parse_ignore_line(stripped, allowed)

    return allowed


def _parse_ignore_line(line: str, allowed: set[tuple[str, str]]) -> None:
    """Parse a single 'src.x -> src.y' line."""
    # Remove inline comments
    if "#" in line:
        line = line.split("#", 1)[0]
    line = line.strip()
    if "->" not in line:
        return
    left, right = line.split("->", 1)
    left = left.strip()
    right = right.strip()
    if left and right:
        allowed.add((left, right))


def _matches_prefix(module: str, prefix: str) -> bool:
    """Check if module is the prefix or a descendant of it."""
    return module == prefix or module.startswith(prefix + ".")


def classify_import(source_file: Path, source_mod: str, target_mod: str) -> str:
    """Classify a single import as allowed, exempt, or violation."""
    # Legacy flat endpoints are exempt
    if LEGACY_FLAT_ENDPOINTS.search(str(source_file)):
        return "exempt"

    return "allowed" if _is_allowed(source_mod, target_mod) else "violation"


def _is_allowed(source_mod: str, target_mod: str) -> bool:
    """Check if an import edge is explicitly allowed by .importlinter."""
    # Direct match or prefix match against ignore_imports
    for left, right in ALLOWED_EDGES:
        if _matches_prefix(source_mod, left) and _matches_prefix(target_mod, right):
            return True
    return False


ALLOWED_EDGES: set[tuple[str, str]] = parse_ignore_imports(IMPORTLINTER_CFG)


def _collect_type_checking_nodes(tree: ast.Module) -> set[int]:
    """Return id() of all AST nodes inside TYPE_CHECKING blocks.

    NOTE: Must receive the same parsed tree object as the caller uses for
    ast.walk(). id() stability is guaranteed only within a single ast.parse()
    lifetime -- do NOT call this with a separately re-parsed tree.

    TYPE_CHECKING imports are annotation-only and never executed at runtime.
    Counting them as fan-out would produce false circular-dep reports.
    Covers both `if TYPE_CHECKING:` and `if typing.TYPE_CHECKING:` forms.
    """
    tc_ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute)
            and test.attr == "TYPE_CHECKING"
            and isinstance(test.value, ast.Name)
            and test.value.id == "typing"
        )
        if is_tc:
            for child in ast.walk(node):
                tc_ids.add(id(child))
    return tc_ids


def scan_module_contract_aware(
    source_name: str, dirs: list[str]
) -> tuple[dict[str, dict[str, int]], int]:
    """Scan a module and classify each cross-module import.

    Returns:
        counts: dict[classification][target_module] -> count
        files: number of source files scanned
    """

    counts: dict[str, dict[str, int]] = {
        "allowed": {},
        "exempt": {},
        "violation": {},
    }
    files = 0

    for d in dirs:
        p = REPO_ROOT / d
        if not p.exists():
            continue
        paths = [p] if p.is_file() else list(p.rglob("*.py"))
        for path in paths:
            parts = path.parts
            if any("test" in part.lower() for part in parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            files += 1
            # NOTE: tc_ids computed from the same tree -- do not re-parse between calls
            tc_ids = _collect_type_checking_nodes(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                if id(node) in tc_ids:
                    continue
                mod = node.module
                if mod.startswith("src.core.src."):
                    mod = "src." + mod[len("src.core.src.") :]
                if not mod.startswith("src."):
                    continue
                target_bucket = classify(mod)
                if target_bucket is None or target_bucket == source_name:
                    continue

                # Determine source module from file path
                rel = path.relative_to(REPO_ROOT)
                rel_parts = rel.with_suffix("").parts
                source_mod = ".".join(rel_parts)

                classification = classify_import(path, source_mod, mod)
                counts[classification][target_bucket] = (
                    counts[classification].get(target_bucket, 0) + 1
                )

    return counts, files


def main() -> None:
    print("=" * 80)
    print("CONTRACT-AWARE DSM ANALYSIS")
    print("allowed = toegestaan door .importlinter")
    print("exempt  = legacy flat *_endpoints.py")
    print("violation = echte schending")
    print("=" * 80)
    print()

    total_violations = 0
    module_violations: dict[str, dict[str, int]] = {}

    for mod in MODULES:
        dirs = SOURCE_DIRS.get(mod, [])
        counts, files = scan_module_contract_aware(mod, dirs)
        allowed = sum(counts["allowed"].values())
        exempt = sum(counts["exempt"].values())
        violations = sum(counts["violation"].values())
        total_violations += violations
        module_violations[mod] = counts["violation"]

        print(
            f"{mod:<16} files={files:>4}  allowed={allowed:>4}  exempt={exempt:>4}  violation={violations:>4}"
        )

    print()
    print("=" * 80)
    print("VIOLATION MATRIX")
    print("=" * 80)
    print(f"{'FROM-TO':>14}", end="")
    short = {
        "tenancy": "tenancy",
        "auth": "auth",
        "governance": "gov",
        "agent_runtime": "agt_rt",
        "llm": "llm",
        "tool_broker": "tool",
        "worker": "worker",
        "domain_pack": "dom_pk",
        "core_api": "core_api",
        "infra": "infra",
        "shared": "shared",
        "integrations": "integr",
    }
    for m in MODULES:
        print(f"{short[m]:>8}", end="")
    print()
    print("-" * (14 + 8 * len(MODULES)))

    for from_mod in MODULES:
        print(f"{short[from_mod]:>14}", end="")
        for to_mod in MODULES:
            v = module_violations[from_mod].get(to_mod, 0)
            print(f"{v:>8}", end="")
        print()

    print()
    print("=" * 80)
    print("CIRCULAR VIOLATIONS (echte schendingen)")
    print("=" * 80)
    found = False
    for a in MODULES:
        for b in MODULES:
            if a >= b:
                continue
            ab = module_violations[a].get(b, 0)
            ba = module_violations[b].get(a, 0)
            if ab > 0 and ba > 0:
                sev = "KRITIEK" if (ab + ba) >= 100 else "MEDIUM" if (ab + ba) >= 20 else "LAAG"
                print(f"  [{sev}] {a} <-> {b}: {ab} heen / {ba} terug")
                found = True
    if not found:
        print("  Geen circulaire violations gevonden.")

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(
        f"Total imports scanned:        {sum(sum(scan_module_contract_aware(m, SOURCE_DIRS.get(m, []))[0]['violation'].values()) for m in MODULES) + total_violations}"
    )
    print(f"Total violations:             {total_violations}")
    print(
        f"KRITIEK circular violations:  {sum(1 for a in MODULES for b in MODULES if a < b and module_violations[a].get(b, 0) > 0 and module_violations[b].get(a, 0) > 0 and module_violations[a].get(b, 0) + module_violations[b].get(a, 0) >= 100)}"
    )
    print()
    print("NOTE: This is the contract-aware view. Compare with scripts/dsm_full_analysis.py")
    print("      to see how many by-design imports are currently mislabeled as KRITIEK.")


if __name__ == "__main__":
    main()
