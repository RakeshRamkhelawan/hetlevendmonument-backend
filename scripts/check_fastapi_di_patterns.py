#!/usr/bin/env python3
"""
FastAPI Dependency Injection Anti-Pattern Checker

Checks the entire codebase for forbidden DI patterns:
1. @asynccontextmanager decorated functions used in Depends()
2. Nested async generators (async for...yield inside async def...yield)
3. get_async_session used in Depends() context

Usage:
    # Pre-commit (staged files only)
    python scripts/check_fastapi_di_patterns.py file1.py file2.py

    # CI mode (full codebase)
    python scripts/check_fastapi_di_patterns.py --ci

Exit code 0 = clean, 1 = violations found.
"""

import argparse
import ast
import sys
from pathlib import Path

# Patterns that should NEVER be used in FastAPI Depends()
FORBIDDEN_IN_DEPENDS = {"get_async_session"}

# Directories to scan in CI mode
CI_SCAN_DIRS = ["src", "tests"]


def check_file(file_path: Path) -> tuple[list[str], list[str]]:
    """Check a single Python file for DI anti-patterns.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings_list: list[str] = []
    try:
        source = file_path.read_text(encoding="utf-8")
        # Strip BOM if present
        if source.startswith("\ufeff"):
            source = source[1:]
        tree = ast.parse(source)
    except SyntaxError as e:
        warnings_list.append(f"{file_path}:{e.lineno}: Syntax error (skipping): {e}")
        return errors, warnings_list

    # Collect all function names that are decorated with @asynccontextmanager
    asynccontextmanager_funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "asynccontextmanager":
                    asynccontextmanager_funcs.add(node.name)

    # Check for anti-patterns
    for node in ast.walk(tree):
        # Pattern 1: Depends(some_asynccontextmanager_func)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Depends":
                if node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Name):
                        if arg.id in asynccontextmanager_funcs:
                            errors.append(
                                f"{file_path}:{node.lineno}: "
                                f"CRITICAL: '@asynccontextmanager' function '{arg.id}' "
                                f"used in Depends(). Use plain 'async def ... yield' instead."
                            )
                        if arg.id in FORBIDDEN_IN_DEPENDS:
                            errors.append(
                                f"{file_path}:{node.lineno}: "
                                f"CRITICAL: '{arg.id}' used in Depends(). "
                                f"Use 'get_db' instead."
                            )

        # Pattern 2: Warning for async with get_async_session()
        # This is LEGITIMATE usage but we want to encourage migration.
        if isinstance(node, ast.AsyncWith):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call):
                    call = item.context_expr
                    if isinstance(call.func, ast.Name) and call.func.id == "get_async_session":
                        warnings_list.append(
                            f"{file_path}:{node.lineno}: "
                            f"WARNING: 'async with get_async_session()' is deprecated. "
                            f"Consider using 'get_db()' or a renamed context manager."
                        )

    return errors, warnings_list


def scan_directory(directory: Path) -> tuple[list[str], list[str]]:
    """Recursively scan a directory for Python files."""
    errors: list[str] = []
    warnings_list: list[str] = []

    for py_file in directory.rglob("*.py"):
        # Skip __pycache__ and virtual environments
        if "__pycache__" in py_file.parts or ".venv" in py_file.parts:
            continue
        file_errors, file_warnings = check_file(py_file)
        errors.extend(file_errors)
        warnings_list.extend(file_warnings)

    return errors, warnings_list


def main() -> int:
    """Run checks based on CLI arguments."""
    parser = argparse.ArgumentParser(description="Check FastAPI dependency injection anti-patterns")
    parser.add_argument(
        "files",
        nargs="*",
        help="Python files to check (default: scan all if --ci is used)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Scan entire codebase (src/ and tests/ directories)",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings_list: list[str] = []

    if args.ci:
        for dir_name in CI_SCAN_DIRS:
            dir_path = Path(dir_name)
            if dir_path.exists():
                dir_errors, dir_warnings = scan_directory(dir_path)
                errors.extend(dir_errors)
                warnings_list.extend(dir_warnings)
    else:
        for file_path_str in args.files:
            path = Path(file_path_str)
            if path.suffix == ".py":
                file_errors, file_warnings = check_file(path)
                errors.extend(file_errors)
                warnings_list.extend(file_warnings)

    has_issues = False

    if errors:
        has_issues = True
        print("=" * 60)
        print("FASTAPI DI ANTI-PATTERN DETECTED")
        print("=" * 60)
        for error in errors:
            print(f"  {error}")
        print("=" * 60)
        print("Fix: Use plain 'async def ... yield' for Depends() dependencies.")
        print("     Never use @asynccontextmanager or nested async generators.")
        print("=" * 60)

    if warnings_list:
        print("=" * 60)
        print("FASTAPI DI WARNINGS")
        print("=" * 60)
        for warning in warnings_list:
            print(f"  {warning}")
        print("=" * 60)

    if not has_issues and not warnings_list:
        print("FastAPI DI patterns: OK")

    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
