"""ML Monitoring with Prometheus metrics."""

import logging
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, Info

logger = logging.getLogger(__name__)

# Prometheus metrics for ML
ML_PREDICTIONS_TOTAL = Counter(
    "ml_predictions_total",
    "Total ML predictions made",
    ["pack_id", "confidence_bucket", "score_source"],
)

ML_PREDICTION_LATENCY = Histogram(
    "ml_prediction_latency_seconds",
    "ML prediction latency in seconds",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

ML_MODEL_ACCURACY = Gauge("ml_model_accuracy", "Current model accuracy on test set")

ML_MODEL_PRECISION = Gauge("ml_model_precision", "Current model precision on test set")

ML_MODEL_RECALL = Gauge("ml_model_recall", "Current model recall on test set")

ML_TRAINING_SAMPLES = Gauge("ml_training_samples", "Number of samples used for last training")

ML_MODEL_INFO = Info("ml_model", "ML model metadata")

ML_PREDICTION_ERRORS = Counter(
    "ml_prediction_errors_total", "Total ML prediction errors", ["error_type"]
)


class MLMonitor:
    """Monitor ML model performance and expose metrics."""

    @staticmethod
    def log_prediction(
        pack_id: str,
        score: float,
        latency_ms: float,
        score_source: str = "ml_blend",
    ) -> None:
        """Log a prediction with its metrics."""
        # Determine confidence bucket
        if score >= 0.8:
            bucket = "high"
        elif score >= 0.6:
            bucket = "medium"
        else:
            bucket = "low"

        ML_PREDICTIONS_TOTAL.labels(
            pack_id=pack_id,
            confidence_bucket=bucket,
            score_source=score_source,
        ).inc()

        ML_PREDICTION_LATENCY.observe(latency_ms / 1000)

    @staticmethod
    def log_training_metrics(
        accuracy: float,
        precision: float,
        recall: float,
        sample_count: int,
        model_version: str = "1.0.0",
    ) -> None:
        """Log training metrics."""
        ML_MODEL_ACCURACY.set(accuracy)
        ML_MODEL_PRECISION.set(precision)
        ML_MODEL_RECALL.set(recall)
        ML_TRAINING_SAMPLES.set(sample_count)
        ML_MODEL_INFO.info({"version": model_version})

    @staticmethod
    def log_error(error_type: str) -> None:
        """Log a prediction error."""
        ML_PREDICTION_ERRORS.labels(error_type=error_type).inc()

    @staticmethod
    def get_metrics_summary() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current metrics summary for health checks."""
        return {
            "model_accuracy": ML_MODEL_ACCURACY._value.get(),
            "model_precision": ML_MODEL_PRECISION._value.get(),
            "model_recall": ML_MODEL_RECALL._value.get(),
            "training_samples": ML_TRAINING_SAMPLES._value.get(),
        }
