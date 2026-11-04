"""Simple /me test without Unicode"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script - requires running backend")
def test_me_simple():
    """Simple /me test - manual execution only"""
    # Test admin user
    print("\n[TEST 1] Admin user:")
    r1 = requests.post(
        "http://localhost:8001/api/v1/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
        timeout=15,
    )
    print(f"Login status: {r1.status_code}")

    if r1.status_code == 200:
        token = r1.json()["access_token"]
        print(f"Token: {token[:50]}...")

        r2 = requests.get(
            "http://localhost:8001/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        print(f"/me status: {r2.status_code}")

        if r2.status_code == 200:
            print(f"/me response: {r2.json()}")
            print("[PASS] Admin user authenticated successfully")
        else:
            print(f"/me error: {r2.text[:200]}")
            print("[FAIL] Token verification failed")
    else:
        print(f"Login error: {r1.text[:200]}")
        print("[FAIL] Login failed")

    # Test Demo user
    print("\n[TEST 2] Demo user:")
    r3 = requests.post(
        "http://localhost:8001/api/v1/auth/login",
        json={"email": "Demo@sanskritisetu.org", "password": "Demo123!"},
        timeout=15,
    )
    print(f"Login status: {r3.status_code}")

    if r3.status_code == 200:
        token2 = r3.json()["access_token"]
        print(f"Token: {token2[:50]}...")

        r4 = requests.get(
            "http://localhost:8001/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token2}"},
            timeout=10,
        )
        print(f"/me status: {r4.status_code}")

        if r4.status_code == 200:
            print(f"/me response: {r4.json()}")
            print("[PASS] Demo user authenticated successfully")
        else:
            print(f"/me error: {r4.text[:200]}")
            print("[FAIL] Token verification failed")
    else:
        print(f"Login error: {r3.text[:200]}")
        print("[FAIL] Login failed")
