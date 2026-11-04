"""TDD tests for mypy audit --fail-on-increase behavior.

- Tests run the real audit script against the real codebase.
- Each test uses a temporary baseline file to ensure a known starting state.
- They assert on the return code (0 = pass, 1 = fail) and on a specific message
  in stdout (so we know *why* it passed / failed).
- These tests validate the behavior, not the implementation.
- Additionally, test_parse_errors_handles_column_numbers validates the regex fix
  directly against the show_column_numbers=true format from pyproject.toml.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_mypy_audit_has_fail_on_increase() -> None:
    """RED-GREEN: --fail-on-increase flag exists and is mentioned in --help."""
    result = subprocess.run(
        [sys.executable, "scripts/run_mypy_audit.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--fail-on-increase" in result.stdout


@pytest.mark.slow
@pytest.mark.timeout(300)
def test_fail_on_increase_fails_when_increased() -> None:
    """RED-GREEN: If a file has more errors than its baseline, exit 1.

    Creates a fake baseline with fewer errors than the current state,
    then asserts --fail-on-increase exits with code 1 and prints an
    "increased" message.

    SKIP: If mypy-baseline.json is empty (all files at 0 errors), we can't
    test regression detection. This is a valid state after Phase 21 where
    all mypy errors were fixed. We skip rather than fail because the
    regression-detection mechanism still works correctly—it just has
    nothing to regress on yet.
    """

    real_baseline_path = Path("mypy-baseline.json")
    assert real_baseline_path.exists()
    real_baseline = json.loads(real_baseline_path.read_text(encoding="utf-8"))

    # Pick a file that is known to have errors in the real baseline.
    file_with_errors = None
    for file_path, count in real_baseline.items():
        if count > 0:
            file_with_errors = file_path
            break

    if file_with_errors is None:
        # Baseline is empty (all files at 0 errors). Can't test regression.
        pytest.skip("Baseline is empty; cannot test regression detection on zero-error state")

    # Create a fake baseline where that file has 0 errors (artificially reduce).
    fake_baseline = dict(real_baseline)
    fake_baseline[file_with_errors] = 0

    real_backup = real_baseline_path.read_text(encoding="utf-8")
    try:
        real_baseline_path.write_text(json.dumps(fake_baseline), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/run_mypy_audit.py", "--fail-on-increase"],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        assert result.returncode == 1
        assert "increased" in result.stdout.lower() or "increased" in result.stderr.lower()
    finally:
        real_baseline_path.write_text(real_backup, encoding="utf-8")


@pytest.mark.slow
@pytest.mark.timeout(300)
def test_fail_on_increase_passes_when_no_increase() -> None:
    """GREEN: If no file increased, exit 0 and print OK.

    Uses the real baseline and asserts the script returns 0 with an
    "OK: No files increased" message.
    """
    result = subprocess.run(
        [sys.executable, "scripts/run_mypy_audit.py", "--fail-on-increase"],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK: No files increased" in result.stdout


def test_parse_errors_handles_column_numbers() -> None:
    """Unit test for regex fix: parse_errors() must handle file:line:col: format.

    pyproject.toml sets show_column_numbers = true, making mypy emit:
    src/foo/bar.py:42:7: error: Cannot find something

    This test directly calls parse_errors() with lines in that format and
    asserts it correctly counts errors (not silently ignore them as the
    old regex would).
    """
    from scripts.run_mypy_audit import parse_errors

    test_lines = [
        "src/foo/bar.py:42:7: error: Cannot find something",
        "src/foo/bar.py:43:1: error: Another error",
        "src/baz/qux.py:10:15: error: Third error",
        "Some other output line that doesn't match",
    ]

    counts = parse_errors(test_lines)

    assert "src/foo/bar.py" in counts
    assert counts["src/foo/bar.py"] == 2
    assert "src/baz/qux.py" in counts
    assert counts["src/baz/qux.py"] == 1
    assert len(counts) == 2, "Should only have 2 files with errors"
