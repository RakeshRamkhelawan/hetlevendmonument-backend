import time
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram


class SecurityMetrics:
    def __init__(self) -> None:
        self.token_validation_duration = Histogram(
            "token_validation_seconds",
            "Time spent validating tokens",
            buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0],
        )

        self.validation_failures = Counter(
            "token_validation_failures_total",
            "Number of token validation failures",
            ["reason"],
        )

        self.active_sessions = Gauge("active_sessions", "Number of currently active sessions")

        self.migration_progress = Gauge(
            "token_migration_progress", "Percentage of tokens migrated to new system"
        )

    def track_validation(
        self, start_time: float, success: bool, reason: str | None = None
    ) -> None:
        duration = time.time() - start_time
        self.token_validation_duration.observe(duration)

        if not success:
            self.validation_failures.labels(reason=reason).inc()

    def update_session_count(self, count: int) -> None:
        self.active_sessions.set(count)

    def update_migration_progress(self, percentage: float) -> None:
        self.migration_progress.set(percentage)


metrics = SecurityMetrics()
