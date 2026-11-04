"""ML Prediction Service for pack recommendations with caching."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional, Protocol, cast
from collections.abc import Callable

from src.core.config.config import get_settings

# Try to import data collector, may not exist yet
MLDataCollector: Any  # TODO(TYPE): replace Any with concrete type
try:
    from src.ml.data_collector import MLDataCollector
except ImportError:
    MLDataCollector = None

logger = logging.getLogger(__name__)


class _DataCollector(Protocol):
    async def get_company_features(self, company_id: str) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type
    async def get_department_features(self, department_id: str) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type


class MLPredictionService:
    """
    Singleton service for ML pack recommendations.
    Caches model in memory for fast inference.
    """

    _instance: ClassVar[Optional["MLPredictionService"]] = None
    _model: Any | None = None  # TODO(TYPE): replace Any with concrete type
    _model_loaded_at: datetime | None = None
    _model_version: str = "1.0.0"

    def __new__(cls) -> "MLPredictionService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def load_model(self) -> bool:
        """Load model from disk."""
        from src.ml.pack_recommendation_model import PackRecommendationModel

        try:
            settings = get_settings()
            self._model = PackRecommendationModel(
                model_path=getattr(settings, "ml_model_path", "models/pack_recommendation.pkl")
            )
            self._model.load()
            self._model_loaded_at = datetime.now(timezone.utc)
            logger.info("ML model loaded successfully")
            return True
        except FileNotFoundError:
            logger.warning("ML model file not found, predictions unavailable")
            return False
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            return False

    def _get_cache_key(self, company_id: str, department_id: str, pack_id: str) -> str:
        """Generate cache key for prediction."""
        return f"{company_id}:{department_id}:{pack_id}"

    async def predict(self, company_id: str, department_id: str, pack_id: str) -> float | None:
        """
        Predict pack suitability score.
        Returns None if ML unavailable.
        """
        from src.ml.feature_engineering import PackFeatureEngineer
        from src.ml.monitoring import MLMonitor

        start_time = time.time()

        # Load model if needed
        model = self._model
        if model is None:
            success = await self.load_model()
            if not success:
                return None
            model = self._model
            if model is None:
                return None

        # Check if data collector is available
        if MLDataCollector is None:
            logger.warning("MLDataCollector not available, predictions unavailable")
            return None

        try:
            # Collect features
            collector = cast(
                _DataCollector,
                cast(Callable[[], Any], MLDataCollector)(),  # TODO(TYPE): replace Any with concrete type
            )
            company_features = await collector.get_company_features(company_id)
            dept_features = await collector.get_department_features(department_id)

            # Engineer features
            engineer = cast(Callable[[], PackFeatureEngineer], PackFeatureEngineer)()
            features: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                **engineer.extract_company_features(company_features),
                **engineer.extract_department_features(dept_features),
            }

            # Predict
            score = model.predict(features)

            # Log metrics
            latency_ms = (time.time() - start_time) * 1000
            logger.debug(f"ML prediction for pack {pack_id}: {score:.3f} ({latency_ms:.1f}ms)")

            # Log to Prometheus metrics
            MLMonitor.log_prediction(
                pack_id=pack_id,
                score=score,
                latency_ms=latency_ms,
                score_source="ml_blend",
            )

            prediction_score: float | None = score
            return prediction_score

        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            MLMonitor.log_error(error_type="prediction_failed")
            return None

    def get_model_info(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get model metadata."""
        return {
            "loaded": self._model is not None,
            "loaded_at": self._model_loaded_at.isoformat() if self._model_loaded_at else None,
            "version": self._model_version,
        }

    def reload_model(self) -> None:
        """Reload model from disk (after retraining)."""
        self._model = None
        self._model_loaded_at = None
        logger.info("ML model cache cleared, will reload on next prediction")


# Global singleton instance
ml_prediction_service = MLPredictionService()
