"""
Chaos Engineering Test - Data Isolation Validation
==================================================

Sprint 3 Task 3.2.1: Chaos Engineering Tests

Test Scenario:
- 50 concurrent tenants making queries
- Inject random backend replica failures
- Verify zero cross-tenant data leakage
- Verify automatic recovery

Chaos Injection:
- Kill random backend replica every 2 minutes
- Verify Nginx routes to healthy replicas
- Verify automatic replica restart
- Verify zero data corruption

Acceptance Criteria:
- Zero cross-tenant queries (tenant A never sees tenant B data)
- Zero data corruption (checksums match before/after)
- Zero request failures during failover
- Recovery time <30 seconds
"""

import asyncio
import hashlib
import logging
import shutil
import subprocess

# Add project root to path
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.agents.models import Agent
from src.core.database.database import DatabaseManager, get_async_session
from src.core.models.rbac_models import Tenant, User

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def _require_chaos_environment(base_url: str) -> None:
    if shutil.which("docker") is None:
        pytest.skip("Chaos data-isolation test requires Docker")

    missing_containers = []
    for container_name in ["backend-1", "backend-2", "backend-3"]:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or result.stdout.strip().lower() != "true":
            missing_containers.append(container_name)

    if missing_containers:
        pytest.skip(
            "Chaos data-isolation test requires running replica set: "
            + ", ".join(missing_containers)
        )

    db_manager = DatabaseManager()
    try:
        initialized = await db_manager.initialize()
    except Exception as exc:
        pytest.skip(f"Chaos data-isolation test requires live PostgreSQL: {exc}")

    if not initialized:
        pytest.skip("Chaos data-isolation test requires live PostgreSQL")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            response = await client.get("/health")
            if response.status_code != 200:
                pytest.skip(f"Chaos data-isolation test requires healthy backend at {base_url}")
    except Exception as exc:
        pytest.skip(f"Chaos data-isolation test requires backend at {base_url}: {exc}")


