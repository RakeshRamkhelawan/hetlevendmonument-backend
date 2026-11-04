#!/usr/bin/env python3
"""
Snapshot Script for Production-Mirror Test Environment
======================================================

Dit script maakt snapshots van de production-mirror database staat en
kan deze later herstellen. Ondersteunt twee modi:
- snapshot: Dump huidige database staat naar bestand
- restore: Herstel database uit snapshot bestand

Usage:
    python scripts/snapshot_prod_mirror.py snapshot                 # Dump database
    python scripts/snapshot_prod_mirror.py snapshot --output backup.sql
    python scripts/snapshot_prod_mirror.py restore backup.sql
    python scripts/snapshot_prod_mirror.py restore --file backup.sql
    python scripts/snapshot_prod_mirror.py list                     # List all snapshots

Environment:
    DATABASE_URL: PostgreSQL connection string (defaults to production-mirror)
    PGPASSWORD: PostgreSQL password (optional)

Author: AI Test Infrastructure Team
Date: December 2025
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def _validate_db_identifier(name: str) -> str:
    """Validate and return a safe PostgreSQL identifier.

    Raises ValueError if the name contains characters that could
    enable SQL injection. PostgreSQL identifiers: letters, digits,
    underscores only. Max 63 characters.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid database identifier '{name}'. Only letters, digits and underscores allowed."
        )
    return name


# Connection URL must be provided via DATABASE_URL environment variable
DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL")
if not DEFAULT_DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")
SNAPSHOTS_DIR = Path(__file__).parent.parent / "snapshots"


