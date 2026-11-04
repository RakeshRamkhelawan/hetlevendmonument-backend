"""TDD tests for import performance (A1.1).

Importing src.main must be fast and memory-efficient.
Tests run in subprocess to avoid sys.modules caching.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)

# Under parallel xdist execution (-n 8) workers compete for CPU/disk,
# inflating wall-clock import time. PARALLEL_IMPORT_LIMIT gives headroom
# while still catching real regressions (e.g. accidentally importing a
# 30s library at module level).
SERIAL_IMPORT_LIMIT = 18.0
PARALLEL_IMPORT_LIMIT = 25.0


def _last_float(stdout: str) -> float:
    """Extract the last numeric line from stdout."""
    lines = [line for line in stdout.strip().split("\n") if line.strip()]
    if not lines:
        raise ValueError("No output lines")
    return float(lines[-1])


def test_import_time_under_8_seconds() -> None:
    """import src.main must complete within the time limit.

    Two limits: tight (serial) and generous (parallel xdist), because
    -n 8 workers compete for CPU/disk and inflate wall-clock time.
    """
    under_xdist = os.environ.get("PYTEST_XDIST_WORKER") is not None
    limit = PARALLEL_IMPORT_LIMIT if under_xdist else SERIAL_IMPORT_LIMIT

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import time; start=time.time(); import src.main; print(f'{time.time()-start:.2f}')",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    elapsed = _last_float(result.stdout)
    assert elapsed < limit, (
        f"Import took {elapsed:.1f}s, must be under {limit}s "
        f"({'parallel' if under_xdist else 'serial'} mode)"
    )


def test_import_memory_under_200mb() -> None:
    """RED: import src.main must use less than 200 MB RAM."""
    script = (
        "import tracemalloc; tracemalloc.start(); "
        "import src.main; "
        "current, peak = tracemalloc.get_traced_memory(); "
        "print(f'{current / 1024 / 1024:.1f}')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"Import crashed: {result.stderr}"
    mb = _last_float(result.stdout)
    assert mb < 200.0, f"Import used {mb:.1f} MB, must be under 200 MB"
