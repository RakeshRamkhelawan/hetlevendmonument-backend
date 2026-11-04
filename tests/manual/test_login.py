"""Simple login test"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script")
def test_login():
    """Simple login test - manual execution only"""
    response = requests.post(
        "http://localhost:8001/api/v1/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "admin123"},
    )

    print(f"Status: {response.status_code}")

    if response.ok:
        data = response.json()
        token = data.get("access_token", "")
        print("[OK] Login successful!")
        print(f"Token (first 50 chars): {token[:50]}...")
        print(f"Token type: {data.get('token_type')}")
    else:
        print(f"[FAIL] Error: {response.text}")
