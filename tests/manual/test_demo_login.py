"""Test Demo user login"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script")
def test_demo_login():
    """Demo login test - manual execution only"""
    print("TEST: Demo login")
    try:
        response = requests.post(
            "http://localhost:8001/api/v1/auth/login",
            json={"email": "Demo@sanskritisetu.org", "password": "Demo123!"},
            timeout=15,
        )
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:200]}")
    except Exception as e:
        print(f"ERROR: {e}")
