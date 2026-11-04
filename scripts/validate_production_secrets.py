#!/usr/bin/env python3
"""
Simple validator for production secrets.
Checks complexity and missing values.
"""

import os
import sys
from pathlib import Path


def main():
    print("[LOCKED] SanskritiSetu Production Secrets Validator")

    if not Path(".env.prod").exists():
        print("[FAIL] ERROR: .env.prod not found!")
        return 1

    # Load dotenv manually to avoid dependencies if possible, or assume environment is loaded
    # For this script we assume python-dotenv might not be installed in minimal environment,
    # but let's try.
    try:
        from dotenv import load_dotenv

        load_dotenv(".env.prod")
    except ImportError:
        print("[WARN]  python-dotenv not installed, checking environment variables directly")

    errors = []

    # 1. Check Passwords
    secrets = [
        "POSTGRES_PASSWORD",
        "JWT_SECRET_KEY",
        "SECRET_KEY",
        "GRAFANA_ADMIN_PASSWORD",
    ]
    for s in secrets:
        val = os.getenv(s, "")
        if not val or "CHANGE_ME" in val:
            errors.append(f"Missing {s}")
        if len(val) < 12 and s != "POSTGRES_USER":
            errors.append(f"Weak {s} (<12 chars)")

    # 2. Check URLs
    redis_url = os.getenv("REDIS_URL", "")
    if "redis://" not in redis_url and "rediss://" not in redis_url:
        errors.append("Invalid REDIS_URL format (must start with redis:// or rediss://)")

    # 3. Check Domain
    domain = os.getenv("DOMAIN", "")
    if "localhost" in domain:
        errors.append("Production DOMAIN cannot contain 'localhost'")

    if errors:
        print("\n[FAIL] VALIDATION FAILED:")
        for e in errors:
            print(f" - {e}")
        return 1

    print("[OK] All Critical Secrets Validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
