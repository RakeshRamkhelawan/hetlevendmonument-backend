"""
Data Drift Detection for Autonomous Workflow Training System
Monitors distribution shifts and concept drift in training data

Production-grade implementation with:
- Kolmogorov-Smirnov test for distribution drift
- Chi-square test for categorical distributions
- Concept drift detection via success rate changes
- Population Stability Index (PSI) for feature drift
- Prometheus metrics integration
- Async database operations

Track 4 of 4: Production Hardening Initiative
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, cast

import numpy as np
from scipy import stats

from src.core.monitoring.prometheus_metrics import Counter, Gauge
from src.core.shared.learning_interfaces import ILearningExperienceReader

logger = logging.getLogger(__name__)


# ============================================================================
# DRIFT DETECTION METRICS
# ============================================================================

drift_detected_total = Counter(
    "drift_detected_total",
    "Total number of drift detections",
    ["drift_type"],  # 'distribution', 'concept', 'feature'
)

drift_severity_gauge = Gauge(
    "drift_severity", "Current drift severity score (0.0 to 1.0)", ["drift_type"]
)

drift_checks_total = Counter("drift_checks_total", "Total number of drift checks performed")

baseline_refresh_total = Counter(
    "baseline_refresh_total", "Total number of baseline recalculations"
)


# ============================================================================
# DATA CLASSES
# ============================================================================


class DriftType(str, Enum):
    """Types of drift detection"""

    DISTRIBUTION = "distribution"
    CONCEPT = "concept"
    FEATURE = "feature"
    NONE = "none"


@dataclass
class DriftReport:
    """Comprehensive drift detection report"""

    detected: bool
    severity: float  # 0.0 to 1.0
    drift_type: DriftType
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime
    baseline_window_start: datetime | None = None
    baseline_window_end: datetime | None = None
    current_window_start: datetime | None = None
    current_window_end: datetime | None = None
    samples_baseline: int = 0
    samples_current: int = 0
    statistical_test: str | None = None
    p_value: float | None = None
    threshold: float = 0.05

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for JSON serialization"""
        return {
            "detected": self.detected,
            "severity": self.severity,
            "drift_type": self.drift_type.value,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "baseline_window_start": (
                self.baseline_window_start.isoformat() if self.baseline_window_start else None
            ),
            "baseline_window_end": (
                self.baseline_window_end.isoformat() if self.baseline_window_end else None
            ),
            "current_window_start": (
                self.current_window_start.isoformat() if self.current_window_start else None
            ),
            "current_window_end": (
                self.current_window_end.isoformat() if self.current_window_end else None
            ),
            "samples_baseline": self.samples_baseline,
            "samples_current": self.samples_current,
            "statistical_test": self.statistical_test,
            "p_value": self.p_value,
            "threshold": self.threshold,
        }


