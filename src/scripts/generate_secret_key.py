import secrets


def generate_secret_key(length: int = 64) -> str:
    """
    Generates a cryptographically strong random text string for use as a secret key.
    The length parameter specifies the number of random bytes to generate, which
    results in a key string of approximately 1.33 * length characters.
    """
    if length < 32:
        raise ValueError("Secret key length should be at least 32 bytes for security.")
    return secrets.token_urlsafe(length)


if __name__ == "__main__":
    try:
        key = generate_secret_key()
        print(f"Generated Secret Key: {key}")
        print(
            "\nIMPORTANT: Add this key to your environment variables (e.g., .env file) as SECRET_KEY."
        )
        print('For example: SECRET_KEY="' + key + '"')
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
