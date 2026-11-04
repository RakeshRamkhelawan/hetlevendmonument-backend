#!/usr/bin/env python3
"""Direct test of authentication WITHOUT async/ORM"""

import sqlite3

import bcrypt
import pytest


def _test_auth(email, password):
    """Helper function to test authentication"""
    db = sqlite3.connect("sanskriti_setu.db")
    cursor = db.cursor()

    # Get user
    cursor.execute("SELECT id, email, hashed_password FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        print("[ERROR] User not found in database")
        return False

    user_id, user_email, hashed_password = user
    print(f"[OK] User found: ID={user_id}, Email={user_email}")
    print(f"Hash from DB: {hashed_password[:60]}...")

    # Verify password with bcrypt
    try:
        result = bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
        print(f"bcrypt.checkpw() result: {result}")

        if result:
            print("[SUCCESS] Password MATCHES!")
            return True
        else:
            print("[ERROR] Password DOES NOT match")
            return False
    except Exception as e:
        print(f"[ERROR] bcrypt exception: {e}")
        return False
    finally:
        db.close()


@pytest.mark.skip(reason="Manual test script - requires local database")
def test_auth_raw():
    """Direct test of authentication - manual execution only"""
    email = "admin@sanskritisetu.org"
    password = "admin123"

    print(f"\n[*] Testing authentication for {email}...")
    print(f"Password: {password}\n")

    success = _test_auth(email, password)
    print(f"\nResult: {'SUCCESS' if success else 'FAILED'}\n")
