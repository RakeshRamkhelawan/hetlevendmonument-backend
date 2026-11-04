"""
AUDIT-DB-01: Detect direct database imports in router files.

Read-only AST scan that reports which router files in src/core/api/v1/
still import forbidden database symbols directly. Used for chunk planning
when migrating remaining domains to a service layer.

Usage:
    python scripts/detect_db_imports.py
    python scripts/detect_db_imports.py --output .tmp/db_import_offenders.json
    python scripts/detect_db_imports.py --verbose
"""

import argparse
import ast
import json
import sys
from pathlib import Path

_FORBIDDEN_NAMES = {
    "get_db",
    "AsyncSession",
    "select",
    "func",
    "insert",
    "update",
    "delete",
    "text",
}

_FORBIDDEN_MODULES = {
    "sqlalchemy",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.future",
    "src.core.database.database",
    "src.core.database",
}


def _is_forbidden_import(node: ast.ImportFrom | ast.Import) -> list[str]:
    found: list[str] = []
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            if alias.name in _FORBIDDEN_NAMES:
                found.append(alias.name)
            if module in _FORBIDDEN_MODULES and alias.name not in {"Base", "db_manager"}:
                if alias.name not in found:
                    found.append(alias.name)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in _FORBIDDEN_MODULES:
                found.append(alias.name)
    return found


def scan_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            hits.extend(_is_forbidden_import(node))

    seen: set[str] = set()
    deduped: list[str] = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            deduped.append(h)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect direct DB imports in router files.")
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write JSON report to this path (default: stdout only)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each scanned file to stderr",
    )
    parser.add_argument(
        "--root",
        metavar="DIR",
        default=".",
        help="Project root (default: current directory)",
    )
    args = parser.parse_args()

    root = Path(args.root)
    router_glob = "src/core/api/v1/**/router*.py"
    router_files = sorted(root.glob(router_glob))

    offenders: list[dict] = []
    for path in router_files:
        if args.verbose:
            print(f"scanning {path}", file=sys.stderr)
        hits = scan_file(path)
        if hits:
            offenders.append(
                {
                    "file": str(path.relative_to(root)).replace("\\", "/"),
                    "forbidden_imports": hits,
                }
            )

    report = {
        "scanned": len(router_files),
        "offenders": offenders,
        "clean": len(router_files) - len(offenders),
    }

    print(json.dumps(report, indent=2))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {out_path}", file=sys.stderr)

    return 0 if not offenders else 1


if __name__ == "__main__":
    sys.exit(main())
