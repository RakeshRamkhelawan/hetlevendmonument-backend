#!/usr/bin/env python3
"""Backend API connectivity test"""

import time
from datetime import datetime, timezone

import pytest
import requests


def _log(msg):
    """Helper function to log with timestamp"""
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")


@pytest.mark.skip(reason="Manual test script")
def test_backend_api():
    """Backend API connectivity test - manual execution only"""
    _log("=== BACKEND API CONNECTIVITY TEST ===\n")

    # Test 1: Health endpoint
    _log("[1] Testing /health endpoint:")
    try:
        start = time.time()
        response = requests.get("http://localhost:8001/health", timeout=5)
        elapsed = time.time() - start
        _log(f"    Status: {response.status_code}")
        _log(f"    Duration: {elapsed:.2f}s")
        if response.status_code == 200:
            _log(f"    Body: {response.json()}")
            _log("    Health check PASSED")
        else:
            _log("    Unexpected status code")
    except requests.exceptions.Timeout:
        _log("    TIMEOUT - Backend not responding")
    except requests.exceptions.ConnectionError as e:
        _log(f"    CONNECTION ERROR: {e}")
    except Exception as e:
        _log(f"    Error: {e}")

    _log("")

    # Test 2: Login endpoint
    _log("[2] Testing /api/v1/auth/login endpoint:")
    try:
        start = time.time()
        response = requests.post(
            "http://localhost:8001/api/v1/auth/login",
            json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
            timeout=5,
        )
        elapsed = time.time() - start
        _log(f"    Status: {response.status_code}")
        _log(f"    Duration: {elapsed:.2f}s")
        if response.status_code == 200:
            data = response.json()
            _log("    Login SUCCESSFUL")
            _log(f"    Token: {data.get('access_token', 'N/A')[:50]}...")
        else:
            _log(f"    Status {response.status_code}")
            _log(f"    Body: {response.text[:200]}")
    except requests.exceptions.Timeout:
        _log("    TIMEOUT - Backend not responding")
    except requests.exceptions.ConnectionError as e:
        _log(f"    CONNECTION ERROR: {e}")
    except Exception as e:
        _log(f"    Error: {e}")

    _log("")

    # Test 3: CORS preflight
    _log("[3] Testing CORS preflight (OPTIONS /api/v1/auth/login):")
    try:
        start = time.time()
        response = requests.options(
            "http://localhost:8001/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
            timeout=5,
        )
        elapsed = time.time() - start
        _log(f"    Status: {response.status_code}")
        _log(f"    Duration: {elapsed:.2f}s")

        cors_header = response.headers.get("Access-Control-Allow-Origin")
        if cors_header:
            _log(f"    CORS Header: {cors_header}")
            if cors_header == "http://localhost:5173":
                _log("    CORS preflight PASSED for localhost:5173")
            else:
                _log(f"    CORS allows '{cors_header}' but frontend is on localhost:5173")
        else:
            _log("    No Access-Control-Allow-Origin header!")
    except Exception as e:
        _log(f"    Error: {e}")

    _log("")
    _log("=== SUMMARY ===")
    _log("If all tests PASSED: Backend is fine, issue is browser-specific")
    _log("If tests FAILED: Backend needs restart or troubleshooting")
