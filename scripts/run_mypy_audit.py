"""Run mypy and fail if error count increases vs baseline.

Same pattern as run_pyright_audit.py: stores a baseline in mypy-baseline.json
(per-file error counts). CI passes --fail-on-increase so new errors block the
build while existing ones are tracked separately.

Usage:
    python scripts/run_mypy_audit.py                 # report only
    python scripts/run_mypy_audit.py --fail-on-increase  # block on regressions
    python scripts/run_mypy_audit.py --update-baseline   # write new baseline
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "mypy-baseline.json"

# mypy error line format:  src/foo/bar.py:42: error: ...
# The message is optional: mypy's pretty-printer sometimes wraps a long message
# onto the next physical line, leaving nothing after "error:" (e.g.
# "events_router.py:137:28: error:" with the text on line 2). Without the `?`
# such lines silently fail to match and the error is dropped from the count.
_LINE_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+)(?::\d+)?: error:(?:\s+(?P<msg>.+))?$")


def run_mypy() -> tuple[int, list[str]]:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "src/"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    lines = result.stdout.splitlines() + result.stderr.splitlines()
    return result.returncode, lines


def parse_errors(lines: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for line in lines:
        m = _LINE_RE.match(line)
        if m:
            counts[m.group("file")] += 1
    return dict(counts)


def total(counts: dict[str, int]) -> int:
    return sum(counts.values())


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def save_baseline(counts: dict[str, int]) -> None:
    BASELINE_PATH.write_text(json.dumps(counts, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Baseline written: {BASELINE_PATH} ({total(counts)} errors across {len(counts)} files)")


def check_regressions(current: dict[str, int], baseline: dict[str, int]) -> list[str]:
    regressions: list[str] = []
    for file_path, count in current.items():
        prev = baseline.get(file_path, 0)
        if count > prev:
            regressions.append(f"  {file_path}: {prev} -> {count} (+{count - prev})")
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MyPy audit with baseline tracking")
    parser.add_argument(
        "--fail-on-increase",
        action="store_true",
        help="Exit 1 if any file has more errors than baseline",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite baseline with current error counts",
    )
    args = parser.parse_args(argv)

    print("Running mypy src/ ...")
    _, lines = run_mypy()
    current = parse_errors(lines)
    baseline = load_baseline()

    print(f"Total errors:    {total(current)}")
    print(f"Baseline errors: {total(baseline)}")
    print(f"Files with errors: {len(current)}")

    if args.update_baseline:
        save_baseline(current)
        return 0

    if args.fail_on_increase:
        regressions = check_regressions(current, baseline)
        if regressions:
            print("\nERROR: mypy errors increased in these files:")
            for r in regressions:
                print(r)
            print("\nError details:")
            regressed_files = {r.strip().split(":")[0] for r in regressions}
            for line in lines:
                m = _LINE_RE.match(line)
                if m and m.group("file") in regressed_files:
                    print(f"  {line}")
            print("\nFix the new errors or run --update-baseline after review.")
            return 1
        print("\nOK: No files increased their mypy error count.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
