#!/usr/bin/env python3
"""
Complete authentication flow test
Tests login -> get token -> use token to access /me
"""

import asyncio
import json
from typing import Any, Dict

import requests

BASE_URL = "http://localhost:8001"
TEST_CREDENTIALS = {
    "admin": {"email": "admin@sanskritisetu.org", "password": "Admin123!"},
    "user": {"email": "Demo@sanskritisetu.org", "password": "Demo123!"},
}


def test_login(user_type: str = "admin") -> Dict[str, Any]:
    """Test login endpoint"""
    print(f"\n[TEST 1] Login as {user_type}")
    print("=" * 60)

    creds = TEST_CREDENTIALS[user_type]
    url = f"{BASE_URL}/api/v1/auth/login"

    payload = {"email": creds["email"], "password": creds["password"]}

    print(f"POST {url}")
    print(f"Body: {json.dumps(payload, indent=2)}")

    response = requests.post(url, json=payload)
    print(f"Status: {response.status_code}")

    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        if response.status_code == 200:
            print("✅ LOGIN SUCCESSFUL")
            return data
        else:
            print("❌ LOGIN FAILED")
            return None
    except Exception as e:
        print(f"❌ Error parsing response: {e}")
        print(f"Raw response: {response.text}")
        return None


def test_me_endpoint(token: str, token_type: str = "bearer") -> bool:
    """Test /me endpoint with token"""
    print("\n[TEST 2] Get /me with token")
    print("=" * 60)

    url = f"{BASE_URL}/api/v1/auth/me"
    headers = {"Authorization": f"{token_type} {token}"}

    print(f"GET {url}")
    print(f"Headers: Authorization: {token_type} {token[:50]}...")

    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")

    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        if response.status_code == 200:
            print("✅ /ME ENDPOINT SUCCESS")
            return True
        else:
            print("❌ /ME ENDPOINT FAILED")
            return False
    except Exception as e:
        print(f"❌ Error parsing response: {e}")
        print(f"Raw response: {response.text}")
        return False


def test_protected_endpoint(token: str) -> bool:
    """Test a protected endpoint"""
    print("\n[TEST 3] Access protected endpoint")
    print("=" * 60)

    url = f"{BASE_URL}/api/v1/auth/protected-test"
    headers = {"Authorization": f"Bearer {token}"}

    print(f"GET {url}")
    print(f"Headers: Authorization: Bearer {token[:50]}...")

    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")

    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        if response.status_code == 200:
            print("✅ PROTECTED ENDPOINT SUCCESS")
            return True
        else:
            print("❌ PROTECTED ENDPOINT FAILED")
            return False
    except Exception as e:
        print(f"❌ Error parsing response: {e}")
        print(f"Raw response: {response.text}")
        return False


def main():
    print("\n" + "=" * 60)
    print("AUTHENTICATION FLOW TEST")
    print("=" * 60)

    # Test 1: Login
    login_response = test_login("admin")
    if not login_response:
        print("\n❌ TESTS ABORTED - Login failed")
        return

    # Extract token from response
    access_token = login_response.get("access_token")
    if not access_token:
        print("\n❌ No access_token in response")
        return

    print(f"\n✅ Extracted token: {access_token[:50]}...")

    # Test 2: /me endpoint
    me_success = test_me_endpoint(access_token)

    # Test 3: Protected endpoint (if /me succeeded)
    if me_success:
        protected_success = test_protected_endpoint(access_token)
    else:
        print("\n⚠️ Skipping protected endpoint test because /me failed")

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("✅ Login: SUCCESS")
    print(f"{'✅' if me_success else '❌'} /me endpoint: {'SUCCESS' if me_success else 'FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
