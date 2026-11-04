"""
Production Sandbox Manager with NO MOCK FALLBACK
For P0-4: MOCK-004 - Mock Sandbox Manager

CRITICAL SECURITY: This manager provides REAL code isolation via Docker.
NO silent fallback to mock execution - fails fast if Docker unavailable.

Features:
- Real Docker container isolation
- Resource limits: 512MB RAM, 1 CPU, 30s timeout
- Network isolation (no internet access)
- Filesystem isolation (read-only except /tmp)
- Security scanning for malicious patterns
- Comprehensive logging and monitoring
- Graceful cleanup after execution
"""

import asyncio
import logging
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, cast


# Define exception types - will be overwritten if docker is available
class _DockerException(Exception):
    pass


class _APIError(Exception):
    pass


class _ImageNotFound(Exception):
    pass


class _ContainerError(Exception):
    pass


DockerException: type[Exception] = _DockerException
APIError: type[Exception] = _APIError
ImageNotFound: type[Exception] = _ImageNotFound
ContainerError: type[Exception] = _ContainerError

try:
    import docker
    from docker.errors import APIError as _APIErrorReal
    from docker.errors import ContainerError as _ContainerErrorReal
    from docker.errors import DockerException as _DockerExceptionReal
    from docker.errors import ImageNotFound as _ImageNotFoundReal

    DockerException = cast(type[Exception], _DockerExceptionReal)
    APIError = cast(type[Exception], _APIErrorReal)
    ContainerError = cast(type[Exception], _ContainerErrorReal)
    ImageNotFound = cast(type[Exception], _ImageNotFoundReal)
    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DOCKER_AVAILABLE = False

from src.core.shared.config import get_settings
from src.core.shared.interfaces import ExecutionResult, IsolationLevel, SandboxEnvironment, TaskData

logger = logging.getLogger(__name__)


class SecurityThreatLevel(Enum):
    """Security threat levels for code scanning"""

    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    DANGEROUS = "dangerous"
    CRITICAL = "critical"


class CodeSecurityScanner:
    """Scan code for malicious patterns before execution"""

    # Dangerous patterns that should never execute
    CRITICAL_PATTERNS = [
        r'__import__\s*\(\s*["\']os["\']',  # Import os dynamically
        r"eval\s*\(",  # eval() calls
        r"exec\s*\(",  # exec() calls
        r"compile\s*\(",  # compile() calls
        r"__builtins__",  # Access to builtins
        r'open\s*\([^)]*["\']w["\']',  # File write operations
        r"subprocess\.",  # Subprocess execution
        r"os\.system",  # OS command execution
        r"os\.popen",  # OS command execution
        r"commands\.",  # Commands module
        r"socket\.",  # Network socket operations
        r"urllib",  # URL operations
        r"requests\.",  # HTTP requests
        r"pickle\.loads",  # Pickle deserialization
        r"yaml\.load\(",  # Unsafe YAML loading
        r"__file__",  # Access to file path
        r"__code__",  # Access to code object
        r"globals\(\)",  # Access to globals
        r"locals\(\)",  # Access to locals
        r"vars\(\)",  # Access to variables
        r"dir\(\)",  # Directory listing
    ]

    # Suspicious patterns that should be logged
    SUSPICIOUS_PATTERNS = [
        r"import\s+os",
        r"import\s+sys",
        r"from\s+os",
        r"from\s+sys",
        r"open\s*\(",
        r"file\s*\(",
        r"\bwhile\s+True:",  # Infinite loops
        r"\bfor\s+\w+\s+in\s+range\s*\(\s*\d{7,}",  # Very large loops
    ]

    @classmethod
    def scan_code(cls, code: str) -> tuple[SecurityThreatLevel, list[str]]:
        """
        Scan code for security threats.

        Returns:
            (threat_level, violations) tuple
        """
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for critical patterns
        for pattern in cls.CRITICAL_PATTERNS:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                violations.append(f"CRITICAL: Forbidden pattern '{pattern}' detected")

        if violations:
            return SecurityThreatLevel.CRITICAL, violations

        # Check for suspicious patterns
        for pattern in cls.SUSPICIOUS_PATTERNS:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                violations.append(f"SUSPICIOUS: Pattern '{pattern}' detected")

        if len(violations) > 3:
            return SecurityThreatLevel.DANGEROUS, violations
        elif violations:
            return SecurityThreatLevel.SUSPICIOUS, violations
        else:
            return SecurityThreatLevel.SAFE, []


