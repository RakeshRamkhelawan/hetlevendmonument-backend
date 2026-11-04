import os
import sys


def rotate_secret_key() -> None:
    """
    Generates a new secret key and provides instructions for rotation.
    """
    # Import lazily so this script works both as module and standalone script.
    from src.scripts.generate_secret_key import generate_secret_key

    print("\n--- Secret Key Rotation Process ---")
    print("1. Generating a new cryptographically secure secret key...")
    new_key = generate_secret_key()
    print(f"New Generated Secret Key: {new_key}")

    print("\n2. IMPORTANT: Update your environment configuration:")
    print("   - If using a .env file, update the SECRET_KEY entry:")
    print(f'     SECRET_KEY="{new_key}"')
    print(
        "   - If using a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault), update the secret value there."
    )
    print("   - If using Kubernetes secrets, update the secret and redeploy.")

    print("\n3. Restart all instances of the application to pick up the new key.")

    print("\n4. Invalidate existing JWT tokens (if applicable):")
    print("   - All existing user sessions secured with the old key will become invalid.")
    print("   - Users will need to log in again.")
    print(
        "   - If using a JWT blacklist/revocation mechanism, ensure it's cleared or updated as needed."
    )

    print("\n--- Rotation Complete ---")
    print("Ensure all steps are followed to maintain security.")


if __name__ == "__main__":
    # Add scripts directory to Python path if not already there
    script_dir = os.path.dirname(__file__)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    rotate_secret_key()
