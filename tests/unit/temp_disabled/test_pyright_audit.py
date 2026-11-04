"""TDD tests for pyright audit --fail-on-increase behavior.

- Tests run the real audit script against the real codebase.
- Each test uses a temporary baseline file to ensure a known starting state.
- They assert on the return code (0 = pass, 1 = fail) and on a specific message
  in stdout (so we know *why* it passed / failed).
- These tests validate the behavior, not the implementation.

QUARANTINE NOTE: These tests invoke pyright as a subprocess (~60-300s per test).
They are excluded from the default unit suite via pyproject.toml norecursedirs
and --ignore=tests/unit/temp_disabled.

To run explicitly:
    pytest tests/unit/temp_disabled/test_pyright_audit.py --run-typecheck --timeout=600

Pyright also runs as a standalone CI step (ci-feature.yml) -- no pytest needed for
basic error-count tracking.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.typecheck]


def test_pyright_audit_has_fail_on_increase():
    """RED-GREEN: --fail-on-increase flag exists and is mentioned in --help."""
    result = subprocess.run(
        [sys.executable, "scripts/run_pyright_audit.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--fail-on-increase" in result.stdout


def test_fail_on_increase_fails_when_increased():
    """RED-GREEN: If a file has more errors than its baseline, exit 1.

    Creates a fake baseline with 0 errors for a real file that we know has
    errors, then asserts --fail-on-increase exits with code 1 and prints an
    "increased" message.
    """
    real_baseline_path = Path("pyright-baseline.json")
    assert real_baseline_path.exists()
    real_baseline = json.loads(real_baseline_path.read_text(encoding="utf-8"))

    # Pick a file that is known to have errors in the real baseline.
    file_with_errors = None
    for file_path, count in real_baseline.items():
        if count > 0:
            file_with_errors = file_path
            break
    assert file_with_errors is not None, "Need at least one file with >0 errors"

    # Create a fake baseline where that file has 0 errors.
    fake_baseline = dict(real_baseline)
    fake_baseline[file_with_errors] = 0

    tmp_baseline = Path("pyright-baseline.json.tmp")
    try:
        tmp_baseline.write_text(json.dumps(fake_baseline), encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_pyright_audit.py",
                "--fail-on-increase",
                "--baseline-file",
                str(tmp_baseline),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        assert result.returncode == 1
        assert "increased" in result.stdout.lower() or "increased" in result.stderr.lower()
    finally:
        if tmp_baseline.exists():
            tmp_baseline.unlink()


def test_fail_on_increase_passes_when_no_increase():
    """GREEN: If no file increased, exit 0 and print OK.

    Uses the real baseline and asserts the script returns 0 with an
    "OK: No files increased" message.
    """
    result = subprocess.run(
        [sys.executable, "scripts/run_pyright_audit.py", "--fail-on-increase"],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK: No files increased" in result.stdout
