"""
Copilot Admin CLI - Forensic auditing and hash chain verification.

Usage:
    python tools/copilot_admin.py verify-chain --tenant-id 1
    python tools/copilot_admin.py inspect --decision-id UUID
"""

import argparse
import asyncio
import logging
import sys
from uuid import UUID

from src.core.copilot.audit.forensics import HashChainVerifier
from src.core.database.database import db_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def verify_chain(tenant_id: int):
    """Verify integrity for a tenant."""
    print(f"[*] Verifying hash chain for tenant {tenant_id}...")
    verifier = HashChainVerifier(db_manager.get_session)
    
    report = await verifier.verify_tenant_chain(tenant_id)
    
    if report.is_valid:
        print(f"[OK] Chain is VALID. Verified {report.total_records} records.")
    else:
        print(f"[FAIL] Chain is CORRUPT! Detected {len(report.errors)} integrity issues.")
        for err in report.errors:
            print(f"  - {err}")
        sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="Copilot Admin CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # verify-chain command
    verify_parser = subparsers.add_parser("verify-chain", help="Verify hash chain integrity")
    verify_parser.add_argument("--tenant-id", type=int, required=True, help="ID of the tenant to verify")

    # inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a specific decision")
    inspect_parser.add_argument("--decision-id", type=str, required=True, help="UUID of the decision")

    args = parser.parse_args()

    if args.command == "verify-chain":
        await verify_chain(args.tenant_id)
    elif args.command == "inspect":
        # Placeholder for detailed inspection
        print(f"[*] Inspecting decision {args.decision_id} (not fully implemented)")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