class ChaosEngineer:
    """
    Chaos engineering orchestrator for data isolation testing.

    Injects failures while validating:
    - Multi-tenant data isolation
    - Automatic failover
    - Zero data corruption
    - Recovery time <30 seconds
    """

    def __init__(self, base_url: str = "http://localhost:8100"):
        self.base_url = base_url
        self.tenants: List[str] = []
        self.tenant_tokens: Dict[str, str] = {}
        self.tenant_data: Dict[str, Dict[str, Any]] = {}
        self.backend_containers = ["backend-1", "backend-2", "backend-3"]

    async def setup(self, num_tenants: int = 50):
        """
        Setup test environment with multiple tenants.

        Creates 50 tenants with sample data for chaos testing.
        """
        logger.info("🏗️ Setting up %s tenants for chaos testing...", num_tenants)

        # Get database session
        db_manager = DatabaseManager()
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            for i in range(num_tenants):
                tenant_id = f"chaos_tenant_{i:03d}"

                # Create tenant
                tenant = Tenant(
                    id=tenant_id,
                    name=f"Chaos Test Tenant {i}",
                    plan="pro",
                    status="active",
                )
                session.add(tenant)

                # Create user for this tenant
                user = User(
                    tenant_id=tenant_id,
                    email=f"{tenant_id}@chaos.test",
                    hashed_password="hashed_password_placeholder",
                    full_name=f"Chaos User {i}",
                    is_active=True,
                )
                session.add(user)

                # Create sample agents
                for j in range(5):
                    agent = Agent(
                        tenant_id=tenant_id,
                        name=f"{tenant_id}_agent_{j}",
                        agent_type="analyzer",
                        description=f"Chaos test agent {j} for tenant {i}",
                        config={"model": "gpt-4"},
                    )
                    session.add(agent)

                await session.commit()

                self.tenants.append(tenant_id)

                # Calculate checksum for tenant data
                checksum = await self._calculate_tenant_checksum(session, tenant_id)
                self.tenant_data[tenant_id] = {
                    "checksum": checksum,
                    "user_count": 1,
                    "agent_count": 5,
                }

                logger.info("✅ Created tenant %s with checksum %s...", tenant_id, checksum[:16])

        logger.info("✅ Setup complete: %s tenants ready", num_tenants)

    async def _calculate_tenant_checksum(self, session: AsyncSession, tenant_id: str) -> str:
        """
        Calculate checksum of all tenant data for corruption detection.
        """
        # Get all user emails for this tenant
        users_result = await session.execute(
            select(User.email).filter(User.tenant_id == tenant_id).order_by(User.email)
        )
        user_emails = [row[0] for row in users_result]

        # Get all agent names for this tenant
        agents_result = await session.execute(
            select(Agent.name).filter(Agent.tenant_id == tenant_id).order_by(Agent.name)
        )
        agent_names = [row[0] for row in agents_result]

        # Combine and hash
        data_string = "|".join(user_emails + agent_names)
        checksum = hashlib.sha256(data_string.encode()).hexdigest()

        return checksum

    async def run_concurrent_queries(self, duration_seconds: int = 120):
        """
        Run concurrent queries from all tenants.

        Each tenant:
        - Lists their own agents
        - Gets agent details
        - Creates conversations
        - Verifies data isolation
        """
        logger.info("🚀 Starting concurrent queries for %s seconds...", duration_seconds)

        start_time = time.time()
        violation_count = 0
        total_requests = 0
        failed_requests = 0

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            while time.time() - start_time < duration_seconds:
                # Each tenant makes a query
                tasks = []
                for tenant_id in self.tenants:
                    task = self._tenant_query(client, tenant_id)
                    tasks.append(task)

                # Run queries concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Check results for violations
                for tenant_id, result in zip(self.tenants, results):
                    total_requests += 1

                    if isinstance(result, Exception):
                        failed_requests += 1
                        logger.warning("Request failed for %s: %s", tenant_id, result)
                        continue

                    result_data = cast(Dict[str, Any], result)

                    # Check for cross-tenant data leakage
                    if result_data.get("violation"):
                        violation_count += 1
                        logger.error(
                            f"🚨 DATA LEAK DETECTED: {tenant_id} received data "
                            f"from {result_data['foreign_tenant']}"
                        )

                # Small delay between rounds
                await asyncio.sleep(0.1)

        logger.info("✅ Concurrent queries completed")
        logger.info("Total requests: %s", total_requests)
        logger.info("Failed requests: %s", failed_requests)
        logger.info("Cross-tenant violations: %s", violation_count)

        return {
            "total_requests": total_requests,
            "failed_requests": failed_requests,
            "violations": violation_count,
            "success_rate": (total_requests - failed_requests) / total_requests * 100,
        }

    async def _tenant_query(self, client: httpx.AsyncClient, tenant_id: str) -> Dict[str, Any]:
        """
        Single tenant query with data isolation check.
        """
        # In a real implementation, we'd use JWT tokens here
        # For now, we'll use a custom header to simulate tenant context

        response = await client.get("/api/agents", headers={"X-Tenant-ID": tenant_id})

        if response.status_code != 200:
            return {"error": response.status_code}

        agents = response.json().get("agents", [])

        # Check all agents belong to this tenant
        for agent in agents:
            if agent.get("tenant_id") != tenant_id:
                return {
                    "violation": True,
                    "foreign_tenant": agent.get("tenant_id"),
                    "expected_tenant": tenant_id,
                }

        return {"success": True, "agent_count": len(agents)}

    async def inject_backend_failure(self, container_name: str):
        """
        Kill a backend container to simulate failure.

        Returns the time when container was killed.
        """
        logger.warning("💥 Injecting failure: Killing %s...", container_name)

        try:
            # Kill the container
            subprocess.run(["docker", "kill", container_name], check=True, capture_output=True)

            kill_time = time.time()
            logger.warning("💀 %s killed at %s", container_name, datetime.now())

            return kill_time

        except subprocess.CalledProcessError as e:
            logger.error("Failed to kill %s: %s", container_name, e)
            return None

    async def wait_for_recovery(
        self, container_name: str, kill_time: float, timeout: int = 60
    ) -> Optional[float]:
        """
        Wait for container to automatically restart.

        Returns recovery time in seconds.
        """
        logger.info("⏳ Waiting for %s to recover...", container_name)

        start_wait = time.time()

        while time.time() - start_wait < timeout:
            try:
                # Check if container is running
                result = subprocess.run(
                    ["docker", "inspect", "-", "{{.State.Running}}", container_name],
                    capture_output=True,
                    text=True,
                )

                if result.stdout.strip() == "true":
                    recovery_time = time.time() - kill_time
                    logger.info(f"✅ {container_name} recovered in {recovery_time:.2f} seconds")
                    return recovery_time

            except subprocess.CalledProcessError:
                pass

            await asyncio.sleep(1)

        logger.error("❌ %s did not recover within %s seconds", container_name, timeout)
        return None

    async def verify_data_integrity(self):
        """
        Verify no data corruption occurred during chaos testing.

        Compares current checksums with original checksums.
        """
        logger.info("🔍 Verifying data integrity...")

        corrupted_tenants = []

        db_manager = DatabaseManager()
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            for tenant_id in self.tenants:
                original_checksum = self.tenant_data[tenant_id]["checksum"]
                current_checksum = await self._calculate_tenant_checksum(session, tenant_id)

                if original_checksum != current_checksum:
                    corrupted_tenants.append(tenant_id)
                    logger.error(
                        f"🚨 DATA CORRUPTION: {tenant_id} "
                        f"(original: {original_checksum[:8]}, "
                        f"current: {current_checksum[:8]})"
                    )

        if corrupted_tenants:
            logger.error("❌ Data corruption detected in %s tenants", len(corrupted_tenants))
            return False
        else:
            logger.info("✅ Data integrity verified: No corruption detected")
            return True

    async def cleanup(self):
        """Remove test data."""
        if not self.tenants:
            # Setup never ran — nothing to clean up
            return

        logger.info("🧹 Cleaning up test data...")

        db_manager = DatabaseManager()
        try:
            initialized = await db_manager.initialize()
        except Exception as exc:
            logger.warning("Skipping chaos cleanup because database is unavailable: %s", exc)
            return

        if not initialized:
            logger.warning("Skipping chaos cleanup because database could not initialize")
            return

        async with db_manager.get_session() as session:
            # Delete test tenants and cascade delete all related data
            # CAST needed because id is INTEGER and LIKE only works on TEXT
            await session.execute(
                text("DELETE FROM tenants WHERE CAST(id AS TEXT) LIKE 'chaos_tenant_%'")
            )
            await session.commit()

        logger.info("✅ Cleanup complete")


