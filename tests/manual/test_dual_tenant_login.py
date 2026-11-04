"""
Test login voor beide tenants: Admin en Demo
"""

import json

import requests

BASE_URL = "http://localhost:8001"


def test_login(email, password, tenant_name):
    """Test login voor een specifieke user."""
    print(f"\n{'='*70}")
    print(f"🧪 Testing login voor: {email} ({tenant_name})")
    print("=" * 70)

    # Login request
    login_data = {
        "username": email,  # OAuth2PasswordRequestForm verwacht 'username'
        "password": password,
    }

    print(f"📤 POST {BASE_URL}/api/v1/auth/login")
    print(f"   Data: username={email}, password={'*' * len(password)}")

    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data=login_data,  # OAuth2 verwacht form data, niet JSON
            timeout=10,
        )

        print(f"📥 Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            access_token = data.get("access_token")
            token_type = data.get("token_type")

            print("✅ Login SUCCESS!")
            print(f"   Access Token: {access_token[:50]}...")
            print(f"   Token Type: {token_type}")

            # Test /auth/me endpoint
            print(f"\n📤 GET {BASE_URL}/api/v1/auth/me")
            headers = {"Authorization": f"Bearer {access_token}"}
            me_response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=headers, timeout=10)

            print(f"📥 Status: {me_response.status_code}")

            if me_response.status_code == 200:
                user_data = me_response.json()
                print("✅ /auth/me SUCCESS!")
                print(f"   User ID: {user_data.get('id')}")
                print(f"   Email: {user_data.get('email')}")
                print(f"   Tenant ID: {user_data.get('tenant_id')}")
                print(f"   Active: {user_data.get('is_active')}")

                # Decode JWT to check tenant_id claim
                import base64

                try:
                    # JWT format: header.payload.signature
                    payload = access_token.split(".")[1]
                    # Add padding if needed
                    payload += "=" * (4 - len(payload) % 4)
                    decoded = base64.b64decode(payload)
                    jwt_data = json.loads(decoded)
                    print("\n🔐 JWT Payload:")
                    print(f"   Subject (sub): {jwt_data.get('sub')}")
                    print(f"   Tenant ID: {jwt_data.get('tenant_id')}")
                    print(f"   Expires: {jwt_data.get('exp')}")
                except Exception as e:
                    print(f"   ⚠️ Could not decode JWT: {e}")

                return True
            else:
                print("❌ /auth/me FAILED!")
                print(f"   Response: {me_response.text}")
                return False
        else:
            print("❌ Login FAILED!")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def main():
    """Test beide tenant logins."""
    print("\n" + "=" * 70)
    print("🧪 DUAL TENANT LOGIN TEST - SanskritiSetu.org")
    print("=" * 70)

    results = []

    # Test 1: Admin tenant
    results.append(
        test_login(
            email="admin@sanskritisetu.org",
            password="Admin123!",
            tenant_name="SanskritiSetu Admin",
        )
    )

    # Test 2: Demo tenant
    results.append(
        test_login(
            email="Demo@sanskritisetu.org",
            password="Demo123!",
            tenant_name="Demo Organization",
        )
    )

    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    print(f"Admin Login: {'✅ PASS' if results[0] else '❌ FAIL'}")
    print(f"Demo Login:  {'✅ PASS' if results[1] else '❌ FAIL'}")
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all(results) else '❌ SOME TESTS FAILED'}")
    print("=" * 70)

    return 0 if all(results) else 1


if __name__ == "__main__":
    exit(main())