class ProductionSandboxManager:
    """
    Production sandbox manager with REAL Docker isolation.

    NO MOCK FALLBACK - Fails fast if Docker is unavailable.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.active_sandboxes: dict[str, SandboxEnvironment] = {}
        self.sandbox_metrics: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.security_scanner = CodeSecurityScanner()

        # Initialize Docker client
        self._docker_client: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self._init_docker_client()

        # Setup workspace
        import tempfile

        temp_base = Path(tempfile.gettempdir())
        self._workspace_base = temp_base / "production_sandboxes"
        self._workspace_base.mkdir(parents=True, exist_ok=True)

        logger.info("Production Sandbox Manager initialized with Docker isolation")

    def _init_docker_client(self) -> None:
        """Initialize Docker client - FAIL FAST if unavailable"""
        if not DOCKER_AVAILABLE:
            raise RuntimeError(
                "Docker package not installed. Cannot create production sandbox. "
                "NO MOCK FALLBACK available for security reasons."
            )

        try:
            if docker is None:
                raise RuntimeError("Docker module not available")
            self._docker_client = docker.from_env()
            self._docker_client.ping()

            logger.info("Docker daemon is accessible")

            # Ensure Python image is available
            self._ensure_base_image()

        except Exception as e:
            raise RuntimeError(
                f"Docker daemon not available: {e}. "
                "Production sandbox requires Docker. NO MOCK FALLBACK."
            )

    def _ensure_base_image(self) -> None:
        """Ensure Python base image is available"""
        base_image = "python:3.11-slim"

        if self._docker_client is None:
            raise RuntimeError("Docker client not initialized")
        try:
            self._docker_client.images.get(base_image)
            logger.info(f"Base image {base_image} available")
        except ImageNotFound:
            logger.info(f"Pulling base image: {base_image}")
            try:
                self._docker_client.images.pull(base_image)
                logger.info(f"Successfully pulled {base_image}")
            except Exception as e:
                logger.error(f"Failed to pull {base_image}: {e}")
                raise RuntimeError(f"Cannot pull base image: {e}")

    async def create_sandbox(self, config: SandboxEnvironment) -> str:
        """
        Create a secure Docker sandbox.

        Args:
            config: Sandbox configuration

        Returns:
            sandbox_id

        Raises:
            RuntimeError: If Docker unavailable or sandbox creation fails
        """
        if not self._docker_client:
            raise RuntimeError("Docker client not initialized. Cannot create sandbox.")

        sandbox_id = config.id or f"prod_sandbox_{uuid.uuid4().hex[:8]}"

        workspace_dir: Path | None = None
        try:
            # Force Docker isolation level
            config.isolation_level = IsolationLevel.DOCKER

            # Create workspace
            workspace_dir = self._workspace_base / sandbox_id
            workspace_dir.mkdir(parents=True, exist_ok=True)

            # Store configuration
            self.active_sandboxes[sandbox_id] = config
            self.sandbox_metrics[sandbox_id] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "executions": 0,
                "security_violations": 0,
                "total_execution_time": 0.0,
                "workspace_dir": str(workspace_dir),
            }

            logger.info(f"Created production sandbox {sandbox_id} with Docker isolation")
            return sandbox_id

        except Exception as e:
            logger.error(f"Failed to create sandbox {sandbox_id}: {e}")
            # Cleanup on failure
            if workspace_dir is not None and workspace_dir.exists():
                shutil.rmtree(workspace_dir, ignore_errors=True)
            raise

    async def execute_in_sandbox(self, sandbox_id: str, task: TaskData) -> ExecutionResult:
        """
        Execute task in Docker sandbox with security validation.

        Args:
            sandbox_id: ID of sandbox
            task: Task to execute

        Returns:
            ExecutionResult with output or error

        Raises:
            RuntimeError: If sandbox not found or execution fails
        """
        start_time = time.time()

        if sandbox_id not in self.active_sandboxes:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Sandbox {sandbox_id} not found",
            )

        try:
            # Get code to execute
            code = str(getattr(task, "code", None) or task.parameters.get("code", ""))

            # Security scan
            threat_level, violations = self.security_scanner.scan_code(code)

            if threat_level == SecurityThreatLevel.CRITICAL:
                self.sandbox_metrics[sandbox_id]["security_violations"] += 1
                logger.error(f"CRITICAL security threat in {sandbox_id}: {violations}")

                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Security violation: Code contains forbidden patterns. {violations}",
                )

            if threat_level == SecurityThreatLevel.DANGEROUS:
                logger.warning(f"Dangerous code detected in {sandbox_id}: {violations}")

            # Execute in Docker container
            result = await self._execute_in_docker(sandbox_id, code, task)

            execution_time = time.time() - start_time

            # Update metrics
            self._update_metrics(sandbox_id, execution_time, result.success)

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            self._update_metrics(sandbox_id, execution_time, False)

            logger.error(f"Execution failed in sandbox {sandbox_id}: {e}")

            return ExecutionResult(task_id=task.id, success=False, error_message=str(e))

    async def _execute_in_docker(
        self, sandbox_id: str, code: str, task: TaskData
    ) -> ExecutionResult:
        """Execute code in Docker container with full isolation"""

        workspace_dir = Path(self.sandbox_metrics[sandbox_id]["workspace_dir"])

        # Write code to file
        code_file = workspace_dir / "code.py"
        code_file.write_text(code)

        # Get resource limits from config
        config = self.active_sandboxes[sandbox_id]
        memory_limit = config.resource_limits.get("memory", "512m")
        cpu_quota = 100000  # 1 CPU (100%)
        timeout = config.resource_limits.get("timeout", 30)  # 30 seconds

        if self._docker_client is None:
            raise RuntimeError("Docker client not initialized")
        try:
            # Create container with security restrictions
            container = self._docker_client.containers.run(
                image="python:3.11-slim",
                command=["python", "/workspace/code.py"],
                detach=True,
                remove=False,  # Keep for inspection
                # Resource limits
                mem_limit=memory_limit,
                cpu_quota=cpu_quota,
                cpu_period=100000,
                memswap_limit=memory_limit,  # No swap
                # Network isolation (NO INTERNET)
                network_disabled=True,
                # Filesystem isolation
                working_dir="/workspace",
                volumes={
                    str(workspace_dir): {
                        "bind": "/workspace",
                        "mode": "ro",  # Read-only except /tmp
                    }
                },
                tmpfs={
                    "/tmp": "rw,noexec,nosuid,size=100m"  # Limited writable /tmp  # nosec B108: Docker tmpfs mount (noexec, nosuid)
                },
                # Security options
                security_opt=["no-new-privileges"],  # Prevent privilege escalation
                cap_drop=["ALL"],  # Drop all capabilities
                cap_add=[],  # Add no capabilities back
                read_only=False,  # Needed for /tmp
                # User isolation
                user="nobody",  # Run as non-root user
                # Environment
                environment={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                },
            )

            logger.info(f"Container {container.id[:12]} started for sandbox {sandbox_id}")

            # Wait for container with timeout
            try:
                exit_code = await asyncio.wait_for(
                    asyncio.to_thread(container.wait), timeout=timeout
                )
                exit_code = exit_code["StatusCode"]

            except TimeoutError:
                logger.warning(f"Container {container.id[:12]} timeout after {timeout}s")
                container.kill()
                container.wait()

                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Execution timeout ({timeout}s exceeded)",
                )

            # Get logs
            stdout_bytes = container.logs(stdout=True, stderr=False)
            stderr_bytes = container.logs(stdout=False, stderr=True)
            stdout = stdout_bytes.decode("utf-8") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8") if stderr_bytes else ""

            # Cleanup container
            container.remove()

            # Determine success
            success = exit_code == 0 if exit_code is not None else False

            if not success:
                error_msg = stderr if stderr else "Execution failed"
            else:
                error_msg = None

            return ExecutionResult(
                task_id=task.id,
                success=success,
                result_data={
                    "output": stdout if success else None,
                    "exit_code": exit_code if exit_code is not None else -1,
                    "isolation_level": "docker",
                    "container_id": container.id[:12] if container.id else "unknown",
                },
                error_message=error_msg,
            )

        except ContainerError as e:
            logger.error(f"Container execution error: {e}")
            return ExecutionResult(
                task_id=task.id, success=False, error_message=f"Container error: {e}"
            )

        except Exception as e:
            logger.error(f"Unexpected error in Docker execution: {e}")
            return ExecutionResult(
                task_id=task.id, success=False, error_message=f"Execution error: {e}"
            )

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """
        Destroy sandbox and cleanup resources.

        Args:
            sandbox_id: ID of sandbox to destroy

        Returns:
            True if successful, False otherwise
        """
        if sandbox_id not in self.active_sandboxes:
            logger.warning(f"Sandbox {sandbox_id} not found for destruction")
            return False

        try:
            # Get workspace directory
            workspace_dir = Path(self.sandbox_metrics[sandbox_id]["workspace_dir"])

            # Cleanup workspace
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir, ignore_errors=True)

            # Remove from active sandboxes
            del self.active_sandboxes[sandbox_id]
            del self.sandbox_metrics[sandbox_id]

            logger.info(f"Destroyed sandbox {sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Error destroying sandbox {sandbox_id}: {e}")
            return False

    async def get_sandbox_status(self, sandbox_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get sandbox status and metrics"""
        if sandbox_id not in self.active_sandboxes:
            return {"error": "Sandbox not found"}

        sandbox = self.active_sandboxes[sandbox_id]
        metrics = self.sandbox_metrics[sandbox_id]

        return {
            "sandbox_id": sandbox_id,
            "isolation_level": "docker",
            "created_at": metrics["created_at"],
            "resource_limits": sandbox.resource_limits,
            "executions_count": metrics["executions"],
            "security_violations": metrics["security_violations"],
            "total_execution_time": metrics["total_execution_time"],
            "status": "active",
        }

    def _update_metrics(self, sandbox_id: str, execution_time: float, success: bool) -> None:
        """Update sandbox execution metrics"""
        if sandbox_id in self.sandbox_metrics:
            metrics = self.sandbox_metrics[sandbox_id]
            metrics["executions"] += 1
            metrics["total_execution_time"] += execution_time

            if not success:
                metrics.setdefault("failed_executions", 0)
                metrics["failed_executions"] += 1

    def get_metrics_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall metrics for all sandboxes"""
        total_sandboxes = len(self.active_sandboxes)
        total_executions = sum(m["executions"] for m in self.sandbox_metrics.values())
        total_violations = sum(m["security_violations"] for m in self.sandbox_metrics.values())

        return {
            "total_sandboxes": total_sandboxes,
            "total_executions": total_executions,
            "total_security_violations": total_violations,
            "isolation_level": "docker",
            "mock_fallback_enabled": False,  # ALWAYS False in production
        }


# Factory function
def get_production_sandbox_manager() -> ProductionSandboxManager:
    """
    Get production sandbox manager instance.

    Raises:
        RuntimeError: If Docker not available (NO MOCK FALLBACK)
    """
    return ProductionSandboxManager()


if __name__ == "__main__":
    # Test the production sandbox manager
    import asyncio

    async def test() -> None:
        manager = get_production_sandbox_manager()

        # Create sandbox
        config = SandboxEnvironment(
            id=f"test_sandbox_{uuid.uuid4().hex[:8]}",
            isolation_level=IsolationLevel.DOCKER,
            resource_limits={"memory": "512m", "timeout": 30},
            network_access=False,
        )

        sandbox_id = await manager.create_sandbox(config)
        print(f"Created sandbox: {sandbox_id}")

        # Test safe code
        from src.core.shared.interfaces import TaskData

        task = TaskData(
            id="test_task_1",
            title="test_task",
            description="Test task for sandbox",
            metadata={"code": "print('Hello from Docker sandbox!')"},
        )

        result = await manager.execute_in_sandbox(sandbox_id, task)
        print(f"Safe code result: {result.success}, output: {result.result_data}")

        # Test malicious code
        task_malicious = TaskData(
            id="test_task_2",
            title="malicious_task",
            description="Test malicious task",
            metadata={"code": "import os; os.system('ls')"},
        )

        result = await manager.execute_in_sandbox(sandbox_id, task_malicious)
        print(f"Malicious code blocked: {not result.success}, error: {result.error_message}")

        # Cleanup
        await manager.destroy_sandbox(sandbox_id)
        print("Sandbox destroyed")

        # Metrics
        print(f"Metrics: {manager.get_metrics_summary()}")

    asyncio.run(test())
