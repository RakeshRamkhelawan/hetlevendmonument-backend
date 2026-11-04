#!/usr/bin/env python3
"""Test both users"""

import pytest
import requests


@pytest.mark.skip(reason="Manual test script")
def test_both_users():
    """Test both admin and demo users - manual execution only"""
    users = [
        ("admin@sanskritisetu.org", "Admin123!"),
        ("Demo@sanskritisetu.org", "Demo123!"),
    ]

    print("[*] Testing both users...\n")

    for email, password in users:
        print(f"Testing: {email}")
        try:
            response = requests.post(
                "http://localhost:3005/api/v1/auth/token",
                data={"username": email, "password": password},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                print("  Status: 200 - SUCCESS")
                print(f"  User ID: {data.get('user', {}).get('id')}")
                print(f"  Tenant: {data.get('user', {}).get('tenant_id')}")
            else:
                print(f"  Status: {response.status_code} - FAILED")
                print(f"  Message: {response.text[:100]}")
        except Exception as e:
            print(f"  ERROR: {e}")
        print()
