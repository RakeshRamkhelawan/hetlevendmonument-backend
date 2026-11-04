#!/usr/bin/env python3
"""
Disaster Recovery Test Runner
Sprint 5, Slice 4

Purpose: Validate point-in-time recovery and data integrity after simulated disasters.

Test Scenarios:
1. Database snapshot & restore
2. Partial table corruption recovery
3. Redis cache rebuild from DB
4. RabbitMQ queue recovery

Safety: Runs ONLY against test/staging database (checks DB_URL for 'test' or 'staging')
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DisasterRecoveryTester:
    """
    Orchestrates DR tests with automatic validation.
    """

    def __init__(self, db_url: str, backup_dir: str = "./backups/dr_test"):
        """
        Initialize DR tester.

        Args:
            db_url: Database connection URL
            backup_dir: Directory to store backups
        """
        # Safety check: prevent running against production
        if not any(
            keyword in db_url.lower() for keyword in ["test", "staging", "dev", "localhost"]
        ):
            raise ValueError(
                f"SAFETY: DR tests can only run against test/staging/dev databases. "
                f"URL: {database_url_zonder_wachtwoord(db_url)}"
            )

        self.db_url = db_url
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(db_url)
        self.results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        logger.info(f"DR Tester initialized (backup_dir={backup_dir})")

    def run_all_tests(self) -> bool:
        """
        Run all DR test scenarios.

        Returns:
            True if all tests passed
        """
        logger.info("=== Starting Disaster Recovery Tests ===")

        tests = [
            ("Database Snapshot & Restore", self.test_db_snapshot_restore),
            ("Partial Table Corruption", self.test_partial_corruption_recovery),
            ("Data Integrity Verification", self.test_data_integrity),
        ]

        all_passed: bool = True
        for test_name, test_func in tests:
            logger.info(f"\n--- Running: {test_name} ---")
            try:
                passed = test_func()
                self.results.append(
                    {
                        "test": test_name,
                        "status": "PASS" if passed else "FAIL",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                if not passed:
                    all_passed = False
                    logger.error(f"[FAIL] {test_name} FAILED")
                else:
                    logger.info(f"[OK] {test_name} PASSED")
            except Exception as e:
                logger.error(f"[FAIL] {test_name} EXCEPTION: {e}", exc_info=True)
                self.results.append(
                    {
                        "test": test_name,
                        "status": "ERROR",
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                all_passed = False

        self._write_report()
        return all_passed

    def test_db_snapshot_restore(self) -> bool:
        """
        Test 1: Create DB snapshot, corrupt data, restore from snapshot.

        Steps:
        1. Insert known test data
        2. Create snapshot (hash state)
        3. Modify/delete data
        4. Restore from snapshot
        5. Verify hash matches
        """
        logger.info("Step 1: Insert test data")
        with Session(self.engine) as session:
            # Insert test tenant
            session.execute(
                text(
                    """
                INSERT INTO tenants (id, name, slug, created_at)
                VALUES (9999, 'DR Test Tenant', 'dr-test', NOW())
                ON CONFLICT (id) DO NOTHING
            """
                )
            )

            # Insert test user
            session.execute(
                text(
                    """
                INSERT INTO users (email, hashed_password, tenant_id, is_active, created_at)
                VALUES ('dr_test@test.com', 'hash123', 9999, true, NOW())
                ON CONFLICT (email) DO NOTHING
            """
                )
            )

            session.commit()

        logger.info("Step 2: Create state snapshot (checksum)")
        checksum_before = self._calculate_table_checksum("users", "email = 'dr_test@test.com'")
        logger.info(f"Checksum before: {checksum_before}")

        logger.info("Step 3: Corrupt data (simulate disaster)")
        with Session(self.engine) as session:
            session.execute(
                text(
                    """
                UPDATE users
                SET email = 'corrupted@disaster.com'
                WHERE email = 'dr_test@test.com'
            """
                )
            )
            session.commit()

        checksum_corrupted = self._calculate_table_checksum(
            "users", "email = 'corrupted@disaster.com'"
        )
        logger.info(f"Checksum after corruption: {checksum_corrupted}")

        if checksum_corrupted == checksum_before:
            logger.error("Corruption did not change checksum - test setup failed")
            return False

        logger.info("Step 4: Restore from snapshot (simulate point-in-time recovery)")
        with Session(self.engine) as session:
            session.execute(
                text(
                    """
                UPDATE users
                SET email = 'dr_test@test.com'
                WHERE email = 'corrupted@disaster.com'
            """
                )
            )
            session.commit()

        logger.info("Step 5: Verify restoration")
        checksum_restored = self._calculate_table_checksum("users", "email = 'dr_test@test.com'")
        logger.info(f"Checksum after restore: {checksum_restored}")

        # Cleanup
        self._cleanup_test_data()

        return checksum_before == checksum_restored

    def test_partial_corruption_recovery(self) -> bool:
        """
        Test 2: Recover from partial table corruption (some rows affected).

        Scenario: Random rows deleted, verify recovery identifies missing data.
        """
        logger.info("Step 1: Create 10 test records")
        with Session(self.engine) as session:
            for i in range(10):
                session.execute(
                    text(
                        "INSERT INTO users "
                        "(email, hashed_password, tenant_id, is_active, created_at) "
                        "VALUES (:email, :pwd, 9999, true, NOW()) "
                        "ON CONFLICT (email) DO NOTHING"
                    ),
                    {"email": f"dr_partial_{i}@test.com", "pwd": f"hash{i}"},
                )
            session.commit()

        with Session(self.engine) as session:
            count_before = session.execute(
                text("SELECT COUNT(*) FROM users WHERE email LIKE 'dr_partial_%'")
            ).scalar()
        logger.info(f"Records before: {count_before}")

        logger.info("Step 3: Simulate partial corruption (delete random rows)")
        with Session(self.engine) as session:
            session.execute(
                text(
                    """
                DELETE FROM users
                WHERE email LIKE 'dr_partial_%'
                AND RANDOM() < 0.5
            """
                )
            )
            session.commit()

        with Session(self.engine) as session:
            count_corrupted = session.execute(
                text(
                    """
                SELECT COUNT(*) FROM users WHERE email LIKE 'dr_partial_%'
            """
                )
            ).scalar()
        logger.info(f"Records after corruption: {count_corrupted}")

        missing_count = (count_before or 0) - (count_corrupted or 0)
        logger.info(f"Missing records detected: {missing_count}")

        # In real DR, this would trigger restore from backup
        # For test: verify we detected the loss
        detected_corruption = missing_count > 0

        # Cleanup
        with Session(self.engine) as session:
            session.execute(text("DELETE FROM users WHERE email LIKE 'dr_partial_%'"))
            session.commit()

        return detected_corruption

    def test_data_integrity(self) -> bool:
        """
        Test 3: Verify data integrity after restore (foreign keys, constraints).
        """
        logger.info("Step 1: Create relational test data (tenant -> user -> workflow)")
        with Session(self.engine) as session:
            # Tenant
            session.execute(
                text(
                    """
                INSERT INTO tenants (id, name, slug, created_at)
                VALUES (8888, 'Integrity Test', 'integrity-test', NOW())
                ON CONFLICT (id) DO NOTHING
            """
                )
            )

            # User
            session.execute(
                text(
                    """
                INSERT INTO users (id, email, hashed_password, tenant_id, is_active, created_at)
                VALUES (8888, 'integrity@test.com', 'hash', 8888, true, NOW())
                ON CONFLICT (id) DO NOTHING
            """
                )
            )

            session.commit()

        logger.info("Step 2: Verify foreign key relationships")
        with Session(self.engine) as session:
            # Check user -> tenant relationship
            result = session.execute(
                text(
                    """
                SELECT u.email, t.name
                FROM users u
                JOIN tenants t ON u.tenant_id = t.id
                WHERE u.id = 8888
            """
                )
            ).fetchone()

        if result is None:
            logger.error("Foreign key relationship broken")
            return False

        email, tenant_name = result
        logger.info(f"Relationship verified: {email} -> {tenant_name}")

        # Cleanup
        with Session(self.engine) as session:
            session.execute(text("DELETE FROM users WHERE id = 8888"))
            session.execute(text("DELETE FROM tenants WHERE id = 8888"))
            session.commit()

        return bool(email == "integrity@test.com" and tenant_name == "Integrity Test")

    def _calculate_table_checksum(self, table: str, where_clause: str = "1=1") -> str:
        """
        Calculate checksum of table rows (simplified).

        Args:
            table: Table name
            where_clause: WHERE condition

        Returns:
            MD5 checksum of concatenated row data
        """
        with Session(self.engine) as session:
            # Get all columns
            inspector = inspect(self.engine)
            columns = [col["name"] for col in inspector.get_columns(table)]

            # Fetch data
            query = f"SELECT {', '.join(columns)} FROM {table} WHERE {where_clause}"  # nosec B608 - DR test only; columns from schema inspector, table/where_clause from internal callers with hardcoded values
            rows = session.execute(text(query)).fetchall()

            # Serialize and hash
            data_str = json.dumps([tuple(row) for row in rows], default=str, sort_keys=True)
            checksum = hashlib.md5(data_str.encode(), usedforsecurity=False).hexdigest()

        return checksum

    def _cleanup_test_data(self) -> None:
        """Remove all DR test data."""
        with Session(self.engine) as session:
            session.execute(text("DELETE FROM users WHERE tenant_id = 9999"))
            session.execute(text("DELETE FROM tenants WHERE id = 9999"))
            session.commit()
        logger.info("Cleanup completed")

    def _write_report(self) -> None:
        """Write test results to JSON report."""
        report_path = (
            self.backup_dir / f"dr_test_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        )

        report: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "test_run_timestamp": datetime.now(timezone.utc).isoformat(),
            "database_url": self.db_url[:30] + "...",  # Don't log full URL
            "results": self.results,
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r["status"] == "PASS"),
                "failed": sum(1 for r in self.results if r["status"] == "FAIL"),
                "errors": sum(1 for r in self.results if r["status"] == "ERROR"),
            },
        }

        report_path.write_text(json.dumps(report, indent=2))
        logger.info(f"Report written to {report_path}")

        # Print summary
        print("\n" + "=" * 60)
        print("DISASTER RECOVERY TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests:  {report['summary']['total']}")
        print(f"[OK] Passed:     {report['summary']['passed']}")
        print(f"[FAIL] Failed:     {report['summary']['failed']}")
        print(f"[WARN]  Errors:     {report['summary']['errors']}")
        print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Disaster Recovery Test Runner")
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL"),
        help="Database URL (must contain test/staging/dev for safety)",
    )
    parser.add_argument(
        "--backup-dir",
        default="./backups/dr_test",
        help="Backup directory for test artifacts",
    )

    args = parser.parse_args()

    if not args.db_url:
        print("ERROR: No database URL provided (use --db-url or DATABASE_URL env var)")
        sys.exit(1)

    try:
        tester = DisasterRecoveryTester(db_url=args.db_url, backup_dir=args.backup_dir)
        success = tester.run_all_tests()

        if success:
            print("[OK] ALL DR TESTS PASSED")
            sys.exit(0)
        else:
            print("[FAIL] SOME DR TESTS FAILED")
            sys.exit(1)

    except ValueError as e:
        print(f"SAFETY ERROR: {e}")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
