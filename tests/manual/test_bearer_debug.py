#!/usr/bin/env python3
"""
Debug Bearer token extraction
"""

import pytest
import requests

BASE_URL = "http://localhost:8001"


@pytest.mark.skip(reason="Manual test script - requires running backend")
def test_bearer_debug():
    """Debug Bearer token extraction - manual execution only"""
    # Step 1: Get token
    print("[1] Getting token...")
    login_response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
    )
    print(f"Login response: {login_response.status_code}")
    token = login_response.json().get("access_token")
    print(f"Token: {token[:50]}...")

    # Step 2: Call /me with various header formats
    print("\n[2] Testing different Authorization header formats...")

    test_cases = [
        ("Bearer " + token, "Bearer (space)"),
        ("bearer " + token, "bearer (lowercase, space)"),
        (token, "No prefix"),
    ]

    for header_value, description in test_cases:
        print(f"\n  Testing: {description}")
        print(f"  Header value: {header_value[:50]}...")

        response = requests.get(
            f"{BASE_URL}/api/v1/auth/me", headers={"Authorization": header_value}
        )

        print(f"  Response status: {response.status_code}")
        print(f"  Response body: {response.json()}")
