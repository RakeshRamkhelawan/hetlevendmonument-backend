#!/usr/bin/env python3
"""
Parallel Test Runner for SanskritiSetu
Optimized for speed with proper worker allocation per test type.
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# Test categories with optimal worker settings
TEST_PROFILES = {
    "unit": {
        "paths": ["tests/unit"],
        "workers": 4,  # Parallel safe
        "timeout": 60,
        "markers": "unit",
    },
    "integration": {
        "paths": ["tests/integration"],
        "workers": 2,  # Some DB contention
        "timeout": 120,
        "markers": "integration",
    },
    "e2e": {
        "paths": ["tests/e2e"],
        "workers": 1,  # Sequential (shared state)
        "timeout": 300,
        "markers": "e2e",
    },
    "security": {
        "paths": ["tests/security"],
        "workers": 2,
        "timeout": 120,
        "markers": "security",
    },
    "als": {
        "paths": ["tests/als"],
        "workers": 2,
        "timeout": 120,
        "markers": "als",
    },
    "enterprise": {
        "paths": ["tests/enterprise"],
        "workers": 2,
        "timeout": 120,
        "markers": None,
    },
    "performance": {
        "paths": ["tests/performance", "tests/chaos"],
        "workers": 1,  # Benchmarks sequential
        "timeout": 180,
        "markers": "performance",
    },
    "governance": {
        "paths": ["tests/governance", "tests/compliance"],
        "workers": 2,
        "timeout": 60,
        "markers": "governance",
    },
}


def run_test_profile(name: str, config: dict) -> dict:
    """Run a test profile with optimal settings."""
    paths = [p for p in config["paths"] if Path(p).exists()]
    if not paths:
        return {"name": name, "status": "skipped", "reason": "no paths"}

    workers = config["workers"]
    timeout = config["timeout"]
    markers = config.get("markers")

    # Build command
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *paths,
        "-v",
        "--tb=short",
        "--timeout",
        str(timeout),
        "--ignore=tests/root_scripts",
        "--ignore=tests/manual",
    ]

    # Add xdist for parallel execution if workers > 1
    if workers > 1:
        cmd.extend(["-n", str(workers), "--dist", "loadfile"])
    else:
        cmd.append("-pno:xdist")  # Disable xdist

    # Add marker filter if specified
    if markers:
        cmd.extend(["-m", markers])

    print(f"\n{'='*60}")
    print(f"Running {name} tests (workers={workers})...")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    start = datetime.now()
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = (datetime.now() - start).total_seconds()

    # Parse results
    output = result.stdout + "\n" + result.stderr
    passed = output.count(" PASSED")
    failed = output.count(" FAILED")
    error = output.count(" ERROR")
    skipped = output.count(" SKIPPED")

    return {
        "name": name,
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "duration": duration,
        "passed": passed,
        "failed": failed,
        "error": error,
        "skipped": skipped,
        "output": output[-2000:] if len(output) > 2000 else output,
    }


def run_all_profiles():
    """Run all test profiles and report results."""
    results = []

    # Run sequentially but each profile may use parallel workers
    for name, config in TEST_PROFILES.items():
        result = run_test_profile(name, config)
        results.append(result)

        # Save progress
        with open("logs/parallel_test_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 60)
    print("PARALLEL TEST RUN SUMMARY")
    print("=" * 60)

    total_passed = 0
    total_failed = 0
    total_duration = 0

    for r in results:
        status_icon = "[OK]" if r["status"] == "passed" else "[FAIL]"
        print(
            f"{status_icon} {r['name']:15} | {r['passed']:4} passed | {r['failed']:4} failed | {r['duration']:6.1f}s"
        )
        total_passed += r.get("passed", 0)
        total_failed += r.get("failed", 0)
        total_duration += r.get("duration", 0)

    print("=" * 60)
    print(f"TOTAL: {total_passed} passed, {total_failed} failed, {total_duration:.1f}s")
    print("=" * 60)

    return total_failed == 0


def run_fast_feedback():
    """Run only fast unit tests for quick feedback."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit",
        "-m",
        "not slow",
        "-x",  # Stop on first failure
        "--tb=line",
        "--timeout",
        "30",
        "-n",
        "4",
    ]

    print("Running fast feedback tests...")
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run tests with parallel optimization")
    parser.add_argument("profile", nargs="?", help="Run specific profile")
    parser.add_argument("--all", action="store_true", help="Run all profiles")
    parser.add_argument("--fast", action="store_true", help="Fast feedback only")
    parser.add_argument("--ci", action="store_true", help="CI mode (parallel safe)")

    args = parser.parse_args()

    if args.fast:
        success = run_fast_feedback()
    elif args.all or args.ci:
        success = run_all_profiles()
    elif args.profile:
        if args.profile in TEST_PROFILES:
            result = run_test_profile(args.profile, TEST_PROFILES[args.profile])
            print(json.dumps(result, indent=2, default=str))
            success = result["status"] == "passed"
        else:
            print(f"Unknown profile: {args.profile}")
            print(f"Available: {', '.join(TEST_PROFILES.keys())}")
            success = False
    else:
        print("Usage:")
        print("  python scripts/run_tests_parallel.py --fast     # Quick feedback")
        print("  python scripts/run_tests_parallel.py --all      # Full suite")
        print("  python scripts/run_tests_parallel.py --ci       # CI mode")
        print("  python scripts/run_tests_parallel.py <profile>  # Specific profile")
        print(f"\nProfiles: {', '.join(TEST_PROFILES.keys())}")
        success = True

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