class SnapshotManager:
    """Manager voor database snapshots."""

    def __init__(self, database_url: str = DEFAULT_DATABASE_URL):
        self.database_url = database_url
        self.snapshots_dir = SNAPSHOTS_DIR
        self.snapshots_dir.mkdir(exist_ok=True, parents=True)

        # Parse database connection details
        self._parse_connection_string()

    def _parse_connection_string(self) -> None:
        """Parse PostgreSQL connection string."""
        try:
            # Format: postgresql://user:password@host:port/database
            url = self.database_url.replace("postgresql+asyncpg://", "postgresql://")

            if "://" not in url:
                raise ValueError("Invalid database URL format (expected scheme://...); value not shown")

            _, rest = url.split("://", 1)

            if "@" in rest:
                creds, location = rest.rsplit("@", 1)
                if ":" in creds:
                    self.db_user, self.db_password = creds.split(":", 1)
                else:
                    self.db_user = creds
                    self.db_password = ""
            else:
                self.db_user = "postgres"
                self.db_password = ""
                location = rest

            if ":" in location:
                host, rest = location.rsplit(":", 1)
                if "/" in rest:
                    port_str, self.db_name = rest.split("/", 1)
                    self.db_port = int(port_str)
                else:
                    self.db_host = location
                    self.db_port = 5432
                    self.db_name = "sanskriti_prodmirror"
                self.db_host = host
            else:
                self.db_host = location.split("/")[0]
                self.db_port = 5432
                if "/" in location:
                    self.db_name = location.split("/", 1)[1]
                else:
                    self.db_name = "sanskriti_prodmirror"

            # Validate the parsed name before it is used in any SQL statement.
            # All three SQL-building methods rely on this being a safe identifier.
            self.db_name = _validate_db_identifier(self.db_name)

            print(
                f"[OK] Parsed connection: {self.db_user}@{self.db_host}:{self.db_port}/{self.db_name}"
            )

        except ValueError:
            # Re-raise validation errors so the caller sees the injection attempt.
            raise
        except Exception as e:
            raise RuntimeError(
                f"Could not parse DATABASE_URL: {e}. "
                "Set DATABASE_URL to a valid PostgreSQL connection string."
            ) from e

    def _get_pg_env(self) -> dict:
        """Get environment variables for pg_dump/psql."""
        env = os.environ.copy()
        if self.db_password:
            env["PGPASSWORD"] = self.db_password
        return env

    def snapshot(self, output_file: Optional[str] = None) -> bool:
        """
        Maak snapshot van huidige database staat.

        Args:
            output_file: Optioneel outputbestand. Defaults to snapshots/timestamp.sql

        Returns:
            True als snapshot succesvol, False anders
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.snapshots_dir / f"snapshot_{timestamp}.sql"
        else:
            output_file = Path(output_file)
            if not output_file.is_absolute():
                output_file = self.snapshots_dir / output_file

        output_file.parent.mkdir(exist_ok=True, parents=True)

        print(f"[*] Starting snapshot to {output_file}...")

        try:
            # Use pg_dump with format and compression
            cmd = [
                "pg_dump",
                "-h",
                self.db_host,
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                self.db_name,
                "-v",  # Verbose
                "--no-password",
                "-F",
                "c",  # Custom format (compressed)
                "-f",
                str(output_file),
            ]

            env = self._get_pg_env()
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                print(f"[FAIL] pg_dump failed: {result.stderr}")
                return False

            file_size = output_file.stat().st_size
            print(f"[OK] Snapshot created: {output_file} ({file_size / 1024 / 1024:.2f} MB)")

            # Create metadata file
            self._save_snapshot_metadata(output_file)
            return True

        except subprocess.TimeoutExpired:
            print("[FAIL] Snapshot timed out (>5 minutes)")
            return False
        except FileNotFoundError:
            print("[FAIL] pg_dump not found. Install PostgreSQL tools.")
            return False
        except Exception as e:
            print(f"[FAIL] Snapshot error: {e}")
            return False

    def restore(self, snapshot_file: str) -> bool:
        """
        Herstel database uit snapshot.

        Args:
            snapshot_file: Snapshot bestand om te herstellen

        Returns:
            True als restore succesvol, False anders
        """
        snapshot_path = Path(snapshot_file)
        if not snapshot_path.is_absolute():
            snapshot_path = self.snapshots_dir / snapshot_file

        if not snapshot_path.exists():
            print(f"[FAIL] Snapshot file not found: {snapshot_path}")
            return False

        print(f"[*] Starting restore from {snapshot_path}...")

        try:
            # Terminate all connections to database
            print("[*] Terminating active connections...")
            self._terminate_connections()

            # Drop and recreate database
            print("[*] Dropping and recreating database...")
            if not self._recreate_database():
                return False

            # Restore using pg_restore
            cmd = [
                "pg_restore",
                "-h",
                self.db_host,
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                self.db_name,
                "-v",  # Verbose
                "--no-password",
                "-c",  # Clean (drop objects)
                str(snapshot_path),
            ]

            env = self._get_pg_env()
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                print(f"[FAIL] pg_restore failed: {result.stderr}")
                return False

            print(f"[OK] Restore completed from {snapshot_path}")
            return True

        except subprocess.TimeoutExpired:
            print("[FAIL] Restore timed out (>5 minutes)")
            return False
        except FileNotFoundError:
            print("[FAIL] pg_restore not found. Install PostgreSQL tools.")
            return False
        except Exception as e:
            print(f"[FAIL] Restore error: {e}")
            return False

    def _terminate_connections(self) -> None:
        """Terminate all connections to the database."""
        try:
            cmd = [
                "psql",
                "-h",
                self.db_host,
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "--no-password",
                "-c",
                # self.db_name is validated as a safe identifier in _parse_connection_string
                f"SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '{self.db_name}' AND pid <> pg_backend_pid();",  # nosec B608
            ]

            env = self._get_pg_env()
            subprocess.run(cmd, env=env, capture_output=True, timeout=30)
        except Exception as e:
            print(f"[WARN] Could not terminate connections: {e}")

    def _recreate_database(self) -> bool:
        """Drop and recreate database."""
        try:
            # Drop existing database
            cmd_drop = [
                "psql",
                "-h",
                self.db_host,
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "--no-password",
                "-c",
                # self.db_name is validated as a safe identifier in _parse_connection_string
                f"DROP DATABASE IF EXISTS {self.db_name};",  # nosec B608
            ]

            # Create new database
            cmd_create = [
                "psql",
                "-h",
                self.db_host,
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "--no-password",
                "-c",
                # self.db_name is validated as a safe identifier in _parse_connection_string
                f"CREATE DATABASE {self.db_name};",  # nosec B608
            ]

            env = self._get_pg_env()

            result = subprocess.run(cmd_drop, env=env, capture_output=True, timeout=30)
            if result.returncode != 0:
                print(f"[WARN] Drop failed: {result.stderr}")

            result = subprocess.run(cmd_create, env=env, capture_output=True, timeout=30)
            if result.returncode != 0:
                print(f"[FAIL] Create failed: {result.stderr}")
                return False

            return True

        except subprocess.TimeoutExpired:
            print("[FAIL] Database recreation timed out")
            return False
        except Exception as e:
            print(f"[FAIL] Database recreation error: {e}")
            return False

    def list_snapshots(self) -> None:
        """List all available snapshots."""
        if not self.snapshots_dir.exists():
            print("[INFO] No snapshots directory found")
            return

        snapshots = sorted(self.snapshots_dir.glob("snapshot_*.sql"))

        if not snapshots:
            print("[INFO] No snapshots found")
            return

        print("\n[*] Available snapshots:")
        print("-" * 70)
        print(f"{'Filename':<40} {'Size':<15} {'Created':<15}")
        print("-" * 70)

        for snapshot in snapshots:
            size = snapshot.stat().st_size
            mtime = datetime.fromtimestamp(snapshot.stat().st_mtime)
            size_mb = f"{size / 1024 / 1024:.2f} MB"

            # Try to load metadata
            metadata_file = snapshot.with_suffix(".json")
            if metadata_file.exists():
                try:
                    with open(metadata_file) as f:
                        metadata = json.load(f)
                        print(
                            f"{snapshot.name:<40} {size_mb:<15} {metadata.get('created', ''):<15}"
                        )
                except:
                    print(
                        f"{snapshot.name:<40} {size_mb:<15} {mtime.strftime('%Y-%m-%d %H:%M'):<15}"
                    )
            else:
                print(f"{snapshot.name:<40} {size_mb:<15} {mtime.strftime('%Y-%m-%d %H:%M'):<15}")

        print("-" * 70)
        print(f"Total: {len(snapshots)} snapshot(s)")

    def _save_snapshot_metadata(self, snapshot_file: Path) -> None:
        """Save metadata about snapshot."""
        try:
            metadata = {
                "created": datetime.now().isoformat(),
                "database": self.db_name,
                "host": self.db_host,
                "port": self.db_port,
                "size_bytes": snapshot_file.stat().st_size,
            }

            metadata_file = snapshot_file.with_suffix(".json")
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"[WARN] Could not save metadata: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage production-mirror database snapshots",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python snapshot_prod_mirror.py snapshot              # Dump database
  python snapshot_prod_mirror.py snapshot -o backup.sql
  python snapshot_prod_mirror.py restore backup.sql
  python snapshot_prod_mirror.py list
        """,
    )

    parser.add_argument(
        "command", choices=["snapshot", "restore", "list"], help="Operation to perform"
    )

    parser.add_argument(
        "target", nargs="?", help="Target file (for restore) or output (for snapshot)"
    )

    parser.add_argument("-o", "--output", help="Output file for snapshot")

    parser.add_argument("-f", "--file", help="Input file for restore")

    parser.add_argument(
        "--db-url",
        default=DEFAULT_DATABASE_URL,
        help="Database URL (default: production-mirror)",
    )

    args = parser.parse_args()

    manager = SnapshotManager(args.db_url)

    if args.command == "snapshot":
        output_file = args.output or args.target
        success = manager.snapshot(output_file)
        sys.exit(0 if success else 1)

    elif args.command == "restore":
        input_file = args.file or args.target
        if not input_file:
            print("[FAIL] No input file specified")
            sys.exit(1)
        success = manager.restore(input_file)
        sys.exit(0 if success else 1)

    elif args.command == "list":
        manager.list_snapshots()
        sys.exit(0)


if __name__ == "__main__":
    main()