# ============================================================================
# PYTEST TEST SUITE
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.chaos
async def test_data_isolation_with_backend_failures():
    """
    Test data isolation under chaos conditions.

    - Creates 50 tenants with sample data
    - Runs concurrent queries for 2 minutes
    - Injects backend failures every 30 seconds
    - Verifies zero cross-tenant data leaks
    - Verifies zero data corruption
    - Verifies automatic recovery <30 seconds
    """
    chaos = ChaosEngineer()

    try:
        await _require_chaos_environment(chaos.base_url)

        # Setup test environment
        await chaos.setup(num_tenants=50)

        # Track metrics
        recovery_times = []

        # Start concurrent queries in background
        query_task = asyncio.create_task(chaos.run_concurrent_queries(duration_seconds=120))

        # Inject failures every 30 seconds
        for i in range(4):  # 4 failures over 2 minutes
            await asyncio.sleep(30)

            # Pick a random backend to kill
            container = chaos.backend_containers[i % 3]

            # Inject failure
            kill_time = await chaos.inject_backend_failure(container)

            if kill_time:
                # Wait for recovery
                recovery_time = await chaos.wait_for_recovery(container, kill_time, timeout=60)

                if recovery_time:
                    recovery_times.append(recovery_time)

                    # Assert recovery time <30 seconds
                    assert recovery_time < 30, f"Recovery took {recovery_time:.2f}s (target: <30s)"

        # Wait for queries to complete
        query_results = await query_task

        # Verify zero cross-tenant violations
        assert (
            query_results["violations"] == 0
        ), f"Found {query_results['violations']} cross-tenant data leaks!"

        # Verify data integrity
        assert await chaos.verify_data_integrity(), "Data corruption detected!"

        # Verify success rate
        assert (
            query_results["success_rate"] > 99.9
        ), f"Success rate too low: {query_results['success_rate']:.2f}%"

        # Log results
        logger.info("\n" + "=" * 80)
        logger.info("🎉 CHAOS TEST PASSED")
        logger.info("=" * 80)
        logger.info("Total requests: %s", query_results["total_requests"])
        logger.info("Failed requests: %s", query_results["failed_requests"])
        logger.info("Success rate: %.2f%", query_results["success_rate"])
        logger.info("Cross-tenant violations: %s", query_results["violations"])
        logger.info("Backend failures injected: %s", len(recovery_times))
        logger.info("Average recovery time: %.2fs", sum(recovery_times) / len(recovery_times))
        logger.info("Max recovery time: %.2fs", max(recovery_times))
        logger.info("=" * 80)

    finally:
        # Cleanup
        await chaos.cleanup()


if __name__ == "__main__":
    """
    Run chaos test standalone (without pytest).
    """
    asyncio.run(test_data_isolation_with_backend_failures())
