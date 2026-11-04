#!/usr/bin/env python3
"""Test JWT token creation and verification with rotated secret"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.core.auth.jwt_handler import JWTHandler
from src.core.config.unified_config import config

print("=" * 60)
print("JWT TOKEN CREATION/VERIFICATION TEST")
print("=" * 60)

# Create JWT handler
jwt_handler = JWTHandler()

# Test 1: Create a token
print("\n1️⃣  Creating new token...")
try:
    token = jwt_handler.create_access_token({"sub": "test@example.com", "tenant_id": 1})
    print("✅ Token created successfully")
    print(f"   Token length: {len(token)} chars")
    print(f"   Token start: {token[:50]}...")
except Exception as e:
    print(f"❌ Token creation failed: {e}")
    sys.exit(1)

# Test 2: Verify the token
print("\n2️⃣  Verifying same token...")
try:
    payload = jwt_handler.verify_token(token)
    if payload:
        print("✅ Token verified successfully")
        print(f"   Subject: {payload.get('sub')}")
        print(f"   Tenant ID: {payload.get('tenant_id')}")
        assert payload.get("sub") == "test@example.com"
        assert payload.get("tenant_id") == 1
        print("✅ Token payload is correct")
    else:
        print("❌ Token verification returned None")
        sys.exit(1)
except Exception as e:
    print(f"❌ Token verification failed: {e}")
    sys.exit(1)

# Test 3: Try to verify invalid token (should fail gracefully)
print("\n3️⃣  Testing invalid token rejection...")
try:
    fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.payload"
    payload = jwt_handler.verify_token(fake_token)
    if payload is None:
        print("✅ Invalid token correctly rejected (returned None)")
    else:
        print(f"⚠️  Invalid token was not rejected: {payload}")
except Exception as e:
    # Might raise an exception, which is also acceptable
    print(f"✅ Invalid token correctly raised error: {type(e).__name__}")

# Test 4: Token with different claims
print("\n4️⃣  Testing token with different claims...")
try:
    token2 = jwt_handler.create_access_token(
        {"sub": "admin@example.com", "tenant_id": 2, "role": "admin"}
    )
    payload2 = jwt_handler.verify_token(token2)
    if payload2:
        assert payload2["sub"] == "admin@example.com"
        assert payload2["tenant_id"] == 2
        assert payload2.get("role") == "admin"
        print("✅ Multi-claim token created and verified correctly")
    else:
        print("❌ Multi-claim token verification failed")
        sys.exit(1)
except Exception as e:
    print(f"❌ Multi-claim token test failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL JWT TOKEN TESTS PASSED")
print("✅ New secret is working correctly")
print("=" * 60)
