
"""
Monkeypatch for bcrypt/__passlib compatibility issue.

Problem: passlib 1.7.4 tries to read bcrypt.__about__.__version__
but bcrypt 4.1.2 removed this attribute.

Solution: Add a fake __about__ module to bcrypt with __version__
"""


def patch_bcrypt_about_attribute() -> None:
    """Add __about__ attribute to bcrypt for passlib compatibility"""
    import bcrypt

    # Check if already patched
    if hasattr(bcrypt, "__about__"):
        return

    # Create a simple namespace for __about__
    class About:
        __version__ = getattr(bcrypt, "__version__", "unknown")

    setattr(bcrypt, "__about__", About())
    about = getattr(bcrypt, "__about__")
    print(f"[OK] Monkeypatched bcrypt.__about__.__version__ = {about.__version__}")


# Apply patch immediately on import
patch_bcrypt_about_attribute()
