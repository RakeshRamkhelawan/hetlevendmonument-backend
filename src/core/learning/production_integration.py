#!/usr/bin/env python3
"""
M-MDP Production Integration System - Phase 3 Day 20-21
A/B testing framework, gradual deployment, and performance monitoring
"""

import hashlib
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, cast
from collections.abc import Callable
from src.core.exceptions import ValidatieFout

logger = logging.getLogger(__name__)


class DeploymentPhase(Enum):
    """Deployment phases for gradual rollout"""

    DISABLED = "disabled"
    CANARY = "canary"  # 1-5% traffic
    BETA = "beta"  # 10-25% traffic
    STAGED = "staged"  # 50% traffic
    FULL = "full"  # 100% traffic


class ABTestStatus(Enum):
    """A/B test status"""

    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class MetricType(Enum):
    """Performance metric types"""

    ACCURACY = "accuracy"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    RESOURCE_USAGE = "resource_usage"
    USER_SATISFACTION = "user_satisfaction"
    BUSINESS_KPI = "business_kpi"


@dataclass
class ABTestConfiguration:
    """A/B test configuration"""

    test_id: str
    test_name: str
    description: str
    control_group: str  # Control variant identifier
    treatment_groups: list[str]  # Treatment variant identifiers
    traffic_allocation: dict[str, float]  # Variant -> traffic percentage
    success_metrics: list[str]
    minimum_sample_size: int
    maximum_duration_days: int
    confidence_level: float = 0.95
    early_stopping_enabled: bool = True
    stratification_keys: list[str] | None = None  # For stratified sampling


@dataclass
class ABTestVariant:
    """A/B test variant configuration"""

    variant_id: str
    variant_name: str
    description: str
    configuration: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    traffic_percentage: float
    is_control: bool = False


@dataclass
class ABTestResult:
    """A/B test result"""

    test_id: str
    variant_id: str
    metric_name: str
    metric_value: float
    sample_size: int
    confidence_interval: tuple[float, float]
    p_value: float | None = None
    effect_size: float | None = None
    timestamp: datetime | None = None


@dataclass
class DeploymentConfig:
    """Deployment configuration"""

    deployment_id: str
    feature_name: str
    target_variant: str
    current_phase: DeploymentPhase
    traffic_percentage: float
    rollout_schedule: dict[DeploymentPhase, datetime]
    success_criteria: dict[str, float]
    rollback_triggers: dict[str, float]
    monitoring_window_hours: int = 24


@dataclass
class PerformanceMetric:
    """Performance metric measurement"""

    metric_id: str
    metric_type: MetricType
    metric_name: str
    value: float
    timestamp: datetime
    tags: dict[str, str] | None = None
    variant_id: str | None = None
    deployment_id: str | None = None


