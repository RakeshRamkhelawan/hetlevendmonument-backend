"""
Sandbox Performance Optimizer
Advanced performance optimization for Docker sandbox execution with caching, pooling, and monitoring
"""

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DOCKER_AVAILABLE = False

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil: Any = None  # type: ignore[no-redef]
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


class OptimizationLevel(Enum):
    """Performance optimization levels"""

    BASIC = "basic"  # Basic optimizations
    STANDARD = "standard"  # Standard performance optimizations
    AGGRESSIVE = "aggressive"  # Maximum performance optimizations


@dataclass
class PerformanceMetrics:
    """Performance metrics for sandbox operations"""

    container_creation_time: float = 0.0
    container_start_time: float = 0.0
    code_execution_time: float = 0.0
    container_cleanup_time: float = 0.0
    total_execution_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    disk_io_mb: float = 0.0
    network_io_mb: float = 0.0
    cache_hit_rate: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ContainerPool:
    """Container pool for reusing containers"""

    image: str
    containers: deque[Any] = field(default_factory=deque)  # TODO(TYPE): replace Any with concrete type
    max_size: int = 5
    min_size: int = 1
    created_count: int = 0
    reused_count: int = 0
    last_cleanup: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ImageCache:
    """Docker image caching and pre-warming system"""

    def __init__(self, docker_client: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self.docker_client = docker_client
        self.cached_images: set[str] = set()
        self.image_pull_times: dict[str, float] = {}
        self.prewarmed_images: set[str] = set()

    async def ensure_image(self, image: str) -> bool:
        """Ensure image is available, pull if necessary"""
        if image in self.cached_images:
            return True

        try:
            start_time = time.time()

            # Check if image exists locally
            try:
                self.docker_client.images.get(image)
                logger.debug(f"Image {image} found locally")
            except Exception:
                logger.info(f"Pulling image {image}...")
                self.docker_client.images.pull(image)
                logger.info(f"Successfully pulled {image}")

            pull_time = time.time() - start_time
            self.image_pull_times[image] = pull_time
            self.cached_images.add(image)

            return True

        except Exception as e:
            logger.error(f"Failed to ensure image {image}: {e}")
            return False

    async def prewarm_images(self, images: list[str]) -> None:
        """Pre-warm commonly used images"""
        logger.info(f"Pre-warming {len(images)} images...")

        for image in images:
            if await self.ensure_image(image):
                self.prewarmed_images.add(image)
                logger.debug(f"Pre-warmed image: {image}")

    def get_cache_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get image cache statistics"""
        return {
            "cached_images": len(self.cached_images),
            "prewarmed_images": len(self.prewarmed_images),
            "total_pull_time": sum(self.image_pull_times.values()),
            "average_pull_time": (
                sum(self.image_pull_times.values()) / len(self.image_pull_times)
                if self.image_pull_times
                else 0
            ),
            "image_pull_times": self.image_pull_times,
        }


class ContainerPoolManager:
    """Manages pools of containers for different images"""

    def __init__(
        self,
        docker_client: Any,  # TODO(TYPE): replace Any with concrete type
        optimization_level: OptimizationLevel = OptimizationLevel.STANDARD,
    ) -> None:
        self.docker_client = docker_client
        self.optimization_level = optimization_level
        self.pools: dict[str, ContainerPool] = {}
        self.active_containers: dict[str, Any] = {}  # container_id -> container  # TODO(TYPE): replace Any with concrete type
        self.container_metrics: dict[str, PerformanceMetrics] = {}
        self._cleanup_thread: threading.Thread | None = None
        self._stop_cleanup = threading.Event()

        # Pool configuration based on optimization level
        if optimization_level == OptimizationLevel.BASIC:
            self.default_pool_size = 2
            self.max_pool_size = 3
        elif optimization_level == OptimizationLevel.STANDARD:
            self.default_pool_size = 3
            self.max_pool_size = 5
        else:  # AGGRESSIVE
            self.default_pool_size = 5
            self.max_pool_size = 10

        self._start_cleanup_thread()

    def _start_cleanup_thread(self) -> None:
        """Start background cleanup thread"""
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        logger.info("Container pool cleanup thread started")

    def _cleanup_worker(self) -> None:
        """Background worker for pool cleanup"""
        while not self._stop_cleanup.is_set():
            try:
                self._cleanup_expired_containers()
                time.sleep(30)  # Cleanup every 30 seconds
            except Exception as e:
                logger.error(f"Error in pool cleanup worker: {e}")
                time.sleep(60)

    def _cleanup_expired_containers(self) -> None:
        """Clean up expired containers from pools"""
        current_time = datetime.now(timezone.utc)

        for image, pool in self.pools.items():
            # Remove expired containers (older than 10 minutes)
            expired_containers: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for container in list(pool.containers):
                try:
                    # Check if container is still running
                    container.reload()
                    if container.status != "running":
                        expired_containers.append(container)
                    elif (current_time - pool.last_cleanup).total_seconds() > 600:  # 10 minutes
                        expired_containers.append(container)
                except Exception:
                    expired_containers.append(container)

            for container in expired_containers:
                try:
                    pool.containers.remove(container)
                    container.stop(timeout=5)
                    container.remove(force=True)
                    logger.debug(f"Cleaned up expired container from {image} pool")
                except Exception as e:
                    logger.warning(f"Error cleaning up container: {e}")

            pool.last_cleanup = current_time

    async def get_container(self, image: str, config: dict[str, Any]) -> tuple[Any, bool]:  # TODO(TYPE): replace Any with concrete type
        """Get container from pool or create new one"""
        start_time = time.time()

        # Get or create pool
        if image not in self.pools:
            self.pools[image] = ContainerPool(image=image, max_size=self.max_pool_size, min_size=1)

        pool = self.pools[image]

        # Try to get container from pool
        while pool.containers:
            container = pool.containers.popleft()
            try:
                # Check if container is still healthy
                container.reload()
                if container.status == "running":
                    pool.reused_count += 1
                    creation_time = time.time() - start_time
                    logger.debug(f"Reused container from {image} pool (took {creation_time:.3f}s)")
                    return container, True  # True = reused
            except Exception as e:
                logger.debug(f"Container in pool is unhealthy, removing: {e}")
                try:
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception:
                    pass

        # Create new container if pool is empty
        try:
            container = self.docker_client.containers.create(**config)
            container.start()

            pool.created_count += 1
            creation_time = time.time() - start_time

            logger.debug(f"Created new container for {image} (took {creation_time:.3f}s)")
            return container, False  # False = newly created

        except Exception as e:
            logger.error(f"Failed to create container for {image}: {e}")
            raise

    async def return_container(self, image: str, container: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Return container to pool for reuse"""
        if image not in self.pools:
            # Container was created outside of pool system
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except Exception as e:
                logger.warning(f"Error cleaning up non-pooled container: {e}")
            return

        pool = self.pools[image]

        try:
            # Check if container is still healthy
            container.reload()

            if container.status == "running" and len(pool.containers) < pool.max_size:
                # Reset container environment by executing cleanup
                try:
                    container.exec_run(
                        cmd=["sh", "-c", "rm -rf /workspace/* 2>/dev/null || true"],
                        workdir="/workspace",
                    )
                except Exception as e:
                    logger.debug(f"Error cleaning container workspace: {e}")

                pool.containers.append(container)
                logger.debug(f"Returned container to {image} pool")
            else:
                # Pool is full or container is unhealthy
                container.stop(timeout=5)
                container.remove(force=True)
                logger.debug("Container discarded (pool full or unhealthy)")

        except Exception as e:
            logger.warning(f"Error returning container to pool: {e}")
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except Exception:
                pass

    def get_pool_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get container pool statistics"""
        stats: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for image, pool in self.pools.items():
            stats[image] = {
                "pool_size": len(pool.containers),
                "max_size": pool.max_size,
                "created_count": pool.created_count,
                "reused_count": pool.reused_count,
                "reuse_rate": pool.reused_count
                / max(pool.created_count + pool.reused_count, 1)
                * 100,
                "last_cleanup": pool.last_cleanup.isoformat(),
            }

        return stats

    def stop(self) -> None:
        """Stop pool manager and cleanup"""
        self._stop_cleanup.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=10)

        # Clean up all pools
        for image, pool in self.pools.items():
            for container in list(pool.containers):
                try:
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(f"Error cleaning up container in {image} pool: {e}")


class CodeCache:
    """Cache for compiled/preprocessed code"""

    def __init__(self, max_size: int = 1000) -> None:
        self.cache: dict[str, tuple[str, datetime]] = {}
        self.max_size = max_size
        self.hit_count = 0
        self.miss_count = 0

    def _hash_code(self, code: str) -> str:
        """Generate hash for code"""
        import hashlib

        return hashlib.sha256(code.encode()).hexdigest()

    def get(self, code: str) -> str | None:
        """Get preprocessed code from cache"""
        code_hash = self._hash_code(code)

        if code_hash in self.cache:
            cached_code, timestamp = self.cache[code_hash]

            # Check if cache entry is still valid (1 hour)
            if (datetime.now(timezone.utc) - timestamp).total_seconds() < 3600:
                self.hit_count += 1
                return cached_code
            else:
                del self.cache[code_hash]

        self.miss_count += 1
        return None

    def set(self, original_code: str, processed_code: str) -> None:
        """Store processed code in cache"""
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_hash = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_hash]

        code_hash = self._hash_code(original_code)
        self.cache[code_hash] = (processed_code, datetime.now(timezone.utc))

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cache statistics"""
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0

        return {
            "cache_size": len(self.cache),
            "max_size": self.max_size,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": hit_rate,
        }


class PerformanceOptimizer:
    """Main performance optimizer for sandbox operations"""

    def __init__(
        self,
        docker_client: Any,  # TODO(TYPE): replace Any with concrete type
        optimization_level: OptimizationLevel = OptimizationLevel.STANDARD,
    ) -> None:
        self.docker_client = docker_client
        self.optimization_level = optimization_level
        self.image_cache = ImageCache(docker_client)
        self.container_pool = ContainerPoolManager(docker_client, optimization_level)
        self.code_cache = CodeCache(
            max_size=500 if optimization_level == OptimizationLevel.AGGRESSIVE else 200
        )

        # Performance tracking
        self.execution_metrics: deque[Any] = deque(maxlen=1000)  # TODO(TYPE): replace Any with concrete type
        self.system_metrics: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        # Pre-warm common images
        self._prewarm_common_images()

    def _prewarm_common_images(self) -> None:
        """Pre-warm commonly used Docker images"""
        common_images = [
            "python:3.11-slim",
            "node:18-alpine",
            "golang:1.21-alpine",
            "rust:1.70-slim",
        ]

        if self.optimization_level in [
            OptimizationLevel.STANDARD,
            OptimizationLevel.AGGRESSIVE,
        ]:
            # Pre-warm in background
            asyncio.create_task(self.image_cache.prewarm_images(common_images))

    async def optimize_container_creation(
        self, image: str, config: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[Any, PerformanceMetrics]:  # TODO(TYPE): replace Any with concrete type
        """Optimize container creation with pooling and caching"""
        metrics = PerformanceMetrics()
        start_time = time.time()

        # Ensure image is available
        await self.image_cache.ensure_image(image)

        # Get container from pool
        container_start = time.time()
        container, reused = await self.container_pool.get_container(image, config)
        metrics.container_creation_time = time.time() - container_start

        if not reused:
            # Start container if newly created
            start_start = time.time()
            if container.status != "running":
                container.start()
            metrics.container_start_time = time.time() - start_start

        # Update cache hit rate
        if reused:
            metrics.cache_hit_rate = 1.0

        metrics.total_execution_time = time.time() - start_time
        return container, metrics

    def preprocess_code(self, code: str, language: str = "python") -> str:
        """Preprocess and optimize code for execution"""
        # Check cache first
        cached_code = self.code_cache.get(code)
        if cached_code:
            return cached_code

        processed_code = code

        # Language-specific optimizations
        if language == "python":
            processed_code = self._optimize_python_code(code)
        elif language == "javascript":
            processed_code = self._optimize_javascript_code(code)

        # Cache the processed code
        self.code_cache.set(code, processed_code)

        return processed_code

    def _optimize_python_code(self, code: str) -> str:
        """Optimize Python code for better performance"""
        optimizations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Add performance imports if not present
        if "import time" not in code and "time." in code:
            optimizations.append("import time")

        if "import sys" not in code and "sys." in code:
            optimizations.append("import sys")

        # Add optimization header
        if optimizations:
            header = "\n".join(optimizations) + "\n\n"
            code = header + code

        # Add performance monitoring
        if self.optimization_level == OptimizationLevel.AGGRESSIVE:
            code = """
import time
_start_time = time.time()

{code}

_end_time = time.time()
print("Execution completed in {{_end_time - _start_time:.4f}} seconds")
"""

        return code

    def _optimize_javascript_code(self, code: str) -> str:
        """Optimize JavaScript code for better performance"""
        if self.optimization_level == OptimizationLevel.AGGRESSIVE:
            code = """
const _startTime = performance.now();

{code}

const _endTime = performance.now();
// Execution completed in ${(_endTime - _startTime)/1000} seconds
"""

        return code

    async def optimize_execution(
        self, container: Any, code: str, language: str = "python"  # TODO(TYPE): replace Any with concrete type
    ) -> PerformanceMetrics:
        """Optimize code execution with monitoring"""
        metrics = PerformanceMetrics()
        start_time = time.time()

        # Preprocess code
        optimized_code = self.preprocess_code(code, language)

        # Monitor system resources before execution
        self._get_system_stats()

        # Execute optimized code
        exec_start = time.time()
        try:
            # Language-specific execution
            if language == "python":
                await self._execute_python_optimized(container, optimized_code)
            elif language == "javascript":
                await self._execute_javascript_optimized(container, optimized_code)
            else:
                await self._execute_generic(container, optimized_code)
        except Exception as e:
            logger.error(f"Execution error: {e}")
            raise

        metrics.code_execution_time = time.time() - exec_start

        # Monitor system resources after execution
        final_stats = self._get_system_stats()
        metrics.cpu_usage_percent = final_stats.get("cpu_percent", 0)
        metrics.memory_usage_mb = final_stats.get("memory_mb", 0)

        metrics.total_execution_time = time.time() - start_time

        # Store metrics for analysis
        self.execution_metrics.append(metrics)

        return metrics

    async def _execute_python_optimized(self, container: Any, code: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Execute Python code with optimizations"""
        # Create optimized execution script
        script = """
import sys
import io
import contextlib
import time

# Redirect stdout for better performance
old_stdout = sys.stdout
sys.stdout = buffer = io.StringIO()

try:
    {code}
finally:
    sys.stdout = old_stdout
    output = buffer.getvalue()
    if output.strip():
        print(output.strip())
"""

        # Write and execute
        container.put_archive("/workspace", self._create_tar_archive("execute.py", script.encode()))
        result = container.exec_run(
            cmd=["python", "/workspace/execute.py"],
            workdir="/workspace",
            environment={"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )

        return result

    async def _execute_javascript_optimized(self, container: Any, code: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Execute JavaScript code with optimizations"""
        script = """
const startTime = performance.now();

{code}

const endTime = performance.now();
// Execution time: ${(endTime - startTime)/1000}s
"""

        container.put_archive("/workspace", self._create_tar_archive("execute.js", script.encode()))
        result = container.exec_run(cmd=["node", "/workspace/execute.js"], workdir="/workspace")

        return result

    async def _execute_generic(self, container: Any, code: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Execute generic code"""
        container.put_archive("/workspace", self._create_tar_archive("execute.py", code.encode()))
        result = container.exec_run(cmd=["python", "/workspace/execute.py"], workdir="/workspace")

        return result

    def _create_tar_archive(self, filename: str, content: bytes) -> bytes:
        """Create tar archive for file transfer"""
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

    def _get_system_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current system performance statistics"""
        try:
            if not PSUTIL_AVAILABLE:
                return {
                    "cpu_percent": 50.0,  # Mock value
                    "memory_mb": 1024.0,  # Mock value
                    "disk_io_mb": 10.0,  # Mock value
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            if psutil is None:
                return {
                    "cpu_percent": 50.0,  # Mock value
                    "memory_mb": 1024.0,  # Mock value
                    "disk_io_mb": 10.0,  # Mock value
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            disk_counters = psutil.disk_io_counters()
            disk_io_mb = (
                sum([disk_counters.read_bytes, disk_counters.write_bytes]) / (1024 * 1024)
                if disk_counters
                else 10.0
            )
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_mb": psutil.virtual_memory().used / (1024 * 1024),
                "disk_io_mb": disk_io_mb,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.debug(f"Error getting system stats: {e}")
            return {}

    async def return_container(self, image: str, container: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Return container to pool for reuse"""
        await self.container_pool.return_container(image, container)

    def get_performance_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate comprehensive performance report"""
        if not self.execution_metrics:
            return {"error": "No execution metrics available"}

        recent_metrics = list(self.execution_metrics)[-100:]  # Last 100 executions

        # Calculate averages
        avg_creation_time = sum(m.container_creation_time for m in recent_metrics) / len(
            recent_metrics
        )
        avg_execution_time = sum(m.code_execution_time for m in recent_metrics) / len(
            recent_metrics
        )
        avg_total_time = sum(m.total_execution_time for m in recent_metrics) / len(recent_metrics)
        avg_memory = sum(m.memory_usage_mb for m in recent_metrics) / len(recent_metrics)
        avg_cpu = sum(m.cpu_usage_percent for m in recent_metrics) / len(recent_metrics)
        avg_cache_hit = sum(m.cache_hit_rate for m in recent_metrics) / len(recent_metrics)

        return {
            "optimization_level": self.optimization_level.value,
            "total_executions": len(self.execution_metrics),
            "recent_executions": len(recent_metrics),
            "performance_averages": {
                "container_creation_time": round(avg_creation_time, 4),
                "code_execution_time": round(avg_execution_time, 4),
                "total_execution_time": round(avg_total_time, 4),
                "memory_usage_mb": round(avg_memory, 2),
                "cpu_usage_percent": round(avg_cpu, 2),
                "cache_hit_rate": round(avg_cache_hit * 100, 2),
            },
            "image_cache_stats": self.image_cache.get_cache_stats(),
            "container_pool_stats": self.container_pool.get_pool_stats(),
            "code_cache_stats": self.code_cache.get_stats(),
            "system_stats": self._get_system_stats(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def stop(self) -> None:
        """Stop optimizer and cleanup resources"""
        self.container_pool.stop()
        logger.info("Performance optimizer stopped")


# Factory functions
def create_performance_optimizer(
    optimization_level: OptimizationLevel = OptimizationLevel.STANDARD,
) -> PerformanceOptimizer | None:
    """Create performance optimizer if Docker is available"""
    if not DOCKER_AVAILABLE:
        logger.warning("Docker not available, performance optimization disabled")
        return None

    try:
        if docker is None:
            logger.warning("Docker not available, performance optimization disabled")
            return None
        docker_client = docker.from_env()
        return PerformanceOptimizer(docker_client, optimization_level)
    except Exception as e:
        logger.error(f"Failed to create performance optimizer: {e}")
        return None
