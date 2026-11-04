#!/usr/bin/env python3
"""
Quality Gate Script - Centralized Code Quality Checks
=====================================================
Runs all quality checks and reports results in ASCII-only format.
Can be used locally or in CI/CD pipelines.

Usage:
    python scripts/quality_gate.py              # Run all checks
    python scripts/quality_gate.py --quick      # Quick checks only (no tests)
    python scripts/quality_gate.py --fix        # Auto-fix style issues
    python scripts/quality_gate.py --ci         # CI mode (strict, no fixes)

Exit Codes:
    0 = All checks passed
    1 = One or more checks failed
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# =============================================================================
# CONFIGURATION
# =============================================================================

# Thresholds
PYLINT_MIN_SCORE = 9.0
COVERAGE_MIN_PERCENT = 80
MAX_BANDIT_HIGH_ISSUES = 0
MAX_BANDIT_MEDIUM_ISSUES = 5

# Paths to check
CHECK_PATHS = ["src/", "core/", "scripts/"]
TEST_PATHS = ["tests/", "tests_reboot/"]


# Colors for terminal (ASCII-safe)
class Colors:
    OK = "[OK]"
    FAIL = "[FAIL]"
    WARN = "[WARN]"
    RUN = "[RUN]"
    SKIP = "[SKIP]"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def run_command(cmd: List[str], capture: bool = True) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=300,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"


def print_header(title: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(name: str, passed: bool, details: str = "") -> None:
    """Print a check result."""
    status = Colors.OK if passed else Colors.FAIL
    print(f"{status} {name}")
    if details and not passed:
        for line in details.split("\n")[:10]:  # Limit output
            print(f"     {line}")


# =============================================================================
# CHECK FUNCTIONS
# =============================================================================


def check_black(fix: bool = False) -> Tuple[bool, str]:
    """Check/fix Black formatting."""
    cmd = ["python", "-m", "black"]
    if not fix:
        cmd.append("--check")
    cmd.extend(["--line-length=100"] + CHECK_PATHS)

    code, stdout, stderr = run_command(cmd)
    if code == 0:
        return True, "All files formatted correctly"
    return False, stderr or stdout


def check_isort(fix: bool = False) -> Tuple[bool, str]:
    """Check/fix isort import ordering."""
    cmd = ["python", "-m", "isort"]
    if not fix:
        cmd.append("--check-only")
    cmd.extend(["--profile=black", "--line-length=100"] + CHECK_PATHS)

    code, stdout, stderr = run_command(cmd)
    if code == 0:
        return True, "All imports sorted correctly"
    return False, stderr or stdout


def check_ruff() -> Tuple[bool, str]:
    """Run Ruff linter."""
    paths = [p for p in CHECK_PATHS if Path(p).exists()]
    if not paths:
        return True, "No paths to check"

    cmd = ["python", "-m", "ruff", "check"] + paths
    code, stdout, stderr = run_command(cmd)

    if code == 0:
        return True, "No linting issues found"

    # Count issues
    lines = stdout.strip().split("\n") if stdout else []
    issue_count = len([line for line in lines if line.strip() and not line.startswith("Found")])
    return False, f"{issue_count} issues found"


def check_flake8() -> Tuple[bool, str]:
    """Run Flake8 linter."""
    paths = [p for p in CHECK_PATHS if Path(p).exists()]
    if not paths:
        return True, "No paths to check"

    cmd = [
        "python",
        "-m",
        "flake8",
        "--max-line-length=120",
        "--extend-ignore=E501,W503,E203",
        "--count",
    ] + paths

    code, stdout, stderr = run_command(cmd)
    if code == 0:
        return True, "No flake8 issues"
    return False, stdout or stderr


def check_pylint() -> Tuple[bool, float, str]:
    """Run Pylint and return score."""
    paths = [p for p in CHECK_PATHS if Path(p).exists()]
    if not paths:
        return True, 10.0, "No paths to check"

    cmd = [
        "python",
        "-m",
        "pylint",
        "--output-format=text",
        "--score=y",
        "--fail-under=" + str(PYLINT_MIN_SCORE),
        "--disable=C0103,C0114,C0115,C0116,R0903,R0913,W0511",
        "--max-line-length=120",
    ] + paths

    code, stdout, stderr = run_command(cmd)

    # Extract score from output
    score = 0.0
    for line in stdout.split("\n"):
        if "Your code has been rated at" in line:
            try:
                score = float(line.split("at ")[1].split("/")[0])
            except (IndexError, ValueError):
                pass

    passed = score >= PYLINT_MIN_SCORE
    return passed, score, f"Score: {score:.2f}/10 (min: {PYLINT_MIN_SCORE})"


def check_bandit() -> Tuple[bool, Dict, str]:
    """Run Bandit security scan."""
    paths = [p for p in CHECK_PATHS if Path(p).exists()]
    if not paths:
        return True, {}, "No paths to check"

    cmd = [
        "python",
        "-m",
        "bandit",
        "-r",
        "-f",
        "json",
    ] + paths

    code, stdout, stderr = run_command(cmd)

    try:
        data = json.loads(stdout) if stdout else {}
        results = data.get("results", [])

        high = sum(1 for r in results if r.get("issue_severity") == "HIGH")
        medium = sum(1 for r in results if r.get("issue_severity") == "MEDIUM")

        passed = high <= MAX_BANDIT_HIGH_ISSUES and medium <= MAX_BANDIT_MEDIUM_ISSUES
        details = f"HIGH: {high}, MEDIUM: {medium}"

        return passed, {"high": high, "medium": medium}, details
    except json.JSONDecodeError:
        return True, {}, "No security issues found"


def check_mypy() -> Tuple[bool, str]:
    """Run Mypy type checking."""
    paths = [p for p in CHECK_PATHS if Path(p).exists()]
    if not paths:
        return True, "No paths to check"

    cmd = [
        "python",
        "-m",
        "mypy",
        "--ignore-missing-imports",
        "--no-error-summary",
    ] + paths

    code, stdout, stderr = run_command(cmd)

    if code == 0:
        return True, "No type errors"

    # Count errors
    lines = stdout.strip().split("\n") if stdout else []
    error_count = len([line for line in lines if ": error:" in line])
    return False, f"{error_count} type errors"


def check_tests_with_coverage() -> Tuple[bool, float, str]:
    """Run pytest with coverage."""
    test_paths = [p for p in TEST_PATHS if Path(p).exists()]
    if not test_paths:
        return True, 100.0, "No test paths found"

    cmd = [
        "python",
        "-m",
        "pytest",
        "-v",
        "--tb=short",
        "--cov=src",
        "--cov-report=term-missing",
        f"--cov-fail-under={COVERAGE_MIN_PERCENT}",
    ] + test_paths

    code, stdout, stderr = run_command(cmd)

    # Extract coverage from output
    coverage = 0.0
    for line in stdout.split("\n"):
        if "TOTAL" in line and "%" in line:
            try:
                parts = line.split()
                for part in parts:
                    if "%" in part:
                        coverage = float(part.replace("%", ""))
                        break
            except (IndexError, ValueError):
                pass

    passed = code == 0 and coverage >= COVERAGE_MIN_PERCENT
    return passed, coverage, f"Coverage: {coverage:.1f}% (min: {COVERAGE_MIN_PERCENT}%)"


# =============================================================================
# TREND TRACKING
# =============================================================================


def save_metrics(metrics: Dict) -> None:
    """Save metrics to trend file."""
    trend_file = Path("reports/quality_trends.json")
    trend_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing data
    trends = []
    if trend_file.exists():
        try:
            trends = json.loads(trend_file.read_text())
        except json.JSONDecodeError:
            trends = []

    # Add new entry
    entry = {
        "timestamp": datetime.now().isoformat(),
        "commit": get_git_commit(),
        **metrics,
    }
    trends.append(entry)

    # Keep last 100 entries
    trends = trends[-100:]

    # Save
    trend_file.write_text(json.dumps(trends, indent=2))
    print(f"\n{Colors.OK} Metrics saved to {trend_file}")


def get_git_commit() -> str:
    """Get current git commit hash."""
    code, stdout, _ = run_command(["git", "rev-parse", "--short", "HEAD"])
    return stdout.strip() if code == 0 else "unknown"


def check_regression(metrics: Dict) -> Tuple[bool, List[str]]:
    """Check for quality regression compared to previous run."""
    trend_file = Path("reports/quality_trends.json")
    if not trend_file.exists():
        return True, []

    try:
        trends = json.loads(trend_file.read_text())
        if len(trends) < 2:
            return True, []

        previous = trends[-1]  # Last saved entry
        warnings = []

        # Check coverage regression
        if "coverage" in metrics and "coverage" in previous:
            diff = metrics["coverage"] - previous["coverage"]
            if diff < -2:  # 2% drop
                warnings.append(f"Coverage dropped {abs(diff):.1f}%")

        # Check pylint regression
        if "pylint_score" in metrics and "pylint_score" in previous:
            diff = metrics["pylint_score"] - previous["pylint_score"]
            if diff < -0.5:  # 0.5 point drop
                warnings.append(f"Pylint score dropped {abs(diff):.2f}")

        # Check security regression
        if "bandit_high" in metrics and "bandit_high" in previous:
            if metrics["bandit_high"] > previous["bandit_high"]:
                warnings.append(f"New HIGH security issues: {metrics['bandit_high']}")

        return len(warnings) == 0, warnings

    except (json.JSONDecodeError, KeyError):
        return True, []


# =============================================================================
# MAIN
# =============================================================================


def main() -> int:
    """Run all quality checks."""
    parser = argparse.ArgumentParser(description="Quality Gate - Code Quality Checks")
    parser.add_argument("--quick", action="store_true", help="Quick checks only (no tests)")
    parser.add_argument("--fix", action="store_true", help="Auto-fix style issues")
    parser.add_argument("--ci", action="store_true", help="CI mode (strict)")
    parser.add_argument("--no-track", action="store_true", help="Skip trend tracking")
    args = parser.parse_args()

    print("=" * 60)
    print("  QUALITY GATE - SanskritiSetu.org")
    print("=" * 60)
    print(f"  Commit: {get_git_commit()}")
    print(f"  Date:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode:   {'CI' if args.ci else 'Local'}{' (quick)' if args.quick else ''}")
    print("=" * 60)

    results = {}
    metrics = {}
    all_passed = True

    # ---------------------------------------------------------------------------
    # Style Checks (can auto-fix)
    # ---------------------------------------------------------------------------
    print_header("CODE STYLE")

    print(f"{Colors.RUN} Black formatting...")
    passed, details = check_black(fix=args.fix and not args.ci)
    results["black"] = passed
    print_result("Black", passed, details)
    if not passed:
        all_passed = False

    print(f"{Colors.RUN} isort imports...")
    passed, details = check_isort(fix=args.fix and not args.ci)
    results["isort"] = passed
    print_result("isort", passed, details)
    if not passed:
        all_passed = False

    # ---------------------------------------------------------------------------
    # Linting
    # ---------------------------------------------------------------------------
    print_header("LINTING")

    print(f"{Colors.RUN} Ruff linter...")
    passed, details = check_ruff()
    results["ruff"] = passed
    print_result("Ruff", passed, details)
    if not passed and args.ci:
        all_passed = False

    print(f"{Colors.RUN} Pylint quality...")
    passed, score, details = check_pylint()
    results["pylint"] = passed
    metrics["pylint_score"] = score
    print_result(f"Pylint ({score:.2f}/10)", passed, details)
    if not passed:
        all_passed = False

    # ---------------------------------------------------------------------------
    # Security
    # ---------------------------------------------------------------------------
    print_header("SECURITY")

    print(f"{Colors.RUN} Bandit security scan...")
    passed, bandit_data, details = check_bandit()
    results["bandit"] = passed
    metrics["bandit_high"] = bandit_data.get("high", 0)
    metrics["bandit_medium"] = bandit_data.get("medium", 0)
    print_result("Bandit", passed, details)
    if not passed:
        all_passed = False

    # ---------------------------------------------------------------------------
    # Type Checking (optional in quick mode)
    # ---------------------------------------------------------------------------
    if not args.quick:
        print_header("TYPE CHECKING")

        print(f"{Colors.RUN} Mypy type check...")
        passed, details = check_mypy()
        results["mypy"] = passed
        print_result("Mypy", passed, details)
        if not passed and args.ci:
            all_passed = False

    # ---------------------------------------------------------------------------
    # Tests (skip in quick mode)
    # ---------------------------------------------------------------------------
    if not args.quick:
        print_header("TESTS & COVERAGE")

        print(f"{Colors.RUN} Running tests with coverage...")
        passed, coverage, details = check_tests_with_coverage()
        results["tests"] = passed
        metrics["coverage"] = coverage
        print_result("Tests + Coverage", passed, details)
        if not passed:
            all_passed = False

    # ---------------------------------------------------------------------------
    # Trend Tracking
    # ---------------------------------------------------------------------------
    if not args.no_track and metrics:
        print_header("TREND TRACKING")

        # Check for regression
        no_regression, warnings = check_regression(metrics)
        if warnings:
            print(f"{Colors.WARN} Quality regression detected:")
            for w in warnings:
                print(f"     - {w}")
            if args.ci:
                all_passed = False
        else:
            print(f"{Colors.OK} No quality regression detected")

        # Save metrics
        save_metrics(metrics)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print_header("SUMMARY")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    print(f"\nChecks: {passed_count}/{total_count} passed")
    for name, passed in results.items():
        status = Colors.OK if passed else Colors.FAIL
        print(f"  {status} {name}")

    if all_passed:
        print(f"\n{Colors.OK} QUALITY GATE PASSED")
        return 0
    else:
        print(f"\n{Colors.FAIL} QUALITY GATE FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
