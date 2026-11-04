#!/usr/bin/env python3
"""
Complete authentication flow test for both tenants
Tests login -> get token -> use token to access /me endpoint
"""

import json
from typing import Any, Dict

import requests

BASE_URL = "http://localhost:8001"
TEST_CREDENTIALS = {
    "admin": {
        "email": "admin@sanskritisetu.org",
        "password": "Admin123!",
        "tenant": "Tenant 1",
    },
    "demo": {
        "email": "Demo@sanskritisetu.org",
        "password": "Demo123!",
        "tenant": "Tenant 1",
    },
}


def print_header(title: str):
    """Print formatted header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def test_complete_flow(user_type: str) -> bool:
    """Test complete auth flow for a user"""
    print_header(f"Testing {user_type.upper()} User")

    creds = TEST_CREDENTIALS[user_type]

    # Step 1: Login
    print("\n[STEP 1] Login")
    print(f"  Email: {creds['email']}")
    print(f"  Tenant: {creds['tenant']}")

    login_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )

    if login_response.status_code != 200:
        print(f"  ❌ Login failed with status {login_response.status_code}")
        print(f"  Response: {login_response.json()}")
        return False

    login_data = login_response.json()
    access_token = login_data.get("access_token")
    user_info = login_data.get("user", {})

    print("  ✅ Login successful")
    print(f"  Token: {access_token[:50]}...")
    print(f"  User ID: {user_info.get('id')}")
    print(f"  Tenant ID: {user_info.get('tenant_id')}")
    print(f"  Roles: {user_info.get('roles')}")

    # Step 2: Call /me endpoint
    print("\n[STEP 2] Get /me endpoint")
    print(f"  Authorization: bearer {access_token[:50]}...")

    me_response = requests.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"bearer {access_token}"},  # lowercase bearer
    )

    if me_response.status_code != 200:
        print(f"  ❌ /me endpoint failed with status {me_response.status_code}")
        print(f"  Response: {me_response.json()}")
        return False

    me_data = me_response.json()

    print("  ✅ /me endpoint successful")
    print(f"  Email: {me_data.get('email')}")
    print(f"  User ID: {me_data.get('id')}")
    print(f"  Tenant ID: {me_data.get('tenant_id')}")
    print(f"  Roles: {me_data.get('roles')}")

    # Verify data consistency
    if user_info.get("id") != me_data.get("id"):
        print("  ⚠️ WARNING: User ID mismatch!")
        return False

    if user_info.get("tenant_id") != me_data.get("tenant_id"):
        print("  ⚠️ WARNING: Tenant ID mismatch!")
        return False

    print(f"\n  ✅ All checks passed for {user_type} user")
    return True


def test_case_insensitive_bearer():
    """Test that Bearer header is case-insensitive"""
    print_header("Testing Case-Insensitive Bearer Header")

    # Get token
    login_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
    )
    token = login_response.json()["access_token"]

    test_cases = [
        ("Bearer", f"Bearer {token}"),
        ("bearer", f"bearer {token}"),
        ("BEARER", f"BEARER {token}"),
        ("BeArEr", f"BeArEr {token}"),
    ]

    all_passed = True
    for name, header_value in test_cases:
        response = requests.get(
            f"{BASE_URL}/api/v1/auth/me", headers={"Authorization": header_value}
        )
        status = "✅" if response.status_code == 200 else "❌"
        all_passed = all_passed and (response.status_code == 200)
        print(f"  {status} {name:10} -> Status {response.status_code}")

    return all_passed


def main():
    print("\n" + "=" * 70)
    print("  SANSKRITI SETU - AUTHENTICATION FLOW VERIFICATION")
    print("=" * 70)

    results = {}

    # Test both users
    for user_type in ["admin", "demo"]:
        results[user_type] = test_complete_flow(user_type)

    # Test case-insensitive Bearer
    results["case_insensitive"] = test_case_insensitive_bearer()

    # Summary
    print_header("SUMMARY")
    print(f"  ✅ Admin user flow:        {'PASS' if results['admin'] else 'FAIL'}")
    print(f"  ✅ Demo user flow:         {'PASS' if results['demo'] else 'FAIL'}")
    print(f"  ✅ Case-insensitive Bearer: {'PASS' if results['case_insensitive'] else 'FAIL'}")

    all_passed = all(results.values())
    print(f"\n  Overall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    print("=" * 70 + "\n")

    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nAborted by user")
        exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
