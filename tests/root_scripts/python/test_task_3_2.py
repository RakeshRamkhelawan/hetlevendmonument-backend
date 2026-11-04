"""Quick script to check if SecurityHeadersMiddleware is registered and working.

This file lives under tests/, but it is a utility script and must not be auto-collected
by pytest. Running application code at import time causes slow/noisy test collection.
"""

import sys

sys.path.insert(0, "src")

from fastapi.testclient import TestClient

from src.main import app

# Prevent pytest from collecting this helper script as a test module.
__test__ = False


def main() -> None:
    """Run middleware/header checks as a standalone script."""
    client = TestClient(app)

    print("Testing SecurityHeadersMiddleware...")
    print("=" * 60)

    # Test 1: Check middleware is registered
    print("\n1. Middleware Registration:")
    middleware_names = [m.cls.__name__ for m in app.user_middleware]
    print(f"   Registered middleware: {middleware_names}")

    if "SecurityHeadersMiddleware" in middleware_names:
        print("   [OK] SecurityHeadersMiddleware IS REGISTERED")
    else:
        print("   [FAIL] SecurityHeadersMiddleware NOT REGISTERED")

    # Test 2: Check security headers in response
    print("\n2. Security Headers Test:")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")

    security_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": True,  # Just check presence
    }

    found = 0
    for header, expected in security_headers.items():
        if header in response.headers:
            actual = response.headers[header]
            if expected is True or expected in actual:
                print(f"   [OK] {header}: {actual}")
                found += 1
            else:
                print(f"   [WARN] {header}: {actual} (expected: {expected})")
        else:
            print(f"   [FAIL] {header}: MISSING")

    print(f"\n   Found {found}/{len(security_headers)} security headers")

    if found >= 4:
        print("\n[OK] TASK 3.2: ALREADY COMPLETE - SecurityHeadersMiddleware works!")
    else:
        print("\n[FAIL] TASK 3.2: INCOMPLETE - Missing security headers")

    print("=" * 60)


if __name__ == "__main__":
    main()
