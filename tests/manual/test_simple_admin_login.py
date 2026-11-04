"""Simple login test - no fancy formatting"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script")
def test_simple_admin_login():
    """Simple admin login test - manual execution only"""
    print("TEST: Admin login")
    try:
        response = requests.post(
            "http://localhost:8001/api/v1/auth/login",
            json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
            timeout=15,
        )
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:200]}")
    except Exception as e:
        print(f"ERROR: {e}")
