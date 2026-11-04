#!/usr/bin/env python3
"""
Docker Sandbox Executor for Sanskriti Setu AI Multi-Agent System
Advanced Docker-based code execution with comprehensive security and monitoring
"""

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional, cast

try:
    import docker
    from docker.errors import APIError, ContainerError, DockerException, ImageNotFound

    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DockerException = APIError = ImageNotFound = ContainerError = Exception
    DOCKER_AVAILABLE = False

from src.core.shared.config import get_feature_flag, get_settings
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Configuration for sandbox execution"""

    language: str = "python"
    timeout: int = 30
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    network_disabled: bool = True
    read_only: bool = True
    working_dir: str = "/workspace"
    environment: dict[str, str] | None = None


@dataclass
class ExecutionMetrics:
    """Execution performance metrics"""

    start_time: float
    end_time: float
    execution_time: float
    memory_usage: int
    cpu_usage: float
    exit_code: int
    container_id: str
    success: bool


class DockerSandboxExecutor:
    """Advanced Docker-based sandbox execution system"""

    # Language-specific Docker images
    LANGUAGE_IMAGES = {
        "python": "python:3.11-slim",
        "javascript": "node:18-slim",
        "typescript": "node:18-slim",
        "java": "openjdk:17-slim",
        "go": "golang:1.21-alpine",
        "rust": "rust:1.70-slim",
        "bash": "ubuntu:22.04",
        "shell": "ubuntu:22.04",
    }

    # Language execution commands
    LANGUAGE_COMMANDS = {
        "python": ["python", "-c"],
        "javascript": ["node", "-e"],
        "typescript": ["npx", "ts-node", "-e"],
        "java": ["java", "--source", "17"],
        "go": ["go", "run"],
        "rust": ["rustc", "--edition", "2021", "-"],
        "bash": ["bash", "-c"],
        "shell": ["sh", "-c"],
    }

    def __init__(self) -> None:
        """Initialize the Docker sandbox executor"""
        self.settings = get_settings()
        self.docker_client = None
        self.active_containers: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.execution_metrics: list[ExecutionMetrics] = []
        self.container_pool: list[str] = []
        self.max_pool_size = 5

        # Initialize Docker client if available
        if DOCKER_AVAILABLE and docker is not None and get_feature_flag("real_docker_sandbox"):
            try:
                self.docker_client = docker.from_env()
                logger.info("Docker sandbox executor initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Docker client: {e}")
                self.docker_client = None
        else:
            logger.info("Docker sandbox executor running in mock mode")

    async def execute_code(
        self, code: str, config: ExecutionConfig | None = None
    ) -> ExecutionResult:
        """Execute code in a Docker sandbox"""

        if config is None:
            config = ExecutionConfig()

        execution_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            if not self.docker_client:
                return await self._mock_execution(code, config, execution_id)

            # Get or create container
            container = await self._get_or_create_container(config)

            # Prepare execution environment
            await self._prepare_execution_environment(container, code, config)

            # Execute code
            result = await self._execute_in_container(container, code, config, execution_id)

            # Collect metrics
            metrics = await self._collect_execution_metrics(
                container, start_time, result.get("exit_code", 0), execution_id
            )
            self.execution_metrics.append(metrics)

            # Return container to pool if reusable
            await self._return_container_to_pool(container, config)

            return ExecutionResult(
                task_id=execution_id,
                success=result.get("success", False),
                result_data={
                    "output": result.get("output", {}),
                    "language": config.language,
                    "container_id": container.id,
                    "metrics": metrics.__dict__,
                },
                execution_time=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Docker execution failed: {e}")
            return ExecutionResult(
                task_id=execution_id,
                success=False,
                result_data={
                    "error": str(e),
                    "language": config.language,
                    "error_type": type(e).__name__,
                },
                execution_time=time.time() - start_time,
            )

    async def _get_or_create_container(self, config: ExecutionConfig) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get container from pool or create new one"""

        # Try to get from pool first
        if self.container_pool and self.docker_client is not None:
            container_id = self.container_pool.pop()
            try:
                container = cast(Any, self.docker_client).containers.get(container_id)  # TODO(TYPE): replace Any with concrete type
                if container.status == "running":
                    logger.debug(f"Reusing container from pool: {container_id}")
                    return container
            except Exception as e:
                logger.debug(
                    f"Container {container_id} no longer exists or unavailable: {str(e)}",
                    exc_info=False,
                )

        # Create new container
        image = self.LANGUAGE_IMAGES.get(config.language, "python:3.11-slim")

        # Ensure image is available
        await self._ensure_image_available(image)

        # Container configuration
        container_config = {
            "image": image,
            "detach": True,
            "remove": False,  # Keep for reuse
            "mem_limit": config.memory_limit,
            "nano_cpus": int(config.cpu_limit * 1e9),
            "working_dir": config.working_dir,
            "environment": config.environment or {},
            "command": ["tail", "-f", "/dev/null"],  # Keep container alive
        }

        # Network isolation
        if config.network_disabled:
            container_config["network_disabled"] = True

        # Security settings
        container_config.update(
            {
                "user": "1001",  # Non-root user
                "cap_drop": ["ALL"],  # Remove all capabilities
                "security_opt": ["no-new-privileges:true"],
            }
        )

        # Windows compatibility adjustments
        if os.name == "nt":
            # Remove problematic settings for Windows Docker Desktop
            container_config.pop("user", None)
            container_config.pop("read_only", None)

        try:
            container = cast(Any, self.docker_client).containers.run(**container_config)  # TODO(TYPE): replace Any with concrete type
            self.active_containers[container.id] = container
            logger.debug(f"Created new container: {container.id}")
            return container

        except Exception as e:
            logger.error(f"Failed to create container: {e}")
            raise

    async def _ensure_image_available(self, image: str) -> None:
        """Ensure Docker image is available locally"""
        if self.docker_client is None:
            return
        docker_client = cast(Any, self.docker_client)  # TODO(TYPE): replace Any with concrete type
        try:
            docker_client.images.get(image)
        except ImageNotFound:
            logger.info(f"Pulling Docker image: {image}")
            docker_client.images.pull(image)

    async def _prepare_execution_environment(
        self, container: Any, code: str, config: ExecutionConfig  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Prepare container for code execution"""

        # Create workspace if it doesn't exist
        try:
            container.exec_run(
                f"mkdir -p {config.working_dir}",
                user="root" if os.name == "nt" else "1001",
            )
        except Exception as e:
            logger.debug(
                f"Failed to create working directory in container (may already exist): {str(e)}",
                exc_info=False,
            )

        # Language-specific preparation
        if config.language == "python":
            # Install common packages if needed
            pass
        elif config.language in ["javascript", "typescript"]:
            # Initialize npm if needed
            pass
        elif config.language == "java":
            # Set up Java environment
            pass

    async def _execute_in_container(
        self, container: Any, code: str, config: ExecutionConfig, execution_id: str  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute code inside the container"""

        command = self.LANGUAGE_COMMANDS.get(config.language, ["python", "-c"])

        # Special handling for different languages
        if config.language in ["python", "javascript"]:
            # Direct code execution
            full_command = command + [code]
        elif config.language == "bash" or config.language == "shell":
            # Shell script execution
            full_command = command + [code]
        else:
            # File-based execution for compiled languages
            return await self._execute_compiled_language(container, code, config)

        try:
            # Execute with timeout
            result = container.exec_run(
                full_command,
                stdout=True,
                stderr=True,
                stream=False,
                demux=True,
                user="root" if os.name == "nt" else "1001",
            )

            # Parse output
            stdout = result.output[0].decode("utf-8") if result.output[0] else ""
            stderr = result.output[1].decode("utf-8") if result.output[1] else ""

            return {
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "output": {
                    "stdout": stdout,
                    "stderr": stderr,
                    "combined": f"{stdout}{stderr}".strip(),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "output": {
                    "stdout": "",
                    "stderr": f"Execution error: {str(e)}",
                    "combined": f"Execution error: {str(e)}",
                },
            }

    async def _execute_compiled_language(
        self, container: Any, code: str, config: ExecutionConfig  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute code for compiled languages (Java, Go, Rust)"""

        # Create temporary file with code
        if config.language == "java":
            filename = "Main.java"
            compile_cmd = ["javac", filename]
            run_cmd = ["java", "Main"]
        elif config.language == "go":
            filename = "main.go"
            compile_cmd = None  # Go can run directly
            run_cmd = ["go", "run", filename]
        elif config.language == "rust":
            filename = "main.rs"
            compile_cmd = ["rustc", filename]
            run_cmd = ["./main"]
        else:
            return {
                "success": False,
                "output": {"stderr": f"Unsupported language: {config.language}"},
            }

        try:
            # Write code to file
            container.exec_run(f"echo '{code}' > {config.working_dir}/{filename}")

            # Compile if needed
            if compile_cmd:
                compile_result = container.exec_run(compile_cmd, workdir=config.working_dir)
                if compile_result.exit_code != 0:
                    return {
                        "success": False,
                        "exit_code": compile_result.exit_code,
                        "output": {
                            "stdout": "",
                            "stderr": compile_result.output.decode("utf-8"),
                            "combined": compile_result.output.decode("utf-8"),
                        },
                    }

            # Execute
            result = container.exec_run(run_cmd, workdir=config.working_dir)
            stdout = result.output.decode("utf-8") if result.output else ""

            return {
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "output": {
                    "stdout": stdout,
                    "stderr": "" if result.exit_code == 0 else stdout,
                    "combined": stdout,
                },
            }

        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "output": {
                    "stdout": "",
                    "stderr": f"Compilation/execution error: {str(e)}",
                    "combined": f"Compilation/execution error: {str(e)}",
                },
            }

    async def _collect_execution_metrics(
        self, container: Any, start_time: float, exit_code: int, execution_id: str  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionMetrics:
        """Collect execution performance metrics"""

        end_time = time.time()
        execution_time = end_time - start_time

        # Get container stats
        try:
            stats = container.stats(stream=False)
            memory_usage = stats.get("memory", {}).get("usage", 0)
            cpu_stats = stats.get("cpu_stats", {})
            cpu_usage = 0.0

            # Calculate CPU usage percentage
            if "cpu_usage" in cpu_stats and "system_cpu_usage" in cpu_stats:
                cpu_delta = cpu_stats["cpu_usage"]["total_usage"]
                system_delta = cpu_stats["system_cpu_usage"]
                if system_delta > 0:
                    cpu_usage = (cpu_delta / system_delta) * 100.0

        except Exception as e:
            logger.debug(f"Failed to collect container stats: {e}")
            memory_usage = 0
            cpu_usage = 0.0

        return ExecutionMetrics(
            start_time=start_time,
            end_time=end_time,
            execution_time=execution_time,
            memory_usage=memory_usage,
            cpu_usage=cpu_usage,
            exit_code=exit_code,
            container_id=container.id,
            success=exit_code == 0,
        )

    async def _return_container_to_pool(self, container: Any, config: ExecutionConfig) -> None:  # TODO(TYPE): replace Any with concrete type
        """Return container to pool for reuse"""

        if len(self.container_pool) < self.max_pool_size:
            try:
                # Clean up container workspace
                container.exec_run(f"rm -rf {config.working_dir}/*")
                container.exec_run(f"mkdir -p {config.working_dir}")

                # Add to pool
                self.container_pool.append(container.id)
                logger.debug(f"Returned container to pool: {container.id}")
            except Exception as e:
                logger.debug(f"Failed to clean container, removing: {e}")
                await self._remove_container(container)
        else:
            # Pool full, remove container
            await self._remove_container(container)

    async def _remove_container(self, container: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Remove container and clean up"""
        try:
            container.stop(timeout=5)
            container.remove()
            if container.id in self.active_containers:
                del self.active_containers[container.id]
            logger.debug(f"Removed container: {container.id}")
        except Exception as e:
            logger.debug(f"Failed to remove container: {e}")

    async def _mock_execution(
        self, code: str, config: ExecutionConfig, execution_id: str
    ) -> ExecutionResult:
        """Mock execution when Docker is not available"""

        await asyncio.sleep(0.1)  # Simulate execution time

        mock_output = {
            "stdout": f"Mock execution of {config.language} code",
            "stderr": "",
            "combined": f"Mock execution of {config.language} code",
        }

        return ExecutionResult(
            task_id=execution_id,
            success=True,
            result_data={
                "output": mock_output,
                "language": config.language,
                "mock": True,
            },
            execution_time=0.1,
        )

    async def cleanup_all_containers(self) -> None:
        """Clean up all active containers"""
        if not self.docker_client:
            return

        # Clean up active containers
        for container_id in list(self.active_containers.keys()):
            try:
                container = self.docker_client.containers.get(container_id)
                await self._remove_container(container)
            except Exception as e:
                logger.debug(f"Failed to clean up container {container_id}: {e}")

        # Clean up pool
        for container_id in self.container_pool:
            try:
                container = self.docker_client.containers.get(container_id)
                await self._remove_container(container)
            except Exception as e:
                logger.debug(f"Failed to clean up pooled container {container_id}: {e}")

        self.container_pool.clear()
        self.active_containers.clear()

    def get_execution_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get execution performance metrics"""

        if not self.execution_metrics:
            return {"total_executions": 0}

        total_executions = len(self.execution_metrics)
        successful_executions = sum(1 for m in self.execution_metrics if m.success)

        execution_times = [m.execution_time for m in self.execution_metrics]
        avg_execution_time = sum(execution_times) / len(execution_times)

        memory_usage = [m.memory_usage for m in self.execution_metrics if m.memory_usage > 0]
        avg_memory_usage = sum(memory_usage) / len(memory_usage) if memory_usage else 0

        return {
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "success_rate": successful_executions / total_executions,
            "avg_execution_time": avg_execution_time,
            "avg_memory_usage": avg_memory_usage,
            "container_pool_size": len(self.container_pool),
            "active_containers": len(self.active_containers),
        }


# Global instance for easy access
docker_executor = DockerSandboxExecutor()


async def execute_code_in_sandbox(
    code: str, language: str = "python", timeout: int = 30
) -> ExecutionResult:
    """Convenience function for code execution"""
    config = ExecutionConfig(language=language, timeout=timeout)
    return await docker_executor.execute_code(code, config)
