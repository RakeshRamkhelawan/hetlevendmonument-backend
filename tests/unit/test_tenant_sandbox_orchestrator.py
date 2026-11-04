"""
Tests for Tenant Sandbox Orchestrator

Tests tenant isolation, quota enforcement, and sandbox lifecycle management.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Deze tests bouwen een sandbox in een constructor, en die roept `docker.from_env()` aan
# -- een ECHTE verbinding naar de Docker-daemon (ADR-036 OP-214).
from tests.fixtures.docker_sandbox import geen_echte_docker_daemon  # noqa: F401

from src.core.sandbox.tenant_sandbox_orchestrator import (
    SandboxConfig,
    SandboxMetrics,
    SandboxState,
    SandboxType,
    TenantQuota,
    TenantSandboxOrchestrator,
    TenantSandboxPool,
)


class TestTenantQuota:
    """Tests for TenantQuota dataclass"""

    def test_default_quota_values(self):
        """Test default quota values are reasonable"""
        quota = TenantQuota()
        assert quota.max_concurrent_sandboxes == 5
        assert quota.max_memory_mb == 2048
        assert quota.max_cpu_cores == 2.0
        assert quota.max_daily_executions == 1000

    def test_custom_quota(self):
        """Test custom quota values"""
        quota = TenantQuota(
            max_concurrent_sandboxes=10,
            max_memory_mb=4096,
            max_cpu_cores=4.0,
        )
        assert quota.max_concurrent_sandboxes == 10
        assert quota.max_memory_mb == 4096


class TestTenantSandboxPool:
    """Tests for TenantSandboxPool"""

    def test_pool_creation(self):
        """Test pool is created with correct tenant ID"""
        pool = TenantSandboxPool(tenant_id=1, quota=TenantQuota())
        assert pool.tenant_id == 1
        assert pool.network_name == "tenant_1_net"
        assert pool.volume_name == "tenant_1_data"
        assert len(pool.active_sandboxes) == 0

    def test_pool_network_naming(self):
        """Test network names are tenant-specific"""
        pool1 = TenantSandboxPool(tenant_id=1, quota=TenantQuota())
        pool2 = TenantSandboxPool(tenant_id=2, quota=TenantQuota())
        assert pool1.network_name != pool2.network_name


class TestSandboxConfig:
    """Tests for SandboxConfig"""

    def test_default_config(self):
        """Test default sandbox configuration"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        assert config.language == "python"
        assert config.memory_limit_mb == 256
        assert config.network_enabled is False

    def test_research_config(self):
        """Test research sandbox configuration"""
        config = SandboxConfig(
            sandbox_type=SandboxType.RESEARCH,
            persistent_storage=True,
            memory_limit_mb=512,
        )
        assert config.persistent_storage is True
        assert config.memory_limit_mb == 512