class ABTestingFramework:
    """A/B testing framework for M-MDP system evaluation"""

    def __init__(self) -> None:
        self.active_tests: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.test_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.test_configurations: dict[str, ABTestConfiguration] = {}
        self.traffic_router = TrafficRouter()
        self.statistical_analyzer = StatisticalAnalyzer()

    async def create_ab_test(self, config: ABTestConfiguration) -> str:
        """Create a new A/B test"""
        try:
            # Validate configuration
            await self._validate_test_config(config)

            # Store test configuration
            self.test_configurations[config.test_id] = config

            # Initialize test tracking
            test_state = {
                "config": config,
                "status": ABTestStatus.PLANNING,
                "start_time": None,
                "end_time": None,
                "participants": {},  # variant_id -> participant_count
                "results": {},  # metric_name -> {variant_id -> results}
                "statistical_significance": {},
            }

            self.active_tests[config.test_id] = test_state

            logger.info(f"Created A/B test: {config.test_id} - {config.test_name}")
            return config.test_id

        except Exception as e:
            logger.error(f"Failed to create A/B test: {e}")
            raise

    async def _validate_test_config(self, config: ABTestConfiguration) -> None:
        """Validate A/B test configuration"""
        # Check traffic allocation sums to 100%
        total_traffic = sum(config.traffic_allocation.values())
        if abs(total_traffic - 1.0) > 0.001:
            raise ValueError(f"Traffic allocation must sum to 100%, got {total_traffic * 100}%")

        # Check control group exists
        if config.control_group not in config.traffic_allocation:
            raise ValueError(f"Control group '{config.control_group}' not in traffic allocation")

        # Check treatment groups exist
        for treatment in config.treatment_groups:
            if treatment not in config.traffic_allocation:
                raise ValueError(f"Treatment group '{treatment}' not in traffic allocation")

        # Validate minimum sample size
        if config.minimum_sample_size < 100:
            raise ValidatieFout("Minimum sample size should be at least 100 for statistical validity")

    async def start_ab_test(self, test_id: str) -> bool:
        """Start an A/B test"""
        try:
            if test_id not in self.active_tests:
                raise ValueError(f"A/B test {test_id} not found")

            test_state = self.active_tests[test_id]
            config = cast(ABTestConfiguration, test_state["config"])

            # Configure traffic router
            await self.traffic_router.configure_test_routing(test_id, config.traffic_allocation)

            # Update test state
            test_state["status"] = ABTestStatus.RUNNING
            test_state["start_time"] = datetime.now(timezone.utc)

            # Initialize participant tracking
            for variant_id in config.traffic_allocation.keys():
                test_state["participants"][variant_id] = 0

            logger.info(f"Started A/B test: {test_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start A/B test {test_id}: {e}")
            return False

    async def assign_variant(
        self, test_id: str, user_id: str, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Assign a user to a test variant"""
        try:
            if test_id not in self.active_tests:
                raise ValueError(f"A/B test {test_id} not found")

            test_state = self.active_tests[test_id]

            if test_state["status"] != ABTestStatus.RUNNING:
                # Return control group if test not running
                config = cast(ABTestConfiguration, test_state["config"])
                return config.control_group

            # Use traffic router for assignment
            variant_id = await self.traffic_router.assign_variant(
                test_id, user_id, context if context is not None else {}
            )

            # Track participant
            test_state["participants"][variant_id] += 1

            return variant_id

        except Exception as e:
            logger.error(f"Failed to assign variant for test {test_id}, user {user_id}: {e}")
            # Fallback to control group
            fallback_config = cast(ABTestConfiguration, self.active_tests[test_id]["config"])
            return fallback_config.control_group

    async def record_metric(
        self,
        test_id: str,
        user_id: str,
        variant_id: str,
        metric_name: str,
        metric_value: float,
    ) -> None:
        """Record a metric value for A/B test analysis"""
        try:
            if test_id not in self.active_tests:
                return

            test_state = self.active_tests[test_id]

            if test_state["status"] != ABTestStatus.RUNNING:
                return

            # Initialize metric tracking if needed
            if metric_name not in test_state["results"]:
                test_state["results"][metric_name] = {}

            if variant_id not in test_state["results"][metric_name]:
                test_state["results"][metric_name][variant_id] = []

            # Record metric
            test_state["results"][metric_name][variant_id].append(
                {"user_id": user_id, "value": metric_value, "timestamp": datetime.now(timezone.utc)}
            )

            # Check for statistical significance periodically
            if len(test_state["results"][metric_name][variant_id]) % 100 == 0:
                await self._check_statistical_significance(test_id, metric_name)

        except Exception as e:
            logger.error(f"Failed to record metric for test {test_id}: {e}")

    async def _check_statistical_significance(self, test_id: str, metric_name: str) -> None:
        """Check statistical significance of test results"""
        try:
            test_state = self.active_tests[test_id]
            config = test_state["config"]

            if metric_name not in config.success_metrics:
                return

            results = test_state["results"].get(metric_name, {})
            control_group = config.control_group

            if control_group not in results:
                return

            # Check each treatment group against control
            for treatment_group in config.treatment_groups:
                if treatment_group not in results:
                    continue

                control_values = [r["value"] for r in results[control_group]]
                treatment_values = [r["value"] for r in results[treatment_group]]

                # Need minimum sample size
                if (
                    len(control_values) < config.minimum_sample_size
                    or len(treatment_values) < config.minimum_sample_size
                ):
                    continue

                # Perform statistical test
                significance_result = await self.statistical_analyzer.test_significance(
                    control_values, treatment_values, config.confidence_level
                )

                # Store result
                test_key = f"{metric_name}_{treatment_group}"
                test_state["statistical_significance"][test_key] = significance_result

                # Check for early stopping
                if config.early_stopping_enabled and significance_result["significant"]:
                    logger.info(
                        f"Statistical significance achieved for {test_id}, metric {metric_name}, treatment {treatment_group}"
                    )

        except Exception as e:
            logger.error(f"Failed to check statistical significance for test {test_id}: {e}")

    async def get_test_results(self, test_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current results of an A/B test"""
        if test_id not in self.active_tests:
            return {}

        test_state = self.active_tests[test_id]
        config = test_state["config"]

        results_summary: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "test_id": test_id,
            "test_name": config.test_name,
            "status": test_state["status"].value,
            "start_time": test_state["start_time"],
            "participants": test_state["participants"],
            "metrics": {},
            "statistical_significance": test_state["statistical_significance"],
        }

        # Summarize metrics
        for metric_name, metric_results in test_state["results"].items():
            results_summary["metrics"][metric_name] = {}

            for variant_id, values in metric_results.items():
                if values:
                    metric_values = [v["value"] for v in values]
                    results_summary["metrics"][metric_name][variant_id] = {
                        "count": len(metric_values),
                        "mean": statistics.mean(metric_values),
                        "std": statistics.stdev(metric_values) if len(metric_values) > 1 else 0.0,
                        "min": min(metric_values),
                        "max": max(metric_values),
                    }

        return results_summary


