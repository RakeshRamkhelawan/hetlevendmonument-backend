"""
Complete test: Login + VIBE workflow generation
"""

import json

import requests

BASE_URL = "http://localhost:8100"  # Port updated from 8000 to 8100


def test_login():
    """Test login and get token"""
    print("[1/3] Testing login...")
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": "test@example.com", "password": "TestPass123"},
    )

    if response.status_code != 200:
        print(f"[FAIL] Login failed: {response.status_code}")
        print(response.text)
        return None

    data = response.json()
    token = data.get("access_token")
    print(f"[OK] Login successful, token: {token[:20]}...")
    return token


def test_vibe(token):
    """Test VIBE workflow generation"""
    print("\n[2/3] Testing VIBE workflow generation...")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "prompt": "Create a simple heritage preservation workflow",
        "complexity": "simple",
    }

    response = requests.post(f"{BASE_URL}/api/v1/vibe/generate", headers=headers, json=payload)

    if response.status_code != 200:
        print(f"[FAIL] VIBE failed: {response.status_code}")
        print(response.text)
        return False

    data = response.json()
    print(f"[OK] VIBE workflow generated: {data.get('workflow_name', 'Unknown')}")
    print(f"     Steps: {len(data.get('steps', []))}")
    return True


def main():
    print("=" * 60)
    print("VIBE WORKFLOW TEST - Post Legacy Role ID Removal")
    print("=" * 60)

    # Step 1: Login
    token = test_login()
    if not token:
        print("\n[ABORT] Cannot proceed without valid token")
        return

    # Step 2: Test VIBE
    success = test_vibe(token)

    # Step 3: Summary
    print("\n[3/3] Test Summary")
    print("=" * 60)
    if success:
        print("[SUCCESS] All tests passed!")
        print("[OK] Legacy role_id removal was successful")
        print("[OK] VIBE workflow works with new RBAC system")
    else:
        print("[FAIL] VIBE test failed")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback

        traceback.print_exc()
