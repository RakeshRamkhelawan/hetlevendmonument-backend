#!/usr/bin/env python3
"""
Security Configuration Validator
TDD GREEN PHASE: Minimal implementation to pass tests

Validates all security-critical configuration before deployment
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple


# Load .env file if it exists
def load_env_file():
    """Load environment variables from .env file"""
    try:
        from dotenv import load_dotenv

        # Try to find .env in current dir or parent dirs
        current_dir = Path.cwd()
        env_file = current_dir / ".env"

        if not env_file.exists():
            # Try parent directory (if running from scripts/)
            env_file = current_dir.parent / ".env"

        if env_file.exists():
            load_dotenv(env_file, override=False)
            print(f"[U+0001F4C4] Loaded environment from: {env_file}")
        else:
            print("[WARN]  No .env file found, using system environment variables")
    except ImportError:
        print("[WARN]  python-dotenv not installed, using system environment variables only")


def validate_jwt_secret() -> Tuple[bool, str]:
    """Validate JWT secret key strength"""
    secret = os.getenv("JWT_SECRET_KEY", "")

    if not secret:
        return False, "JWT_SECRET_KEY not set"

    if len(secret) < 32:
        return False, f"JWT secret too short ({len(secret)} chars, minimum 32)"

    # Check for common insecure patterns
    insecure_patterns = ["dev-", "test-", "change", "password"]
    for pattern in insecure_patterns:
        if pattern.lower() in secret.lower():
            return False, f"Insecure pattern '{pattern}' detected in secret"

    return True, f"JWT secret is strong ({len(secret)} characters)"


def validate_database_url() -> Tuple[bool, str]:
    """Validate database URL doesn't use default credentials"""
    db_url = os.getenv("DATABASE_URL", "")

    if not db_url:
        return False, "DATABASE_URL not set"

    # Check for weak default credentials
    weak_patterns = [
        "postgres:postgres@",
        ":password@",
        "root:root@",
        ":admin@",
    ]

    for pattern in weak_patterns:
        if pattern in db_url:
            return False, f"Weak database credentials detected: {pattern}"

    return True, "Database credentials appear secure"


def validate_cors_policy() -> Tuple[bool, str]:
    """Validate CORS is not wide open"""
    allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*")

    if allowed_origins == "*":
        return False, "CORS allows ALL origins (security risk)"

    if "http://" in allowed_origins and os.getenv("ENVIRONMENT") == "production":
        return False, "HTTP origins in production (should be HTTPS only)"

    return True, f"CORS policy is restrictive: {allowed_origins}"


def validate_environment_mode() -> Tuple[bool, str]:
    """Validate environment is explicitly set"""
    env = os.getenv("ENVIRONMENT", "").lower()

    if not env:
        return False, "ENVIRONMENT not set (should be development/staging/production)"

    if env not in ["development", "staging", "production"]:
        return False, f"Unknown environment: {env}"

    return True, f"Environment: {env}"


def validate_debug_mode() -> Tuple[bool, str]:
    """Validate DEBUG is disabled in production"""
    env = os.getenv("ENVIRONMENT", "").lower()
    debug = os.getenv("DEBUG", "False").lower()

    if env == "production" and debug in ["true", "1", "yes"]:
        return False, "DEBUG mode enabled in PRODUCTION (critical risk)"

    return True, "DEBUG mode configuration OK"


def main():
    """Run all security configuration validations"""
    # Load .env file first
    load_env_file()
    print()

    print("=" * 70)
    print("SECURITY CONFIGURATION VALIDATOR")
    print("=" * 70)
    print()

    validators = [
        ("JWT Secret", validate_jwt_secret),
        ("Database URL", validate_database_url),
        ("CORS Policy", validate_cors_policy),
        ("Environment Mode", validate_environment_mode),
        ("Debug Mode", validate_debug_mode),
    ]

    results: List[Tuple[str, bool, str]] = []

    for name, validator in validators:
        try:
            is_valid, message = validator()
            results.append((name, is_valid, message))
        except Exception as e:
            results.append((name, False, f"Validation error: {str(e)}"))

    # Print results
    all_passed = True
    for name, is_valid, message in results:
        status = "[OK] PASS" if is_valid else "[FAIL] FAIL"
        print(f"{status} | {name:20s} | {message}")
        if not is_valid:
            all_passed = False

    print()
    print("=" * 70)

    if all_passed:
        print("[OK] ALL SECURITY CHECKS PASSED")
        print("System is ready for deployment")
        sys.exit(0)
    else:
        print("[FAIL] SECURITY VALIDATION FAILED")
        print("Fix the issues above before deploying")
        sys.exit(1)


if __name__ == "__main__":
    main()
