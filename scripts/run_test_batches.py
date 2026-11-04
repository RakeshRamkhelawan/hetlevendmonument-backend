#!/usr/bin/env python3
"""
Test Batch Runner for SanskritiSetu
Runs tests in batches of ~500 to manage memory and complexity.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Test batches configuration (~500 tests each)
BATCHES = {
    1: {
        "name": "Core Unit Tests",
        "paths": [
            "tests/unit/test_core",
            "tests/unit/test_auth",
            "tests/unit/test_api",
            "tests/unit/test_security",
            "tests/unit/test_config",
        ],
        "estimated_tests": 450,
    },
    2: {
        "name": "Unit Tests - Agents",
        "paths": [
            "tests/unit/agents",
            "tests/unit/capabilities",
            "tests/unit/test_agents",
        ],
        "estimated_tests": 500,
    },
    3: {
        "name": "Unit Tests - Remaining",
        "paths": [
            "tests/unit",
        ],
        "exclude": [
            "tests/unit/test_core",
            "tests/unit/test_auth",
            "tests/unit/test_api",
            "tests/unit/test_security",
            "tests/unit/test_config",
            "tests/unit/agents",
            "tests/unit/capabilities",
            "tests/unit/test_agents",
        ],
        "estimated_tests": 500,
    },
    4: {
        "name": "Integration - Auth & Core",
        "paths": [
            "tests/integration/test_auth",
            "tests/integration/test_core",
            "tests/integration/test_config",
        ],
        "estimated_tests": 500,
    },
    5: {
        "name": "Integration - API Endpoints",
        "paths": [
            "tests/integration/api",
            "tests/integration/test_api",
            "tests/integration/test_endpoints",
        ],
        "estimated_tests": 500,
    },
    6: {
        "name": "Integration - Remaining",
        "paths": [
            "tests/integration",
        ],
        "exclude": [
            "tests/integration/test_auth",
            "tests/integration/test_core",
            "tests/integration/test_config",
            "tests/integration/api",
            "tests/integration/test_api",
            "tests/integration/test_endpoints",
        ],
        "estimated_tests": 500,
    },
    7: {
        "name": "E2E Tests",
        "paths": [
            "tests/e2e",
        ],
        "estimated_tests": 500,
    },
    8: {
        "name": "ALS Tests",
        "paths": [
            "tests/als",
        ],
        "estimated_tests": 500,
    },
    9: {
        "name": "Security Tests",
        "paths": [
            "tests/security",
        ],
        "estimated_tests": 500,
    },
    10: {
        "name": "Performance & Chaos",
        "paths": [
            "tests/performance",
            "tests/chaos",
        ],
        "estimated_tests": 500,
    },
    11: {
        "name": "Governance & Compliance",
        "paths": [
            "tests/governance",
            "tests/compliance",
        ],
        "estimated_tests": 500,
    },
    12: {
        "name": "Enterprise Tests",
        "paths": [
            "tests/enterprise",
        ],
        "estimated_tests": 500,
    },
    13: {
        "name": "Phase Tests",
        "paths": [
            "tests/integration/phase",
            "tests/e2e/phase",
        ],
        "estimated_tests": 500,
    },
    14: {
        "name": "Canvas & Focus Builder",
        "paths": [
            "tests/integration/test_canvas",
            "tests/integration/test_focus_builder",
            "tests/unit/test_canvas",
            "tests/unit/test_focus_builder",
        ],
        "estimated_tests": 500,
    },
    15: {
        "name": "Procedures & Workflow",
        "paths": [
            "tests/integration/procedures",
            "tests/integration/workflow",
            "tests/unit/procedures",
            "tests/unit/workflow",
        ],
        "estimated_tests": 500,
    },
    16: {
        "name": "Tool Broker & Monitoring",
        "paths": [
            "tests/core/tool_broker",
            "tests/integration/monitoring",
            "tests/unit/monitoring",
        ],
        "estimated_tests": 500,
    },
    17: {
        "name": "Event Handlers & Infrastructure",
        "paths": [
            "tests/event_handlers",
            "tests/infrastructure",
            "tests/integration/event_handlers",
        ],
        "estimated_tests": 500,
    },
    18: {
        "name": "Semantic Router & AI Quality",
        "paths": [
            "tests/semantic_router",
            "tests/integration/ai_quality",
            "tests/unit/ai_quality",
        ],
        "estimated_tests": 500,
    },
    19: {
        "name": "Regression & Resilience",
        "paths": [
            "tests/regression",
            "tests/integration/resilience",
        ],
        "estimated_tests": 500,
    },
    20: {
        "name": "Remaining Tests",
        "paths": [
            "tests",
        ],
        "exclude": [
            "tests/unit",
            "tests/integration",
            "tests/e2e",
            "tests/als",
            "tests/security",
            "tests/performance",
            "tests/chaos",
            "tests/governance",
            "tests/compliance",
            "tests/enterprise",
            "tests/event_handlers",
            "tests/infrastructure",
            "tests/regression",
            "tests/core",
            "tests/semantic_router",
            "tests/fixtures",
            "tests/manual",
            "tests/root_scripts",
            "tests/__pycache__",
        ],
        "estimated_tests": 500,
    },
}


def get_existing_paths(paths: List[str]) -> List[str]:
    """Filter to only existing paths."""
    return [p for p in paths if Path(p).exists()]


def run_batch(batch_num: int, verbose: bool = True) -> Dict:
    """Run a specific batch of tests."""
    if batch_num not in BATCHES:
        print(f"Batch {batch_num} not found!")
        return {"error": "Batch not found"}

    batch = BATCHES[batch_num]
    paths = get_existing_paths(batch["paths"])

    if not paths:
        print(f"No valid paths found for batch {batch_num}")
        return {"error": "No valid paths"}

    print(f"\n{'='*60}")
    print(f"BATCH {batch_num}: {batch['name']}")
    print(f"Estimated tests: {batch['estimated_tests']}")
    print(f"Paths: {paths}")
    print(f"{'='*60}\n")

    # Build pytest command
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *paths,
        "-v",
        "--tb=short",
        "--continue-on-collection-errors",
        "--ignore=tests/root_scripts",
        "-p",
        "no:warnings",
    ]

    # Add excludes if specified
    if "exclude" in batch:
        for exclude in batch["exclude"]:
            if Path(exclude).exists():
                cmd.extend(["--ignore", exclude])

    if verbose:
        print(f"Command: {' '.join(cmd)}\n")

    # Run tests
    start_time = datetime.now()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,  # 30 minute timeout per batch
    )
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Parse results
    output = result.stdout + "\n" + result.stderr

    # Count pass/fail
    passed = output.count(" PASSED")
    failed = output.count(" FAILED")
    error = output.count(" ERROR")
    skipped = output.count(" SKIPPED")

    # Extract failures
    failures = []
    lines = output.split("\n")
    for i, line in enumerate(lines):
        if "FAILED" in line or "ERROR" in line:
            failures.append(line.strip())

    result_dict = {
        "batch": batch_num,
        "name": batch["name"],
        "duration": duration,
        "return_code": result.returncode,
        "passed": passed,
        "failed": failed,
        "error": error,
        "skipped": skipped,
        "failures": failures[:20],  # First 20 failures
        "output": output if verbose else None,
    }

    # Print summary
    print(f"\n{'='*60}")
    print(f"BATCH {batch_num} RESULTS:")
    print(f"Duration: {duration:.1f}s")
    print(f"Passed: {passed}, Failed: {failed}, Errors: {error}, Skipped: {skipped}")
    print(f"Return code: {result.returncode}")
    if failures:
        print("\nFirst failures:")
        for f in failures[:10]:
            print(f"  - {f}")
    print(f"{'='*60}\n")

    return result_dict


def run_all_batches(start_from: int = 1):
    """Run all batches sequentially."""
    results = []

    for batch_num in range(start_from, 21):
        result = run_batch(batch_num)
        results.append(result)

        # Save progress
        progress_file = Path("logs/test_batch_progress.json")
        progress_file.parent.mkdir(exist_ok=True)
        with open(progress_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

        # Stop on critical error
        if result.get("error"):
            print(f"Critical error in batch {batch_num}, stopping.")
            break

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run test batches")
    parser.add_argument("batch", nargs="?", type=int, help="Run specific batch number (1-20)")
    parser.add_argument("--all", action="store_true", help="Run all batches")
    parser.add_argument("--from", dest="start_from", type=int, default=1, help="Start from batch N")

    args = parser.parse_args()

    if args.batch:
        run_batch(args.batch)
    elif args.all:
        run_all_batches(args.start_from)
    else:
        print("Test Batch Runner")
        print(f"Total batches: {len(BATCHES)}")
        print("\nUsage:")
        print("  python scripts/run_test_batches.py 1      # Run batch 1")
        print("  python scripts/run_test_batches.py --all  # Run all batches")
        print("  python scripts/run_test_batches.py --all --from 5  # Start from batch 5")
        print("\nBatches:")
        for num, batch in BATCHES.items():
            paths = get_existing_paths(batch["paths"])
            print(
                f"  {num}: {batch['name']} (~{batch['estimated_tests']} tests, {len(paths)} dirs)"
            )


if __name__ == "__main__":
    main()
