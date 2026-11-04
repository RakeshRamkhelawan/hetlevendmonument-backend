#!/usr/bin/env python3
"""
System Monitor Agent - Specialized Agent for System Health and Metrics
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import NotRequired, TypedDict

import psutil

from src.core.subagents.agent_factory import BaseAgent

logger = logging.getLogger(__name__)


class _MonitorErrorResult(TypedDict):
    error: str
    available_types: list[str]


class _MonitorTaskResult(TypedDict):
    monitor_type: str
    result: dict[str, object]
    timestamp: str
    agent_id: str


class _SystemHealthResult(TypedDict):
    health_score: int
    health_status: str
    issues: list[str]
    metrics: dict[str, float]
    error: NotRequired[str]


class _ResourceUsageResult(TypedDict):
    cpu: dict[str, object]
    memory: dict[str, object]
    disk: dict[str, object]
    network: dict[str, object]
    timestamp: str
    error: NotRequired[str]


class _ProcessInfo(TypedDict):
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: str


class _ProcessMonitorResult(TypedDict):
    total_processes: int
    top_processes: list[_ProcessInfo]
    sort_by: str
    timestamp: str
    error: NotRequired[str]


class _NetworkInterfaceAddr(TypedDict):
    family: str
    address: str
    netmask: str | None
    broadcast: str | None


class _NetworkStatusResult(TypedDict):
    interfaces: dict[str, list[_NetworkInterfaceAddr]]
    network_stats: dict[str, int]
    connection_stats: dict[str, int]
    total_connections: int
    timestamp: str
    error: NotRequired[str]


class _DiskPartitionInfo(TypedDict):
    mountpoint: str
    filesystem: str
    total_gb: float
    used_gb: float
    free_gb: float
    usage_percent: float


class _DiskAnalysisResult(TypedDict):
    partitions: dict[str, _DiskPartitionInfo | dict[str, str]]
    io_statistics: dict[str, int]
    timestamp: str
    error: NotRequired[str]


class SystemMonitorAgent(BaseAgent):
    """Specialized agent for system monitoring tasks"""

    async def _agent_specific_init(self) -> None:
        """Initialize system monitoring capabilities"""
        self.monitoring_functions = {
            "system_health": self._check_system_health,
            "resource_usage": self._get_resource_usage,
            "process_monitoring": self._monitor_processes,
            "network_status": self._check_network_status,
            "disk_analysis": self._analyze_disk_usage,
        }
        logger.info(
            f"System Monitor Agent {self.agent_id} initialized with {len(self.monitoring_functions)} functions"
        )

    async def _execute_specific_task(  # type: ignore[override]
        self, task_data: dict[str, str | dict[str, object]]
    ) -> _MonitorTaskResult | _MonitorErrorResult:
        """Execute system monitoring task"""
        monitor_type = task_data.get("monitor_type", "system_health")
        parameters = task_data.get("parameters", {})

        if monitor_type not in self.monitoring_functions:
            return {
                "error": f"Unknown monitoring type: {monitor_type}",
                "available_types": list(self.monitoring_functions.keys()),
            }

        monitoring_function = self.monitoring_functions[monitor_type]
        result = await monitoring_function(parameters)

        return {
            "monitor_type": monitor_type,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
        }

    async def _check_system_health(
        self, parameters: dict[str, str | int | float]
    ) -> _SystemHealthResult:
        """Check overall system health"""
        try:
            cpu_usage = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            health_score = 100
            issues: list[str] = []
            # CPU health
            if cpu_usage > 90:
                health_score -= 30
                issues.append("High CPU usage")
            elif cpu_usage > 70:
                health_score -= 15
                issues.append("Moderate CPU usage")

            # Memory health
            if memory.percent > 90:
                health_score -= 25
                issues.append("High memory usage")
            elif memory.percent > 75:
                health_score -= 10
                issues.append("Moderate memory usage")

            # Disk health
            if disk.percent > 95:
                health_score -= 20
                issues.append("Very low disk space")
            elif disk.percent > 85:
                health_score -= 10
                issues.append("Low disk space")

            health_status = (
                "excellent"
                if health_score >= 90
                else "good"
                if health_score >= 70
                else "fair"
                if health_score >= 50
                else "poor"
            )

            return {
                "health_score": max(0, health_score),
                "health_status": health_status,
                "issues": issues,
                "metrics": {
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory.percent,
                    "disk_usage": disk.percent,
                },
            }

        except Exception as e:
            return {"error": f"Health check failed: {e}"}  # pyright: ignore[reportReturnType]

    async def _get_resource_usage(
        self, parameters: dict[str, str | int | float]
    ) -> _ResourceUsageResult:
        """Get detailed resource usage information"""
        try:
            # CPU information
            cpu_info = {
                "usage_percent": psutil.cpu_percent(interval=0.1),
                "core_count": psutil.cpu_count(),
                "frequency": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {},
                "per_core_usage": psutil.cpu_percent(interval=0.1, percpu=True),
            }

            # Memory information
            memory = psutil.virtual_memory()
            memory_info = {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "usage_percent": memory.percent,
                "buffers_gb": round(getattr(memory, "buffers", 0) / (1024**3), 2),
                "cached_gb": round(getattr(memory, "cached", 0) / (1024**3), 2),
            }

            # Disk information
            disk = psutil.disk_usage("/")
            disk_info = {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "usage_percent": round(disk.used / disk.total * 100, 2),
            }

            # Network information
            network = psutil.net_io_counters()
            network_info = {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv,
                "connections": len(psutil.net_connections()),
            }

            return {  # type: ignore[return-value]
                "cpu": cpu_info,
                "memory": memory_info,
                "disk": disk_info,
                "network": network_info,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"error": f"Resource usage collection failed: {e}"}  # pyright: ignore[reportReturnType]

    async def _monitor_processes(self, parameters: dict[str, int | str]) -> _ProcessMonitorResult:
        """Monitor running processes"""
        try:
            # `parameters` is `dict[str, int | str]`, dus `.get()` levert `int | str` en dat is geen
            # geldige slice-grens (ADR-036 OP-53). Expliciet omzetten in plaats van erop vertrouwen
            # dat de aanroeper een int stuurt: deze parameters komen van een agent-aanroep en zijn
            # dus modelinvoer. Een onbruikbare waarde valt terug op de default in plaats van de hele
            # meting te laten mislukken -- de try/except eromheen zou er anders een {"error": ...}
            # van maken, en dan verdwijnt een tikfout in een generieke foutmelding.
            top_n_raw = parameters.get("top_n", 10)
            try:
                top_n = int(top_n_raw)
            except (TypeError, ValueError):
                logger.warning("top_n is geen getal (%r); val terug op 10", top_n_raw)
                top_n = 10
            top_n = max(1, min(top_n, 1000))

            sort_by = parameters.get("sort_by", "cpu_percent")

            processes: list[_ProcessInfo] = []
            for proc in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent", "status"]
            ):
                try:
                    proc_info = proc.info
                    processes.append(
                        {
                            "pid": proc_info["pid"],
                            "name": proc_info["name"],
                            "cpu_percent": proc_info["cpu_percent"] or 0,
                            "memory_percent": proc_info["memory_percent"] or 0,
                            "status": proc_info["status"],
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort processes
            if sort_by in ["cpu_percent", "memory_percent"]:
                processes.sort(key=lambda x: x[sort_by], reverse=True)

            return {
                "total_processes": len(processes),
                "top_processes": processes[:top_n],
                "sort_by": sort_by,  # pyright: ignore[reportReturnType]
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"error": f"Process monitoring failed: {e}"}  # pyright: ignore[reportReturnType]

    async def _check_network_status(
        self, parameters: dict[str, str | int | float]
    ) -> _NetworkStatusResult:
        """Check network connectivity and status"""
        try:
            # Get network interfaces
            interfaces: dict[str, list[_NetworkInterfaceAddr]] = {}
            for interface, addrs in psutil.net_if_addrs().items():
                interfaces[interface] = [
                    {
                        "family": addr.family.name,
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast,
                    }
                    for addr in addrs
                ]

            # Get network statistics
            net_io = psutil.net_io_counters()
            network_stats = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "errors_in": net_io.errin,
                "errors_out": net_io.errout,
                "dropped_in": net_io.dropin,
                "dropped_out": net_io.dropout,
            }

            # Connection count by status
            connections = psutil.net_connections()
            connection_stats: dict[str, int] = {}
            for conn in connections:
                status = conn.status
                connection_stats[status] = connection_stats.get(status, 0) + 1

            return {
                "interfaces": interfaces,
                "network_stats": network_stats,
                "connection_stats": connection_stats,
                "total_connections": len(connections),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"error": f"Network status check failed: {e}"}  # pyright: ignore[reportReturnType]

    async def _analyze_disk_usage(
        self, parameters: dict[str, str | int | float]
    ) -> _DiskAnalysisResult:
        """Analyze disk usage patterns"""
        try:
            # Get disk usage for all partitions
            partitions = psutil.disk_partitions()
            disk_analysis: dict[str, _DiskPartitionInfo | dict[str, str]] = {}
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_analysis[partition.device] = {
                        "mountpoint": partition.mountpoint,
                        "filesystem": partition.fstype,
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "usage_percent": round(usage.used / usage.total * 100, 2),
                    }
                except PermissionError:
                    disk_analysis[partition.device] = {"error": "Permission denied"}

            # Disk I/O statistics
            disk_io = psutil.disk_io_counters()
            io_stats = (
                {
                    "read_count": disk_io.read_count,
                    "write_count": disk_io.write_count,
                    "read_bytes": disk_io.read_bytes,
                    "write_bytes": disk_io.write_bytes,
                    "read_time": disk_io.read_time,
                    "write_time": disk_io.write_time,
                }
                if disk_io
                else {}
            )

            return {
                "partitions": disk_analysis,
                "io_statistics": io_stats,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            return {"error": f"Disk analysis failed: {e}"}  # pyright: ignore[reportReturnType]