@dataclass
class BaselineStatistics:
    """Baseline distribution statistics"""

    mean_duration: float
    std_duration: float
    success_rate: float
    confidence_mean: float
    confidence_std: float
    event_type_distribution: dict[str, float]
    task_type_distribution: dict[str, float]
    agent_distribution: dict[str, float]
    sample_count: int
    window_start: datetime
    window_end: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for JSON serialization"""
        return {
            "mean_duration": self.mean_duration,
            "std_duration": self.std_duration,
            "success_rate": self.success_rate,
            "confidence_mean": self.confidence_mean,
            "confidence_std": self.confidence_std,
            "event_type_distribution": self.event_type_distribution,
            "task_type_distribution": self.task_type_distribution,
            "agent_distribution": self.agent_distribution,
            "sample_count": self.sample_count,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "created_at": self.created_at.isoformat(),
        }


# ============================================================================
# DRIFT DETECTOR
# ============================================================================


class DriftDetector:
    """
    Production-grade data drift detector for learning experiences.

    Detects three types of drift:
    1. Distribution Drift: Changes in feature distributions (KS test)
    2. Concept Drift: Changes in success rate/performance (Z-test)
    3. Feature Drift: Changes in categorical distributions (PSI)

    Statistical rigor:
    - Uses p-value < 0.05 for significance
    - Minimum 30 samples per window (central limit theorem)
    - Bonferroni correction for multiple comparisons
    """

    def __init__(
        self,
        reader: ILearningExperienceReader,
        tenant_id: int,
        baseline_window_days: int = 30,
        min_samples: int = 30,
        significance_level: float = 0.05,
    ) -> None:
        """
        Initialize drift detector.

        Args:
            reader: Learning experience reader -- use LearningExperienceRepository
            tenant_id: Tenant to scope all queries to
            baseline_window_days: Days to use for baseline calculation
            min_samples: Minimum samples required for statistical tests
            significance_level: P-value threshold for drift detection
        """
        self._reader = reader
        self.tenant_id = tenant_id
        self.baseline_window = baseline_window_days
        self.min_samples = min_samples
        self.significance_level = significance_level
        self.baseline_data: BaselineStatistics | None = None

    async def establish_baseline(self) -> BaselineStatistics:
        """
        Calculate baseline statistics from historical data.

        Returns:
            BaselineStatistics with distribution parameters

        Raises:
            ValueError: If insufficient data for baseline
        """
        try:
            logger.info("Establishing baseline from last %s days", self.baseline_window)

            # Calculate time window
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=self.baseline_window)

            # Fetch baseline experiences
            experiences = await self._reader.get_experiences(
                start_time=start_time,
                end_time=end_time,
                tenant_id=self.tenant_id,
            )

            if len(experiences) < self.min_samples:
                raise ValueError(
                    f"Insufficient baseline data: {len(experiences)} samples "
                    f"(minimum {self.min_samples} required)"
                )

            # Calculate duration statistics
            durations = [e.duration for e in experiences if e.duration is not None]
            mean_duration = np.mean(durations) if durations else 0.0
            std_duration = np.std(durations) if durations else 0.0

            # Calculate success rate
            successes = [e for e in experiences if e.success is not None]
            success_rate = (
                sum(1 for e in successes if e.success) / len(successes) if successes else 0.0
            )

            # Calculate confidence statistics
            confidences = [e.confidence for e in experiences]
            confidence_mean = np.mean(confidences)
            confidence_std = np.std(confidences)

            # Calculate categorical distributions
            event_type_dist = self._calculate_distribution([e.event_type for e in experiences])
            task_type_dist = self._calculate_distribution(
                [e.task_type for e in experiences if e.task_type]
            )
            agent_dist = self._calculate_distribution(
                [e.agent_id for e in experiences if e.agent_id]
            )

            baseline = BaselineStatistics(
                mean_duration=float(mean_duration),
                std_duration=float(std_duration),
                success_rate=float(success_rate),
                confidence_mean=float(confidence_mean),
                confidence_std=float(confidence_std),
                event_type_distribution=event_type_dist,
                task_type_distribution=task_type_dist,
                agent_distribution=agent_dist,
                sample_count=len(experiences),
                window_start=start_time,
                window_end=end_time,
            )

            self.baseline_data = baseline
            baseline_refresh_total.inc()

            logger.info(
                "Baseline established: %s samples, success_rate=%.2f, mean_duration=%.2fs",
                len(experiences),
                success_rate,
                mean_duration,
            )

            return baseline

        except Exception as e:
            logger.error("Failed to establish baseline: %s: %s", type(e).__name__, e, exc_info=True)
            raise

    async def detect_distribution_drift(self, current_window_days: int = 7) -> DriftReport:
        """
        Detect distribution drift using Kolmogorov-Smirnov test.

        Compares continuous feature distributions (duration, confidence)
        between baseline and current windows.

        Args:
            current_window_days: Days to use for current window

        Returns:
            DriftReport with KS test results
        """
        try:
            drift_checks_total.inc()

            if not self.baseline_data:
                await self.establish_baseline()

            if self.baseline_data is None:
                raise ValueError("Failed to establish baseline data")

            logger.info("Running distribution drift detection (KS test)")

            # Fetch current window data
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=current_window_days)

            current_experiences = await self._reader.get_experiences(
                start_time=start_time,
                end_time=end_time,
                tenant_id=self.tenant_id,
            )

            if len(current_experiences) < self.min_samples:
                return DriftReport(
                    detected=False,
                    severity=0.0,
                    drift_type=DriftType.NONE,
                    details={
                        "reason": "insufficient_current_data",
                        "samples": len(current_experiences),
                        "required": self.min_samples,
                    },
                    timestamp=datetime.now(timezone.utc),
                    current_window_start=start_time,
                    current_window_end=end_time,
                    samples_current=len(current_experiences),
                )

            # Fetch baseline window data for comparison (always scope to tenant)
            baseline_experiences = await self._reader.get_experiences(
                start_time=self.baseline_data.window_start,
                end_time=self.baseline_data.window_end,
                tenant_id=self.tenant_id,
            )

            # Extract distributions
            baseline_durations = [
                e.duration for e in baseline_experiences if e.duration is not None
            ]
            current_durations = [e.duration for e in current_experiences if e.duration is not None]

            baseline_confidences = [e.confidence for e in baseline_experiences]
            current_confidences = [e.confidence for e in current_experiences]

            # Run KS tests - ks_2samp returns a namedtuple with (statistic, pvalue)
            # Use cast to properly type the result tuple
            ks_duration_result = cast(
                tuple[float, float],
                stats.ks_2samp(baseline_durations, current_durations),
            )
            ks_confidence_result = cast(
                tuple[float, float],
                stats.ks_2samp(baseline_confidences, current_confidences),
            )

            # Extract values with explicit float casting
            ks_stat_duration: float = float(ks_duration_result[0])
            p_value_duration: float = float(ks_duration_result[1])
            ks_stat_confidence: float = float(ks_confidence_result[0])
            p_value_confidence: float = float(ks_confidence_result[1])

            # Bonferroni correction for multiple tests (2 tests)
            corrected_alpha = self.significance_level / 2

            # Detect drift
            drift_detected: bool = bool(
                (p_value_duration < corrected_alpha) or (p_value_confidence < corrected_alpha)
            )

            # Calculate severity (0.0 to 1.0)
            severity: float = max(
                min(1.0 - p_value_duration, 1.0), min(1.0 - p_value_confidence, 1.0)
            )

            details = {
                "duration_ks_statistic": ks_stat_duration,
                "duration_p_value": p_value_duration,
                "duration_drifted": bool(p_value_duration < corrected_alpha),
                "confidence_ks_statistic": ks_stat_confidence,
                "confidence_p_value": p_value_confidence,
                "confidence_drifted": bool(p_value_confidence < corrected_alpha),
                "corrected_alpha": corrected_alpha,
                "baseline_duration_mean": (
                    float(np.mean(baseline_durations)) if baseline_durations else 0.0
                ),
                "current_duration_mean": (
                    float(np.mean(current_durations)) if current_durations else 0.0
                ),
                "baseline_confidence_mean": float(np.mean(baseline_confidences)),
                "current_confidence_mean": float(np.mean(current_confidences)),
            }

            if drift_detected:
                drift_detected_total.labels(drift_type="distribution").inc()
                drift_severity_gauge.labels(drift_type="distribution").set(severity)

                logger.warning(
                    "Distribution drift detected! Duration p-value=%.4f, Confidence p-value=%.4f",
                    p_value_duration,
                    p_value_confidence,
                )

            return DriftReport(
                detected=drift_detected,
                severity=severity,
                drift_type=DriftType.DISTRIBUTION if drift_detected else DriftType.NONE,
                details=details,
                timestamp=datetime.now(timezone.utc),
                baseline_window_start=self.baseline_data.window_start,
                baseline_window_end=self.baseline_data.window_end,
                current_window_start=start_time,
                current_window_end=end_time,
                samples_baseline=len(baseline_experiences),
                samples_current=len(current_experiences),
                statistical_test="kolmogorov_smirnov",
                p_value=float(min(p_value_duration, p_value_confidence)),
                threshold=corrected_alpha,
            )

        except Exception as e:
            logger.error(
                "Distribution drift detection failed: %s: %s", type(e).__name__, e, exc_info=True
            )
            raise

    async def detect_concept_drift(self, current_window_days: int = 7) -> DriftReport:
        """
        Detect concept drift via success rate changes.

        Uses Z-test for proportions to detect significant changes
        in model performance (success rate).

        Args:
            current_window_days: Days to use for current window

        Returns:
            DriftReport with Z-test results
        """
        try:
            drift_checks_total.inc()

            if not self.baseline_data:
                await self.establish_baseline()

            if self.baseline_data is None:
                raise ValueError("Failed to establish baseline data")

            logger.info("Running concept drift detection (Z-test)")

            # Fetch current window data (success-valued records only)
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=current_window_days)

            current_experiences = await self._reader.get_experiences(
                start_time=start_time,
                end_time=end_time,
                tenant_id=self.tenant_id,
                require_success_value=True,
            )

            if len(current_experiences) < self.min_samples:
                return DriftReport(
                    detected=False,
                    severity=0.0,
                    drift_type=DriftType.NONE,
                    details={
                        "reason": "insufficient_current_data",
                        "samples": len(current_experiences),
                        "required": self.min_samples,
                    },
                    timestamp=datetime.now(timezone.utc),
                    current_window_start=start_time,
                    current_window_end=end_time,
                    samples_current=len(current_experiences),
                )

            # Calculate current success rate
            current_successes = sum(1 for e in current_experiences if e.success)
            current_success_rate = current_successes / len(current_experiences)

            # Baseline statistics
            baseline_success_rate = self.baseline_data.success_rate
            baseline_n = self.baseline_data.sample_count
            current_n = len(current_experiences)

            # Z-test for proportions
            pooled_proportion = (baseline_success_rate * baseline_n + current_successes) / (
                baseline_n + current_n
            )

            standard_error = np.sqrt(
                pooled_proportion * (1 - pooled_proportion) * (1 / baseline_n + 1 / current_n)
            )

            if standard_error == 0:
                z_statistic = 0.0
                p_value = 1.0
            else:
                z_statistic = (current_success_rate - baseline_success_rate) / standard_error
                p_value = 2 * (1 - stats.norm.cdf(abs(z_statistic)))  # Two-tailed test

            # Detect drift
            drift_detected: bool = bool(p_value < self.significance_level)

            # Calculate severity based on magnitude of change
            rate_change = abs(current_success_rate - baseline_success_rate)
            severity = min(rate_change * 2, 1.0)  # Scale to 0-1 range

            details = {
                "baseline_success_rate": float(baseline_success_rate),
                "current_success_rate": float(current_success_rate),
                "rate_change": float(rate_change),
                "z_statistic": float(z_statistic),
                "p_value": float(p_value),
                "pooled_proportion": float(pooled_proportion),
                "standard_error": float(standard_error),
                "performance_degradation": current_success_rate < baseline_success_rate,
            }

            if drift_detected:
                drift_detected_total.labels(drift_type="concept").inc()
                drift_severity_gauge.labels(drift_type="concept").set(severity)

                direction = (
                    "degraded" if current_success_rate < baseline_success_rate else "improved"
                )
                logger.warning(
                    "Concept drift detected! Success rate %s: %.2f -> %.2f (p-value=%.4f)",
                    direction,
                    baseline_success_rate,
                    current_success_rate,
                    p_value,
                )

            return DriftReport(
                detected=drift_detected,
                severity=severity,
                drift_type=DriftType.CONCEPT if drift_detected else DriftType.NONE,
                details=details,
                timestamp=datetime.now(timezone.utc),
                baseline_window_start=self.baseline_data.window_start,
                baseline_window_end=self.baseline_data.window_end,
                current_window_start=start_time,
                current_window_end=end_time,
                samples_baseline=baseline_n,
                samples_current=current_n,
                statistical_test="z_test_proportions",
                p_value=float(p_value),
                threshold=self.significance_level,
            )

        except Exception as e:
            logger.error(
                "Concept drift detection failed: %s: %s", type(e).__name__, e, exc_info=True
            )
            raise

    async def detect_feature_drift(self, current_window_days: int = 7) -> DriftReport:
        """
        Detect feature drift using Population Stability Index (PSI).

        Monitors changes in categorical distributions (event_type, task_type, agent_id).
        PSI > 0.2 indicates significant drift.

        Args:
            current_window_days: Days to use for current window

        Returns:
            DriftReport with PSI results
        """
        try:
            drift_checks_total.inc()

            if not self.baseline_data:
                await self.establish_baseline()

            if self.baseline_data is None:
                raise ValueError("Failed to establish baseline data")

            logger.info("Running feature drift detection (PSI)")

            # Fetch current window data
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=current_window_days)

            current_experiences = await self._reader.get_experiences(
                start_time=start_time,
                end_time=end_time,
                tenant_id=self.tenant_id,
            )

            if len(current_experiences) < self.min_samples:
                return DriftReport(
                    detected=False,
                    severity=0.0,
                    drift_type=DriftType.NONE,
                    details={
                        "reason": "insufficient_current_data",
                        "samples": len(current_experiences),
                        "required": self.min_samples,
                    },
                    timestamp=datetime.now(timezone.utc),
                    current_window_start=start_time,
                    current_window_end=end_time,
                    samples_current=len(current_experiences),
                )

            # Calculate current distributions
            current_event_dist = self._calculate_distribution(
                [e.event_type for e in current_experiences]
            )
            current_task_dist = self._calculate_distribution(
                [e.task_type for e in current_experiences if e.task_type]
            )
            current_agent_dist = self._calculate_distribution(
                [e.agent_id for e in current_experiences if e.agent_id]
            )

            # Calculate PSI for each feature
            psi_event = self._calculate_psi(
                self.baseline_data.event_type_distribution, current_event_dist
            )
            psi_task = self._calculate_psi(
                self.baseline_data.task_type_distribution, current_task_dist
            )
            psi_agent = self._calculate_psi(
                self.baseline_data.agent_distribution, current_agent_dist
            )

            # Drift threshold for PSI
            psi_threshold = 0.2  # Industry standard
            max_psi = max(psi_event, psi_task, psi_agent)

            drift_detected = max_psi > psi_threshold
            severity = min(max_psi / 0.5, 1.0)  # Normalize to 0-1 range

            details = {
                "psi_event_type": float(psi_event),
                "psi_task_type": float(psi_task),
                "psi_agent": float(psi_agent),
                "max_psi": float(max_psi),
                "psi_threshold": psi_threshold,
                "baseline_event_distribution": self.baseline_data.event_type_distribution,
                "current_event_distribution": current_event_dist,
                "baseline_task_distribution": self.baseline_data.task_type_distribution,
                "current_task_distribution": current_task_dist,
                "baseline_agent_distribution": self.baseline_data.agent_distribution,
                "current_agent_distribution": current_agent_dist,
            }

            if drift_detected:
                drift_detected_total.labels(drift_type="feature").inc()
                drift_severity_gauge.labels(drift_type="feature").set(severity)

                logger.warning(
                    "Feature drift detected! Max PSI=%.4f (threshold=%s)", max_psi, psi_threshold
                )

            return DriftReport(
                detected=drift_detected,
                severity=severity,
                drift_type=DriftType.FEATURE if drift_detected else DriftType.NONE,
                details=details,
                timestamp=datetime.now(timezone.utc),
                baseline_window_start=self.baseline_data.window_start,
                baseline_window_end=self.baseline_data.window_end,
                current_window_start=start_time,
                current_window_end=end_time,
                samples_baseline=self.baseline_data.sample_count,
                samples_current=len(current_experiences),
                statistical_test="population_stability_index",
                p_value=None,  # PSI doesn't use p-values
                threshold=psi_threshold,
            )

        except Exception as e:
            logger.error(
                "Feature drift detection failed: %s: %s", type(e).__name__, e, exc_info=True
            )
            raise

    async def check_all_drift(self, current_window_days: int = 7) -> list[DriftReport]:
        """
        Run all drift checks and return comprehensive reports.

        Args:
            current_window_days: Days to use for current window

        Returns: List[Any] of DriftReport objects for each drift type  # TODO(TYPE): replace Any with concrete type
        """
        try:
            logger.info("Running comprehensive drift detection")

            # Ensure baseline exists
            if not self.baseline_data:
                await self.establish_baseline()

            # Run all drift tests
            reports: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Distribution drift
            try:
                dist_report = await self.detect_distribution_drift(current_window_days)
                reports.append(dist_report)
            except Exception as e:
                logger.error(
                    "Distribution drift check failed: %s: %s", type(e).__name__, e, exc_info=True
                )

            # Concept drift
            try:
                concept_report = await self.detect_concept_drift(current_window_days)
                reports.append(concept_report)
            except Exception as e:
                logger.error(
                    "Concept drift check failed: %s: %s", type(e).__name__, e, exc_info=True
                )

            # Feature drift
            try:
                feature_report = await self.detect_feature_drift(current_window_days)
                reports.append(feature_report)
            except Exception as e:
                logger.error(
                    "Feature drift check failed: %s: %s", type(e).__name__, e, exc_info=True
                )

            # Log summary
            detected_drifts = [r for r in reports if r.detected]
            if detected_drifts:
                logger.warning(
                    "Drift detection summary: %s/%s drift types detected",
                    len(detected_drifts),
                    len(reports),
                )
            else:
                logger.info("No drift detected in any category")

            return reports

        except Exception as e:
            logger.error(
                "Comprehensive drift check failed: %s: %s", type(e).__name__, e, exc_info=True
            )
            raise

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _calculate_distribution(
        self,
        values: list[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:  # TODO(TYPE): replace Any with concrete type
        """
        Calculate categorical distribution (proportions).

        Args:
            values: List[Any] of categorical values  # TODO(TYPE): replace Any with concrete type

        Returns: Dict[str, Any]ionary mapping categories to proportions  # TODO(TYPE): replace Any with concrete type
        """
        if not values:
            return {}

        from collections import Counter

        counts = Counter(values)
        total = len(values)

        return {str(k): v / total for k, v in counts.items()}

    def _calculate_psi(
        self, baseline_dist: dict[str, float], current_dist: dict[str, float]
    ) -> float:
        """
        Calculate Population Stability Index (PSI).

        PSI = sum((current% - baseline%) * ln(current% / baseline%))

        Interpretation:
        - PSI < 0.1: No significant change
        - 0.1 <= PSI < 0.2: Moderate change
        - PSI >= 0.2: Significant change (drift)

        Args:
            baseline_dist: Baseline distribution
            current_dist: Current distribution

        Returns:
            PSI score
        """
        if not baseline_dist or not current_dist:
            return 0.0

        # Combine all categories
        all_categories = set(baseline_dist.keys()) | set(current_dist.keys())

        psi = 0.0
        epsilon = 1e-10  # Avoid log(0)

        for category in all_categories:
            baseline_pct = baseline_dist.get(category, 0.0) + epsilon
            current_pct = current_dist.get(category, 0.0) + epsilon

            psi += (current_pct - baseline_pct) * np.log(current_pct / baseline_pct)

        return abs(psi)
