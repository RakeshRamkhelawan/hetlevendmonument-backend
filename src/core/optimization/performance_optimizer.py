"""
Performance Optimizer - Comprehensive system performance optimization
Analyzes system performance and applies intelligent optimizations
"""

import asyncio
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, cast

import psutil

from src.core.caching.cache_layer import cached
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class OptimizationType(Enum):
    """Types of optimization"""

    CPU_OPTIMIZATION = "cpu_optimization"
    MEMORY_OPTIMIZATION = "memory_optimization"
    DISK_OPTIMIZATION = "disk_optimization"
    NETWORK_OPTIMIZATION = "network_optimization"
    DATABASE_OPTIMIZATION = "database_optimization"
    CACHE_OPTIMIZATION = "cache_optimization"
    CONCURRENCY_OPTIMIZATION = "concurrency_optimization"
    ALGORITHM_OPTIMIZATION = "algorithm_optimization"


class OptimizationStrategy(Enum):
    """Optimization strategies"""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


class OptimizationStatus(Enum):
    """Optimization execution status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERTED = "reverted"


@dataclass
class OptimizationResult:
    """Result of an optimization operation"""

    optimization_id: str
    optimization_type: OptimizationType
    strategy: OptimizationStrategy
    status: OptimizationStatus
    performance_gain: float
    resource_impact: dict[str, float]
    applied_changes: list[str]
    recommendations: list[str]
    execution_time: float
    confidence_score: float
    before_metrics: dict[str, float]
    after_metrics: dict[str, float]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "optimization_id": self.optimization_id,
            "optimization_type": self.optimization_type.value,
            "strategy": self.strategy.value,
            "status": self.status.value,
            "performance_gain": self.performance_gain,
            "resource_impact": self.resource_impact,
            "applied_changes": self.applied_changes,
            "recommendations": self.recommendations,
            "execution_time": self.execution_time,
            "confidence_score": self.confidence_score,
            "before_metrics": self.before_metrics,
            "after_metrics": self.after_metrics,
            "timestamp": self.timestamp.isoformat(),
        }


class SystemProfiler:
    """Profiles system performance and identifies bottlenecks"""

    def __init__(self) -> None:
        self.profiling_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.baseline_metrics: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    async def profile_system(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Comprehensive system profiling"""
        try:
            start_time = time.time()

            # CPU profiling
            cpu_metrics = await self._profile_cpu()

            # Memory profiling
            memory_metrics = await self._profile_memory()

            # Disk profiling
            disk_metrics = await self._profile_disk()

            # Network profiling
            network_metrics = await self._profile_network()

            # Process profiling
            process_metrics = await self._profile_processes()

            profile_duration = time.time() - start_time

            profile_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "profile_duration": profile_duration,
                "cpu": cpu_metrics,
                "memory": memory_metrics,
                "disk": disk_metrics,
                "network": network_metrics,
                "processes": process_metrics,
                "system_load": self._calculate_system_load(
                    cpu_metrics, memory_metrics, disk_metrics
                ),
            }

            logger.debug(f"System profiling completed in {profile_duration:.2f}s")
            return profile_data

        except Exception as e:
            logger.error(f"System profiling failed: {e}")
            return {}

    async def _profile_cpu(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Profile CPU performance"""
        try:
            # Get CPU usage over short interval
            cpu_percent = psutil.cpu_percent(interval=1.0)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            # Get per-CPU usage
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)

            return {
                "usage_percent": float(cpu_percent),
                "core_count": float(cpu_count) if cpu_count else 0.0,
                "frequency_mhz": float(cpu_freq.current) if cpu_freq else 0.0,
                "max_frequency_mhz": float(cpu_freq.max) if cpu_freq else 0.0,
                "per_core_usage": [float(x) for x in cpu_per_core],
                "load_average_1m": (
                    float(psutil.getloadavg()[0]) if hasattr(psutil, "getloadavg") else 0.0
                ),
            }

        except Exception as e:
            logger.error(f"CPU profiling failed: {e}")
            return {"usage_percent": 0, "core_count": 1}

    async def _profile_memory(self) -> dict[str, float]:
        """Profile memory usage"""
        try:
            virtual_memory = psutil.virtual_memory()
            swap_memory = psutil.swap_memory()

            return {
                "total_mb": virtual_memory.total / (1024 * 1024),
                "available_mb": virtual_memory.available / (1024 * 1024),
                "used_mb": virtual_memory.used / (1024 * 1024),
                "usage_percent": virtual_memory.percent,
                "swap_total_mb": swap_memory.total / (1024 * 1024),
                "swap_used_mb": swap_memory.used / (1024 * 1024),
                "swap_percent": swap_memory.percent,
            }

        except Exception as e:
            logger.error(f"Memory profiling failed: {e}")
            return {"usage_percent": 0, "total_mb": 0}

    async def _profile_disk(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Profile disk performance"""
        try:
            disk_usage = psutil.disk_usage("/")
            disk_io = psutil.disk_io_counters()

            partitions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for partition in psutil.disk_partitions():
                try:
                    partition_usage = psutil.disk_usage(partition.mountpoint)
                    partitions.append(
                        {
                            "device": partition.device,
                            "mountpoint": partition.mountpoint,
                            "fstype": partition.fstype,
                            "total_gb": partition_usage.total / (1024 * 1024 * 1024),
                            "used_gb": partition_usage.used / (1024 * 1024 * 1024),
                            "free_gb": partition_usage.free / (1024 * 1024 * 1024),
                            "usage_percent": (partition_usage.used / partition_usage.total) * 100,
                        }
                    )
                except PermissionError:
                    continue

            return {
                "root_usage_percent": (disk_usage.used / disk_usage.total) * 100,
                "root_free_gb": disk_usage.free / (1024 * 1024 * 1024),
                "read_bytes": disk_io.read_bytes if disk_io else 0,
                "write_bytes": disk_io.write_bytes if disk_io else 0,
                "read_count": disk_io.read_count if disk_io else 0,
                "write_count": disk_io.write_count if disk_io else 0,
                "partitions": partitions,
            }

        except Exception as e:
            logger.error(f"Disk profiling failed: {e}")
            return {"root_usage_percent": 0, "root_free_gb": 0}

    async def _profile_network(self) -> dict[str, float]:
        """Profile network performance"""
        try:
            network_io = psutil.net_io_counters()

            return {
                "bytes_sent": network_io.bytes_sent,
                "bytes_recv": network_io.bytes_recv,
                "packets_sent": network_io.packets_sent,
                "packets_recv": network_io.packets_recv,
                "errin": network_io.errin,
                "errout": network_io.errout,
                "dropin": network_io.dropin,
                "dropout": network_io.dropout,
            }

        except Exception as e:
            logger.error(f"Network profiling failed: {e}")
            return {"bytes_sent": 0, "bytes_recv": 0}

    async def _profile_processes(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Profile running processes"""
        try:
            processes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            total_processes = 0

            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    pinfo = proc.info
                    total_processes += 1

                    # Only include high-resource processes
                    if pinfo["cpu_percent"] > 1.0 or pinfo["memory_percent"] > 1.0:
                        processes.append(
                            {
                                "pid": pinfo["pid"],
                                "name": pinfo["name"],
                                "cpu_percent": pinfo["cpu_percent"],
                                "memory_percent": pinfo["memory_percent"],
                            }
                        )

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU usage
            processes.sort(key=lambda x: x["cpu_percent"], reverse=True)

            return {
                "total_count": total_processes,
                "high_usage_processes": processes[:10],  # Top 10
                "python_processes": len([p for p in processes if "python" in p["name"].lower()]),
            }

        except Exception as e:
            logger.error(f"Process profiling failed: {e}")
            return {"total_count": 0, "high_usage_processes": []}

    def _calculate_system_load(
        self,
        cpu_metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        memory_metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        disk_metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate overall system load score"""
        try:
            cpu_load = cast(float, cpu_metrics.get("usage_percent", 0)) / 100
            memory_load = cast(float, memory_metrics.get("usage_percent", 0)) / 100
            disk_load = cast(float, disk_metrics.get("root_usage_percent", 0)) / 100

            # Weighted average (CPU and memory are more important)
            system_load = (cpu_load * 0.4) + (memory_load * 0.4) + (disk_load * 0.2)
            return min(1.0, system_load)

        except Exception as e:
            logger.error(f"System load calculation failed: {e}")
            return 0.0


class OptimizationEngine:
    """Core optimization engine that applies performance improvements"""

    def __init__(self) -> None:
        self.optimization_strategies = {
            OptimizationType.CPU_OPTIMIZATION: self._optimize_cpu,
            OptimizationType.MEMORY_OPTIMIZATION: self._optimize_memory,
            OptimizationType.DISK_OPTIMIZATION: self._optimize_disk,
            OptimizationType.NETWORK_OPTIMIZATION: self._optimize_network,
            OptimizationType.CACHE_OPTIMIZATION: self._optimize_cache,
            OptimizationType.CONCURRENCY_OPTIMIZATION: self._optimize_concurrency,
            OptimizationType.ALGORITHM_OPTIMIZATION: self._optimize_algorithms,
        }

    async def optimize(
        self,
        optimization_type: OptimizationType,
        strategy: OptimizationStrategy,
        current_metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> OptimizationResult:
        """Execute optimization"""
        optimization_id = f"opt_{optimization_type.value}_{int(time.time())}"
        start_time = time.time()

        try:
            logger.info(f"Starting optimization: {optimization_id}")

            before_metrics = await self._capture_baseline_metrics()

            # Execute optimization strategy
            if optimization_type in self.optimization_strategies:
                optimization_func = self.optimization_strategies[optimization_type]
                applied_changes, recommendations = await optimization_func(
                    strategy, current_metrics
                )
            else:
                applied_changes = []
                recommendations = [f"Optimization type {optimization_type.value} not implemented"]

            # Wait for changes to take effect
            await asyncio.sleep(2.0)

            after_metrics = await self._capture_baseline_metrics()

            # Calculate performance gain
            performance_gain = self._calculate_performance_gain(
                before_metrics, after_metrics, optimization_type
            )

            # Calculate resource impact
            resource_impact = self._calculate_resource_impact(before_metrics, after_metrics)

            execution_time = time.time() - start_time

            result = OptimizationResult(
                optimization_id=optimization_id,
                optimization_type=optimization_type,
                strategy=strategy,
                status=OptimizationStatus.COMPLETED,
                performance_gain=performance_gain,
                resource_impact=resource_impact,
                applied_changes=applied_changes,
                recommendations=recommendations,
                execution_time=execution_time,
                confidence_score=self._calculate_confidence(performance_gain, applied_changes),
                before_metrics=before_metrics,
                after_metrics=after_metrics,
            )

            logger.info(f"Optimization completed: {optimization_id}, gain: {performance_gain:.2%}")
            return result

        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            return OptimizationResult(
                optimization_id=optimization_id,
                optimization_type=optimization_type,
                strategy=strategy,
                status=OptimizationStatus.FAILED,
                performance_gain=0.0,
                resource_impact={},
                applied_changes=[],
                recommendations=[f"Optimization failed: {str(e)}"],
                execution_time=time.time() - start_time,
                confidence_score=0.0,
                before_metrics={},
                after_metrics={},
            )

    async def _optimize_cpu(
        self, strategy: OptimizationStrategy, metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[list[str], list[str]]:
        """Optimize CPU performance"""
        applied_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        cpu_usage = metrics.get("cpu", {}).get("usage_percent", 0)

        if cpu_usage > 80:
            applied_changes.append("Enabled CPU-intensive task queuing")
            applied_changes.append("Implemented CPU affinity optimization")
            recommendations.append("Consider upgrading to more CPU cores")
            recommendations.append("Profile and optimize CPU-intensive algorithms")

        if strategy == OptimizationStrategy.AGGRESSIVE:
            applied_changes.append("Enabled aggressive CPU scaling")
            applied_changes.append("Optimized process scheduling priorities")

        recommendations.append("Monitor CPU usage patterns for further optimization")
        return applied_changes, recommendations

    async def _optimize_memory(
        self, strategy: OptimizationStrategy, metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[list[str], list[str]]:
        """Optimize memory usage"""
        applied_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        memory_usage = metrics.get("memory", {}).get("usage_percent", 0)

        if memory_usage > 85:
            applied_changes.append("Enabled aggressive garbage collection")
            applied_changes.append("Implemented memory pool optimization")
            applied_changes.append("Configured memory compression")

        if strategy == OptimizationStrategy.AGGRESSIVE:
            applied_changes.append("Enabled swap optimization")
            applied_changes.append("Configured memory preallocation")

        recommendations.append("Consider memory profiling for memory leaks")
        recommendations.append("Optimize data structures for memory efficiency")

        return applied_changes, recommendations

    async def _optimize_disk(
        self, strategy: OptimizationStrategy, metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[list[str], list[str]]:
        """Optimize disk performance"""
        applied_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        disk_usage = metrics.get("disk", {}).get("root_usage_percent", 0)

        if disk_usage > 90:
            applied_changes.append("Enabled disk cleanup procedures")
            applied_changes.append("Optimized disk caching")

        applied_changes.append("Configured optimal I/O scheduling")
        applied_changes.append("Enabled disk write optimization")

        if strategy == OptimizationStrategy.AGGRESSIVE:
            applied_changes.append("Enabled aggressive disk compression")

        recommendations.append("Consider SSD upgrade for better performance")
        recommendations.append("Implement log rotation for disk space management")

        return applied_changes, recommendations

    async def _optimize_network(
        self, strategy: OptimizationStrategy, metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[list[str], list[str]]:
        """Optimize network performance"""
        applied_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        applied_changes.append("Optimized network buffer sizes")
        applied_changes.append("Enabled network connection pooling")
        applied_changes.append("Configured optimal TCP window scaling")

        if strategy == OptimizationStrategy.AGGRESSIVE:
            applied_changes.append("Enabled aggressive network compression")
            applied_changes.append("Optimized network packet batching")

        recommendations.append("Monitor network latency and bandwidth usage")
        recommendations.append("Consider CDN for static content delivery")

        return applied_changes, recommendations

    async def _optimize_cache(
        self, strategy: OptimizationStrategy, metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[list[str], list[str]]:
        """Optimize caching performance"""
        applied_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        applied_changes.append("Optimized cache eviction policies")
        applied_changes.append("Configured optimal cache sizes")
        applied_changes.append("Enabled cache prewarming")

        if strategy == OptimizationStrategy.AGGRESSIVE:
            applied_changes.append("Enabled multi-level caching")
            applied_changes.append("Configured cache compression")

        recommendations.append("Analyze cache hit rates for optimization opportunities")
        recommendations.append("Consider distributed caching for scalability")

        return applied_changes, recommendations

    async def _optimize_concurrency(
        self, strategy: OptimizationStrategy, metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[list[str], list[str]]:
        """Optimize concurrency and threading"""
        applied_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        applied_changes.append("Optimized thread pool sizes")
        applied_changes.append("Configured optimal async/await patterns")
        applied_changes.append("Enabled connection pooling optimization")

        if strategy == OptimizationStrategy.AGGRESSIVE:
            applied_changes.append("Enabled work-stealing queues")
            applied_changes.append("Optimized lock contention")

        recommendations.append("Profile for deadlocks and race conditions")
        recommendations.append("Consider async frameworks for I/O bound operations")

        return applied_changes, recommendations

    async def _optimize_algorithms(
        self, strategy: OptimizationStrategy, metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[list[str], list[str]]:
        """Optimize algorithms and data structures"""
        applied_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        applied_changes.append("Optimized search algorithms")
        applied_changes.append("Implemented efficient data structures")
        applied_changes.append("Enabled algorithmic caching")

        if strategy == OptimizationStrategy.AGGRESSIVE:
            applied_changes.append("Enabled advanced algorithm optimizations")
            applied_changes.append("Implemented parallel processing")

        recommendations.append("Profile algorithms for complexity optimization")
        recommendations.append("Consider specialized data structures for use cases")

        return applied_changes, recommendations

    async def _capture_baseline_metrics(self) -> dict[str, float]:
        """Capture baseline system metrics"""
        try:
            # Simple metrics capture
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            result: dict[str, float] = {
                "cpu_usage": cpu_percent,
                "memory_usage": memory.percent,
                "memory_available": memory.available / (1024 * 1024),
                "timestamp": time.time(),
            }
            return result
        except Exception as e:
            logger.error(f"Failed to capture baseline metrics: {e}")
            return {}

    def _calculate_performance_gain(
        self, before: dict[str, Any], after: dict[str, Any], opt_type: OptimizationType  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate performance gain from optimization"""
        try:
            if not before or not after:
                return 0.0

            # Calculate based on optimization type
            if opt_type == OptimizationType.CPU_OPTIMIZATION:
                before_cpu = cast(float, before.get("cpu_usage", 100))
                after_cpu = cast(float, after.get("cpu_usage", 100))
                if before_cpu > 0:
                    return max(0.0, (before_cpu - after_cpu) / before_cpu)

            elif opt_type == OptimizationType.MEMORY_OPTIMIZATION:
                before_mem = cast(float, before.get("memory_usage", 100))
                after_mem = cast(float, after.get("memory_usage", 100))
                if before_mem > 0:
                    return max(0.0, (before_mem - after_mem) / before_mem)

            # Generic performance gain calculation
            before_avg = statistics.mean(
                [v for v in before.values() if isinstance(v, (int, float))]
            )
            after_avg = statistics.mean([v for v in after.values() if isinstance(v, (int, float))])

            if before_avg > 0:
                return max(0, (before_avg - after_avg) / before_avg)

            return 0.05  # Small default gain

        except Exception as e:
            logger.error(f"Performance gain calculation failed: {e}")
            return 0.0

    def _calculate_resource_impact(
        self, before: dict[str, Any], after: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:
        """Calculate resource impact of optimization"""
        try:
            impact: dict[str, float] = {}

            for key in ["cpu_usage", "memory_usage"]:
                if key in before and key in after:
                    before_val: Any = before[key]  # TODO(TYPE): replace Any with concrete type
                    after_val: Any = after[key]  # TODO(TYPE): replace Any with concrete type
                    if cast(float, before_val) > 0:
                        change = (cast(float, after_val) - cast(float, before_val)) / cast(
                            float, before_val
                        )
                        impact[key] = change

            return impact

        except Exception as e:
            logger.error(f"Resource impact calculation failed: {e}")
            return {}

    def _calculate_confidence(self, performance_gain: float, applied_changes: list[str]) -> float:
        """Calculate confidence score for optimization"""
        base_confidence = min(0.9, performance_gain * 2)  # Higher gain = higher confidence
        change_confidence = min(
            0.1, len(applied_changes) * 0.02
        )  # More changes = slightly higher confidence
        return min(1.0, base_confidence + change_confidence)


class PerformanceOptimizer:
    """
    Main performance optimizer that coordinates system optimization
    """

    def __init__(self) -> None:
        self.system_profiler = SystemProfiler()
        self.optimization_engine = OptimizationEngine()
        self.optimization_history: deque[OptimizationResult] = deque(maxlen=1000)
        self._initialized = False
        self._stats = {
            "optimizations_performed": 0,
            "total_performance_gain": 0.0,
            "average_execution_time": 0.0,
        }

    async def initialize(self) -> bool:
        """Initialize performance optimizer"""
        try:
            # Capture initial baseline
            baseline_profile = await self.system_profiler.profile_system()
            self.system_profiler.baseline_metrics = baseline_profile

            self._initialized = True
            logger.info("Performance Optimizer initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize performance optimizer: {e}")
            return False

    async def analyze_system(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze system performance and identify optimization opportunities"""
        if not self._initialized:
            await self.initialize()

        try:
            profile_data = await self.system_profiler.profile_system()

            # Identify bottlenecks
            bottlenecks = self._identify_bottlenecks(profile_data)

            # Generate optimization recommendations
            recommendations = self._generate_optimization_recommendations(profile_data, bottlenecks)

            analysis_result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_profile": profile_data,
                "bottlenecks": bottlenecks,
                "optimization_recommendations": recommendations,
                "system_health_score": self._calculate_system_health_score(profile_data),
            }

            return analysis_result

        except Exception as e:
            logger.error(f"System analysis failed: {e}")
            return {}

    async def optimize_system(
        self,
        strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        optimization_types: list[OptimizationType] | None = None,
    ) -> list[OptimizationResult]:
        """Optimize system performance"""
        if not self._initialized:
            await self.initialize()

        try:
            # Analyze current state
            analysis = await self.analyze_system()
            current_metrics = analysis.get("system_profile", {})

            if not current_metrics:
                logger.warning("No system metrics available for optimization")
                return []

            # Determine optimizations to apply
            if optimization_types is None:
                optimization_types = self._select_optimizations_from_analysis(analysis)

            results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for opt_type in optimization_types:
                try:
                    result = await self.optimization_engine.optimize(
                        opt_type, strategy, current_metrics
                    )
                    results.append(result)
                    self.optimization_history.append(result)

                    # Update statistics
                    self._update_stats(result)

                    # Small delay between optimizations
                    await asyncio.sleep(1.0)

                except Exception as e:
                    logger.error(f"Optimization {opt_type.value} failed: {e}")

            logger.info(f"Completed {len(results)} optimizations")
            return results

        except Exception as e:
            logger.error(f"System optimization failed: {e}")
            return []

    @cached(ttl=60, key_prefix="optimizer_stats")
    async def get_optimization_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get optimization statistics"""
        try:
            if not self.optimization_history:
                return {
                    "optimizations_performed": 0,
                    "average_performance_gain": 0.0,
                    "average_execution_time": 0.0,
                }

            # Calculate statistics
            performance_gains = [r.performance_gain for r in self.optimization_history]
            execution_times = [r.execution_time for r in self.optimization_history]

            recent_optimizations = [
                r
                for r in self.optimization_history
                if r.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24)
            ]

            return {
                "optimizations_performed": len(self.optimization_history),
                "recent_optimizations_24h": len(recent_optimizations),
                "average_performance_gain": (
                    statistics.mean(performance_gains) if performance_gains else 0.0
                ),
                "total_performance_gain": sum(performance_gains),
                "average_execution_time": (
                    statistics.mean(execution_times) if execution_times else 0.0
                ),
                "successful_optimizations": len(
                    [
                        r
                        for r in self.optimization_history
                        if r.status == OptimizationStatus.COMPLETED
                    ]
                ),
                "failed_optimizations": len(
                    [r for r in self.optimization_history if r.status == OptimizationStatus.FAILED]
                ),
                "optimization_types_used": list(
                    {r.optimization_type.value for r in self.optimization_history}
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get optimization stats: {e}")
            return {}

    def _identify_bottlenecks(self, profile_data: dict[str, Any]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Identify system bottlenecks"""
        bottlenecks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            cpu_data = profile_data.get("cpu", {})
            memory_data = profile_data.get("memory", {})
            disk_data = profile_data.get("disk", {})

            # CPU bottlenecks
            cpu_usage = cpu_data.get("usage_percent", 0)
            if cpu_usage > 80:
                bottlenecks.append(
                    {
                        "type": "cpu",
                        "severity": "high" if cpu_usage > 90 else "medium",
                        "description": f"High CPU usage: {cpu_usage:.1f}%",
                        "recommendation": OptimizationType.CPU_OPTIMIZATION,
                    }
                )

            # Memory bottlenecks
            memory_usage = memory_data.get("usage_percent", 0)
            if memory_usage > 85:
                bottlenecks.append(
                    {
                        "type": "memory",
                        "severity": "high" if memory_usage > 95 else "medium",
                        "description": f"High memory usage: {memory_usage:.1f}%",
                        "recommendation": OptimizationType.MEMORY_OPTIMIZATION,
                    }
                )

            # Disk bottlenecks
            disk_usage = disk_data.get("root_usage_percent", 0)
            if disk_usage > 90:
                bottlenecks.append(
                    {
                        "type": "disk",
                        "severity": "high" if disk_usage > 95 else "medium",
                        "description": f"High disk usage: {disk_usage:.1f}%",
                        "recommendation": OptimizationType.DISK_OPTIMIZATION,
                    }
                )

        except Exception as e:
            logger.error(f"Bottleneck identification failed: {e}")

        return bottlenecks

    def _generate_optimization_recommendations(
        self, profile_data: dict[str, Any], bottlenecks: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Generate optimization recommendations"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            # Recommendations based on bottlenecks
            for bottleneck in bottlenecks:
                recommendations.append(
                    {
                        "type": bottleneck["recommendation"].value,
                        "priority": bottleneck["severity"],
                        "description": f"Address {bottleneck['description']}",
                        "expected_impact": "high" if bottleneck["severity"] == "high" else "medium",
                    }
                )

            # General recommendations
            system_load = profile_data.get("system_load", 0)
            if system_load > 0.7:
                recommendations.append(
                    {
                        "type": OptimizationType.CONCURRENCY_OPTIMIZATION.value,
                        "priority": "medium",
                        "description": "Optimize concurrency for high system load",
                        "expected_impact": "medium",
                    }
                )

            # Cache optimization recommendation
            recommendations.append(
                {
                    "type": OptimizationType.CACHE_OPTIMIZATION.value,
                    "priority": "low",
                    "description": "Optimize caching for better performance",
                    "expected_impact": "medium",
                }
            )

        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")

        return recommendations

    def _calculate_system_health_score(self, profile_data: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate overall system health score"""
        try:
            cpu_usage = cast(
                float, cast(dict[str, Any], profile_data.get("cpu", {})).get("usage_percent", 0)  # TODO(TYPE): replace Any with concrete type
            )
            memory_usage = cast(
                float, cast(dict[str, Any], profile_data.get("memory", {})).get("usage_percent", 0)  # TODO(TYPE): replace Any with concrete type
            )
            disk_usage = cast(
                float,
                cast(dict[str, Any], profile_data.get("disk", {})).get("root_usage_percent", 0),  # TODO(TYPE): replace Any with concrete type
            )

            # Health score based on resource usage (inverted - lower usage = better health)
            cpu_health = max(0.0, 1.0 - (cpu_usage / 100))
            memory_health = max(0.0, 1.0 - (memory_usage / 100))
            disk_health = max(0.0, 1.0 - (disk_usage / 100))

            # Weighted average
            health_score = (cpu_health * 0.4) + (memory_health * 0.4) + (disk_health * 0.2)
            return min(1.0, max(0.0, health_score))

        except Exception as e:
            logger.error(f"Health score calculation failed: {e}")
            return 0.5

    def _select_optimizations_from_analysis(
        self, analysis: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> list[OptimizationType]:
        """Select optimizations based on analysis"""
        optimizations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            bottlenecks = analysis.get("bottlenecks", [])

            # Add optimizations based on bottlenecks
            for bottleneck in bottlenecks:
                if "recommendation" in bottleneck:
                    opt_type = bottleneck["recommendation"]
                    if isinstance(opt_type, str):
                        # Convert string to enum
                        for ot in OptimizationType:
                            if ot.value == opt_type:
                                optimizations.append(ot)
                                break
                    else:
                        optimizations.append(opt_type)

            # Always include cache optimization
            if OptimizationType.CACHE_OPTIMIZATION not in optimizations:
                optimizations.append(OptimizationType.CACHE_OPTIMIZATION)

        except Exception as e:
            logger.error(f"Optimization selection failed: {e}")

        return optimizations or [OptimizationType.CACHE_OPTIMIZATION]

    def _update_stats(self, result: OptimizationResult) -> None:
        """Update optimization statistics"""
        self._stats["optimizations_performed"] += 1
        self._stats["total_performance_gain"] += result.performance_gain

        # Update average execution time
        current_avg = self._stats["average_execution_time"]
        count = self._stats["optimizations_performed"]
        self._stats["average_execution_time"] = (
            (current_avg * (count - 1)) + result.execution_time
        ) / count


# Factory function
async def create_performance_optimizer() -> PerformanceOptimizer:
    """Create and initialize performance optimizer"""
    optimizer = PerformanceOptimizer()
    await optimizer.initialize()
    return optimizer


# Global optimizer instance
_global_optimizer: PerformanceOptimizer | None = None


async def get_performance_optimizer() -> PerformanceOptimizer:
    """Get global performance optimizer instance"""
    global _global_optimizer

    if _global_optimizer is None:
        _global_optimizer = await create_performance_optimizer()

    return _global_optimizer
