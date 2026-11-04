import asyncio
import os
import re

import asyncpg
from dotenv import load_dotenv

NEW_USER = "sanskriti_user"

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def _validate_identifier(name: str, label: str) -> str:
    """Validate a PostgreSQL identifier (username, database name).

    Raises ValueError if the name could enable SQL injection.
    PostgreSQL identifiers: letters, digits, underscores only, max 63 chars.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid {label} '{name}'. "
            "Only letters, digits and underscores allowed (max 63 chars)."
        )
    return name


async def main():
    # Pas hier laden: een .env laden bij het importeren zette variabelen in
    # os.environ van elke testronde die dit script importeert.
    load_dotenv()
    admin_user = os.getenv("DB_ADMIN_USER", "postgres")
    admin_pass = os.getenv("DB_PASSWORD", "postgres")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "sanskriti_setu")
    new_pass = os.getenv("SANSKRITI_DB_PASSWORD", "")
    db_admin_url = f"postgresql://{admin_user}:{admin_pass}@{db_host}:{db_port}/{db_name}"

    if not new_pass:
        raise ValueError(
            "SANSKRITI_DB_PASSWORD env var is not set. This script requires an explicit password."
        )

    validated_user = _validate_identifier(NEW_USER, "username")
    validated_db = _validate_identifier(db_name, "database name")

    conn = await asyncpg.connect(db_admin_url)
    try:
        # Password is a value, not an identifier -- $1 parameterization works here
        await conn.execute(
            f"CREATE USER {validated_user} WITH PASSWORD $1;",  # nosec B608
            new_pass,
        )
        print(f"User {validated_user} created.")
    except Exception as e:
        if "already exists" in str(e):
            print(f"User {validated_user} already exists.")
        else:
            print(f"Error creating user: {e}")
    try:
        # validated_db is validated as a safe identifier in main()
        await conn.execute(
            f"GRANT ALL PRIVILEGES ON DATABASE {validated_db} TO {validated_user};"  # nosec B608
        )
        print(f"Privileges granted to {validated_user} on {validated_db}.")
    except Exception as e:
        print(f"Error granting privileges: {e}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
