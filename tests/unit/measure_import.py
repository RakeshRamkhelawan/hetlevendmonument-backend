"""Measure import time and memory for src.main."""

import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def measure_time():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import time; start=time.time(); import src.main; "
            "import sys; sys.stdout.write(f'{time.time()-start:.2f}\\n')",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("test_import_time_under_8_seconds: FAIL (crashed)")
        print(result.stderr[:500])
        return
    # Extract the last line which should be the timing
    lines = [line for line in result.stdout.strip().split("\n") if line.strip()]
    if not lines:
        print("test_import_time_under_8_seconds: FAIL (no output)")
        return
    try:
        elapsed = float(lines[-1])
    except ValueError:
        print(f"test_import_time_under_8_seconds: FAIL (could not parse: {lines[-1]!r})")
        return
    if elapsed < 8.0:
        print(f"test_import_time_under_8_seconds: PASS ({elapsed:.1f}s)")
    else:
        print(f"test_import_time_under_8_seconds: FAIL ({elapsed:.1f}s > 8.0s)")


def measure_memory():
    script = (
        "import tracemalloc; tracemalloc.start(); "
        "import src.main; "
        "current, peak = tracemalloc.get_traced_memory(); "
        "import sys; sys.stdout.write(f'{current / 1024 / 1024:.1f}\\n')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("test_import_memory_under_200mb: FAIL (crashed)")
        print(result.stderr[:500])
        return
    lines = [line for line in result.stdout.strip().split("\n") if line.strip()]
    if not lines:
        print("test_import_memory_under_200mb: FAIL (no output)")
        return
    try:
        mb = float(lines[-1])
    except ValueError:
        print(f"test_import_memory_under_200mb: FAIL (could not parse: {lines[-1]!r})")
        return
    if mb < 200.0:
        print(f"test_import_memory_under_200mb: PASS ({mb:.1f} MB)")
    else:
        print(f"test_import_memory_under_200mb: FAIL ({mb:.1f} MB > 200 MB)")


if __name__ == "__main__":
    measure_time()
    measure_memory()
