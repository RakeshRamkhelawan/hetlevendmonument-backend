"""
Enhanced Security Manager for Docker Sandbox
Advanced security controls, validation, and monitoring for container execution
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels for sandbox execution"""

    MINIMAL = "minimal"  # Basic resource limits
    STANDARD = "standard"  # Standard security controls
    HIGH = "high"  # Enhanced security with strict controls
    MAXIMUM = "maximum"  # Maximum security with extensive validation


class SecurityThreat(Enum):
    """Types of security threats to detect"""

    CODE_INJECTION = "code_injection"
    SYSTEM_ACCESS = "system_access"
    NETWORK_ABUSE = "network_abuse"
    RESOURCE_ABUSE = "resource_abuse"
    FILE_SYSTEM_ABUSE = "filesystem_abuse"
    PRIVILEGE_ESCALATION = "privilege_escalation"


@dataclass
class SecurityPolicy:
    """Security policy configuration"""

    level: SecurityLevel = SecurityLevel.STANDARD
    allowed_imports: set[str] = field(
        default_factory=lambda: {
            "os",
            "sys",
            "time",
            "datetime",
            "json",
            "math",
            "random",
            "collections",
            "itertools",
            "functools",
            "operator",
            "string",
            "re",
            "hashlib",
            "uuid",
            "pathlib",
            "numpy",
            "pandas",
            "matplotlib",
            "scipy",
        }
    )
    blocked_imports: set[str] = field(
        default_factory=lambda: {
            "subprocess",
            "multiprocessing",
            "threading",
            "concurrent.futures",
            "socket",
            "urllib",
            "http",
            "ftplib",
            "smtplib",
            "shutil",
            "tempfile",
            "pty",
            "platform",
            "ctypes",
        }
    )
    max_execution_time: int = 30
    max_memory_mb: int = 512
    max_cpu_percent: float = 50.0
    max_file_size_mb: int = 10
    max_files_created: int = 50
    network_access: bool = False
    allow_file_write: bool = True
    allow_system_calls: bool = False


@dataclass
class SecurityViolation:
    """Security violation detected during execution"""

    threat_type: SecurityThreat
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    message: str
    code_location: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class CodeSecurityAnalyzer:
    """Analyzes code for security threats before execution"""

    def __init__(self, policy: SecurityPolicy) -> None:
        self.policy = policy
        self._dangerous_patterns = self._compile_dangerous_patterns()

    def _compile_dangerous_patterns(
        self,
    ) -> list[tuple[re.Pattern[str], SecurityThreat, str]]:
        """Compile regex patterns for dangerous code detection"""
        patterns = [
            # System command execution
            (
                re.compile(r"subprocess\.|os\.system|os\.popen|os\.spawn"),
                SecurityThreat.SYSTEM_ACCESS,
                "System command execution",
            ),
            (
                re.compile(r"exec\(|eval\(|compile\("),
                SecurityThreat.CODE_INJECTION,
                "Dynamic code execution",
            ),
            # File system abuse
            (
                re.compile(r'open\s*\([^)]*["\']\/'),
                SecurityThreat.FILE_SYSTEM_ABUSE,
                "Absolute path file access",
            ),
            (
                re.compile(r"\.\.\/|\.\.\\"),
                SecurityThreat.FILE_SYSTEM_ABUSE,
                "Directory traversal attempt",
            ),
            # Network access
            (
                re.compile(r"socket\.|urllib\.|http\.|requests\."),
                SecurityThreat.NETWORK_ABUSE,
                "Network access attempt",
            ),
            # Privilege escalation
            (
                re.compile(r"import\s+(ctypes|platform|pty)"),
                SecurityThreat.PRIVILEGE_ESCALATION,
                "Privilege escalation imports",
            ),
            (
                re.compile(r"__import__\(|getattr\(|setattr\("),
                SecurityThreat.CODE_INJECTION,
                "Dynamic import/attribute access",
            ),
            # Resource abuse
            (
                re.compile(r"while\s+True\s*:|for.*in.*range\(\d{6,}\)"),
                SecurityThreat.RESOURCE_ABUSE,
                "Potential infinite loop or large iteration",
            ),
        ]

        return patterns

    def analyze_code(self, code: str) -> list[SecurityViolation]:
        """Analyze code for security violations"""
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for blocked imports
        violations.extend(self._check_imports(code))

        # Check for dangerous patterns
        violations.extend(self._check_dangerous_patterns(code))

        # Check code complexity/size
        violations.extend(self._check_code_complexity(code))

        return violations

    def _check_imports(self, code: str) -> list[SecurityViolation]:
        """Check for blocked imports"""
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        import_pattern = re.compile(
            r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", re.MULTILINE
        )
        imports = import_pattern.findall(code)

        for imp in imports:
            base_module = imp.split(".")[0]

            if base_module in self.policy.blocked_imports:
                violations.append(
                    SecurityViolation(
                        threat_type=SecurityThreat.SYSTEM_ACCESS,
                        severity="HIGH",
                        message=f"Blocked import detected: {imp}",
                        context={"import": imp, "base_module": base_module},
                    )
                )

            elif (
                self.policy.level == SecurityLevel.HIGH
                and base_module not in self.policy.allowed_imports
            ):
                violations.append(
                    SecurityViolation(
                        threat_type=SecurityThreat.SYSTEM_ACCESS,
                        severity="MEDIUM",
                        message=f"Unapproved import in high security mode: {imp}",
                        context={"import": imp},
                    )
                )

        return violations

    def _check_dangerous_patterns(self, code: str) -> list[SecurityViolation]:
        """Check for dangerous code patterns"""
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        lines = code.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pattern, threat_type, description in self._dangerous_patterns:
                if pattern.search(line):
                    severity = (
                        "CRITICAL"
                        if threat_type
                        in [SecurityThreat.CODE_INJECTION, SecurityThreat.SYSTEM_ACCESS]
                        else "HIGH"
                    )

                    violations.append(
                        SecurityViolation(
                            threat_type=threat_type,
                            severity=severity,
                            message=f"{description} detected",
                            code_location=f"line {line_num}: {line.strip()}",
                            context={"line_number": line_num, "pattern": description},
                        )
                    )

        return violations

    def _check_code_complexity(self, code: str) -> list[SecurityViolation]:
        """Check for code complexity issues"""
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check code length
        if len(code) > 100000:  # 100KB limit
            violations.append(
                SecurityViolation(
                    threat_type=SecurityThreat.RESOURCE_ABUSE,
                    severity="MEDIUM",
                    message=f"Code size too large: {len(code)} characters",
                    context={"code_size": len(code)},
                )
            )

        # Check for excessive nesting
        max_nesting = 0
        for line in code.split("\n"):
            stripped = line.lstrip()
            if stripped:
                # Count indentation
                indent = len(line) - len(stripped)
                if indent % 4 == 0:  # Assuming 4-space indentation
                    nesting_level = indent // 4
                    max_nesting = max(max_nesting, nesting_level)

        if max_nesting > 10:
            violations.append(
                SecurityViolation(
                    threat_type=SecurityThreat.RESOURCE_ABUSE,
                    severity="MEDIUM",
                    message=f"Excessive code nesting: {max_nesting} levels",
                    context={"max_nesting": max_nesting},
                )
            )

        return violations


