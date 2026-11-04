#!/usr/bin/env python3
"""Quick password verification test"""

from passlib.hash import bcrypt

# Test hash generated in container
test_hash = "$2b$12$XVVU29Q.PkhavpUCoeKIEOPtAlHsIgZG15ChPCqXeYrHbVu68gA7q"

print("Testing password verification:")
print(f"Hash: {test_hash}")
print(f"Verify 'Admin@123': {bcrypt.verify('Admin@123', test_hash)}")
print(f"Verify 'TestPassword123': {bcrypt.verify('TestPassword123', test_hash)}")

# Generate new hash
new_hash = bcrypt.hash("Admin@123")
print(f"\nNew hash for 'Admin@123': {new_hash}")
print(f"Verify new hash: {bcrypt.verify('Admin@123', new_hash)}")
