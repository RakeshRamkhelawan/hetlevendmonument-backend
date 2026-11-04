"""Create test user for authentication"""

import asyncio

import pytest
from passlib.context import CryptContext
from sqlalchemy import create_engine, text


@pytest.mark.skip(reason="Manual database script")
def test_create_test_user():
    """Create test user for authentication - manual execution only"""
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Hash the password
    password = "Test1234"
    hashed_password = pwd_context.hash(password)

    # Connect to database
    engine = create_engine("postgresql://postgres:secure_password@localhost:5432/sanskritisetu")

    with engine.connect() as conn:
        # Check if user exists
        result = conn.execute(text("SELECT id FROM users WHERE email = 'test@example.com'"))
        user = result.fetchone()

        if user:
            # Update existing user
            print("Updating existing user...")
            conn.execute(
                text(
                    "UPDATE users SET hashed_password = :pwd, role_id = 1, "
                    "is_active = true WHERE email = :email"
                ),
                {"pwd": hashed_password, "email": "test@example.com"},
            )
            conn.commit()
            print("User updated: test@example.com")
        else:
            # Create new user
            print("Creating new user...")
            conn.execute(
                text(
                    """
                    INSERT INTO users (email, hashed_password, tenant_id, role_id, is_active, created_at)
                    VALUES (:email, :pwd, 1, 1, true, NOW())
                """
                ),
                {"email": "test@example.com", "pwd": hashed_password},
            )
            conn.commit()
            print("User created: test@example.com")

        print("   Email: test@example.com")
        print(f"   Password: {password}")
        print("   Tenant ID: 1")
        print("   Role ID: 1")


if __name__ == "__main__":
    test_create_test_user()
