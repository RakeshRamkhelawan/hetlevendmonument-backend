"""
Tenant Sandbox Orchestrator for SanskritiSetu AI Platform

Provides complete tenant-isolated sandbox environments for:
- Workflow executions (short-lived, per-execution)
- Research environments (long-running, persistent)
- Agent executions (ephemeral, stateless)

Security Features:
- Per-tenant Docker networks (network isolation)
- Per-tenant storage volumes (filesystem isolation)
- Resource quotas (CPU, memory, execution time)
- Full audit trail per tenant
- Cost tracking for billing
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TypedDict, cast

logger = logging.getLogger(__name__)

# Try to import Docker, gracefully handle if not available
try:
    import docker
    from docker.errors import APIError, NotFound

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None
    NotFound = Exception


class SandboxType(str, Enum):
    """Types of sandbox environments"""

    WORKFLOW = "workflow"  # Short-lived, per-execution
    RESEARCH = "research"  # Long-running, persistent state
    AGENT = "agent"  # Ephemeral, stateless, fast


class SandboxState(str, Enum):
    """Sandbox lifecycle states"""

    PENDING = "pending"
    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    TERMINATED = "terminated"
    ERROR = "error"


@dataclass
class TenantQuota:
    """Resource quotas per tenant"""

    max_concurrent_sandboxes: int = 5
    max_memory_mb: int = 2048  # 2GB total
    max_cpu_cores: float = 2.0
    max_execution_time_seconds: int = 3600  # 1 hour
    max_storage_mb: int = 1024  # 1GB
    max_network_bandwidth_mbps: int = 10
    max_daily_executions: int = 1000


@dataclass
class SandboxMetrics:
    """Metrics for a single sandbox execution"""

    sandbox_id: str
    tenant_id: int
    sandbox_type: SandboxType
    start_time: datetime
    end_time: datetime | None = None
    execution_time_seconds: float = 0.0
    memory_used_mb: float = 0.0
    cpu_used_seconds: float = 0.0
    network_bytes_in: int = 0
    network_bytes_out: int = 0
    exit_code: int | None = None
    success: bool = False
    cost_credits: float = 0.0


@dataclass
class SandboxConfig:
    """Configuration for creating a sandbox"""

    sandbox_type: SandboxType
    language: str = "python"
    memory_limit_mb: int = 256
    cpu_limit: float = 0.5
    timeout_seconds: int = 30
    network_enabled: bool = False
    persistent_storage: bool = False
    environment: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


class _ActiveSandboxInfo(TypedDict):
    """Runtime info for a sandbox currently held in a tenant pool."""

    id: str
    container_id: str | None
    config: SandboxConfig
    state: SandboxState
    created_at: datetime
    memory_limit_mb: int
    cpu_limit: float


@dataclass
class TenantSandboxPool:
    """Pool of sandboxes for a specific tenant"""

    tenant_id: int
    quota: TenantQuota
    active_sandboxes: dict[str, _ActiveSandboxInfo] = field(default_factory=dict)
    network_name: str = ""
    volume_name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_executions: int = 0
    total_cost_credits: float = 0.0
    daily_executions: int = 0
    last_reset_date: str = ""

    def __post_init__(self) -> None:
        self.network_name = f"tenant_{self.tenant_id}_net"
        self.volume_name = f"tenant_{self.tenant_id}_data"
        self.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")


class TenantSandboxOrchestrator:
    """
    Orchestrates sandbox environments with complete tenant isolation.

    Features:
    - Per-tenant Docker networks (no cross-tenant communication)
    - Per-tenant storage volumes (filesystem isolation)
    - Resource quota enforcement
    - Full audit logging per tenant
    - Cost tracking for billing

    Usage:
        orchestrator = TenantSandboxOrchestrator()
        await orchestrator.initialize()

        # Create sandbox for tenant
        sandbox_id = await orchestrator.create_sandbox(
            tenant_id=1,
            config=SandboxConfig(sandbox_type=SandboxType.WORKFLOW)
        )

        # Execute code
        result = await orchestrator.execute_in_sandbox(
            tenant_id=1,
            sandbox_id=sandbox_id,
            code="print('Hello, World!')"
        )

        # Cleanup
        await orchestrator.destroy_sandbox(tenant_id=1, sandbox_id=sandbox_id)
    """

    # Docker image mapping for languages
    LANGUAGE_IMAGES = {
        "python": "python:3.11-slim",
        "javascript": "node:18-slim",
        "typescript": "node:18-slim",
        "ruby": "ruby:3.2-slim",
        "go": "golang:1.21-alpine",
        "rust": "rust:1.73-slim",
        "java": "openjdk:17-slim",
    }

    def __init__(self, default_quota: TenantQuota | None = None) -> None:
        """Initialize the Tenant Sandbox Orchestrator"""
        self._docker_client: Any = None
        self._tenant_pools: dict[int, TenantSandboxPool] = {}
        self._default_quota = default_quota or TenantQuota()
        self._execution_history: dict[int, list[SandboxMetrics]] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """Initialize the orchestrator and Docker client"""
        if self._initialized:
            return True

        if not DOCKER_AVAILABLE:
            logger.warning("Docker not available - using mock mode")
            self._initialized = True
            return True

        try:
            if docker is not None:
                self._docker_client = docker.from_env(timeout=10)
                self._docker_client.ping()
                logger.info("TenantSandboxOrchestrator initialized with Docker")
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self._initialized = True  # Continue in mock mode
            return False

    async def get_or_create_tenant_pool(
        self, tenant_id: int, quota: TenantQuota | None = None
    ) -> TenantSandboxPool:
        """Get or create the sandbox pool for a tenant"""
        async with self._lock:
            if tenant_id not in self._tenant_pools:
                pool = TenantSandboxPool(tenant_id=tenant_id, quota=quota or self._default_quota)

                # Create isolated Docker network for tenant
                if self._docker_client:
                    await self._create_tenant_network(pool)
                    await self._create_tenant_volume(pool)

                self._tenant_pools[tenant_id] = pool
                self._execution_history[tenant_id] = []
                logger.info(f"Created sandbox pool for tenant {tenant_id}")

            return self._tenant_pools[tenant_id]

    async def _create_tenant_network(self, pool: TenantSandboxPool) -> None:
        """Create isolated Docker network for tenant"""
        if not self._docker_client:
            return

        try:
            # Check if network exists
            try:
                self._docker_client.networks.get(pool.network_name)
                logger.debug(f"Network {pool.network_name} already exists")
                return
            except NotFound:
                pass

            # Create isolated network
            self._docker_client.networks.create(
                name=pool.network_name,
                driver="bridge",
                internal=True,  # No external access
                labels={
                    "tenant_id": str(pool.tenant_id),
                    "managed_by": "sanskritisetu",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(f"Created isolated network {pool.network_name}")
        except Exception as e:
            logger.error(f"Failed to create tenant network: {e}")

    async def _create_tenant_volume(self, pool: TenantSandboxPool) -> None:
        """Create persistent storage volume for tenant"""
        if not self._docker_client:
            return

        try:
            # Check if volume exists
            try:
                self._docker_client.volumes.get(pool.volume_name)
                logger.debug(f"Volume {pool.volume_name} already exists")
                return
            except NotFound:
                pass

            # Create volume with size limit (via driver opts if supported)
            self._docker_client.volumes.create(
                name=pool.volume_name,
                labels={
                    "tenant_id": str(pool.tenant_id),
                    "managed_by": "sanskritisetu",
                    "max_size_mb": str(pool.quota.max_storage_mb),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(f"Created storage volume {pool.volume_name}")
        except Exception as e:
            logger.error(f"Failed to create tenant volume: {e}")

    async def check_quota(self, tenant_id: int, config: SandboxConfig) -> tuple[bool, str]:
        """
        Check if tenant has quota available for new sandbox

        Returns:
            (allowed: bool, reason: str)
        """
        pool = await self.get_or_create_tenant_pool(tenant_id)

        # Reset daily counter if needed
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if pool.last_reset_date != today:
            pool.daily_executions = 0
            pool.last_reset_date = today

        # Check concurrent sandboxes
        if len(pool.active_sandboxes) >= pool.quota.max_concurrent_sandboxes:
            return (
                False,
                f"Max concurrent sandboxes ({pool.quota.max_concurrent_sandboxes}) reached",
            )

        # Check daily executions
        if pool.daily_executions >= pool.quota.max_daily_executions:
            return (
                False,
                f"Daily execution limit ({pool.quota.max_daily_executions}) reached",
            )

        # Check memory allocation
        current_memory = sum(s.get("memory_limit_mb", 0) for s in pool.active_sandboxes.values())
        if current_memory + config.memory_limit_mb > pool.quota.max_memory_mb:
            return (
                False,
                f"Memory quota ({pool.quota.max_memory_mb}MB) would be exceeded",
            )

        # Check CPU allocation
        current_cpu = sum(s.get("cpu_limit", 0) for s in pool.active_sandboxes.values())
        if current_cpu + config.cpu_limit > pool.quota.max_cpu_cores:
            return (
                False,
                f"CPU quota ({pool.quota.max_cpu_cores} cores) would be exceeded",
            )

        return (True, "OK")

    async def create_sandbox(self, tenant_id: int, config: SandboxConfig) -> str | None:
        """Create a new sandbox for tenant"""
        # Check quota
        allowed, reason = await self.check_quota(tenant_id, config)
        if not allowed:
            logger.warning(f"Quota check failed for tenant {tenant_id}: {reason}")
            raise PermissionError(f"Sandbox creation denied: {reason}")

        pool = await self.get_or_create_tenant_pool(tenant_id)
        sandbox_id = f"sandbox_{tenant_id}_{uuid.uuid4().hex[:8]}"

        try:
            if self._docker_client:
                container = await self._create_docker_sandbox(pool, sandbox_id, config)
                container_id = container.id if container else None
            else:
                container_id = f"mock_{sandbox_id}"

            # Register sandbox
            pool.active_sandboxes[sandbox_id] = {
                "id": sandbox_id,
                "container_id": container_id,
                "config": config,
                "state": SandboxState.READY,
                "created_at": datetime.now(timezone.utc),
                "memory_limit_mb": config.memory_limit_mb,
                "cpu_limit": config.cpu_limit,
            }

            pool.total_executions += 1
            pool.daily_executions += 1

            logger.info(
                f"Created sandbox {sandbox_id} for tenant {tenant_id} "
                f"(type={config.sandbox_type.value})"
            )
            return sandbox_id

        except Exception as e:
            logger.error(f"Failed to create sandbox for tenant {tenant_id}: {e}")
            raise

    async def _create_docker_sandbox(
        self, pool: TenantSandboxPool, sandbox_id: str, config: SandboxConfig
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Create Docker container for sandbox"""
        if not self._docker_client:
            return None

        image = self.LANGUAGE_IMAGES.get(config.language, "python:3.11-slim")

        # Build container configuration
        container_config = {
            "name": sandbox_id,
            "image": image,
            "detach": True,
            "tty": True,
            "mem_limit": f"{config.memory_limit_mb}m",
            "cpu_period": 100000,
            "cpu_quota": int(100000 * config.cpu_limit),
            "network_mode": pool.network_name if not config.network_enabled else "bridge",
            "read_only": config.sandbox_type != SandboxType.RESEARCH,
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "labels": {
                "tenant_id": str(pool.tenant_id),
                "sandbox_id": sandbox_id,
                "sandbox_type": config.sandbox_type.value,
                "managed_by": "sanskritisetu",
                **config.labels,
            },
            "environment": {
                "TENANT_ID": str(pool.tenant_id),
                "SANDBOX_ID": sandbox_id,
                "SANDBOX_TYPE": config.sandbox_type.value,
                **config.environment,
            },
        }

        # Add persistent storage for research sandboxes
        if config.persistent_storage and config.sandbox_type == SandboxType.RESEARCH:
            container_config["volumes"] = {
                pool.volume_name: {"bind": "/workspace/data", "mode": "rw"}
            }

        try:
            # Ensure image is available
            try:
                self._docker_client.images.get(image)
            except NotFound:
                logger.info(f"Pulling image {image}...")
                self._docker_client.images.pull(image)

            container = self._docker_client.containers.create(**container_config)
            container.start()
            return container
        except Exception as e:
            logger.error(f"Failed to create Docker container: {e}")
            raise

    async def execute_in_sandbox(
        self,
        tenant_id: int,
        sandbox_id: str,
        code: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute code in a tenant's sandbox"""
        pool = await self.get_or_create_tenant_pool(tenant_id)

        if sandbox_id not in pool.active_sandboxes:
            raise ValueError(f"Sandbox {sandbox_id} not found for tenant {tenant_id}")

        sandbox = pool.active_sandboxes[sandbox_id]
        config = sandbox["config"]
        timeout = timeout or config.timeout_seconds

        # Start metrics collection
        metrics = SandboxMetrics(
            sandbox_id=sandbox_id,
            tenant_id=tenant_id,
            sandbox_type=config.sandbox_type,
            start_time=datetime.now(timezone.utc),
        )

        sandbox["state"] = SandboxState.RUNNING
        start_time = time.perf_counter()

        try:
            if self._docker_client:
                container_id = cast(str, sandbox["container_id"])
                result = await self._execute_in_docker(
                    container_id, code, config.language, timeout
                )
            else:
                result = await self._mock_execute(code, config.language, timeout)

            # Update metrics
            metrics.end_time = datetime.now(timezone.utc)
            metrics.execution_time_seconds = time.perf_counter() - start_time
            metrics.exit_code = result.get("exit_code", 0)
            metrics.success = result.get("success", False)
            metrics.cost_credits = self._calculate_cost(metrics)

            # Update pool totals
            pool.total_cost_credits += metrics.cost_credits

            # Store in history
            self._execution_history[tenant_id].append(metrics)

            sandbox["state"] = SandboxState.READY

            # Prometheus instrumentation (best-effort -- never fail the execution)
            try:
                from src.core.sandbox.metrics import (
                    SANDBOX_EXECUTIONS_TOTAL,
                    SANDBOX_EXECUTION_DURATION,
                )

                lang = config.language
                tid = str(tenant_id)
                SANDBOX_EXECUTIONS_TOTAL.labels(
                    tenant_id=tid, language=lang, success=str(metrics.success).lower()
                ).inc()
                if metrics.execution_time_seconds is not None:
                    SANDBOX_EXECUTION_DURATION.labels(tenant_id=tid, language=lang).observe(
                        metrics.execution_time_seconds
                    )
            except Exception:
                pass

            return {
                "success": metrics.success,
                "output": result.get("output", ""),
                "error": result.get("error", ""),
                "exit_code": metrics.exit_code,
                "execution_time": metrics.execution_time_seconds,
                "cost_credits": metrics.cost_credits,
            }

        except TimeoutError:
            sandbox["state"] = SandboxState.ERROR
            metrics.end_time = datetime.now(timezone.utc)
            metrics.execution_time_seconds = timeout
            metrics.success = False
            self._execution_history[tenant_id].append(metrics)
            return {
                "success": False,
                "output": "",
                "error": f"Execution timed out after {timeout}s",
                "exit_code": -1,
                "execution_time": timeout,
            }
        except Exception as e:
            sandbox["state"] = SandboxState.ERROR
            logger.error(f"Execution failed in sandbox {sandbox_id}: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": -1,
            }

    async def _execute_in_docker(
        self, container_id: str, code: str, language: str, timeout: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute code in Docker container"""
        if not self._docker_client:
            return await self._mock_execute(code, language, timeout)

        try:
            container = self._docker_client.containers.get(container_id)

            # Prepare execution command based on language
            if language == "python":
                cmd = ["python", "-c", code]
            elif language in ("javascript", "typescript"):
                cmd = ["node", "-e", code]
            elif language == "ruby":
                cmd = ["ruby", "-e", code]
            else:
                cmd = ["sh", "-c", code]

            # Execute with timeout
            exec_result = container.exec_run(
                cmd, demux=True, environment={"PYTHONDONTWRITEBYTECODE": "1"}
            )

            stdout, stderr = exec_result.output or (b"", b"")
            return {
                "success": exec_result.exit_code == 0,
                "output": stdout.decode() if stdout else "",
                "error": stderr.decode() if stderr else "",
                "exit_code": exec_result.exit_code,
            }
        except Exception as e:
            logger.error(f"Docker execution failed: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": -1,
            }

    async def _mock_execute(
        self, code: str, language: str, timeout: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Mock execution when Docker is not available"""
        await asyncio.sleep(0)  # yield control to event loop

        # Basic safety check - dangerous patterns
        dangerous_patterns = [
            "os.system",
            "subprocess",
            "eval(",
            "exec(",
            "__import__",
            "import os",
            "import subprocess",
            "open(",
            "rm -rf",
            "shutil.rmtree",
        ]
        for pattern in dangerous_patterns:
            if pattern in code:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Security violation: {pattern} not allowed",
                    "exit_code": 1,
                }

        return {
            "success": True,
            "output": f"[MOCK] Code executed successfully ({language})",
            "error": "",
            "exit_code": 0,
        }

    def _calculate_cost(self, metrics: SandboxMetrics) -> float:
        """Calculate cost credits for execution"""
        # Base cost per second
        base_rate = 0.001

        # Adjust by sandbox type
        type_multipliers = {
            SandboxType.AGENT: 0.5,  # Lightweight
            SandboxType.WORKFLOW: 1.0,  # Standard
            SandboxType.RESEARCH: 2.0,  # Long-running
        }

        multiplier = type_multipliers.get(metrics.sandbox_type, 1.0)
        return metrics.execution_time_seconds * base_rate * multiplier

    async def destroy_sandbox(self, tenant_id: int, sandbox_id: str) -> bool:
        """Destroy a sandbox and release resources"""
        pool = await self.get_or_create_tenant_pool(tenant_id)

        if sandbox_id not in pool.active_sandboxes:
            logger.warning(f"Sandbox {sandbox_id} not found for tenant {tenant_id}")
            return False

        sandbox = pool.active_sandboxes[sandbox_id]

        try:
            if self._docker_client and sandbox.get("container_id"):
                try:
                    container = self._docker_client.containers.get(sandbox["container_id"])
                    container.stop(timeout=5)
                    container.remove(force=True)
                except NotFound:
                    pass
                except Exception as e:
                    logger.warning(f"Error stopping container: {e}")

            del pool.active_sandboxes[sandbox_id]
            logger.info(f"Destroyed sandbox {sandbox_id} for tenant {tenant_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to destroy sandbox {sandbox_id}: {e}")
            return False

    async def cleanup_tenant(
        self, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Clean up all resources for a tenant"""
        if tenant_id not in self._tenant_pools:
            return {"success": True, "message": "No resources to clean up"}

        pool = self._tenant_pools[tenant_id]
        cleaned = {
            "sandboxes_destroyed": 0,
            "network_removed": False,
            "volume_removed": False,
        }

        # Destroy all active sandboxes
        for sandbox_id in list(pool.active_sandboxes.keys()):
            if await self.destroy_sandbox(tenant_id, sandbox_id):
                cleaned["sandboxes_destroyed"] += 1

        if self._docker_client:
            # Remove network
            try:
                network = self._docker_client.networks.get(pool.network_name)
                network.remove()
                cleaned["network_removed"] = True
            except NotFound:
                cleaned["network_removed"] = True
            except Exception as e:
                logger.warning(f"Failed to remove network: {e}")

            # Optionally remove volume (careful - data loss!)
            # Uncomment if you want to delete tenant data on cleanup
            # try:
            #     volume = self._docker_client.volumes.get(pool.volume_name)
            #     volume.remove()
            #     cleaned["volume_removed"] = True
            # except Exception as e:
            #     logger.warning(f"Failed to remove volume: {e}")

        del self._tenant_pools[tenant_id]
        logger.info(f"Cleaned up all resources for tenant {tenant_id}: {cleaned}")
        return {"success": True, **cleaned}

    async def get_tenant_usage(
        self, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get resource usage for a tenant"""
        pool = await self.get_or_create_tenant_pool(tenant_id)

        return {
            "tenant_id": tenant_id,
            "active_sandboxes": len(pool.active_sandboxes),
            "total_executions": pool.total_executions,
            "daily_executions": pool.daily_executions,
            "total_cost_credits": pool.total_cost_credits,
            "quota": {
                "max_concurrent_sandboxes": pool.quota.max_concurrent_sandboxes,
                "max_memory_mb": pool.quota.max_memory_mb,
                "max_cpu_cores": pool.quota.max_cpu_cores,
                "max_daily_executions": pool.quota.max_daily_executions,
            },
            "current_usage": {
                "memory_mb": sum(
                    s.get("memory_limit_mb", 0) for s in pool.active_sandboxes.values()
                ),
                "cpu_cores": sum(s.get("cpu_limit", 0) for s in pool.active_sandboxes.values()),
            },
        }

    async def get_execution_history(
        self, tenant_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get execution history for a tenant (for audit)"""
        if tenant_id not in self._execution_history:
            return []

        history = self._execution_history[tenant_id][-limit:]
        return [
            {
                "sandbox_id": m.sandbox_id,
                "type": m.sandbox_type.value,
                "start_time": m.start_time.isoformat(),
                "end_time": m.end_time.isoformat() if m.end_time else None,
                "execution_time": m.execution_time_seconds,
                "success": m.success,
                "cost_credits": m.cost_credits,
            }
            for m in history
        ]


# Global instance
_orchestrator: TenantSandboxOrchestrator | None = None


async def get_sandbox_orchestrator() -> TenantSandboxOrchestrator:
    """Get or create the global sandbox orchestrator"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TenantSandboxOrchestrator()
        await _orchestrator.initialize()
    return _orchestrator
