"""
Script: snapshot_prod_mirror.py

Description:
This script provides functionality to save and restore the database state
for test reproducibility. It connects to the production mirror database,
creates a snapshot of its current state, and allows restoring the state
from a previously saved snapshot.

Usage:
    python snapshot_prod_mirror.py save --output <snapshot_file>
    python snapshot_prod_mirror.py restore --input <snapshot_file>

Environment Variables:
    DATABASE_URL: The connection string for the production mirror database.

Author: SanskritiSetu.org
Date: December 8, 2025
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker

# Add src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from src.core.database.database import Base  # SQLAlchemy Base
from src.core.models.rbac_models import Role, Tenant, User  # Example models


async def create_engine() -> AsyncEngine:
    """Create an async SQLAlchemy engine."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise EnvironmentError("DATABASE_URL environment variable is not set.")
    return create_async_engine(database_url, echo=False, future=True)


async def save_snapshot(output_file: str) -> None:
    """
    Save the current state of the database to a JSON file.

    Args:
        output_file (str): Path to the output snapshot file.
    """
    engine = await create_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    snapshot = {}
    async with async_session() as session:
        async with session.begin():
            # Example: Dump User, Role, and Tenant tables
            for model in [User, Role, Tenant]:
                table_name = model.__tablename__
                query = text(f"SELECT * FROM {table_name}")
                result = await session.execute(query)
                rows = [dict(row) for row in result]
                snapshot[table_name] = rows

    # Write snapshot to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=4)

    print(f"Snapshot saved to {output_file}")


async def restore_snapshot(input_file: str) -> None:
    """
    Restore the database state from a JSON snapshot file.

    Args:
        input_file (str): Path to the input snapshot file.
    """
    engine = await create_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Load snapshot from file
    with open(input_file, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    async with async_session() as session:
        async with session.begin():
            # Example: Restore User, Role, and Tenant tables
            for model in [User, Role, Tenant]:
                table_name = model.__tablename__
                if table_name in snapshot:
                    # Clear existing data
                    await session.execute(text(f"DELETE FROM {table_name}"))
                    # Insert snapshot data
                    rows = snapshot[table_name]
                    for row in rows:
                        await session.execute(
                            text(
                                f"INSERT INTO {table_name} ({', '.join(row.keys())}) VALUES ({', '.join([f':{k}' for k in row.keys()])})"
                            ),
                            row,
                        )

    print(f"Snapshot restored from {input_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Save/Restore database state for test reproducibility."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Save command
    save_parser = subparsers.add_parser(
        "save", help="Save the current database state to a snapshot file."
    )
    save_parser.add_argument("--output", required=True, help="Path to the output snapshot file.")

    # Restore command
    restore_parser = subparsers.add_parser(
        "restore", help="Restore the database state from a snapshot file."
    )
    restore_parser.add_argument("--input", required=True, help="Path to the input snapshot file.")

    args = parser.parse_args()

    if args.command == "save":
        asyncio.run(save_snapshot(args.output))
    elif args.command == "restore":
        asyncio.run(restore_snapshot(args.input))


if __name__ == "__main__":
    main()
