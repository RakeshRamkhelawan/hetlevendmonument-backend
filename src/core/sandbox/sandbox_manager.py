"""
Sandbox Manager for Sanskriti Setu AI Multi-Agent System
Provides isolated execution environments with different levels of isolation
"""

import asyncio
import logging
import os
import shutil
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

try:
    import docker
    from docker.errors import DockerException, ImageNotFound

    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DockerException = ImageNotFound = Exception
    DOCKER_AVAILABLE = False

from src.core.shared.config import get_feature_flag, get_settings
from src.core.shared.interfaces import ExecutionResult, IsolationLevel, SandboxEnvironment, TaskData

logger = logging.getLogger(__name__)


class BaseSandboxManager(ABC):
    """Abstract base class for sandbox managers"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.active_sandboxes: dict[str, SandboxEnvironment] = {}
        self.sandbox_metrics: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    @abstractmethod
    async def create_sandbox(self, config: SandboxEnvironment) -> str:
        """Create a new sandbox environment"""

    @abstractmethod
    async def execute_in_sandbox(self, sandbox_id: str, task: TaskData) -> ExecutionResult:
        """Execute task in specified sandbox"""

    @abstractmethod
    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy sandbox and cleanup resources"""

    async def get_sandbox_status(self, sandbox_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current status of sandbox"""
        if sandbox_id not in self.active_sandboxes:
            return {"error": "Sandbox not found"}

        sandbox = self.active_sandboxes[sandbox_id]
        metrics = self.sandbox_metrics.get(sandbox_id, {})

        return {
            "sandbox_id": sandbox_id,
            "isolation_level": sandbox.isolation_level.value,
            "created_at": sandbox.created_at.isoformat(),
            "resource_limits": sandbox.resource_limits,
            "network_access": sandbox.network_access,
            "executions_count": metrics.get("executions_count", 0),
            "total_execution_time": metrics.get("total_execution_time", 0.0),
            "last_execution": metrics.get("last_execution"),
            "status": "active",
        }

    def _update_metrics(self, sandbox_id: str, execution_time: float, success: bool) -> None:
        """Update sandbox execution metrics"""
        if sandbox_id not in self.sandbox_metrics:
            self.sandbox_metrics[sandbox_id] = {
                "executions_count": 0,
                "total_execution_time": 0.0,
                "successful_executions": 0,
                "failed_executions": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        metrics = self.sandbox_metrics[sandbox_id]
        metrics["executions_count"] += 1
        metrics["total_execution_time"] += execution_time
        metrics["last_execution"] = datetime.now(timezone.utc).isoformat()

        if success:
            metrics["successful_executions"] += 1
        else:
            metrics["failed_executions"] += 1


class MockSandboxManager(BaseSandboxManager):
    """Mock sandbox manager for Week 1 - No real isolation, just simulated execution"""

    def __init__(self) -> None:
        super().__init__()
        self._execution_delay = 0.1  # Simulate execution time
        logger.info("Initialized MockSandboxManager (Week 1 implementation)")

    async def create_sandbox(self, config: SandboxEnvironment) -> str:
        """Create a mock sandbox environment"""
        sandbox_id = config.id or f"mock_sandbox_{uuid.uuid4().hex[:8]}"

        # Override isolation level to mock
        config.isolation_level = IsolationLevel.MOCK

        self.active_sandboxes[sandbox_id] = config
        self.sandbox_metrics[sandbox_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executions_count": 0,
            "total_execution_time": 0.0,
        }

        logger.info(f"Created mock sandbox: {sandbox_id}")
        return sandbox_id

    async def execute_in_sandbox(self, sandbox_id: str, task: TaskData) -> ExecutionResult:
        """Execute task in mock sandbox - just simulate execution"""
        start_time = time.time()

        if sandbox_id not in self.active_sandboxes:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Sandbox {sandbox_id} not found",
            )

        try:
            # Simulate execution delay
            await asyncio.sleep(self._execution_delay)

            # Mock execution based on task type
            result_data = await self._mock_task_execution(task)

            execution_time = time.time() - start_time

            # Update metrics
            self._update_metrics(sandbox_id, execution_time, True)

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data=result_data,
                execution_time=execution_time,
                resource_usage={
                    "memory_used": "64MB",
                    "cpu_time": f"{execution_time:.3f}s",
                    "sandbox_type": "mock",
                },
                logs=[
                    f"Mock execution started in sandbox {sandbox_id}",
                    f"Task type: {task.metadata.get('type', 'general')}",
                    "Execution completed successfully",
                ],
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._update_metrics(sandbox_id, execution_time, False)

            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Mock execution failed: {str(e)}",
                execution_time=execution_time,
            )

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy mock sandbox"""
        if sandbox_id in self.active_sandboxes:
            del self.active_sandboxes[sandbox_id]
            logger.info(f"Destroyed mock sandbox: {sandbox_id}")
            return True
        return False

    async def _mock_task_execution(self, task: TaskData) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Mock task execution with simulated results"""
        task_type = task.metadata.get("type", "general")

        # Different mock results based on task type
        if task_type == "data_analysis":
            return {
                "analysis_results": {
                    "data_points": 1000,
                    "patterns_found": 3,
                    "anomalies": 2,
                    "confidence": 0.85,
                },
                "summary": "Mock data analysis completed successfully",
                "execution_type": "mock",
            }

        elif task_type == "content_generation":
            return {
                "generated_content": f"Mock content generated for: {task.title}",
                "word_count": 250,
                "quality_score": 0.9,
                "execution_type": "mock",
            }

        elif task_type == "system_command":
            return {
                "command_output": "Mock command executed successfully",
                "exit_code": 0,
                "execution_type": "mock",
            }

        else:
            return {
                "result": f"Mock execution completed for task: {task.title}",
                "execution_type": "mock",
                "task_processed": True,
            }

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get sandbox metrics for health monitoring"""
        return {
            "active_sandboxes": len(self.active_sandboxes),
            "total_executions": sum(
                m.get("executions_count", 0) for m in self.sandbox_metrics.values()
            ),
            "successful_executions": sum(
                m.get("successful_executions", 0) for m in self.sandbox_metrics.values()
            ),
            "failed_executions": sum(
                m.get("failed_executions", 0) for m in self.sandbox_metrics.values()
            ),
            "total_execution_time": sum(
                m.get("total_execution_time", 0) for m in self.sandbox_metrics.values()
            ),
            "sandbox_type": "mock",
        }


class DockerSandboxManager(BaseSandboxManager):
    """Docker-based sandbox manager for Week 2+ - Real container isolation"""

    def __init__(self) -> None:
        super().__init__()
        self._docker_client: Any = None
        self._container_configs: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._container_instances: dict[str, Any] = {}  # sandbox_id -> container object  # TODO(TYPE): replace Any with concrete type

        # Use OS-appropriate temp directory
        import tempfile

        temp_base = Path(tempfile.gettempdir())
        self._workspace_base = temp_base / "sanskriti_sandboxes"
        self._workspace_base.mkdir(parents=True, exist_ok=True)

        # Initialize Docker client
        self._init_docker_client()
        logger.info(f"Initialized DockerSandboxManager - Docker available: {DOCKER_AVAILABLE}")

    def _init_docker_client(self) -> None:
        """Initialize Docker client with proper error handling"""
        if not DOCKER_AVAILABLE:
            logger.warning("Docker package not available - falling back to mock")
            return

        try:
            if docker is None:
                logger.warning("Docker package not available")
                return
            self._docker_client = docker.from_env()
            # Test connection
            if self._docker_client is not None:
                self._docker_client.ping()

            # Pull required base images
            self._ensure_base_images()

            logger.info("Docker client initialized successfully")
        except DockerException as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self._docker_client = None
        except Exception as e:
            logger.error(f"Unexpected error initializing Docker: {e}")
            self._docker_client = None

    def _ensure_base_images(self) -> None:
        """Ensure required base images are available"""
        if self._docker_client is None:
            return
        base_images = ["python:3.11-slim", "node:18-alpine", "ubuntu:22.04"]

        for image in base_images:
            try:
                if self._docker_client is not None:
                    self._docker_client.images.get(image)
                logger.debug(f"Base image {image} already available")
            except ImageNotFound:
                logger.info(f"Pulling base image: {image}")
                try:
                    if self._docker_client is not None:
                        self._docker_client.images.pull(image)
                    logger.info(f"Successfully pulled {image}")
                except Exception as e:
                    logger.warning(f"Failed to pull {image}: {e}")

    async def create_sandbox(self, config: SandboxEnvironment) -> str:
        """Create a Docker-based sandbox environment"""
        if not get_feature_flag("real_docker_sandbox") or not self._docker_client:
            # Fall back to mock
            logger.info("Using mock sandbox (Docker unavailable or disabled)")
            mock_manager = MockSandboxManager()
            return await mock_manager.create_sandbox(config)

        sandbox_id = config.id or f"docker_sandbox_{uuid.uuid4().hex[:8]}"

        try:
            # Create workspace directory
            workspace_dir = self._workspace_base / sandbox_id
            workspace_dir.mkdir(parents=True, exist_ok=True)

            # Setup container configuration
            container_config = await self._build_container_config(config, workspace_dir)

            # Create container with Windows-compatible settings
            container = self._docker_client.containers.create(
                image=container_config["image"],
                name=f"sanskriti_sandbox_{sandbox_id}",
                command=["tail", "-", "/dev/null"],  # Keep container running
                detach=True,
                mem_limit=container_config["memory_limit"],
                nano_cpus=int(float(container_config["cpu_limit"]) * 1_000_000_000),
                network_disabled=container_config["network_disabled"],
                working_dir=container_config["working_dir"],
                environment=container_config["environment"],
                volumes=container_config["volumes"],
                # Simplified security for Windows compatibility
                # user="1000:1000",  # Skip non-root user for now
                # read_only=True,     # Skip read-only for now
                # tmpfs={"/tmp": "size=100m,uid=1000,gid=1000"},  # Skip tmpfs for now
                # cap_drop=["ALL"],   # Skip capability dropping for now
                # security_opt=["no-new-privileges"]  # Skip security opt for now
            )

            # Store references
            self._container_configs[sandbox_id] = container_config
            self._container_instances[sandbox_id] = container
            self.active_sandboxes[sandbox_id] = config

            # Initialize metrics
            self.sandbox_metrics[sandbox_id] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "executions_count": 0,
                "total_execution_time": 0.0,
                "successful_executions": 0,
                "failed_executions": 0,
                "workspace_dir": str(workspace_dir),
            }

            container_id = cast(str, container.id)[:12] if container.id else "unknown"
            logger.info(f"Created Docker sandbox: {sandbox_id} with container {container_id}")
            return sandbox_id

        except Exception as e:
            logger.error(f"Failed to create Docker sandbox: {e}")
            # Cleanup on failure
            if sandbox_id in self._container_instances:
                await self._cleanup_container(sandbox_id)
            raise RuntimeError(f"Docker sandbox creation failed: {e}")

    async def _build_container_config(
        self, config: SandboxEnvironment, workspace_dir: Path
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Build container configuration from sandbox environment"""
        # Determine base image based on task requirements
        image = "python:3.11-slim"  # Default
        if "node" in str(config.resource_limits.get("runtime", "")).lower():
            image = "node:18-alpine"
        elif "ubuntu" in str(config.resource_limits.get("runtime", "")).lower():
            image = "ubuntu:22.04"

        # Setup volumes with security
        volumes = {str(workspace_dir): {"bind": "/workspace", "mode": "rw"}}

        # Add read-only mounts
        filesystem_access = config.filesystem_access or {}
        for ro_path in filesystem_access.get("read_only_paths", []):
            if os.path.exists(ro_path):
                volumes[ro_path] = {"bind": f"/readonly{ro_path}", "mode": "ro"}

        return {
            "image": image,
            "memory_limit": config.resource_limits.get("memory", "256m"),
            "cpu_limit": config.resource_limits.get("cpu", "0.5"),
            "network_disabled": not config.network_access,
            "working_dir": "/workspace",
            "environment": {
                "PYTHONPATH": "/workspace",
                "HOME": "/workspace",
                **config.resource_limits.get("env_vars", {}),
            },
            "volumes": volumes,
        }

    async def execute_in_sandbox(self, sandbox_id: str, task: TaskData) -> ExecutionResult:
        """Execute task in Docker sandbox"""
        if not get_feature_flag("real_docker_sandbox") or not self._docker_client:
            # Fall back to mock
            mock_manager = MockSandboxManager()
            return await mock_manager.execute_in_sandbox(sandbox_id, task)

        start_time = time.time()

        if sandbox_id not in self.active_sandboxes:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Docker sandbox {sandbox_id} not found",
            )

        container = self._container_instances.get(sandbox_id)
        if not container:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Docker container for sandbox {sandbox_id} not found",
            )

        try:
            # Prepare execution
            execution_script = await self._prepare_execution_script(task)
            workspace_dir = Path(self.sandbox_metrics[sandbox_id]["workspace_dir"])

            # Write script to workspace
            script_path = workspace_dir / "execute.py"
            with open(script_path, "w") as f:
                f.write(execution_script)

            # Refresh container status and start if needed
            container.reload()
            if container.status != "running":
                container.start()
                # Wait a moment for container to fully start
                import asyncio

                await asyncio.sleep(1)
                container.reload()  # Refresh status again after starting

            # Execute task with timeout
            int(self.active_sandboxes[sandbox_id].resource_limits.get("timeout", 30))

            exec_result = container.exec_run(
                cmd=["python", "/workspace/execute.py"],
                workdir="/workspace",
                # user="1000:1000",  # Skip user specification for Windows compatibility
                environment={"PYTHONPATH": "/workspace", "HOME": "/workspace"},
                stream=False,
                demux=False,
            )

            execution_time = time.time() - start_time

            # Process results
            stdout = (
                exec_result.output.decode("utf-8", errors="replace") if exec_result.output else ""
            )
            exit_code = exec_result.exit_code

            # Get container stats
            stats = container.stats(stream=False)
            memory_usage = self._format_memory_usage(stats)
            cpu_usage = self._format_cpu_usage(stats)

            success = exit_code == 0

            # Update metrics
            self._update_metrics(sandbox_id, execution_time, success)

            result_data = {
                "output": stdout,
                "exit_code": exit_code,
                "container_id": container.id[:12],
                "execution_type": "docker_real",
                "task_type": task.metadata.get("type", "general"),
            }

            if not success:
                result_data["error"] = f"Command failed with exit code {exit_code}"

            return ExecutionResult(
                task_id=task.id,
                success=success,
                result_data=result_data,
                error_message=None if success else f"Execution failed with exit code {exit_code}",
                execution_time=execution_time,
                resource_usage={
                    "memory_used": memory_usage,
                    "cpu_usage": cpu_usage,
                    "sandbox_type": "docker_real",
                    "container_id": container.id[:12],
                },
                logs=[
                    f"Docker execution started in container {container.id[:12]}",
                    f"Task type: {task.metadata.get('type', 'general')}",
                    f"Exit code: {exit_code}",
                    f"Execution time: {execution_time:.3f}s",
                    "Docker execution completed",
                ],
            )

        except Exception as e:
            execution_time = time.time() - start_time
            self._update_metrics(sandbox_id, execution_time, False)

            logger.error(f"Docker execution error in sandbox {sandbox_id}: {e}")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Docker execution failed: {str(e)}",
                execution_time=execution_time,
                resource_usage={
                    "sandbox_type": "docker_real",
                    "error": "execution_failed",
                },
            )

    async def _prepare_execution_script(self, task: TaskData) -> str:
        """Prepare Python script for task execution"""
        task_type = task.metadata.get("type", "general")

        if task_type == "python_code":
            # Direct code execution
            code = task.metadata.get("code", "print('No code provided')")
            indented = "\n".join("    " + line for line in code.split("\n"))
            return f"""#!/usr/bin/env python3
import sys
import json
import traceback

try:
{indented}
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
"""

        elif task_type == "data_analysis":
            return """#!/usr/bin/env python3
import json
import random

# Mock data analysis
result = {
    "analysis_results": {
        "data_points": random.randint(100, 10000),
        "patterns_found": random.randint(1, 10),
        "anomalies": random.randint(0, 5),
        "confidence": round(random.uniform(0.7, 0.95), 2)
    },
    "summary": "Real Docker data analysis completed",
    "execution_type": "docker_real"
}
print(json.dumps(result, indent=2))
"""

        else:
            # Generic task execution
            return f"""#!/usr/bin/env python3
import json

result = {{
    "message": "Task '{task.title}' executed in real Docker container",
    "task_id": "{task.id}",
    "execution_type": "docker_real",
    "status": "completed"
}}
print(json.dumps(result, indent=2))
"""

    def _format_memory_usage(self, stats: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format memory usage from container stats"""
        try:
            memory_usage = stats["memory_stats"]["usage"]
            memory_mb = memory_usage / (1024 * 1024)
            return f"{memory_mb:.1f}MB"
        except (KeyError, TypeError):
            return "unknown"

    def _format_cpu_usage(self, stats: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Format CPU usage from container stats"""
        try:
            cpu_stats = stats["cpu_stats"]
            precpu_stats = stats["precpu_stats"]

            cpu_delta = (
                cpu_stats["cpu_usage"]["total_usage"] - precpu_stats["cpu_usage"]["total_usage"]
            )
            system_delta = cpu_stats["system_cpu_usage"] - precpu_stats["system_cpu_usage"]

            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (
                    (cpu_delta / system_delta) * len(cpu_stats["cpu_usage"]["percpu_usage"]) * 100
                )
                return f"{cpu_percent:.1f}%"
        except (KeyError, TypeError, ZeroDivisionError):
            pass
        return "unknown"

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy Docker sandbox"""
        if sandbox_id not in self.active_sandboxes:
            return False

        try:
            success = await self._cleanup_container(sandbox_id)

            # Clean up workspace directory
            workspace_dir = Path(self.sandbox_metrics.get(sandbox_id, {}).get("workspace_dir", ""))
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir, ignore_errors=True)

            # Remove from tracking
            del self.active_sandboxes[sandbox_id]
            self._container_configs.pop(sandbox_id, None)
            self._container_instances.pop(sandbox_id, None)
            self.sandbox_metrics.pop(sandbox_id, None)

            logger.info(f"Destroyed Docker sandbox: {sandbox_id}")
            return success

        except Exception as e:
            logger.error(f"Failed to destroy Docker sandbox {sandbox_id}: {e}")
            return False

    async def _cleanup_container(self, sandbox_id: str) -> bool:
        """Clean up Docker container for sandbox"""
        container = self._container_instances.get(sandbox_id)
        if not container:
            return True

        try:
            # Stop container if running
            if container.status == "running":
                container.stop(timeout=10)
                logger.debug(f"Stopped container for sandbox {sandbox_id}")

            # Remove container
            container.remove(force=True)
            logger.debug(f"Removed container for sandbox {sandbox_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to cleanup container for sandbox {sandbox_id}: {e}")
            return False

    def _setup_volume_mounts(self, config: SandboxEnvironment) -> dict[str, str]:
        """Setup volume mounts for Docker container (legacy method)"""
        volumes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        filesystem_access = config.filesystem_access or {}
        if filesystem_access.get("read_only_paths"):
            for path in filesystem_access["read_only_paths"]:
                volumes[path] = {"bind": f"/readonly{path}", "mode": "ro"}

        if filesystem_access.get("writable_paths"):
            for path in filesystem_access["writable_paths"]:
                volumes[path] = {"bind": f"/workspace{path}", "mode": "rw"}

        return volumes

    async def get_container_logs(self, sandbox_id: str, tail: int = 100) -> list[str]:
        """Get logs from Docker container"""
        container = self._container_instances.get(sandbox_id)
        if not container:
            return []

        try:
            logs = container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
            return logs.split("\n") if logs else []
        except Exception as e:
            logger.error(f"Failed to get logs for sandbox {sandbox_id}: {e}")
            return []

    async def get_container_stats(self, sandbox_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get real-time stats from Docker container"""
        container = self._container_instances.get(sandbox_id)
        if not container:
            return {}

        try:
            stats = container.stats(stream=False)
            return {
                "memory_usage": self._format_memory_usage(stats),
                "cpu_usage": self._format_cpu_usage(stats),
                "container_id": container.id[:12],
                "status": container.status,
                "created": container.attrs.get("Created", ""),
                "network": stats.get("networks", {}),
            }
        except Exception as e:
            logger.error(f"Failed to get stats for sandbox {sandbox_id}: {e}")
            return {}


class SandboxManagerFactory:
    """Factory for creating appropriate sandbox managers"""

    @staticmethod
    def create_manager(
        isolation_level: IsolationLevel | None = None,
    ) -> BaseSandboxManager:
        """Create sandbox manager based on isolation level and feature flags"""

        if isolation_level is None:
            isolation_level = get_settings().default_isolation_level

        # Check if Docker is available and enabled
        docker_enabled = get_feature_flag("real_docker_sandbox") and DOCKER_AVAILABLE

        if isolation_level == IsolationLevel.MOCK or not docker_enabled:
            logger.info(f"Using MockSandboxManager (docker_enabled: {docker_enabled})")
            return MockSandboxManager()
        elif isolation_level in [IsolationLevel.PROCESS, IsolationLevel.CONTAINER]:
            logger.info(f"Using DockerSandboxManager for isolation level: {isolation_level}")
            return DockerSandboxManager()
        else:
            # VM isolation not yet implemented, fall back to Docker
            logger.warning(f"VM isolation not implemented, using Docker for {isolation_level}")
            return DockerSandboxManager()


# Sandbox utility functions
async def create_default_sandbox(
    isolation_level: IsolationLevel | None = None,
) -> tuple[BaseSandboxManager, str]:
    """Create a default sandbox environment"""
    manager = SandboxManagerFactory.create_manager(isolation_level)

    config = SandboxEnvironment(
        isolation_level=isolation_level or get_settings().default_isolation_level,
        resource_limits={
            "memory": "512MB",
            "cpu": "0.5",
            "timeout": get_settings().sandbox_timeout,
        },
        allowed_capabilities=["file_read", "file_write", "network_limited"],
        network_access=False,
        filesystem_access={
            "read_only_paths": ["/usr", "/bin", "/lib"],
            "writable_paths": [
                "/tmp",
                "/workspace",
            ],  # nosec B108: Docker tmpfs mount (noexec, nosuid)
            "forbidden_paths": ["/etc", "/sys", "/proc"],
        },
    )

    sandbox_id = await manager.create_sandbox(config)
    return manager, sandbox_id


async def execute_task_in_new_sandbox(
    task: TaskData, isolation_level: IsolationLevel | None = None
) -> ExecutionResult:
    """Execute a task in a new, temporary sandbox"""
    manager, sandbox_id = await create_default_sandbox(isolation_level)

    try:
        result = await manager.execute_in_sandbox(sandbox_id, task)
        return result
    finally:
        # Clean up sandbox
        await manager.destroy_sandbox(sandbox_id)


# Enhanced sandbox utilities
async def create_secure_sandbox(
    isolation_level: IsolationLevel | None = None,
    runtime: str = "python",
    memory_limit: str = "512MB",
    cpu_limit: str = "0.5",
    network_access: bool = False,
    timeout: int = 30,
) -> tuple[BaseSandboxManager, str]:
    """Create a secure sandbox with enhanced configuration"""
    manager = SandboxManagerFactory.create_manager(isolation_level)

    config = SandboxEnvironment(
        isolation_level=isolation_level or get_settings().default_isolation_level,
        resource_limits={
            "memory": memory_limit,
            "cpu": cpu_limit,
            "timeout": timeout,
            "runtime": runtime,
        },
        allowed_capabilities=["file_read", "file_write", "compute"]
        + (["network_limited"] if network_access else []),
        network_access=network_access,
        filesystem_access={
            "read_only_paths": ["/usr", "/bin", "/lib"] if runtime == "python" else [],
            "writable_paths": [
                "/tmp",
                "/workspace",
            ],  # nosec B108: Docker tmpfs mount (noexec, nosuid)
            "forbidden_paths": ["/etc", "/sys", "/proc", "/dev"],
        },
    )

    sandbox_id = await manager.create_sandbox(config)
    return manager, sandbox_id


# Sandbox monitoring and management
class SandboxMonitor:
    """Monitor and manage multiple sandbox environments"""

    def __init__(self) -> None:
        self.managers: dict[str, BaseSandboxManager] = {}
        self.sandbox_registry: dict[str, str] = {}  # sandbox_id -> manager_id

    def register_manager(self, manager_id: str, manager: BaseSandboxManager) -> None:
        """Register a sandbox manager"""
        self.managers[manager_id] = manager

    async def get_all_sandbox_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get status of all sandboxes across all managers"""
        all_status: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for manager_id, manager in self.managers.items():
            for sandbox_id in manager.active_sandboxes.keys():
                status = await manager.get_sandbox_status(sandbox_id)
                all_status[sandbox_id] = {**status, "manager_id": manager_id}

        return all_status

    async def cleanup_idle_sandboxes(self, max_idle_time: int = 3600) -> int:
        """Clean up sandboxes that have been idle for too long"""
        cleaned_count = 0
        current_time = datetime.now(timezone.utc)

        for manager in self.managers.values():
            for sandbox_id, metrics in manager.sandbox_metrics.items():
                last_execution = metrics.get("last_execution")
                if last_execution:
                    last_exec_time = datetime.fromisoformat(last_execution)
                    idle_time = (current_time - last_exec_time).total_seconds()

                    if idle_time > max_idle_time:
                        if await manager.destroy_sandbox(sandbox_id):
                            cleaned_count += 1
                            logger.info(f"Cleaned up idle sandbox: {sandbox_id}")

        return cleaned_count
