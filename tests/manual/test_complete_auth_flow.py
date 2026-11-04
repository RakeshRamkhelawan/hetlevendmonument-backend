"""Complete authentication flow test - Login + /me endpoint"""

import pytest
import requests


def _test_user(email, password, tenant_name):
    """Helper function to test a user login and /me endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing: {email} ({tenant_name})")
    print("=" * 60)

    # Step 1: Login
    print("1. POST /api/v1/auth/login")
    try:
        login_response = requests.post(
            "http://localhost:8001/api/v1/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        print(f"   Status: {login_response.status_code}")

        if login_response.status_code != 200:
            print(f"   Login failed: {login_response.text[:200]}")
            return False

        token_data = login_response.json()
        access_token = token_data.get("access_token")
        print(f"   Token received: {access_token[:50]}...")

    except Exception as e:
        print(f"   Login error: {e}")
        return False

    # Step 2: Get user profile with token
    print("\n2. GET /api/v1/auth/me")
    try:
        me_response = requests.get(
            "http://localhost:8001/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        print(f"   Status: {me_response.status_code}")

        if me_response.status_code != 200:
            print(f"   /me failed: {me_response.text[:200]}")
            return False

        user_data = me_response.json()
        print(
            f"   User: {user_data.get('email')} "
            f"(ID: {user_data.get('id')}, Tenant: {user_data.get('tenant_id')})"
        )
        return True

    except Exception as e:
        print(f"   /me error: {e}")
        return False


@pytest.mark.skip(reason="Manual test script")
def test_complete_auth_flow():
    """Complete authentication flow test - manual execution only"""
    # Test both tenants
    print("\n" + "=" * 60)
    print("COMPLETE AUTHENTICATION FLOW TEST")
    print("=" * 60)

    results = []
    results.append(
        (
            "Admin",
            _test_user("admin@sanskritisetu.org", "Admin123!", "SanskritiSetu Admin"),
        )
    )
    results.append(("Demo", _test_user("Demo@sanskritisetu.org", "Demo123!", "Demo Organization")))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{name} tenant: {status}")

    all_passed = all(success for _, success in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 60)