class ResourceMonitor:
    """Monitors resource usage during execution"""

    def __init__(self, policy: SecurityPolicy) -> None:
        self.policy = policy
        self.start_time: float | None = None
        self.violations: list[SecurityViolation] = []

    def start_monitoring(self) -> None:
        """Start monitoring resource usage"""
        self.start_time = time.time()
        self.violations = []

    def check_execution_time(self) -> SecurityViolation | None:
        """Check if execution time exceeds limits"""
        if not self.start_time:
            return None

        elapsed = time.time() - self.start_time
        if elapsed > self.policy.max_execution_time:
            return SecurityViolation(
                threat_type=SecurityThreat.RESOURCE_ABUSE,
                severity="HIGH",
                message=f"Execution timeout: {elapsed:.2f}s > {self.policy.max_execution_time}s",
                context={
                    "elapsed_time": elapsed,
                    "limit": self.policy.max_execution_time,
                },
            )
        return None

    def get_container_stats(self, container: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get container resource statistics"""
        try:
            stats = container.stats(stream=False)

            # Calculate CPU percentage
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            cpu_percent = 0.0
            if cpu_stats and precpu_stats:
                cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu_stats.get(
                    "cpu_usage", {}
                ).get("total_usage", 0)
                system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get(
                    "system_cpu_usage", 0
                )

                if system_delta > 0 and cpu_delta >= 0:
                    num_cpus = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []))
                    cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0

            # Get memory stats
            memory_stats = stats.get("memory_stats", {})
            memory_usage = memory_stats.get("usage", 0)
            memory_limit = memory_stats.get("limit", 0)
            memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0

            return {
                "cpu_percent": cpu_percent,
                "memory_usage_mb": memory_usage / (1024 * 1024),
                "memory_percent": memory_percent,
                "memory_limit_mb": memory_limit / (1024 * 1024),
                "network_rx": stats.get("networks", {}).get("eth0", {}).get("rx_bytes", 0),
                "network_tx": stats.get("networks", {}).get("eth0", {}).get("tx_bytes", 0),
            }

        except Exception as e:
            logger.error(f"Failed to get container stats: {e}")
            return {}

    def check_resource_violations(self, stats: dict[str, Any]) -> list[SecurityViolation]:  # TODO(TYPE): replace Any with concrete type
        """Check for resource usage violations"""
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check CPU usage
        cpu_percent = stats.get("cpu_percent", 0)
        if cpu_percent > self.policy.max_cpu_percent:
            violations.append(
                SecurityViolation(
                    threat_type=SecurityThreat.RESOURCE_ABUSE,
                    severity="HIGH",
                    message=(
                        f"CPU usage exceeded: {cpu_percent:.1f}% > {self.policy.max_cpu_percent}%"
                    ),
                    context={
                        "cpu_percent": cpu_percent,
                        "limit": self.policy.max_cpu_percent,
                    },
                )
            )

        # Check memory usage
        memory_mb = stats.get("memory_usage_mb", 0)
        if memory_mb > self.policy.max_memory_mb:
            violations.append(
                SecurityViolation(
                    threat_type=SecurityThreat.RESOURCE_ABUSE,
                    severity="HIGH",
                    message=(
                        f"Memory usage exceeded: {memory_mb:.1f}MB > {self.policy.max_memory_mb}MB"
                    ),
                    context={
                        "memory_mb": memory_mb,
                        "limit": self.policy.max_memory_mb,
                    },
                )
            )

        # Check network usage if disabled
        if not self.policy.network_access:
            network_total = stats.get("network_rx", 0) + stats.get("network_tx", 0)
            if network_total > 1024:  # More than 1KB of network traffic
                violations.append(
                    SecurityViolation(
                        threat_type=SecurityThreat.NETWORK_ABUSE,
                        severity="HIGH",
                        message=f"Unauthorized network access detected: {network_total} bytes",
                        context={"network_bytes": network_total},
                    )
                )

        return violations


class SecurityManager:
    """Main security manager for enhanced Docker sandbox security"""

    def __init__(self, security_level: SecurityLevel = SecurityLevel.STANDARD) -> None:
        self.policy = self._create_policy(security_level)
        self.code_analyzer = CodeSecurityAnalyzer(self.policy)
        self.resource_monitor = ResourceMonitor(self.policy)
        self.violation_history: dict[str, list[SecurityViolation]] = {}

    def _create_policy(self, level: SecurityLevel) -> SecurityPolicy:
        """Create security policy based on security level"""
        base_policy = SecurityPolicy(level=level)

        if level == SecurityLevel.MINIMAL:
            base_policy.max_execution_time = 60
            base_policy.max_memory_mb = 1024
            base_policy.max_cpu_percent = 80.0
            base_policy.allow_system_calls = True

        elif level == SecurityLevel.HIGH:
            base_policy.max_execution_time = 15
            base_policy.max_memory_mb = 256
            base_policy.max_cpu_percent = 25.0
            base_policy.network_access = False
            base_policy.allow_system_calls = False
            # More restrictive allowed imports
            base_policy.allowed_imports = {
                "math",
                "json",
                "datetime",
                "random",
                "string",
                "re",
            }

        elif level == SecurityLevel.MAXIMUM:
            base_policy.max_execution_time = 10
            base_policy.max_memory_mb = 128
            base_policy.max_cpu_percent = 20.0
            base_policy.network_access = False
            base_policy.allow_system_calls = False
            base_policy.allow_file_write = False
            # Very restrictive
            base_policy.allowed_imports = {"math", "json", "datetime"}

        return base_policy

    def validate_code_security(
        self, code: str, sandbox_id: str | None = None
    ) -> tuple[bool, list[SecurityViolation]]:
        """Validate code for security violations before execution"""
        violations = self.code_analyzer.analyze_code(code)

        # Store violations in history
        if sandbox_id:
            if sandbox_id not in self.violation_history:
                self.violation_history[sandbox_id] = []
            self.violation_history[sandbox_id].extend(violations)

        # Determine if code should be blocked
        critical_violations = [v for v in violations if v.severity == "CRITICAL"]
        high_violations = [v for v in violations if v.severity == "HIGH"]

        # Block execution if there are critical violations
        # or too many high violations
        should_block = len(critical_violations) > 0 or len(high_violations) > 3

        return not should_block, violations

    def create_secure_container_config(self, base_config: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Enhance container configuration with security settings"""
        secure_config = base_config.copy()

        # Enhanced security options based on policy level
        if self.policy.level in [SecurityLevel.HIGH, SecurityLevel.MAXIMUM]:
            secure_config.update(
                {
                    # Security options
                    "security_opt": [
                        "no-new-privileges:true",
                        "seccomp:unconfined",  # Could be more restrictive
                    ],
                    # Capability restrictions
                    "cap_drop": ["ALL"],
                    "cap_add": (
                        ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"]
                        if self.policy.allow_file_write
                        else []
                    ),
                    # Resource limits (more restrictive)
                    "mem_limit": f"{self.policy.max_memory_mb}m",
                    "cpu_quota": int(
                        self.policy.max_cpu_percent * 1000
                    ),  # CPU quota in microseconds
                    "cpu_period": 100000,  # Standard CPU period
                    # Network isolation
                    "network_disabled": not self.policy.network_access,
                    # Read-only root filesystem for maximum security
                    "read_only": self.policy.level == SecurityLevel.MAXIMUM,
                    # Temporary filesystems
                    "tmpfs": (
                        {
                            "/tmp": f"size={self.policy.max_file_size_mb}m,uid=1000,gid=1000,noexec"  # nosec B108: Docker tmpfs mount (noexec, nosuid)
                        }
                        if self.policy.level == SecurityLevel.MAXIMUM
                        else {}
                    ),
                    # User namespace (if supported)
                    "user": "1000:1000",  # Non-root user
                }
            )

        return secure_config

    def monitor_execution(self, container: Any, sandbox_id: str) -> list[SecurityViolation]:  # TODO(TYPE): replace Any with concrete type
        """Monitor container execution for security violations"""
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Start monitoring
        self.resource_monitor.start_monitoring()

        # Check execution time
        time_violation = self.resource_monitor.check_execution_time()
        if time_violation:
            violations.append(time_violation)

        # Get and check resource stats
        try:
            stats = self.resource_monitor.get_container_stats(container)
            resource_violations = self.resource_monitor.check_resource_violations(stats)
            violations.extend(resource_violations)

        except Exception as e:
            logger.error(f"Failed to monitor container {sandbox_id}: {e}")
            violations.append(
                SecurityViolation(
                    threat_type=SecurityThreat.SYSTEM_ACCESS,
                    severity="MEDIUM",
                    message=f"Monitoring error: {e}",
                    context={"error": str(e)},
                )
            )

        # Store violations
        if sandbox_id not in self.violation_history:
            self.violation_history[sandbox_id] = []
        self.violation_history[sandbox_id].extend(violations)

        return violations

    def get_security_report(self, sandbox_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate comprehensive security report for sandbox"""
        violations = self.violation_history.get(sandbox_id, [])

        # Count violations by type and severity
        by_type: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

        for violation in violations:
            threat_type = violation.threat_type.value
            by_type[threat_type] = by_type.get(threat_type, 0) + 1
            by_severity[violation.severity] += 1

        # Calculate security score (100 - penalties)
        security_score = 100
        security_score -= by_severity["CRITICAL"] * 25
        security_score -= by_severity["HIGH"] * 10
        security_score -= by_severity["MEDIUM"] * 5
        security_score -= by_severity["LOW"] * 1
        security_score = max(0, security_score)

        # Determine overall security status
        if by_severity["CRITICAL"] > 0:
            status = "CRITICAL"
        elif by_severity["HIGH"] > 3:
            status = "HIGH_RISK"
        elif by_severity["HIGH"] > 0 or by_severity["MEDIUM"] > 5:
            status = "MEDIUM_RISK"
        else:
            status = "SECURE"

        return {
            "sandbox_id": sandbox_id,
            "security_level": self.policy.level.value,
            "security_score": security_score,
            "status": status,
            "total_violations": len(violations),
            "violations_by_type": by_type,
            "violations_by_severity": by_severity,
            "policy_settings": {
                "max_execution_time": self.policy.max_execution_time,
                "max_memory_mb": self.policy.max_memory_mb,
                "max_cpu_percent": self.policy.max_cpu_percent,
                "network_access": self.policy.network_access,
                "allow_file_write": self.policy.allow_file_write,
                "allow_system_calls": self.policy.allow_system_calls,
            },
            "recent_violations": [
                {
                    "type": v.threat_type.value,
                    "severity": v.severity,
                    "message": v.message,
                    "timestamp": v.timestamp.isoformat(),
                    "context": v.context,
                }
                for v in violations[-10:]  # Last 10 violations
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def cleanup_history(self, sandbox_id: str) -> None:
        """Clean up violation history for sandbox"""
        if sandbox_id in self.violation_history:
            del self.violation_history[sandbox_id]


# Utility functions for creating security managers with different profiles
def create_development_security_manager() -> SecurityManager:
    """Create security manager for development/testing"""
    return SecurityManager(SecurityLevel.MINIMAL)


def create_production_security_manager() -> SecurityManager:
    """Create security manager for production environments"""
    return SecurityManager(SecurityLevel.HIGH)


def create_maximum_security_manager() -> SecurityManager:
    """Create security manager with maximum security"""
    return SecurityManager(SecurityLevel.MAXIMUM)
