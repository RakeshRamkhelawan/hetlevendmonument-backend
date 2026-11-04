#!/usr/bin/env python3
"""Direct test of bcrypt password verification"""

import bcrypt

email = "admin@sanskritisetu.org"
password_input = "admin123"

# New hash we just created
correct_hash = "$2b$12$vjwrDA2ryM5VAD5nn30bPuNXEnZ03bfpx7mC6Rd5bSEdT0wyiLb.i"

print("\n════ BCRYPT VERIFICATION TEST ════\n")
print(f"Email: {email}")
print(f"Input password: {password_input}")
print(f"Hash in DB: {correct_hash}\n")

# Test verification
result = bcrypt.checkpw(password_input.encode("utf-8"), correct_hash.encode("utf-8"))
print(f"bcrypt.checkpw() result: {result}")

if result:
    print("✅ Password MATCHES hash\n")
else:
    print("❌ Password DOES NOT match hash\n")
