"""Test password hash verification"""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash from database
stored_hash = "$2b$12$7esv3q1bKWq6PtUDyf8LIOrfbR76uMPrk1F4By47jpBtaDd6cOt6C"
password = "Admin123!"

print("=" * 50)
print("PASSWORD VERIFICATION TEST")
print("=" * 50)
print(f"Password: {password}")
print(f"Hash: {stored_hash[:30]}...")
print()

try:
    result = pwd_context.verify(password, stored_hash)
    print(f"Verification result: {result}")
    print()

    if result:
        print("[OK] ✓ Password MATCHES hash!")
    else:
        print("[FAIL] ✗ Password does NOT match hash")

except Exception as e:
    print(f"[ERROR] Verification failed: {e}")