class TrafficRouter:
    """Traffic routing for A/B tests and gradual deployments"""

    def __init__(self) -> None:
        self.routing_rules: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.user_assignments: dict[str, str] = {}  # Consistent assignment tracking

    async def configure_test_routing(
        self, test_id: str, traffic_allocation: dict[str, float]
    ) -> None:
        """Configure traffic routing for A/B test"""
        self.routing_rules[test_id] = {
            "type": "ab_test",
            "allocation": traffic_allocation,
            "created_at": datetime.now(timezone.utc),
        }

    async def configure_deployment_routing(
        self, deployment_id: str, target_variant: str, traffic_percentage: float
    ) -> None:
        """Configure traffic routing for gradual deployment"""
        self.routing_rules[deployment_id] = {
            "type": "deployment",
            "target_variant": target_variant,
            "traffic_percentage": traffic_percentage,
            "created_at": datetime.now(timezone.utc),
        }

    async def assign_variant(
        self, rule_id: str, user_id: str, _context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Assign user to variant based on routing rules"""
        try:
            if rule_id not in self.routing_rules:
                raise ValueError(f"Routing rule {rule_id} not found")

            # Check for existing assignment (consistency)
            assignment_key = f"{rule_id}_{user_id}"
            if assignment_key in self.user_assignments:
                return self.user_assignments[assignment_key]

            rule = self.routing_rules[rule_id]

            if rule["type"] == "ab_test":
                variant = await self._assign_ab_test_variant(
                    user_id, rule["allocation"], _context if _context is not None else {}
                )
            elif rule["type"] == "deployment":
                variant = await self._assign_deployment_variant(
                    user_id, rule, _context if _context is not None else {}
                )
            else:
                raise ValueError(f"Unknown routing rule type: {rule['type']}")

            # Store assignment for consistency
            self.user_assignments[assignment_key] = variant
            return variant

        except Exception as e:
            logger.error(f"Failed to assign variant for rule {rule_id}, user {user_id}: {e}")
            # Fallback to first available variant
            if rule_id in self.routing_rules:
                rule = self.routing_rules[rule_id]
                if rule["type"] == "ab_test":
                    allocation_dict = cast(dict[str, float], rule["allocation"])
                    allocation_keys: list[str] = list(allocation_dict.keys())
                    return allocation_keys[0]
                elif rule["type"] == "deployment":
                    return "control"  # Safe fallback
            return "control"

    async def _assign_ab_test_variant(
        self,
        user_id: str,
        allocation: dict[str, float],
        _context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Assign variant for A/B test using consistent hashing"""
        # Use consistent hashing based on user_id
        hash_input = f"ab_test_{user_id}".encode()
        hash_value = int(hashlib.md5(hash_input, usedforsecurity=False).hexdigest(), 16)
        bucket = (hash_value % 100000) / 100000.0  # 0.0 to 1.0

        # Find variant based on cumulative allocation
        cumulative = 0.0
        for variant_id, percentage in allocation.items():
            cumulative += percentage
            if bucket <= cumulative:
                return variant_id

        # Fallback to last variant
        return list(allocation.keys())[-1]

    async def _assign_deployment_variant(
        self,
        user_id: str,
        rule: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        _context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Assign variant for gradual deployment"""
        # Use consistent hashing
        hash_input = f"deployment_{user_id}".encode()
        hash_value = int(hashlib.md5(hash_input, usedforsecurity=False).hexdigest(), 16)
        bucket = (hash_value % 100000) / 100000.0

        if bucket <= rule["traffic_percentage"]:
            variant: str = rule["target_variant"]
            return variant
        else:
            return "control"


class GradualDeploymentSystem:
    """Gradual deployment system for safe M-MDP rollouts"""

    def __init__(self) -> None:
        self.deployments: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.deployment_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.traffic_router = TrafficRouter()
        self.performance_monitor = PerformanceMonitor()

    async def create_deployment(self, config: DeploymentConfig) -> str:
        """Create a new gradual deployment"""
        try:
            # Initialize deployment state
            deployment_state = {
                "config": config,
                "current_phase": DeploymentPhase.DISABLED,
                "phase_start_time": datetime.now(timezone.utc),
                "metrics_history": [],
                "health_status": "healthy",
                "rollback_triggered": False,
            }

            self.deployments[config.deployment_id] = deployment_state

            logger.info(
                f"Created deployment: {config.deployment_id} for feature {config.feature_name}"
            )
            deployment_id: str = config.deployment_id
            return deployment_id

        except Exception as e:
            logger.error(f"Failed to create deployment: {e}")
            raise

    async def advance_deployment_phase(self, deployment_id: str) -> bool:
        """Advance deployment to next phase"""
        try:
            if deployment_id not in self.deployments:
                raise ValueError(f"Deployment {deployment_id} not found")

            deployment_state = self.deployments[deployment_id]
            config = cast(DeploymentConfig, deployment_state["config"])
            current_phase = cast(DeploymentPhase, deployment_state["current_phase"])

            # Determine next phase
            phase_order = [
                DeploymentPhase.DISABLED,
                DeploymentPhase.CANARY,
                DeploymentPhase.BETA,
                DeploymentPhase.STAGED,
                DeploymentPhase.FULL,
            ]

            current_index = phase_order.index(current_phase)
            if current_index >= len(phase_order) - 1:
                logger.info(f"Deployment {deployment_id} already at final phase")
                return False

            next_phase = phase_order[current_index + 1]

            # Check if ready to advance (time and metrics)
            if not await self._check_advancement_criteria(deployment_id, next_phase):
                return False

            # Update deployment state
            deployment_state["current_phase"] = next_phase
            deployment_state["phase_start_time"] = datetime.now(timezone.utc)

            # Update traffic routing
            traffic_percentage = self._get_phase_traffic_percentage(next_phase)
            await self.traffic_router.configure_deployment_routing(
                deployment_id, config.target_variant, traffic_percentage
            )

            logger.info(f"Advanced deployment {deployment_id} to phase {next_phase.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to advance deployment phase: {e}")
            return False

    def _get_phase_traffic_percentage(self, phase: DeploymentPhase) -> float:
        """Get traffic percentage for deployment phase"""
        phase_percentages = {
            DeploymentPhase.DISABLED: 0.0,
            DeploymentPhase.CANARY: 0.05,  # 5%
            DeploymentPhase.BETA: 0.20,  # 20%
            DeploymentPhase.STAGED: 0.50,  # 50%
            DeploymentPhase.FULL: 1.0,  # 100%
        }
        return phase_percentages.get(phase, 0.0)

    async def _check_advancement_criteria(
        self, deployment_id: str, next_phase: DeploymentPhase
    ) -> bool:
        """Check if deployment can advance to next phase"""
        deployment_state = self.deployments[deployment_id]
        config = deployment_state["config"]

        # Check minimum time in current phase
        time_in_phase = datetime.now(timezone.utc) - deployment_state["phase_start_time"]
        min_phase_duration = timedelta(hours=config.monitoring_window_hours)

        if time_in_phase < min_phase_duration:
            logger.info(f"Deployment {deployment_id} needs more time in current phase")
            return False

        # Check performance metrics
        recent_metrics = await self.performance_monitor.get_recent_metrics(
            deployment_id, hours=config.monitoring_window_hours
        )

        # Validate success criteria
        for metric_name, threshold in config.success_criteria.items():
            metric_values = [m.value for m in recent_metrics if m.metric_name == metric_name]
            if not metric_values:
                logger.warning(f"No data for metric {metric_name} in deployment {deployment_id}")
                return False

            avg_value = statistics.mean(metric_values)
            if avg_value < threshold:
                logger.warning(
                    f"Metric {metric_name} below threshold for deployment {deployment_id}"
                )
                return False

        # Check rollback triggers
        for metric_name, threshold in config.rollback_triggers.items():
            metric_values = [m.value for m in recent_metrics if m.metric_name == metric_name]
            if metric_values:
                avg_value = statistics.mean(metric_values)
                if avg_value > threshold:  # Assuming higher values trigger rollback
                    logger.warning(f"Rollback trigger activated for deployment {deployment_id}")
                    await self.rollback_deployment(deployment_id)
                    return False

        return True

    async def rollback_deployment(self, deployment_id: str) -> bool:
        """Rollback deployment to previous safe state"""
        try:
            if deployment_id not in self.deployments:
                return False

            deployment_state = self.deployments[deployment_id]

            # Set traffic back to 0% (control variant)
            await self.traffic_router.configure_deployment_routing(deployment_id, "control", 0.0)

            # Update state
            deployment_state["current_phase"] = DeploymentPhase.DISABLED
            deployment_state["rollback_triggered"] = True
            deployment_state["health_status"] = "rolled_back"

            logger.warning(f"Rolled back deployment {deployment_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to rollback deployment {deployment_id}: {e}")
            return False


class PerformanceMonitor:
    """Performance monitoring system for production M-MDP"""

    def __init__(self) -> None:
        self.metrics_buffer: list[PerformanceMetric] = []
        self.metric_aggregations: dict[str, list[PerformanceMetric]] = {}
        self.alert_thresholds: dict[str, dict[str, float]] = {}
        self.alert_handlers: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type

    async def record_metric(self, metric: PerformanceMetric) -> None:
        """Record a performance metric"""
        metric.timestamp = metric.timestamp or datetime.now(timezone.utc)
        self.metrics_buffer.append(metric)

        # Trigger real-time analysis if needed
        if len(self.metrics_buffer) % 100 == 0:
            await self._process_metrics_batch()

        # Check alert thresholds
        await self._check_alert_thresholds(metric)

    async def _process_metrics_batch(self) -> None:
        """Process batch of metrics for aggregation"""
        try:
            # Group metrics by type and time window
            current_time = datetime.now(timezone.utc)
            window_start = current_time - timedelta(minutes=5)  # 5-minute windows

            window_metrics = [m for m in self.metrics_buffer if m.timestamp >= window_start]

            # Aggregate by metric type
            for metric in window_metrics:
                key = f"{metric.metric_type.value}_{metric.metric_name}"
                if key not in self.metric_aggregations:
                    self.metric_aggregations[key] = []

                self.metric_aggregations[key].append(metric)

            # Cleanup old metrics
            self.metrics_buffer = [m for m in self.metrics_buffer if m.timestamp >= window_start]

        except Exception as e:
            logger.error(f"Failed to process metrics batch: {e}")

    async def _check_alert_thresholds(self, metric: PerformanceMetric) -> None:
        """Check if metric exceeds alert thresholds"""
        threshold_key = f"{metric.metric_type.value}_{metric.metric_name}"

        if threshold_key in self.alert_thresholds:
            threshold = self.alert_thresholds[threshold_key]

            if metric.value > threshold["max_value"] or metric.value < threshold["min_value"]:
                alert = {
                    "timestamp": metric.timestamp,
                    "metric": metric,
                    "threshold": threshold,
                    "severity": "high" if metric.value > threshold["critical_value"] else "medium",
                }

                for handler in self.alert_handlers:
                    await handler(alert)

    async def get_recent_metrics(
        self, deployment_id: str | None = None, hours: int = 24
    ) -> list[PerformanceMetric]:
        """Get recent metrics, optionally filtered by deployment"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        filtered_metrics = [
            m
            for m in self.metrics_buffer
            if m.timestamp >= cutoff_time
            and (deployment_id is None or m.deployment_id == deployment_id)
        ]

        return filtered_metrics

    def add_alert_threshold(
        self,
        metric_type: MetricType,
        metric_name: str,
        min_value: float,
        max_value: float,
        critical_value: float,
    ) -> None:
        """Add alert threshold for a metric"""
        key = f"{metric_type.value}_{metric_name}"
        self.alert_thresholds[key] = {
            "min_value": min_value,
            "max_value": max_value,
            "critical_value": critical_value,
        }

    def add_alert_handler(self, handler: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add alert handler function"""
        self.alert_handlers.append(handler)


class StatisticalAnalyzer:
    """Statistical analysis for A/B tests and performance comparisons"""

    async def test_significance(
        self,
        control_values: list[float],
        treatment_values: list[float],
        confidence_level: float = 0.95,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Test statistical significance between control and treatment groups"""
        try:
            if len(control_values) < 30 or len(treatment_values) < 30:
                result: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                    "significant": False,
                    "reason": "Insufficient sample size (minimum 30 per group)",
                    "p_value": None,
                    "effect_size": None,
                }
                return result

            # Calculate basic statistics
            control_mean = statistics.mean(control_values)
            treatment_mean = statistics.mean(treatment_values)
            control_std = statistics.stdev(control_values)
            treatment_std = statistics.stdev(treatment_values)

            # Calculate effect size (Cohen's d)
            pooled_std = (
                (len(control_values) - 1) * control_std**2
                + (len(treatment_values) - 1) * treatment_std**2
            ) / (len(control_values) + len(treatment_values) - 2)
            pooled_std = pooled_std**0.5

            effect_size = (treatment_mean - control_mean) / pooled_std if pooled_std > 0 else 0

            # Simple t-test approximation (in production, use scipy.stats)
            # This is a simplified implementation
            se_diff = (
                control_std**2 / len(control_values) + treatment_std**2 / len(treatment_values)
            ) ** 0.5
            t_stat = (treatment_mean - control_mean) / se_diff if se_diff > 0 else 0

            # Approximate p-value (simplified)
            # In production, use proper statistical libraries
            p_value = 2 * (1 - abs(t_stat) / (abs(t_stat) + 1))  # Rough approximation

            alpha = 1 - confidence_level
            significant = p_value < alpha

            return {
                "significant": significant,
                "p_value": p_value,
                "effect_size": effect_size,
                "control_mean": control_mean,
                "treatment_mean": treatment_mean,
                "control_std": control_std,
                "treatment_std": treatment_std,
                "control_n": len(control_values),
                "treatment_n": len(treatment_values),
                "confidence_level": confidence_level,
            }

        except Exception as e:
            logger.error(f"Failed to test significance: {e}")
            return {
                "significant": False,
                "reason": f"Statistical test failed: {str(e)}",
                "p_value": None,
                "effect_size": None,
            }


# Global instances
ab_testing_framework = ABTestingFramework()
gradual_deployment_system = GradualDeploymentSystem()
performance_monitor = PerformanceMonitor()
statistical_analyzer = StatisticalAnalyzer()

# Export main components
__all__ = [
    "DeploymentPhase",
    "ABTestStatus",
    "MetricType",
    "ABTestConfiguration",
    "ABTestVariant",
    "ABTestResult",
    "DeploymentConfig",
    "PerformanceMetric",
    "ABTestingFramework",
    "TrafficRouter",
    "GradualDeploymentSystem",
    "PerformanceMonitor",
    "StatisticalAnalyzer",
    "ab_testing_framework",
    "gradual_deployment_system",
    "performance_monitor",
    "statistical_analyzer",
]
