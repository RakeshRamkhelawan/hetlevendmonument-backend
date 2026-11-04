"""
Predictive Analytics Engine - Future state prediction and trend analysis
Implements time series forecasting and predictive modeling for system optimization
"""

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from collections.abc import Awaitable, Callable
from typing import Any, NotRequired, Optional, TypedDict, cast

from src.core.caching import cache_system
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class PredictionType(Enum):
    """Types of predictions"""

    LOAD_FORECAST = "load_forecast"
    PERFORMANCE_TREND = "performance_trend"
    RESOURCE_DEMAND = "resource_demand"
    USER_BEHAVIOR = "user_behavior"
    SYSTEM_HEALTH = "system_health"
    CAPACITY_PLANNING = "capacity_planning"
    ANOMALY_DETECTION = "anomaly_detection"


class TimeHorizon(Enum):
    """Prediction time horizons"""

    SHORT_TERM = "short_term"  # Next 1 hour
    MEDIUM_TERM = "medium_term"  # Next 24 hours
    LONG_TERM = "long_term"  # Next 7 days


class PredictionConfidence(Enum):
    """Prediction confidence levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class _ForecastResult(TypedDict):
    """Typed result returned by forecasting models."""

    forecast: list[float]
    accuracy: NotRequired[float]


@dataclass
class PredictionRequest:
    """Request for prediction analysis"""

    request_id: str
    prediction_type: PredictionType
    time_horizon: TimeHorizon
    target_metrics: list[str]
    historical_data: dict[str, list[float]]
    context: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "prediction_type": self.prediction_type.value,
            "time_horizon": self.time_horizon.value,
            "target_metrics": self.target_metrics,
            "historical_data": self.historical_data,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PredictionResult:
    """Result of prediction analysis"""

    request_id: str
    prediction_type: PredictionType
    predictions: dict[str, list[float]]
    confidence: PredictionConfidence
    confidence_score: float
    time_points: list[str]
    trends: dict[str, str]
    anomalies: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    recommendations: list[str]
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "prediction_type": self.prediction_type.value,
            "predictions": self.predictions,
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "time_points": self.time_points,
            "trends": self.trends,
            "anomalies": self.anomalies,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class TimeSeriesAnalyzer:
    """Analyzes time series data for patterns and trends"""

    def __init__(self) -> None:
        self.seasonal_patterns: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.trend_cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    def analyze_trend(
        self, data: list[float], time_points: list[datetime] | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze trend in time series data"""
        if len(data) < 3:
            return {
                "trend": "insufficient_data",
                "strength": 0.0,
                "direction": "unknown",
            }

        try:
            # Simple linear trend analysis
            x = list(range(len(data)))
            y = data

            # Calculate linear regression
            n = len(data)
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(xi * yi for xi, yi in zip(x, y))
            sum_x2 = sum(xi * xi for xi in x)

            # Slope (trend direction and strength)
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

            # Correlation coefficient (trend strength)
            mean_x = sum_x / n
            mean_y = sum_y / n

            numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
            denominator_x = sum((xi - mean_x) ** 2 for xi in x)
            denominator_y = sum((yi - mean_y) ** 2 for yi in y)

            if denominator_x > 0 and denominator_y > 0:
                correlation = numerator / (math.sqrt(denominator_x) * math.sqrt(denominator_y))
            else:
                correlation = 0

            # Determine trend direction
            if abs(slope) < 0.01:
                direction = "stable"
            elif slope > 0:
                direction = "increasing"
            else:
                direction = "decreasing"

            # Trend strength based on correlation
            strength = abs(correlation)

            return {
                "trend": direction,
                "strength": strength,
                "direction": direction,
                "slope": slope,
                "correlation": correlation,
            }

        except Exception as e:
            logger.error(f"Trend analysis failed: {e}")
            return {"trend": "error", "strength": 0.0, "direction": "unknown"}

    def detect_seasonality(
        self, data: list[float], period: int = 24
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Detect seasonal patterns in data"""
        if len(data) < period * 2:
            return {"seasonal": False, "period": 0, "strength": 0.0}

        try:
            # Simple seasonal detection using autocorrelation
            n = len(data)
            mean_val = statistics.mean(data)

            # Calculate autocorrelation at specified period
            numerator = sum(
                (data[i] - mean_val) * (data[i - period] - mean_val) for i in range(period, n)
            )

            denominator = sum((x - mean_val) ** 2 for x in data)

            if denominator > 0:
                autocorr = numerator / denominator
            else:
                autocorr = 0

            # Consider seasonal if autocorrelation > 0.3
            is_seasonal = abs(autocorr) > 0.3

            return {
                "seasonal": is_seasonal,
                "period": period if is_seasonal else 0,
                "strength": abs(autocorr),
                "autocorrelation": autocorr,
            }

        except Exception as e:
            logger.error(f"Seasonality detection failed: {e}")
            return {"seasonal": False, "period": 0, "strength": 0.0}

    def detect_anomalies(
        self, data: list[float], threshold: float = 2.0
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Detect anomalies in time series data"""
        if len(data) < 5:
            return []

        try:
            anomalies: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            mean_val = statistics.mean(data)
            std_val = statistics.stdev(data) if len(data) > 1 else 0

            if std_val == 0:
                return []

            for i, value in enumerate(data):
                z_score = abs((value - mean_val) / std_val)

                if z_score > threshold:
                    anomaly = {
                        "index": i,
                        "value": value,
                        "z_score": z_score,
                        "type": "outlier",
                        "severity": "high" if z_score > 3.0 else "medium",
                    }
                    anomalies.append(anomaly)

            return anomalies

        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return []


class ForecastingEngine:
    """Implements various forecasting algorithms"""

    def __init__(self) -> None:
        self.models: dict[str, Callable[..., Awaitable[dict[str, object]]]] = {
            "simple_moving_average": self._forecast_moving_average,
            "exponential_smoothing": self._forecast_exponential_smoothing,
            "linear_trend": self._forecast_linear_trend,
            "seasonal_decomposition": self._forecast_seasonal,
        }

    async def forecast(
        self, data: list[float], periods: int, method: str = "exponential_smoothing"
    ) -> dict[str, object]:
        """Generate forecast using specified method"""
        if method not in self.models:
            method = "exponential_smoothing"

        try:
            forecast_func = self.models[method]
            result = cast(_ForecastResult, await forecast_func(data, periods))
            forecast_values = result["forecast"]

            # Calculate confidence intervals (simplified)
            if len(data) > 1:
                std_error = statistics.stdev(data) / math.sqrt(len(data))
                confidence_95 = 1.96 * std_error

                return {
                    "forecast": forecast_values,
                    "accuracy": result.get("accuracy", 0.0),
                    "confidence_intervals": {
                        "lower_95": [max(0, pred - confidence_95) for pred in forecast_values],
                        "upper_95": [pred + confidence_95 for pred in forecast_values],
                    },
                }

            return {
                "forecast": forecast_values,
                "accuracy": result.get("accuracy", 0.0),
            }

        except Exception as e:
            logger.error(f"Forecasting failed with method {method}: {e}")
            return {
                "forecast": [data[-1]] * periods if data else [0] * periods,
                "accuracy": 0.0,
            }

    async def _forecast_moving_average(
        self, data: list[float], periods: int, window: int = 5
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Simple moving average forecast"""
        if len(data) < window:
            window = len(data)

        if window == 0:
            return {"forecast": [0] * periods, "accuracy": 0.0}

        # Calculate moving average
        recent_avg = statistics.mean(data[-window:])

        # Forecast is simply the moving average extended
        forecast = [recent_avg] * periods

        # Simple accuracy based on recent variance
        recent_data = data[-window:]
        variance = statistics.variance(recent_data) if len(recent_data) > 1 else 0
        accuracy = max(0, 1 - (variance / (recent_avg**2)) if recent_avg != 0 else 0)

        return {
            "forecast": forecast,
            "accuracy": accuracy,
            "method": "moving_average",
            "window_size": window,
        }

    async def _forecast_exponential_smoothing(
        self, data: list[float], periods: int, alpha: float = 0.3
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Exponential smoothing forecast"""
        if not data:
            return {"forecast": [0] * periods, "accuracy": 0.0}

        # Initialize with first value
        smoothed = [data[0]]

        # Calculate exponentially smoothed values
        for i in range(1, len(data)):
            smoothed_value = alpha * data[i] + (1 - alpha) * smoothed[-1]
            smoothed.append(smoothed_value)

        # Forecast using last smoothed value
        last_smoothed = smoothed[-1]
        forecast = [last_smoothed] * periods

        # Calculate accuracy based on fit to historical data
        if len(data) > 1:
            errors = [abs(data[i] - smoothed[i]) for i in range(len(data))]
            mae = statistics.mean(errors)
            data_range = max(data) - min(data)
            accuracy = max(0, 1 - (mae / data_range)) if data_range > 0 else 0.5
        else:
            accuracy = 0.5

        return {
            "forecast": forecast,
            "accuracy": accuracy,
            "method": "exponential_smoothing",
            "alpha": alpha,
        }

    async def _forecast_linear_trend(
        self, data: list[float], periods: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Linear trend forecast"""
        if len(data) < 2:
            return {"forecast": [data[0] if data else 0] * periods, "accuracy": 0.0}

        try:
            # Calculate linear regression
            x = list(range(len(data)))
            n = len(data)

            sum_x = sum(x)
            sum_y = sum(data)
            sum_xy = sum(xi * yi for xi, yi in zip(x, data))
            sum_x2 = sum(xi * xi for xi in x)

            # Calculate slope and intercept
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            intercept = (sum_y - slope * sum_x) / n

            # Generate forecast
            forecast: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for i in range(periods):
                future_x = len(data) + i
                predicted_y = slope * future_x + intercept
                forecast.append(max(0, predicted_y))  # Ensure non-negative

            # Calculate R-squared for accuracy
            mean_y = statistics.mean(data)
            ss_tot = sum((yi - mean_y) ** 2 for yi in data)
            ss_res = sum((data[i] - (slope * i + intercept)) ** 2 for i in range(len(data)))

            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            accuracy = max(0, r_squared)

            return {
                "forecast": forecast,
                "accuracy": accuracy,
                "method": "linear_trend",
                "slope": slope,
                "intercept": intercept,
            }

        except Exception as e:
            logger.error(f"Linear trend forecast failed: {e}")
            return {"forecast": [data[-1]] * periods, "accuracy": 0.0}

    async def _forecast_seasonal(
        self, data: list[float], periods: int, season_length: int = 24
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Seasonal decomposition forecast"""
        if len(data) < season_length * 2:
            # Fall back to exponential smoothing
            return await self._forecast_exponential_smoothing(data, periods)

        try:
            # Simple seasonal decomposition
            seasonal_indices: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Calculate seasonal pattern
            for i in range(season_length):
                seasonal_values: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                for j in range(i, len(data), season_length):
                    seasonal_values.append(data[j])

                if seasonal_values:
                    seasonal_indices.append(statistics.mean(seasonal_values))
                else:
                    seasonal_indices.append(1.0)

            # Normalize seasonal indices
            avg_seasonal = statistics.mean(seasonal_indices)
            if avg_seasonal > 0:
                seasonal_indices = [si / avg_seasonal for si in seasonal_indices]

            # Calculate trend (simplified)
            trend_slope = (data[-1] - data[0]) / len(data)

            # Generate forecast
            forecast: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            base_value = data[-1]

            for i in range(periods):
                trend_component = base_value + (trend_slope * (i + 1))
                seasonal_component = seasonal_indices[(len(data) + i) % season_length]
                predicted_value = trend_component * seasonal_component
                forecast.append(max(0, predicted_value))

            # Simple accuracy estimate
            accuracy = 0.7  # Default for seasonal model

            return {
                "forecast": forecast,
                "accuracy": accuracy,
                "method": "seasonal_decomposition",
                "season_length": season_length,
            }

        except Exception as e:
            logger.error(f"Seasonal forecast failed: {e}")
            return await self._forecast_exponential_smoothing(data, periods)


class PredictiveAnalyticsEngine:
    """
    Main predictive analytics engine
    Provides forecasting, trend analysis, and predictive insights
    """

    def __init__(self) -> None:
        self.time_series_analyzer = TimeSeriesAnalyzer()
        self.forecasting_engine = ForecastingEngine()
        self.prediction_cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self._initialized = False
        self._stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "predictions_made": 0,
            "accuracy_scores": [],
            "cache_hits": 0,
            "cache_misses": 0,
        }

    async def initialize(self) -> bool:
        """Initialize predictive analytics engine"""
        try:
            self._initialized = True
            logger.info("Predictive Analytics Engine initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize predictive analytics engine: {e}")
            return False

    async def generate_prediction(self, request: PredictionRequest) -> PredictionResult:
        """Generate prediction based on request"""
        if not self._initialized:
            await self.initialize()

        try:
            # Check cache first
            cache_key = self._generate_cache_key(request)
            cached_result = await cache_system.get(cache_key)

            if cached_result:
                self._stats["cache_hits"] += 1
                logger.debug(f"Returning cached prediction for {request.request_id}")
                return PredictionResult(
                    **cast(dict[str, object], cached_result)  # type: ignore[arg-type]
                )

            self._stats["cache_misses"] += 1

            # Generate new prediction
            result = await self._create_prediction(request)

            # Cache result
            await cache_system.set(cache_key, result.to_dict(), ttl=300)  # 5 minutes

            self._stats["predictions_made"] += 1
            return result

        except Exception as e:
            logger.error(f"Prediction generation failed: {e}")
            return self._create_error_result(request, str(e))

    async def _create_prediction(self, request: PredictionRequest) -> PredictionResult:
        """Create prediction based on request type"""

        if request.prediction_type == PredictionType.LOAD_FORECAST:
            return await self._predict_load_forecast(request)
        elif request.prediction_type == PredictionType.PERFORMANCE_TREND:
            return await self._predict_performance_trend(request)
        elif request.prediction_type == PredictionType.RESOURCE_DEMAND:
            return await self._predict_resource_demand(request)
        elif request.prediction_type == PredictionType.USER_BEHAVIOR:
            return await self._predict_user_behavior(request)
        elif request.prediction_type == PredictionType.SYSTEM_HEALTH:
            return await self._predict_system_health(request)
        elif request.prediction_type == PredictionType.CAPACITY_PLANNING:
            return await self._predict_capacity_planning(request)
        elif request.prediction_type == PredictionType.ANOMALY_DETECTION:
            return await self._predict_anomaly_detection(request)
        else:
            return await self._predict_generic(request)

    async def _predict_load_forecast(self, request: PredictionRequest) -> PredictionResult:
        """Predict system load forecast"""
        periods = self._get_periods_for_horizon(request.time_horizon)
        predictions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        trends: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        anomalies: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for metric_name, data in request.historical_data.items():
            if not data:
                continue

            # Analyze trend
            trend_analysis = self.time_series_analyzer.analyze_trend(data)
            trends[metric_name] = trend_analysis["trend"]

            # Detect anomalies
            metric_anomalies = self.time_series_analyzer.detect_anomalies(data)
            for anomaly in metric_anomalies:
                anomaly["metric"] = metric_name
            anomalies.extend(metric_anomalies)

            # Generate forecast
            forecast_result = await self.forecasting_engine.forecast(
                data, periods, "seasonal_decomposition"
            )
            predictions[metric_name] = forecast_result["forecast"]

        # Generate time points
        time_points = self._generate_time_points(request.time_horizon, periods)

        # Calculate overall confidence
        confidence_score = self._calculate_confidence(request.historical_data, anomalies)
        confidence = self._get_confidence_level(confidence_score)

        # Generate recommendations
        recommendations = self._generate_load_recommendations(trends, predictions, anomalies)

        return PredictionResult(
            request_id=request.request_id,
            prediction_type=request.prediction_type,
            predictions=predictions,
            confidence=confidence,
            confidence_score=confidence_score,
            time_points=time_points,
            trends=trends,
            anomalies=anomalies,
            recommendations=recommendations,
        )

    async def _predict_performance_trend(self, request: PredictionRequest) -> PredictionResult:
        """Predict performance trends"""
        periods = self._get_periods_for_horizon(request.time_horizon)
        predictions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        trends: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        anomalies: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for metric_name, data in request.historical_data.items():
            if not data:
                continue

            # Analyze performance trend
            trend_analysis = self.time_series_analyzer.analyze_trend(data)
            trends[metric_name] = trend_analysis["trend"]

            # Use exponential smoothing for performance metrics
            forecast_result = await self.forecasting_engine.forecast(
                data, periods, "exponential_smoothing"
            )
            predictions[metric_name] = forecast_result["forecast"]

            # Detect performance anomalies
            metric_anomalies = self.time_series_analyzer.detect_anomalies(data, threshold=1.5)
            for anomaly in metric_anomalies:
                anomaly["metric"] = metric_name
            anomalies.extend(metric_anomalies)

        time_points = self._generate_time_points(request.time_horizon, periods)
        confidence_score = self._calculate_confidence(request.historical_data, anomalies)
        confidence = self._get_confidence_level(confidence_score)

        recommendations = self._generate_performance_recommendations(trends, predictions, anomalies)

        return PredictionResult(
            request_id=request.request_id,
            prediction_type=request.prediction_type,
            predictions=predictions,
            confidence=confidence,
            confidence_score=confidence_score,
            time_points=time_points,
            trends=trends,
            anomalies=anomalies,
            recommendations=recommendations,
        )

    async def _predict_resource_demand(self, request: PredictionRequest) -> PredictionResult:
        """Predict resource demand"""
        periods = self._get_periods_for_horizon(request.time_horizon)
        predictions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        trends: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for metric_name, data in request.historical_data.items():
            if not data:
                continue

            trend_analysis = self.time_series_analyzer.analyze_trend(data)
            trends[metric_name] = trend_analysis["trend"]

            # Use linear trend for resource demand
            forecast_result = await self.forecasting_engine.forecast(data, periods, "linear_trend")
            predictions[metric_name] = forecast_result["forecast"]

        time_points = self._generate_time_points(request.time_horizon, periods)
        confidence_score = 0.8  # Resource demand is usually more predictable
        confidence = self._get_confidence_level(confidence_score)

        recommendations = self._generate_resource_recommendations(trends, predictions)

        return PredictionResult(
            request_id=request.request_id,
            prediction_type=request.prediction_type,
            predictions=predictions,
            confidence=confidence,
            confidence_score=confidence_score,
            time_points=time_points,
            trends=trends,
            anomalies=[],
            recommendations=recommendations,
        )

    async def _predict_generic(self, request: PredictionRequest) -> PredictionResult:
        """Generic prediction for unspecified types"""
        periods = self._get_periods_for_horizon(request.time_horizon)
        predictions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        trends: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for metric_name, data in request.historical_data.items():
            if not data:
                continue

            trend_analysis = self.time_series_analyzer.analyze_trend(data)
            trends[metric_name] = trend_analysis["trend"]

            forecast_result = await self.forecasting_engine.forecast(data, periods)
            predictions[metric_name] = forecast_result["forecast"]

        time_points = self._generate_time_points(request.time_horizon, periods)
        confidence_score = 0.6
        confidence = self._get_confidence_level(confidence_score)

        return PredictionResult(
            request_id=request.request_id,
            prediction_type=request.prediction_type,
            predictions=predictions,
            confidence=confidence,
            confidence_score=confidence_score,
            time_points=time_points,
            trends=trends,
            anomalies=[],
            recommendations=[],
        )

    def _get_periods_for_horizon(self, horizon: TimeHorizon) -> int:
        """Get number of periods for time horizon"""
        if horizon == TimeHorizon.SHORT_TERM:
            return 12  # 12 periods (5-minute intervals for 1 hour)
        elif horizon == TimeHorizon.MEDIUM_TERM:
            return 24  # 24 periods (hourly for 24 hours)
        else:  # LONG_TERM
            return 7  # 7 periods (daily for 1 week)

    def _generate_time_points(self, horizon: TimeHorizon, periods: int) -> list[str]:
        """Generate time points for prediction"""
        now = datetime.now(timezone.utc)
        time_points: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if horizon == TimeHorizon.SHORT_TERM:
            delta = timedelta(minutes=5)
        elif horizon == TimeHorizon.MEDIUM_TERM:
            delta = timedelta(hours=1)
        else:  # LONG_TERM
            delta = timedelta(days=1)

        for i in range(periods):
            future_time = now + (delta * (i + 1))
            time_points.append(future_time.isoformat())

        return time_points

    def _calculate_confidence(
        self,
        historical_data: dict[str, list[float]],
        anomalies: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate confidence score for prediction"""
        total_points = sum(len(data) for data in historical_data.values())

        if total_points == 0:
            return 0.0

        # Base confidence on data quantity
        data_confidence = min(1.0, total_points / 100)  # Full confidence at 100+ points

        # Reduce confidence based on anomalies
        anomaly_penalty = len(anomalies) * 0.05  # 5% penalty per anomaly
        anomaly_confidence = max(0.0, 1.0 - anomaly_penalty)

        return data_confidence * anomaly_confidence

    def _get_confidence_level(self, score: float) -> PredictionConfidence:
        """Convert confidence score to confidence level"""
        if score >= 0.8:
            return PredictionConfidence.VERY_HIGH
        elif score >= 0.6:
            return PredictionConfidence.HIGH
        elif score >= 0.4:
            return PredictionConfidence.MEDIUM
        else:
            return PredictionConfidence.LOW

    def _generate_load_recommendations(
        self,
        trends: dict[str, str],
        predictions: dict[str, list[float]],
        anomalies: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate recommendations for load forecast"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for increasing trends
        increasing_metrics = [metric for metric, trend in trends.items() if trend == "increasing"]
        if increasing_metrics:
            recommendations.append(
                f"Scale up resources for increasing load in: {', '.join(increasing_metrics)}"
            )

        # Check for high predicted values
        for metric, values in predictions.items():
            if values and max(values) > statistics.mean(values) * 1.5:
                recommendations.append(f"Prepare for peak load in {metric}")

        # Check for anomalies
        if anomalies:
            recommendations.append("Investigate recent anomalies before peak periods")

        return recommendations

    def _generate_performance_recommendations(
        self,
        trends: dict[str, str],
        predictions: dict[str, list[float]],
        anomalies: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate recommendations for performance trends"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for decreasing performance trends
        decreasing_metrics = [metric for metric, trend in trends.items() if trend == "decreasing"]
        if decreasing_metrics:
            recommendations.append(
                f"Optimize performance for degrading metrics: {', '.join(decreasing_metrics)}"
            )

        # Check for performance anomalies
        if anomalies:
            high_severity_anomalies = [a for a in anomalies if a.get("severity") == "high"]
            if high_severity_anomalies:
                recommendations.append("Investigate high-severity performance anomalies")

        return recommendations

    def _generate_resource_recommendations(
        self, trends: dict[str, str], predictions: dict[str, list[float]]
    ) -> list[str]:
        """Generate recommendations for resource demand"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check resource trends
        for metric, trend in trends.items():
            if trend == "increasing":
                recommendations.append(f"Plan capacity increase for {metric}")
            elif trend == "decreasing":
                recommendations.append(f"Consider cost optimization for {metric}")

        return recommendations

    def _generate_cache_key(self, request: PredictionRequest) -> str:
        """Generate cache key for prediction request"""
        key_components = [
            request.prediction_type.value,
            request.time_horizon.value,
            str(sorted(request.target_metrics)),
            str(len(request.historical_data)),
        ]
        return f"prediction:{':'.join(key_components)}"

    def _create_error_result(
        self, request: PredictionRequest, error_message: str
    ) -> PredictionResult:
        """Create error result for failed predictions"""
        return PredictionResult(
            request_id=request.request_id,
            prediction_type=request.prediction_type,
            predictions={},
            confidence=PredictionConfidence.LOW,
            confidence_score=0.0,
            time_points=[],
            trends={},
            anomalies=[],
            recommendations=[f"Prediction failed: {error_message}"],
            metadata={"error": error_message},
        )

    async def get_analytics_stats(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get predictive analytics statistics"""
        avg_accuracy = (
            statistics.mean(self._stats["accuracy_scores"])
            if self._stats["accuracy_scores"]
            else 0.0
        )

        return {
            "predictions_made": self._stats["predictions_made"],
            "average_accuracy": round(avg_accuracy, 3),
            "cache_hit_rate": (
                (
                    self._stats["cache_hits"]
                    / (self._stats["cache_hits"] + self._stats["cache_misses"])
                    * 100
                )
                if (self._stats["cache_hits"] + self._stats["cache_misses"]) > 0
                else 0
            ),
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
        }

    async def predict(
        self,
        prediction_type: PredictionType,
        time_horizon: TimeHorizon,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        features: dict[str, float],
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Alias method for generate_prediction - main prediction method for API compatibility"""
        import uuid

        request = PredictionRequest(
            request_id=f"pred_{uuid.uuid4().hex[:8]}",
            prediction_type=prediction_type,
            time_horizon=time_horizon,
            target_metrics=list(features.keys()),
            historical_data={k: [v] for k, v in features.items()},
            context=context,
        )
        result = await self.generate_prediction(request)

        # Transform to match endpoint expectations
        @dataclass
        class PredictionOutput:
            prediction_id: str
            predicted_value: Any  # TODO(TYPE): replace Any with concrete type
            confidence: float
            uncertainty_bounds: list[float]
            feature_importance: dict[str, float]

        pred_values: list[Any] = (  # TODO(TYPE): replace Any with concrete type
            list(result.predictions.values()) if result.predictions else []
        )  # TODO(TYPE): replace Any with concrete type
        first_pred: Any = None
        if pred_values and len(pred_values) > 0:
            first_item = pred_values[0]
            if isinstance(first_item, list) and len(first_item) > 0:
                first_pred = first_item[0]
            else:
                first_pred = first_item

        if first_pred is None:
            first_pred = 0.0

        pred_keys = list(result.predictions.keys()) if result.predictions else []
        feature_importance: dict[str, float] = {}
        if pred_keys:
            feature_importance = {m: 1.0 / len(pred_keys) for m in pred_keys}

        return PredictionOutput(
            prediction_id=result.request_id,
            predicted_value=first_pred,
            confidence=result.confidence_score,
            uncertainty_bounds=[0.0, 0.0],
            feature_importance=feature_importance,
        )

    async def get_active_models_count(self) -> int:
        """Get number of active predictive models"""
        return (
            len(self.forecasting_engine.models) if hasattr(self.forecasting_engine, "models") else 3
        )

    async def get_average_confidence(self) -> float:
        """Get average prediction confidence"""
        accuracy_scores: list[float] = self._stats.get("accuracy_scores") or []
        if accuracy_scores:
            return round(sum(accuracy_scores) / len(accuracy_scores), 3)
        return 0.0

    async def _predict_user_behavior(self, request: PredictionRequest) -> PredictionResult:
        """Predict user behavior patterns."""
        return await self._predict_generic(request)

    async def _predict_system_health(self, request: PredictionRequest) -> PredictionResult:
        """Predict system health trends."""
        return await self._predict_generic(request)

    async def _predict_capacity_planning(self, request: PredictionRequest) -> PredictionResult:
        """Predict capacity planning needs."""
        return await self._predict_generic(request)

    async def _predict_anomaly_detection(self, request: PredictionRequest) -> PredictionResult:
        """Predict anomalies in system metrics."""
        periods = self._get_periods_for_horizon(request.time_horizon)
        predictions: dict[str, list[float]] = {}
        trends: dict[str, str] = {}
        anomalies: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        for metric_name, data in request.historical_data.items():
            if not data:
                continue

            # Analyze trend
            trend_analysis = self.time_series_analyzer.analyze_trend(data)
            trends[metric_name] = trend_analysis["trend"]

            # Detect anomalies with higher sensitivity
            metric_anomalies = self.time_series_analyzer.detect_anomalies(data, threshold=1.5)
            for anomaly in metric_anomalies:
                anomaly["metric"] = metric_name
            anomalies.extend(metric_anomalies)

            # Generate forecast
            forecast_result = cast(_ForecastResult, await self.forecasting_engine.forecast(data, periods))
            predictions[metric_name] = forecast_result["forecast"]

        time_points = self._generate_time_points(request.time_horizon, periods)
        confidence_score = self._calculate_confidence(request.historical_data, anomalies)
        confidence = self._get_confidence_level(confidence_score)

        recommendations = self._generate_anomaly_recommendations(trends, anomalies)

        return PredictionResult(
            request_id=request.request_id,
            prediction_type=request.prediction_type,
            predictions=predictions,
            confidence=confidence,
            confidence_score=confidence_score,
            time_points=time_points,
            trends=trends,
            anomalies=anomalies,
            recommendations=recommendations,
        )

    def _generate_anomaly_recommendations(
        self,
        trends: dict[str, str],
        anomalies: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate recommendations for anomaly detection."""
        recommendations: list[str] = []

        if anomalies:
            high_severity = [a for a in anomalies if a.get("severity") == "high"]
            if high_severity:
                recommendations.append(f"Investigate {len(high_severity)} high-severity anomalies")

        for metric, trend in trends.items():
            if trend == "increasing":
                recommendations.append(f"Monitor increasing trend in {metric}")
            elif trend == "decreasing":
                recommendations.append(f"Review decreasing trend in {metric}")

        return recommendations


# Factory function
async def create_predictive_analytics_engine() -> PredictiveAnalyticsEngine:
    """Create and initialize predictive analytics engine"""
    engine = PredictiveAnalyticsEngine()
    await engine.initialize()
    return engine


# Global engine instance
_global_analytics_engine: PredictiveAnalyticsEngine | None = None


async def get_predictive_analytics_engine() -> PredictiveAnalyticsEngine:
    """Get global predictive analytics engine instance"""
    global _global_analytics_engine

    if _global_analytics_engine is None:
        _global_analytics_engine = await create_predictive_analytics_engine()

    return _global_analytics_engine
