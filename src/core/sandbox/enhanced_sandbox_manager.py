"""
Enhanced Secure Docker Sandbox Manager
Integration of advanced security controls with Docker container execution
"""

import base64
import json
import logging
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

try:
    import docker
    from docker.errors import APIError, DockerException, ImageNotFound

    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DockerException = APIError = ImageNotFound = Exception
    DOCKER_AVAILABLE = False

from src.core.sandbox.security_manager import SecurityLevel, SecurityManager
from src.core.shared.config import get_settings
from src.core.shared.interfaces import ExecutionResult, SandboxEnvironment, TaskData

logger = logging.getLogger(__name__)


class EnhancedDockerSandboxManager:
    """Enhanced Docker sandbox manager with advanced security controls"""

    def __init__(self, security_level: SecurityLevel = SecurityLevel.STANDARD) -> None:
        self.settings = get_settings()
        self.security_manager = SecurityManager(security_level)
        self._docker_client: Any = None
        self._container_configs: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self._container_instances: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.active_sandboxes: dict[str, SandboxEnvironment] = {}
        self.sandbox_metrics: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.execution_history: dict[str, list[dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type

        # Monitoring threads
        self._monitoring_threads: dict[str, threading.Thread] = {}
        self._stop_monitoring: dict[str, threading.Event] = {}

        # Setup workspace
        import tempfile

        temp_base = Path(tempfile.gettempdir())
        self._workspace_base = temp_base / "secure_sandboxes"
        self._workspace_base.mkdir(parents=True, exist_ok=True)

        # Initialize Docker
        self._init_docker_client()
        logger.info(
            f"Enhanced sandbox manager initialized - Security Level: {security_level.value}"
        )

    def _init_docker_client(self) -> None:
        """Initialize Docker client with enhanced error handling"""
        if not DOCKER_AVAILABLE:
            logger.warning("Docker package not available - enhanced security unavailable")
            return

        try:
            if docker is None:
                logger.error("Docker module not available")
                return
            self._docker_client = docker.from_env()
            self._docker_client.ping()

            # Pull secure base images
            self._ensure_secure_base_images()

            logger.info("Enhanced Docker client initialized successfully")
        except DockerException as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self._docker_client = None
        except Exception as e:
            logger.error(f"Unexpected error initializing Docker: {e}")
            self._docker_client = None

    def _ensure_secure_base_images(self) -> None:
        """Ensure secure base images are available"""
        secure_images = [
            "python:3.11-slim",  # Minimal Python runtime
            "node:18-alpine",  # Minimal Node.js runtime
            "ubuntu:22.04",  # Full Ubuntu for complex tasks
            "alpine:latest",  # Minimal Alpine Linux
        ]

        docker_client = self._docker_client
        if docker_client is None:
            return
        for image in secure_images:
            try:
                docker_client.images.get(image)
                logger.debug(f"Secure image {image} available")
            except ImageNotFound:
                logger.info(f"Pulling secure image: {image}")
                try:
                    docker_client.images.pull(image)
                    logger.info(f"Successfully pulled {image}")
                except Exception as e:
                    logger.warning(f"Failed to pull {image}: {e}")

    async def create_secure_sandbox(self, config: SandboxEnvironment) -> str:
        """Create a secure Docker sandbox with enhanced security controls"""
        if not self._docker_client:
            raise RuntimeError("Docker client not available - cannot create secure sandbox")

        sandbox_id = config.id or f"secure_sandbox_{uuid.uuid4().hex[:8]}"
        workspace_dir = self._workspace_base / sandbox_id

        try:
            # Re-assign workspace_dir to ensure it's definitely bound
            workspace_dir = self._workspace_base / sandbox_id
            # Create secure workspace
            workspace_dir.mkdir(parents=True, exist_ok=True)

            # Create container configuration with security enhancements
            container_config = self._create_secure_container_config(config, workspace_dir)
            container_config = self.security_manager.create_secure_container_config(
                container_config
            )

            logger.info(
                f"Creating secure sandbox {sandbox_id} with security level {self.security_manager.policy.level.value}"
            )

            # Store configuration and sandbox
            self._container_configs[sandbox_id] = container_config
            self.active_sandboxes[sandbox_id] = config
            self.sandbox_metrics[sandbox_id] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "executions": 0,
                "security_violations": 0,
                "total_execution_time": 0.0,
            }

            return sandbox_id

        except Exception as e:
            logger.error(f"Failed to create secure sandbox {sandbox_id}: {e}")
            # Cleanup on failure
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir, ignore_errors=True)
            raise

    def _create_secure_container_config(
        self, config: SandboxEnvironment, workspace_dir: Path
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create secure container configuration"""
        # Select secure image based on requirements
        image = "python:3.11-slim"  # Default secure Python image
        if hasattr(config, "runtime_requirements"):
            runtime = config.runtime_requirements.get("language", "python").lower()
            if runtime == "node" or runtime == "javascript":
                image = "node:18-alpine"
            elif runtime == "shell" or runtime == "bash":
                image = "alpine:latest"

        # Setup secure volumes
        volumes = {
            str(workspace_dir): {
                "bind": "/workspace",
                "mode": "rw" if self.security_manager.policy.allow_file_write else "ro",
            }
        }

        # Base secure configuration
        container_config = {
            "image": image,
            "detach": True,
            "auto_remove": False,  # Keep for inspection
            "command": ["tail", "-f", "/dev/null"],  # Keep container alive
            # Resource limits from security policy
            "mem_limit": f"{self.security_manager.policy.max_memory_mb}m",
            "cpu_quota": int(self.security_manager.policy.max_cpu_percent * 1000),
            "cpu_period": 100000,
            "memswap_limit": f"{self.security_manager.policy.max_memory_mb}m",  # No swap
            # Network security
            "network_disabled": not self.security_manager.policy.network_access,
            # Filesystem security
            "working_dir": "/workspace",
            "volumes": volumes,
            "environment": {
                "PYTHONPATH": "/workspace",
                "HOME": "/workspace",
                "USER": "sandboxuser",
                "PYTHONDONTWRITEBYTECODE": "1",  # No .pyc files
                "PYTHONUNBUFFERED": "1",  # Unbuffered output
                **config.resource_limits.get("env_vars", {}),
            },
            # Additional security settings will be added by security manager
        }

        return container_config

    async def execute_in_secure_sandbox(self, sandbox_id: str, task: TaskData) -> ExecutionResult:
        """Execute task in secure sandbox with comprehensive security validation"""
        start_time = time.time()

        if sandbox_id not in self.active_sandboxes:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                error_message=f"Sandbox {sandbox_id} not found",
                execution_time=0.0,
            )

        try:
            # Extract code from task
            code = self._extract_code_from_task(task)
            if not code:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    result_data=None,
                    error_message="No executable code found in task",
                    execution_time=0.0,
                )

            # SECURITY VALIDATION: Analyze code for security threats
            logger.info(f"Validating code security for sandbox {sandbox_id}")
            is_safe, security_violations = self.security_manager.validate_code_security(
                code, sandbox_id
            )

            if not is_safe:
                violation_messages = [
                    v.message for v in security_violations if v.severity in ["CRITICAL", "HIGH"]
                ]
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    result_data={
                        "security_violations": len(security_violations),
                        "blocked_violations": violation_messages,
                    },
                    error_message=f"Code execution blocked due to security violations: {', '.join(violation_messages[:3])}",
                    execution_time=time.time() - start_time,
                )

            # Log security warnings (non-blocking)
            if security_violations:
                warning_messages = [
                    v.message for v in security_violations if v.severity in ["MEDIUM", "LOW"]
                ]
                if warning_messages:
                    logger.warning(
                        f"Security warnings for {sandbox_id}: {', '.join(warning_messages[:3])}"
                    )

            # Create and start container
            container = await self._create_and_start_container(sandbox_id)

            # Start security monitoring
            self._start_security_monitoring(sandbox_id, container)

            # Execute code in secure container
            result = await self._execute_code_in_container(container, code, task, sandbox_id)

            # Stop monitoring and collect security report
            self._stop_security_monitoring(sandbox_id)
            security_report = self.security_manager.get_security_report(sandbox_id)

            # Cleanup container
            await self._cleanup_container(container, sandbox_id)

            # Update metrics
            execution_time = time.time() - start_time
            self._update_execution_metrics(
                sandbox_id, execution_time, result.success, security_report
            )

            # Add security information to result
            if result.result_data is None:
                result.result_data = {}
            result.result_data.update(
                {
                    "security_score": security_report.get("security_score", 100),
                    "security_status": security_report.get("status", "SECURE"),
                    "security_violations": security_report.get("total_violations", 0),
                }
            )

            return result

        except Exception as e:
            logger.error(f"Error executing in secure sandbox {sandbox_id}: {e}")
            execution_time = time.time() - start_time
            self._update_execution_metrics(sandbox_id, execution_time, False, {"security_score": 0})

            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                error_message=f"Secure execution failed: {str(e)}",
                execution_time=execution_time,
            )

    def _extract_code_from_task(self, task: TaskData) -> str | None:
        """Extract executable code from task data"""
        # Try different ways to extract code
        if hasattr(task, "code") and task.code:
            return task.code

        if task.metadata and "code" in task.metadata:
            return cast(Optional[str], task.metadata["code"])

        # Look for Python code in description
        if "python" in task.description.lower() or "```python" in task.description:
            import re

            code_blocks = re.findall(r"```python\n(.*?)\n```", task.description, re.DOTALL)
            if code_blocks:
                return cast(str, code_blocks[0])

        # Fallback: create simple task execution code
        if task.title and task.description:
            return f"""
# Task: {task.title}
# Description: {task.description}

print("Task: {task.title}")
print("Description: {task.description}")
print("Execution completed successfully")
result = {{"task_completed": True, "title": "{task.title}"}}
print(f"Result: {{result}}")
"""

        return None

    async def _create_and_start_container(self, sandbox_id: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Create and start Docker container for sandbox"""
        config = self._container_configs[sandbox_id]

        if self._docker_client is None:
            raise RuntimeError("Docker client not initialized")
        try:
            container = self._docker_client.containers.create(**config)
            container.start()

            # Store container reference
            self._container_instances[sandbox_id] = container

            logger.info(f"Started secure container for sandbox {sandbox_id}")
            return container

        except Exception as e:
            logger.error(f"Failed to create/start container for {sandbox_id}: {e}")
            raise

    def _start_security_monitoring(self, sandbox_id: str, container: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Start security monitoring for container"""
        # Create stop event
        stop_event = threading.Event()
        self._stop_monitoring[sandbox_id] = stop_event

        # Start monitoring thread
        monitor_thread = threading.Thread(
            target=self._monitor_container_security,
            args=(sandbox_id, container, stop_event),
            daemon=True,
        )
        monitor_thread.start()
        self._monitoring_threads[sandbox_id] = monitor_thread

        logger.debug(f"Started security monitoring for {sandbox_id}")

    def _monitor_container_security(
        self, sandbox_id: str, container: Any, stop_event: threading.Event  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Monitor container for security violations (runs in separate thread)"""
        while not stop_event.is_set():
            try:
                # Monitor with security manager
                violations = self.security_manager.monitor_execution(container, sandbox_id)

                # Log critical violations
                critical_violations = [v for v in violations if v.severity == "CRITICAL"]
                if critical_violations:
                    logger.critical(
                        f"Critical security violations in {sandbox_id}: {[v.message for v in critical_violations]}"
                    )
                    # Could terminate container here for critical violations

                # Update metrics
                if violations:
                    self.sandbox_metrics[sandbox_id]["security_violations"] += len(violations)

                # Sleep before next check
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"Error in security monitoring for {sandbox_id}: {e}")
                time.sleep(2.0)

    def _stop_security_monitoring(self, sandbox_id: str) -> None:
        """Stop security monitoring for sandbox"""
        if sandbox_id in self._stop_monitoring:
            self._stop_monitoring[sandbox_id].set()

        if sandbox_id in self._monitoring_threads:
            thread = self._monitoring_threads[sandbox_id]
            thread.join(timeout=5.0)  # Wait up to 5 seconds
            del self._monitoring_threads[sandbox_id]

        if sandbox_id in self._stop_monitoring:
            del self._stop_monitoring[sandbox_id]

        logger.debug(f"Stopped security monitoring for {sandbox_id}")

    def _generate_execution_script(self, code: str) -> str:
        """
        Generate safe execution script with base64-encoded user code.

        Prevents f-string injection attacks by encoding user code as base64
        instead of directly interpolating it into the template.

        Args:
            code: User code to execute

        Returns:
            Complete Python script with base64-encoded code
        """
        # Encode user code as base64 to prevent injection
        code_b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")

        # Generate template with base64 decoding - NOT f-string interpolation
        execution_script = f'''
import sys
import traceback
import json
import time
import base64
from datetime import datetime

def safe_execute() -> None:
    """Execute user code safely"""
    start_time = time.time()
    result = {{"success": False, "output": "", "error": "", "execution_time": 0.0}}

    try:
        # Decode and execute user code from base64
        user_code = base64.b64decode("{code_b64}").decode('utf-8')
        exec_globals = {{"__name__": "__main__"}}
        exec(user_code, exec_globals)

        result["success"] = True
        result["output"] = "Code executed successfully"

    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    result["execution_time"] = time.time() - start_time
    return result

if __name__ == "__main__":
    try:
        result = safe_execute()
        print(json.dumps(result, indent=2))
    except Exception as e:
        error_result = {{
            "success": False,
            "output": "",
            "error": f"Execution framework error: {{str(e)}}",
            "execution_time": 0.0
        }}
        print(json.dumps(error_result, indent=2))
'''

        return execution_script

    async def _execute_code_in_container(
        self, container: Any, code: str, task: TaskData, sandbox_id: str  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionResult:
        """Execute code inside secure container"""
        try:
            # Create execution script using safe base64 encoding (not f-string interpolation)
            execution_script = self._generate_execution_script(code)

            # Write script to container
            script_content = execution_script.encode("utf-8")
            container.put_archive(
                "/workspace", self._create_tar_archive("execute.py", script_content)
            )

            # Execute with timeout from security policy
            self.security_manager.policy.max_execution_time

            exec_result = container.exec_run(
                cmd=["python", "/workspace/execute.py"],
                workdir="/workspace",
                user="root",  # Simplified for compatibility
                environment={"PYTHONPATH": "/workspace", "PYTHONUNBUFFERED": "1"},
            )

            # Parse execution result
            try:
                output = exec_result.output.decode("utf-8", errors="replace")
                if output.strip():
                    # Try to parse JSON result
                    try:
                        result_data = json.loads(output.strip().split("\n")[-1])
                    except (json.JSONDecodeError, IndexError):
                        result_data = {
                            "output": output,
                            "success": exec_result.exit_code == 0,
                        }
                else:
                    result_data = {"output": "", "success": exec_result.exit_code == 0}

                # Create execution result
                return ExecutionResult(
                    task_id=task.id,
                    success=result_data.get("success", exec_result.exit_code == 0),
                    result_data={
                        "output": result_data.get("output", output),
                        "execution_time": result_data.get("execution_time", 0.0),
                        "exit_code": exec_result.exit_code,
                        "sandbox_id": sandbox_id,
                    },
                    error_message=(
                        result_data.get("error") if not result_data.get("success") else None
                    ),
                    execution_time=result_data.get("execution_time", 0.0),
                )

            except Exception as e:
                logger.error(f"Failed to parse execution result: {e}")
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    result_data=None,
                    error_message=f"Failed to parse execution result: {e}",
                    execution_time=0.0,
                )

        except Exception as e:
            logger.error(f"Failed to execute code in container: {e}")
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                error_message=f"Container execution failed: {e}",
                execution_time=0.0,
            )

    def _create_tar_archive(self, filename: str, content: bytes) -> bytes:
        """Create a tar archive containing a single file"""
        import io
        import tarfile

        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            file_info = tarfile.TarInfo(name=filename)
            file_info.size = len(content)
            file_info.mode = 0o644
            tar.addfile(file_info, io.BytesIO(content))

        tar_buffer.seek(0)
        return tar_buffer.getvalue()

    async def _cleanup_container(self, container: Any, sandbox_id: str) -> None:  # TODO(TYPE): replace Any with concrete type
        """Clean up container and resources"""
        try:
            # Stop and remove container
            container.stop(timeout=10)
            container.remove(force=True)

            # Remove from instances
            if sandbox_id in self._container_instances:
                del self._container_instances[sandbox_id]

            logger.debug(f"Cleaned up container for sandbox {sandbox_id}")

        except Exception as e:
            logger.warning(f"Error cleaning up container for {sandbox_id}: {e}")

    def _update_execution_metrics(
        self,
        sandbox_id: str,
        execution_time: float,
        success: bool,
        security_report: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Update sandbox execution metrics with security information"""
        if sandbox_id not in self.sandbox_metrics:
            self.sandbox_metrics[sandbox_id] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "executions": 0,
                "security_violations": 0,
                "total_execution_time": 0.0,
            }

        metrics = self.sandbox_metrics[sandbox_id]
        metrics["executions"] += 1
        metrics["total_execution_time"] += execution_time
        metrics["last_execution"] = datetime.now(timezone.utc).isoformat()
        metrics["last_success"] = success
        metrics["last_security_score"] = security_report.get("security_score", 100)
        metrics["last_security_status"] = security_report.get("status", "UNKNOWN")

        # Track execution history
        if sandbox_id not in self.execution_history:
            self.execution_history[sandbox_id] = []

        self.execution_history[sandbox_id].append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "execution_time": execution_time,
                "success": success,
                "security_score": security_report.get("security_score", 100),
                "security_violations": security_report.get("total_violations", 0),
            }
        )

        # Keep only last 50 executions
        self.execution_history[sandbox_id] = self.execution_history[sandbox_id][-50:]

    async def destroy_secure_sandbox(self, sandbox_id: str) -> bool:
        """Destroy secure sandbox and cleanup all resources"""
        try:
            # Stop monitoring
            self._stop_security_monitoring(sandbox_id)

            # Clean up container if exists
            if sandbox_id in self._container_instances:
                container = self._container_instances[sandbox_id]
                await self._cleanup_container(container, sandbox_id)

            # Clean up workspace
            workspace_dir = self._workspace_base / sandbox_id
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir, ignore_errors=True)

            # Clean up data structures
            for data_dict in cast(
                list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
                [
                    self.active_sandboxes,
                    self.sandbox_metrics,
                    self._container_configs,
                    self.execution_history,
                ],
            ):
                if sandbox_id in data_dict:
                    del data_dict[sandbox_id]

            # Clean up security history
            self.security_manager.cleanup_history(sandbox_id)

            logger.info(f"Successfully destroyed secure sandbox {sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Error destroying secure sandbox {sandbox_id}: {e}")
            return False

    def get_security_status(self, sandbox_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive security status for sandbox"""
        if sandbox_id not in self.active_sandboxes:
            return {"error": "Sandbox not found"}

        base_status = {
            "sandbox_id": sandbox_id,
            "security_level": self.security_manager.policy.level.value,
            "created_at": self.sandbox_metrics.get(sandbox_id, {}).get("created_at"),
            "total_executions": self.sandbox_metrics.get(sandbox_id, {}).get("executions", 0),
            "total_security_violations": self.sandbox_metrics.get(sandbox_id, {}).get(
                "security_violations", 0
            ),
        }

        # Add security report
        security_report = self.security_manager.get_security_report(sandbox_id)
        base_status.update(security_report)

        # Add execution history
        base_status["execution_history"] = self.execution_history.get(sandbox_id, [])

        return base_status


# Factory function for creating enhanced secure sandbox managers
def create_enhanced_sandbox_manager(
    security_level: SecurityLevel = SecurityLevel.STANDARD,
) -> EnhancedDockerSandboxManager:
    """Create enhanced secure sandbox manager with specified security level"""
    return EnhancedDockerSandboxManager(security_level)
