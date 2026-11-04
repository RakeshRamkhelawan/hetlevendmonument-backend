"""Test login met JSON body in plaats van form data"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script")
def test_json_login():
    """Test login with JSON body - manual execution only"""
    # Test met JSON body
    response = requests.post(
        "http://localhost:8001/api/v1/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
        timeout=10,
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("LOGIN SUCCESSFUL!")
        print(f"Response: {response.json()}")
    else:
        print(f"LOGIN FAILED: {response.text}")
