"""Test of backend uberhaupt JSON kan ontvangen"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script - requires running backend")
def test_basic_connectivity():
    """Test basic connectivity to backend - manual execution only"""
    # Test 1: Simple GET request
    print("TEST 1: GET /health")
    response = requests.get("http://localhost:8001/health", timeout=5)
    print(f"Status: {response.status_code}, Body: {response.text}\n")

    # Test 2: POST with JSON
    print("TEST 2: POST /api/v1/auth/login with JSON")
    try:
        response = requests.post(
            "http://localhost:8001/api/v1/auth/login",
            json={"email": "test@test.com", "password": "test123"},
            timeout=5,
        )
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text}")
    except Exception as e:
        print(f"ERROR: {e}")
