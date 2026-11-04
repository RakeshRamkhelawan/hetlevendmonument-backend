import secrets


def generate_random_string(length: int = 16) -> str:
    """
    Generates a cryptographically strong random string.
    """
    return secrets.token_urlsafe(length)


def rotate_db_credentials() -> None:
    """
    Generates new database credentials and provides instructions for rotation.
    """
    print("\n--- Database Credential Rotation Process ---")
    print("1. Generating new cryptographically secure database credentials...")
    new_user = "sanskriti_user_" + generate_random_string(8)
    new_password = generate_random_string(32)

    print(f"New Database Username: {new_user}")
    print(f"New Database Password: {new_password}")

    print("\n2. IMPORTANT: Update your database server:")
    print("   - Connect to your PostgreSQL database as an administrator.")
    print("   - Execute the following SQL commands:")
    print(f"     CREATE USER {new_user} WITH PASSWORD '{new_password}';")
    print(f"     GRANT ALL PRIVILEGES ON DATABASE sanskriti_setu TO {new_user};")
    print("     -- Optionally, revoke privileges from old user if applicable")
    print("     -- REVOKE ALL PRIVILEGES ON DATABASE sanskriti_setu FROM old_user;")
    print("     -- DROP USER old_user;")

    print("\n3. IMPORTANT: Update your environment configuration:")
    print("   - Construct the new DATABASE_URL:")
    print(
        '     DATABASE_URL="postgresql://{new_user}:{new_password}@<your_db_host>:<your_db_port>/<your_db_name>"'
    )
    print("   - If using a .env file, update the DATABASE_URL entry.")
    print(
        "   - If using a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault), update the secret value there."
    )

    print("\n4. Restart all instances of the application to pick up the new credentials.")

    print("\n--- Rotation Complete ---")
    print("Ensure all steps are followed to maintain security and database access.")


if __name__ == "__main__":
    rotate_db_credentials()
