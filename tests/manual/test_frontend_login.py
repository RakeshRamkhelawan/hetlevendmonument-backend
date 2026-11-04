#!/usr/bin/env python3
"""Test login through frontend container"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script")
def test_frontend_login():
    """Test login through frontend container - manual execution only"""
    print("[*] Testing login through frontend on http://localhost:3005\n")

    email = "admin@sanskritisetu.org"
    password = "Admin123!"

    print("[1] Attempting login via frontend...")
    print(f"    Email: {email}")
    print(f"    Password: {password}\n")

    # The frontend API client should proxy to backend
    try:
        response = requests.post(
            "http://localhost:3005/api/v1/auth/token",
            data={"username": email, "password": password},
            timeout=10,
            allow_redirects=False,
        )

        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Body (first 500 chars): {response.text[:500]}")

        if response.status_code == 200:
            print("\nFrontend proxy working!")
        elif response.status_code in [301, 302, 307, 308]:
            print(f"\nRedirect to: {response.headers.get('Location')}")
        else:
            print("\nError from frontend")

    except Exception as e:
        print(f"ERROR: {e}")

    # Also test if frontend is serving content
    print("\n[2] Testing if frontend is serving index.html...")
    try:
        response = requests.get("http://localhost:3005/", timeout=5)
        print(f"    Status: {response.status_code}")
        if "<!DOCTYPE" in response.text or "<html" in response.text:
            print("    Frontend is serving HTML")
        else:
            print(f"    Response starts with: {response.text[:100]}")
    except Exception as e:
        print(f"    Error: {e}")