class TestTenantSandboxOrchestrator:
    """Tests for TenantSandboxOrchestrator"""

    @pytest.fixture
    async def initialized_orchestrator(self):
        """Create and initialize orchestrator without Docker"""
        # Create orchestrator and initialize (may connect to Docker if available)
        orch = TenantSandboxOrchestrator()
        await orch.initialize()
        # Force mock mode after init so tests use deterministic mock execution
        orch._docker_client = None
        return orch

    @pytest.mark.asyncio
    async def test_initialization(self, initialized_orchestrator):
        """Test orchestrator initializes correctly"""
        assert initialized_orchestrator._initialized is True

    @pytest.mark.asyncio
    async def test_create_tenant_pool(self, initialized_orchestrator):
        """Test tenant pool creation"""
        pool = await initialized_orchestrator.get_or_create_tenant_pool(1)
        assert pool.tenant_id == 1
        assert pool.network_name == "tenant_1_net"

    @pytest.mark.asyncio
    async def test_tenant_pools_are_isolated(self, initialized_orchestrator):
        """Test that different tenants get different pools"""
        pool1 = await initialized_orchestrator.get_or_create_tenant_pool(1)
        pool2 = await initialized_orchestrator.get_or_create_tenant_pool(2)

        assert pool1 is not pool2
        assert pool1.tenant_id != pool2.tenant_id
        assert pool1.network_name != pool2.network_name

    @pytest.mark.asyncio
    async def test_quota_check_passes(self, initialized_orchestrator):
        """Test quota check passes for valid request"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        allowed, reason = await initialized_orchestrator.check_quota(1, config)
        assert allowed is True
        assert reason == "OK"

    @pytest.mark.asyncio
    async def test_quota_check_fails_concurrent_limit(self, initialized_orchestrator):
        """Test quota check fails when concurrent limit reached"""
        # Set low limit
        pool = await initialized_orchestrator.get_or_create_tenant_pool(1)
        pool.quota.max_concurrent_sandboxes = 1

        # Create first sandbox
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await initialized_orchestrator.create_sandbox(1, config)
        assert sandbox_id is not None

        # Try to create second - should be denied
        allowed, reason = await initialized_orchestrator.check_quota(1, config)
        assert allowed is False
        assert "concurrent" in reason.lower()

    @pytest.mark.asyncio
    async def test_quota_check_fails_memory_limit(self, initialized_orchestrator):
        """Test quota check fails when memory limit exceeded"""
        pool = await initialized_orchestrator.get_or_create_tenant_pool(1)
        pool.quota.max_memory_mb = 256

        # Create sandbox using half the memory
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW, memory_limit_mb=200)
        await initialized_orchestrator.create_sandbox(1, config)

        # Try to create another using more than remaining
        config2 = SandboxConfig(sandbox_type=SandboxType.WORKFLOW, memory_limit_mb=200)
        allowed, reason = await initialized_orchestrator.check_quota(1, config2)
        assert allowed is False
        assert "memory" in reason.lower()

    @pytest.mark.asyncio
    async def test_create_sandbox(self, initialized_orchestrator):
        """Test sandbox creation"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await initialized_orchestrator.create_sandbox(1, config)

        assert sandbox_id is not None
        assert sandbox_id.startswith("sandbox_1_")

        pool = initialized_orchestrator._tenant_pools[1]
        assert sandbox_id in pool.active_sandboxes

    @pytest.mark.asyncio
    async def test_execute_in_sandbox(self, initialized_orchestrator):
        """Test code execution in sandbox"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await initialized_orchestrator.create_sandbox(1, config)

        result = await initialized_orchestrator.execute_in_sandbox(
            tenant_id=1,
            sandbox_id=sandbox_id,
            code="print('hello')",
        )

        assert result["success"] is True
        assert "execution_time" in result

    @pytest.mark.asyncio
    async def test_execute_in_nonexistent_sandbox(self, initialized_orchestrator):
        """Test execution in non-existent sandbox fails"""
        with pytest.raises(ValueError):
            await initialized_orchestrator.execute_in_sandbox(
                tenant_id=1,
                sandbox_id="nonexistent",
                code="print('hello')",
            )

    @pytest.mark.asyncio
    async def test_dangerous_code_blocked(self, initialized_orchestrator):
        """Test dangerous code is blocked in mock mode"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await initialized_orchestrator.create_sandbox(1, config)

        # Force mock mode by ensuring docker client is None
        initialized_orchestrator._docker_client = None

        result = await initialized_orchestrator.execute_in_sandbox(
            tenant_id=1,
            sandbox_id=sandbox_id,
            code="import os; os.system('rm -rf /')",
        )

        assert result["success"] is False
        assert "security" in result["error"].lower() or "violation" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_destroy_sandbox(self, initialized_orchestrator):
        """Test sandbox destruction"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await initialized_orchestrator.create_sandbox(1, config)

        result = await initialized_orchestrator.destroy_sandbox(1, sandbox_id)
        assert result is True

        pool = initialized_orchestrator._tenant_pools[1]
        assert sandbox_id not in pool.active_sandboxes

    @pytest.mark.asyncio
    async def test_get_tenant_usage(self, initialized_orchestrator):
        """Test usage reporting"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        await initialized_orchestrator.create_sandbox(1, config)

        usage = await initialized_orchestrator.get_tenant_usage(1)

        assert usage["tenant_id"] == 1
        assert usage["active_sandboxes"] == 1
        assert usage["total_executions"] == 1
        assert "quota" in usage

    @pytest.mark.asyncio
    async def test_execution_history(self, initialized_orchestrator):
        """Test execution history tracking"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await initialized_orchestrator.create_sandbox(1, config)

        await initialized_orchestrator.execute_in_sandbox(
            tenant_id=1,
            sandbox_id=sandbox_id,
            code="print('test')",
        )

        history = await initialized_orchestrator.get_execution_history(1)
        assert len(history) == 1
        assert history[0]["sandbox_id"] == sandbox_id

    @pytest.mark.asyncio
    async def test_cleanup_tenant(self, initialized_orchestrator):
        """Test full tenant cleanup"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        await initialized_orchestrator.create_sandbox(1, config)
        await initialized_orchestrator.create_sandbox(1, config)

        result = await initialized_orchestrator.cleanup_tenant(1)

        assert result["success"] is True
        assert result["sandboxes_destroyed"] == 2
        assert 1 not in initialized_orchestrator._tenant_pools


