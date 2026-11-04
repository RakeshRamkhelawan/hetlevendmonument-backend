"""Test /auth/me endpoint"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script - requires running backend")
def test_me_endpoint():
    """Test /auth/me endpoint - manual execution only"""
    # 1. Login
    login_resp = requests.post(
        "http://localhost:8001/api/v1/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "admin123"},
    )
    print(f"Login: {login_resp.status_code}")
    token = login_resp.json()["access_token"]
    print(f"Token: {token[:50]}...")

    # 2. Test /auth/me
    me_resp = requests.get(
        "http://localhost:8001/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    print(f"\n/auth/me: {me_resp.status_code}")
    if me_resp.ok:
        print(f"User: {me_resp.json()}")
    else:
        print(f"Error: {me_resp.text}")
