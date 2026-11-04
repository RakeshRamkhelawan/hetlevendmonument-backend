"""Simplified login test to debug form parsing"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script")
def test_simple_login():
    """Simplified login test - manual execution only"""
    # Test with explicit Content-Type header
    response = requests.post(
        "http://localhost:8001/api/v1/auth/login",
        data={"username": "admin@sanskritisetu.org", "password": "Admin123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