class TestTenantIsolation:
    """Security tests for tenant isolation"""

    @pytest.fixture
    async def orchestrator(self):
        """Create initialized orchestrator"""
        with patch("src.core.sandbox.tenant_sandbox_orchestrator.DOCKER_AVAILABLE", False):
            orch = TenantSandboxOrchestrator()
            await orch.initialize()
            return orch

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_tenant_cannot_access_other_tenant_sandbox(self, orchestrator):
        """Tenant 1 cannot access Tenant 2's sandbox"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)

        # Tenant 1 creates sandbox
        sandbox_1 = await orchestrator.create_sandbox(1, config)

        # Tenant 2 tries to execute in Tenant 1's sandbox
        with pytest.raises(ValueError):
            await orchestrator.execute_in_sandbox(
                tenant_id=2,
                sandbox_id=sandbox_1,
                code="print('attack')",
            )

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_tenant_cannot_destroy_other_tenant_sandbox(self, orchestrator):
        """Tenant 1 cannot destroy Tenant 2's sandbox"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)

        # Tenant 1 creates sandbox
        sandbox_1 = await orchestrator.create_sandbox(1, config)

        # Tenant 2 tries to destroy Tenant 1's sandbox
        result = await orchestrator.destroy_sandbox(2, sandbox_1)
        assert result is False  # Should fail

        # Sandbox should still exist for Tenant 1
        pool = orchestrator._tenant_pools[1]
        assert sandbox_1 in pool.active_sandboxes

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_tenant_pools_are_completely_isolated(self, orchestrator):
        """Tenants have completely separate sandbox pools"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)

        # Both tenants create sandboxes
        sandbox_1 = await orchestrator.create_sandbox(1, config)
        sandbox_2 = await orchestrator.create_sandbox(2, config)

        pool_1 = orchestrator._tenant_pools[1]
        pool_2 = orchestrator._tenant_pools[2]

        # Sandboxes should be in their respective pools only
        assert sandbox_1 in pool_1.active_sandboxes
        assert sandbox_1 not in pool_2.active_sandboxes
        assert sandbox_2 in pool_2.active_sandboxes
        assert sandbox_2 not in pool_1.active_sandboxes


class TestCostTracking:
    """Tests for cost tracking"""

    @pytest.fixture
    async def orchestrator(self):
        """Create initialized orchestrator"""
        with patch("src.core.sandbox.tenant_sandbox_orchestrator.DOCKER_AVAILABLE", False):
            orch = TenantSandboxOrchestrator()
            await orch.initialize()
            return orch

    @pytest.mark.asyncio
    async def test_cost_calculated_per_execution(self, orchestrator):
        """Test cost is calculated for each execution"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await orchestrator.create_sandbox(1, config)

        result = await orchestrator.execute_in_sandbox(
            tenant_id=1,
            sandbox_id=sandbox_id,
            code="print('test')",
        )

        assert "cost_credits" in result
        assert result["cost_credits"] >= 0

    @pytest.mark.asyncio
    async def test_total_cost_accumulates(self, orchestrator):
        """Test total cost accumulates across executions"""
        config = SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        sandbox_id = await orchestrator.create_sandbox(1, config)

        initial_usage = await orchestrator.get_tenant_usage(1)
        initial_cost = initial_usage["total_cost_credits"]

        await orchestrator.execute_in_sandbox(tenant_id=1, sandbox_id=sandbox_id, code="print('1')")
        await orchestrator.execute_in_sandbox(tenant_id=1, sandbox_id=sandbox_id, code="print('2')")

        final_usage = await orchestrator.get_tenant_usage(1)
        assert final_usage["total_cost_credits"] > initial_cost


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not security or security"])
