#!/usr/bin/env python3
"""
Simulate the React frontend login flow to test the fix
This tests:
1. POST /api/v1/auth/login with credentials
2. Extract access_token from response
3. Store token in "localStorage"
4. GET /api/v1/auth/me with token (like useCurrentUser hook does)
"""

import json

import requests

BASE_API = "http://localhost:3005/api/v1"


def test_react_login_flow():
    """Simulate React frontend's useAuth hook login process"""

    print("=" * 60)
    print("SIMULATING REACT LOGIN FLOW")
    print("=" * 60)

    # Step 1: Login with credentials
    print("\n[STEP 1] Calling authApi.login(email, password)")
    print("  POST /api/v1/auth/login")
    print("  Body: {email: 'admin@sanskritisetu.org', password: 'Admin123!'}")

    login_response = requests.post(
        f"{BASE_API}/auth/login",
        json={"email": "admin@sanskritisetu.org", "password": "Admin123!"},
    )

    print(f"\n  Response Status: {login_response.status_code}")
    print(f"  Response Content-Type: {login_response.headers.get('content-type')}")

    if login_response.status_code != 200:
        print(f"  ❌ FAILED: Expected 200, got {login_response.status_code}")
        print(f"  Response: {login_response.text}")
        return False

    login_data = login_response.json()
    print("\n  Response structure:")
    print(f"    Keys at root level: {list(login_data.keys())}")

    # Check if response has error wrapper (from nginx or middleware)
    if "error" in login_data:
        print("    ERROR WRAPPER DETECTED:")
        print(f"      {json.dumps(login_data, indent=8)}")
        return False

    # The api-client extracts response.data from axios
    # But we're directly getting the response, which is:
    # If the backend returns: {access_token, token_type, user}
    # Then login_data should be: {access_token, token_type, user}

    access_token = login_data.get("access_token")
    if not access_token:
        print("  ❌ FAILED: No access_token in response")
        print(f"  Full response: {json.dumps(login_data, indent=2)}")
        return False

    print(f"  ✅ Got access_token: {access_token[:30]}...")

    # Step 2: Check what would be extracted by useAuth hook
    print("\n[STEP 2] useAuth hook extracts: response.data.access_token")
    print("  response = await authApi.login(...)")
    print("  response is of type: ApiResponse<{access_token, ...}>")
    print("  So response.data should give us: {access_token, token_type, user, ...}")

    # Since we're not going through the api-client wrapper, we need to simulate it
    # In the real React code, the authApi.login returns ApiResponse<...>
    # which means response.data = {access_token, token_type, user}

    print("\n  In React code:")
    print("    const response = await authApi.login(email, password);")
    print("    // response is ApiResponse<...>, not the raw axios response")
    print("    // so response looks like: {data: {access_token, user, ...}, message?, meta?}")
    print("    const { access_token } = response.data;")
    print("    // This would try to access response.data.access_token")
    print("    // But access_token is at response.data.data (DOUBLE NESTED!)")

    # Actually, let me check the api-client wrapper again
    # api.post returns: apiClient.post(...).then((r) => r.data)
    # So the return type is ApiResponse<T> but the value is already r.data
    # This is a TYPE MISMATCH!

    # Let me verify by checking what axios actually returns
    print("\n[STEP 3] Understanding the api-client wrapper")
    print("  authApi.login() returns type: Promise<ApiResponse<...>>")
    print("  But implementation does: api.post(...) which is:")
    print("    apiClient.post(url, data).then((r) => r.data)")
    print("  This returns: r.data from axios response")
    print("  Axios response.data for this endpoint is: {access_token, token_type, user}")
    print("  So the promise actually resolves to: {access_token, token_type, user}")
    print("  NOT: {data: {access_token, ...}}")

    print("\n  THE BUG: useAuth code does response.data.access_token")
    print("  But response is already {access_token, ...}, not {data: {access_token, ...}}")
    print("  So response.data would try to access .data property on {access_token, ...}")
    print("  Which is undefined!")

    # Step 4: Verify /auth/me works
    print("\n[STEP 4] Testing /auth/me with the token (useCurrentUser)")
    print("  GET /api/v1/auth/me")
    print(f"  Header: Authorization: Bearer {access_token[:30]}...")

    me_response = requests.get(
        f"{BASE_API}/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    print(f"\n  Response Status: {me_response.status_code}")
    if me_response.status_code != 200:
        print(f"  ❌ FAILED: Expected 200, got {me_response.status_code}")
        print(f"  Response: {me_response.text}")
        return False

    me_data = me_response.json()
    print(f"  ✅ Got user data: {me_data.get('email')}")

    print("\n" + "=" * 60)
    print("ANALYSIS:")
    print("=" * 60)
    print(
        """
The actual API responses are correct. The issue is in the React code's
understanding of what the api-client wrapper returns.

ACTUAL TYPE CHAIN:
  api.post<T>() returns Promise<ApiResponse<T>>
  BUT: the implementation extracts .data, so actual value is T
  This is a TYPE-VALUE MISMATCH

The fix depends on what api-client actually does:
"""
    )

    print("\nLet's check what the api-client wrapper ACTUALLY returns...")

    return True


if __name__ == "__main__":
    test_react_login_flow()
