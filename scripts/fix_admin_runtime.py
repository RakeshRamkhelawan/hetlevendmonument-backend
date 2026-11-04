import asyncio
import logging
import os
import sys

from sqlalchemy import select

# Add src to python path for module resolution when running as script
sys.path.append(os.getcwd())

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def fix_admin_runtime():
    """
    Resets the admin password using the CURRENT runtime configuration of jwt_handler.
    This ensures that the hash in the database exactly matches the rounds/salt settings
    of the running application container.
    """
    logger.info("[TOOL] Starting Runtime Admin Password Fix...")

    try:
        # Import verify dependencies - essential to load them HERE to get Runtime config
        from src.core.auth.jwt_handler import jwt_handler
        from src.core.database.database import db_manager
        from src.core.models.rbac_models import User

        # Verify current config by hashing a dummy value
        test_hash = await jwt_handler.hash_password("test_rounds_check")
        try:
            # Bcrypt hash format: $2b$rounds$salt...
            # e.g., $2b$12$PcXS...
            start = test_hash.find("$") + 1
            second = test_hash.find("$", start) + 1
            third = test_hash.find("$", second)
            rounds_check = test_hash[second:third]
            logger.info(
                f"[INFO]  Current Runtime Bcrypt Config: cost={rounds_check} (Verified via hash: {test_hash[:15]}...)"
            )
        except Exception:
            logger.warning("Could not determine rounds from hash")

        async with db_manager.get_session() as db:
            result = await db.execute(select(User).where(User.email == "admin@sanskritisetu.org"))
            user = result.scalar_one_or_none()

            if not user:
                logger.error("[FAIL] Admin user 'admin@sanskritisetu.org' not found in DB!")
                return

            # Load password from environment or use secure random
            import secrets

            password_from_env = os.getenv("ADMIN_RESET_PASSWORD")
            new_password = password_from_env or secrets.token_urlsafe(16)
            logger.info("[U+0001F504] Hashing password with current runtime context...")

            # This uses the EXACT SAME valid jwt_handler instance as the app
            hashed = await jwt_handler.hash_password(new_password)

            user.hashed_password = hashed
            await db.commit()

            logger.info(f"[OK] Password for {user.email} reset successfully.")
            if password_from_env:
                logger.info("[LAUNCH] You can now login with the password from ADMIN_RESET_PASSWORD.")
            else:
                # Nieuw gegenereerd: een mens moet het hier overnemen (staat op de uitzonderingslijst van
                # tests/architecture/test_geen_geheim_in_de_uitvoer.py).
                # Bewust print en geen logger: een logger kan naar een bestand of logverzamelaar schrijven
                # en dan blijft het wachtwoord staan.
                print(f"[LAUNCH] You can now login with password: {new_password}")
                print("\n[WARN]  IMPORTANT: Save this password securely! It will not be shown again.")

    except Exception as e:
        logger.error(f"[FAIL] Failed to reset admin password: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(fix_admin_runtime())
