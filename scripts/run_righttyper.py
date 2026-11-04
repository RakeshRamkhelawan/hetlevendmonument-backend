#!/usr/bin/env python3
"""Safe wrapper around RightTyper for bulk Python type inference.

Defaults to dry-run; pass --apply to write annotations back to source files.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

DEFAULT_SCAN_DIR = Path("src")
DEFAULT_OUTPUT_DIR = Path(".tmp") / "righttyper"
DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    r"(^|/)alembic/",
    r"(^|/)generated/",
    r"(^|/)__pycache__/",
    r"(^|/)",
    r"\.egg-info/",
    r"(^|/)\.venv/",
    r"(^|/)venv/",
    r"(^|/)build/",
    r"(^|/)dist/",
)


def _has_righttyper() -> bool:
    return importlib.util.find_spec("righttyper") is not None


def _find_git_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return Path.cwd()
    return Path(result.stdout.strip())


def _git_changed_files(since: str) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRT",
            f"{since}...HEAD",
            "--",
            "*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"ERROR: git diff failed: {result.stderr.strip()}", file=sys.stderr)
        return []
    root = _find_git_root()
    files: list[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        path = root / line
        if path.exists() and path.suffix == ".py":
            files.append(path)
    return files


def _collect_paths(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            print(f"WARNING: path does not exist: {path}", file=sys.stderr)
            continue
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in path.rglob("*.py") if p.is_file())
    return files


def _is_excluded(path: Path, exclude_patterns: tuple[str, ...], root: Path) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return any(re.search(pattern, rel) for pattern in exclude_patterns)


def resolve_targets(
    paths: list[Path] | None,
    since: str | None,
    exclude_patterns: tuple[str, ...],
    root: Path,
) -> list[Path]:
    """Resolve the list of Python files to process."""
    if since:
        candidates = _git_changed_files(since)
        if paths:
            path_set = set(_collect_paths(paths))
            candidates = [p for p in candidates if p in path_set]
    elif paths:
        candidates = _collect_paths(paths)
    else:
        candidates = _collect_paths([root / DEFAULT_SCAN_DIR])

    targets = [
        p for p in candidates if not _is_excluded(p, exclude_patterns, root)
    ]
    return sorted(set(targets))


def build_command(targets: list[Path], apply: bool, output_dir: Path) -> list[str]:
    cmd = [sys.executable, "-m", "righttyper", "--verbose"]
    if apply:
        cmd.append("--output-files")
    else:
        cmd.append("--no-output-files")
    cmd.extend(str(t) for t in targets)
    return cmd


def run_righttyper(cmd: list[str], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bulk Python type inference wrapper (dry-run by default)."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to process (default: src/).",
    )
    parser.add_argument(
        "--since",
        metavar="REF",
        help="Only process .py files changed since REF (e.g. origin/develop).",
    )
    parser.add_argument(
        "--exclude",
        metavar="REGEX",
        action="append",
        default=[],
        help="Additional regex to exclude matching relative paths (can be repeated).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write inferred annotations back to source files (default: dry-run).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for dry-run review output (default: .tmp/righttyper/).",
    )
    args = parser.parse_args(argv)

    if not _has_righttyper():
        print(
            "ERROR: righttyper is not installed. Install with:\n"
            "  pip install righttyper\n"
            "or add it to requirements-test.txt.",
            file=sys.stderr,
        )
        return 1

    root = _find_git_root()
    exclude_patterns = DEFAULT_EXCLUDE_PATTERNS + tuple(args.exclude)
    targets = resolve_targets(
        paths=list(args.paths) if args.paths else None,
        since=args.since,
        exclude_patterns=exclude_patterns,
        root=root,
    )

    if not targets:
        print("No Python files to process.")
        return 0

    mode = "apply" if args.apply else "dry-run"
    print(f"RightTyper {mode}: {len(targets)} file(s)")
    for t in targets:
        print(f"  {t.relative_to(root)}")

    cmd = build_command(targets, args.apply, args.output_dir)
    exit_code = run_righttyper(cmd, args.output_dir)

    status = "applied" if args.apply else "reviewed"
    print(f"RightTyper finished ({status}), exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
