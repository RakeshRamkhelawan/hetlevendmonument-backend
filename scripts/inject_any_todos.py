#!/usr/bin/env python3
"""
Inject TODO(TYPE) comments alongside existing Any usages that lack annotation.

Run once to annotate the baseline codebase. After this, the Any linting gate
(check_any_gate.py) blocks new Any without a TODO(TYPE) or type: ignore comment.

Usage:
    python scripts/inject_any_todos.py              # dry-run (safe, no writes)
    python scripts/inject_any_todos.py --apply      # write changes
    python scripts/inject_any_todos.py --apply --src src/core/api
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))
from scan_any_usage import scan_file  # noqa: E402

TODO_SUFFIX = "  # TODO(TYPE): replace Any with concrete type"

_EXCLUDE_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    "alembic",
    "archive",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp",
}


def _python_files(src_dir: Path) -> list[Path]:
    return [p for p in src_dir.rglob("*.py") if not any(part in _EXCLUDE_DIRS for part in p.parts)]


def inject_file(path: Path, apply: bool) -> int:
    """Append TODO to lines with Any that lack any existing annotation. Returns injected count."""
    usages = scan_file(path)
    # scan_file() geeft sinds BE-CI-006 ook de al geboekte regels terug (die tellen in het
    # ratel-getal mee), dus hier expliciet alleen de ongeboekte stempelen.
    bad_lines = {u.line_no for u in usages if not u.acknowledged}
    if not bad_lines:
        return 0

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    injected = 0

    for lineno in sorted(bad_lines):
        idx = lineno - 1
        if idx >= len(lines):
            continue
        raw = lines[idx]
        stripped = raw.rstrip("\n\r")
        if TODO_SUFFIX.strip() in stripped:
            continue  # idempotent: already present
        if stripped.endswith("\\"):
            continue  # backslash continuation -- appending a comment breaks syntax
        if "Any" not in stripped:
            continue  # TOCTOU guard: file changed between scan and this read
        eol = raw[len(stripped) :]
        lines[idx] = stripped + TODO_SUFFIX + eol
        injected += 1

    if injected and apply:
        path.write_text("".join(lines), encoding="utf-8")

    return injected


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject TODO(TYPE) into Any usages")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--src", default="src", help="Directory to scan (default: src)")
    args = parser.parse_args()

    src_dir = Path(args.src)
    if not src_dir.is_dir():
        print(f"[ERROR] Not a directory: {src_dir}", file=sys.stderr)
        sys.exit(1)

    candidates = _python_files(src_dir)
    total_injected = 0
    modified = 0

    for path in candidates:
        count = inject_file(path, apply=args.apply)
        if count:
            modified += 1
            total_injected += count
            verb = "injected" if args.apply else "would inject"
            print(f"  {path}: {verb} +{count} TODO(TYPE)")

    mode = "Applied" if args.apply else "Dry-run (use --apply to write)"
    print(f"\n[{mode}] {total_injected} TODO(TYPE) comments across {modified} files.")
    if not args.apply and total_injected:
        print("Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
