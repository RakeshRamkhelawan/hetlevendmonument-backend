import os
import sys

sys.path.insert(0, "src")

from src.core.auth.jwt_handler import jwt_handler

print(f"JWT_SECRET: {os.environ.get('JWT_SECRET', 'NOT_SET')}")
print(f"SANSKRITI_SECRET_KEY: {os.environ.get('SANSKRITI_SECRET_KEY', 'NOT_SET')}")

# Create token
token = jwt_handler.create_access_token({"sub": "1", "tenant_id": 1})
print(f"Token created: {token[:80]}...")

# Try to decode
try:
    payload = jwt_handler.verify_token(token)
    print(f"Decode successful: {payload}")
except Exception as e:
    print(f"Decode failed: {e}")
