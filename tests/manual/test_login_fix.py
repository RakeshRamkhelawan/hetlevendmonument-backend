#!/usr/bin/env python3
"""
Test script to verify the login fix works end-to-end
"""

import json
import time

import requests

BASE_URL = "http://localhost:3005"
API_URL = "http://localhost:3005/api/v1"


def test_login_flow():
    """Test the complete login flow through the frontend proxy"""

    print("[1/4] Testing direct backend login...")
    response = requests.post(
        f"{API_URL}/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
    )
    print(f"  Status: {response.status_code}")
    if response.status_code != 200:
        print(f"  ERROR: {response.text}")
        return False

    data = response.json()
    token = data.get("access_token")
    print(f"  Token received: {token[:20]}...")

    print("\n[2/4] Testing /auth/me with token...")
    response = requests.get(f"{API_URL}/auth/me", headers={"Authorization": f"Bearer {token}"})
    print(f"  Status: {response.status_code}")
    if response.status_code != 200:
        print(f"  ERROR: {response.text}")
        return False

    user_data = response.json()
    print(f"  User: {user_data.get('email')}")

    print("\n[3/4] Testing with invalid credentials (should get 401)...")
    response = requests.post(
        f"{API_URL}/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "WrongPassword"},
    )
    print(f"  Status: {response.status_code}")
    if response.status_code != 401:
        print(f"  ERROR: Expected 401, got {response.status_code}")
        return False

    error_data = response.json()
    error_msg = error_data.get("detail", error_data.get("message"))
    print(f"  Error message: {error_msg}")

    if "Invalid email or password" not in str(error_msg):
        print(f"  WARNING: Expected 'Invalid email or password', got '{error_msg}'")

    print("\n[4/4] Checking error response structure...")
    print(f"  Full error response: {json.dumps(error_data, indent=2)}")

    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    try:
        # Wait for services to be ready
        time.sleep(1)
        test_login_flow()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
