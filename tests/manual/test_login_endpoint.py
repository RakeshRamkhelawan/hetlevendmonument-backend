#!/usr/bin/env python3
"""Test login endpoint directly"""

import json

import requests

print("[*] Testing login endpoint on http://localhost:8001/api/v1/auth/token\n")

# Test data
email = "admin@sanskritisetu.org"
password = "Admin123!"

print("[1] Sending login request...")
print(f"    Email: {email}")
print(f"    Password: {password}")
print()

try:
    # Method 1: form data (OAuth2 style)
    print("[METHOD 1] Using form data (application/x-www-form-urlencoded):")
    response1 = requests.post(
        "http://localhost:8001/api/v1/auth/token",
        data={"username": email, "password": password},
        timeout=10,
    )
    print(f"    Status: {response1.status_code}")
    if response1.status_code == 200:
        print("    ✅ SUCCESS!")
        print(f"    Response: {json.dumps(response1.json(), indent=2)[:200]}...")
    else:
        print("    ❌ FAILED")
        print(f"    Response: {response1.text[:300]}")
    print()

    # Method 2: JSON
    print("[METHOD 2] Using JSON body:")
    response2 = requests.post(
        "http://localhost:8001/api/v1/auth/token",
        json={"email": email, "password": password},
        timeout=10,
    )
    print(f"    Status: {response2.status_code}")
    if response2.status_code == 200:
        print("    ✅ SUCCESS!")
        print(f"    Response: {json.dumps(response2.json(), indent=2)[:200]}...")
    else:
        print("    ❌ FAILED")
        print(f"    Response: {response2.text[:300]}")
    print()

    # Method 3: login endpoint
    print("[METHOD 3] Using /api/v1/auth/login (JSON):")
    response3 = requests.post(
        "http://localhost:8001/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    print(f"    Status: {response3.status_code}")
    if response3.status_code == 200:
        print("    ✅ SUCCESS!")
        print(f"    Response: {json.dumps(response3.json(), indent=2)[:200]}...")
    else:
        print("    ❌ FAILED")
        print(f"    Response: {response3.text[:300]}")

except Exception as e:
    print(f"❌ ERROR: {e}")
