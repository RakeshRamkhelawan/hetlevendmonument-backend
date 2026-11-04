"""
Risk Prediction System - TASK-118
Advanced predictive analytics for ethical risk assessment and forecasting
"""

from __future__ import annotations

import json
import logging
import pickle
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,  # TODO(TYPE): replace Any with concrete type
)
from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from src.core.security.secure_pickle import SecureModelLoader

if TYPE_CHECKING:
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.ensemble import GradientBoostingRegressor, IsolationForest, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import cross_val_score
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR

# Optional advanced ML imports
try:
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.ensemble import GradientBoostingRegressor, IsolationForest, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import cross_val_score
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import pandas as pd  # noqa: F401

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)


@dataclass
class RiskPrediction:
    """Comprehensive risk prediction result"""

    risk_score: float
    confidence: float
    risk_trend: str  # 'increasing', 'decreasing', 'stable'
    predicted_timeline: dict[str, float]  # Future risk scores by time period
    risk_factors: dict[str, float]
    anomaly_score: float
    similar_cases: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    predictions_reasoning: list[str]
    uncertainty_bounds: tuple[float, float]
    recommendation_urgency: str


@dataclass
class RiskPattern:
    """Identified risk pattern structure"""

    pattern_id: str
    pattern_type: str
    frequency: int
    risk_escalation_rate: float
    common_factors: list[str]
    historical_outcomes: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    prevention_strategies: list[str]


@dataclass
class PredictiveMetrics:
    """Performance metrics for prediction models"""

    model_accuracy: float
    mean_absolute_error: float
    root_mean_square_error: float
    r2_score: float
    prediction_intervals: dict[str, float]
    feature_importance: dict[str, float]
    model_stability: float


class RiskPredictionSystem:
    """Advanced risk prediction system with temporal analysis and pattern detection"""

    def __init__(self, models_path: str = "models/risk_prediction") -> None:
        self.models_path = Path(models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)

        # SECURITY FIX: Initialize secure model loader with path validation
        self._secure_loader = SecureModelLoader(allowed_dir=str(self.models_path.resolve()))

        # Prediction models
        self.prediction_models: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.anomaly_detectors: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.clustering_models: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.scalers: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        # Historical data and pattern storage
        self.risk_history: deque[dict[str, Any]] = (  # TODO(TYPE): replace Any with concrete type
            deque(  # TODO(TYPE): replace Any with concrete type
                maxlen=10000
            )
        )  # Store recent risk assessments
        self.pattern_database: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.time_series_data: defaultdict[int, list[float]] = defaultdict(list)

        # Performance tracking
        self.prediction_accuracy_history: list[float] = []
        self.model_performance_metrics: dict[
            str, dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type

        # Risk thresholds and categories
        self.risk_thresholds = {
            "minimal": (0.0, 0.2),
            "low": (0.2, 0.4),
            "moderate": (0.4, 0.6),
            "high": (0.6, 0.8),
            "critical": (0.8, 1.0),
        }

        # Temporal analysis parameters
        self.prediction_horizons = [
            "1_hour",
            "6_hours",
            "24_hours",
            "7_days",
            "30_days",
        ]
        self.trend_analysis_window = 100  # Number of recent assessments for trend analysis

        logger.info("Risk Prediction System initialized")

    async def initialize(self) -> bool:
        """Initialize the risk prediction system"""
        try:
            # Load existing models and data
            await self._load_models_and_data()

            # Initialize prediction models
            await self._initialize_prediction_models()

            # Initialize anomaly detection
            await self._initialize_anomaly_detection()

            # Initialize pattern recognition
            await self._initialize_pattern_recognition()

            # Load historical data for analysis
            await self._load_historical_risk_data()

            logger.info("Risk Prediction System fully initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Risk Prediction System: {e}")
            return False

    async def predict_risk(
        self,
        task: TaskData,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        prediction_horizon: str = "24_hours",
    ) -> RiskPrediction:
        """Generate comprehensive risk prediction with temporal analysis"""
        try:
            # Extract features for prediction
            features = await self._extract_prediction_features(task, context or {})

            # Generate base risk prediction
            base_risk_score = await self._predict_base_risk(features)

            # Perform temporal risk analysis
            temporal_predictions = await self._predict_temporal_risk(features, task)

            # Detect anomalies
            anomaly_score = await self._detect_risk_anomalies(features)

            # Analyze risk trends
            risk_trend = await self._analyze_risk_trend(task, base_risk_score)

            # Find similar historical cases
            similar_cases = await self._find_similar_cases(features, task)

            # Calculate prediction confidence
            confidence = await self._calculate_prediction_confidence(features, base_risk_score)

            # Generate uncertainty bounds
            uncertainty_bounds = await self._calculate_uncertainty_bounds(
                base_risk_score, confidence, features
            )

            # Assess recommendation urgency
            urgency = await self._assess_recommendation_urgency(
                base_risk_score, risk_trend, anomaly_score, temporal_predictions
            )

            # Extract key risk factors
            risk_factors = await self._identify_risk_factors(features, task)

            # Generate prediction reasoning
            reasoning = await self._generate_prediction_reasoning(
                base_risk_score,
                risk_trend,
                anomaly_score,
                similar_cases,
                temporal_predictions,
            )

            # Store prediction for future analysis
            await self._store_prediction_result(task, base_risk_score, features, context or {})

            prediction = RiskPrediction(
                risk_score=base_risk_score,
                confidence=confidence,
                risk_trend=risk_trend,
                predicted_timeline=temporal_predictions,
                risk_factors=risk_factors,
                anomaly_score=anomaly_score,
                similar_cases=similar_cases,
                predictions_reasoning=reasoning,
                uncertainty_bounds=uncertainty_bounds,
                recommendation_urgency=urgency,
            )

            return prediction

        except Exception as e:
            logger.error(f"Risk prediction error: {e}")
            return await self._fallback_risk_prediction(task, context or {})

    async def _extract_prediction_features(
        self,
        task: TaskData,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> npt.NDArray[Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract comprehensive features for risk prediction"""
        features: list[float] = []

        # Basic task features
        text = f"{task.title} {task.description}"
        text_lower = text.lower()

        # Text-based features
        features.extend(
            [
                len(text),
                len(text.split()),
                text.count("."),  # Sentence complexity
                text.count(","),  # Clause complexity
            ]
        )

        # Semantic risk indicators
        high_risk_keywords = [
            "delete",
            "destroy",
            "hack",
            "breach",
            "exploit",
            "manipulate",
            "deceive",
            "harm",
            "violate",
            "abuse",
            "override",
            "bypass",
        ]

        medium_risk_keywords = [
            "modify",
            "change",
            "alter",
            "access",
            "update",
            "process",
            "collect",
            "share",
            "store",
            "analyze",
            "track",
        ]

        privacy_keywords = [
            "personal",
            "private",
            "confidential",
            "data",
            "information",
            "profile",
            "identity",
            "biometric",
            "location",
        ]

        security_keywords = [
            "security",
            "authentication",
            "authorization",
            "encryption",
            "firewall",
            "vulnerability",
            "threat",
            "attack",
        ]

        # Calculate keyword scores
        features.extend(
            [
                sum(1 for word in high_risk_keywords if word in text_lower),
                sum(1 for word in medium_risk_keywords if word in text_lower),
                sum(1 for word in privacy_keywords if word in text_lower),
                sum(1 for word in security_keywords if word in text_lower),
            ]
        )

        # Context-based features
        features.extend(
            [
                1.0 if context.get("user_data_involved", False) else 0.0,
                1.0 if context.get("system_critical", False) else 0.0,
                1.0 if context.get("external_access", False) else 0.0,
                1.0 if context.get("automated_decision", False) else 0.0,
                context.get("user_count", 0) / 10000.0,  # Normalized user impact
                context.get("data_sensitivity", 0) / 10.0,  # Normalized data sensitivity
            ]
        )

        # Temporal features
        now = datetime.now(timezone.utc)
        features.extend(
            [
                now.hour / 24.0,  # Time of day
                now.weekday() / 7.0,  # Day of week
                now.month / 12.0,  # Month of year
            ]
        )

        # Priority-based features
        priority_mapping: dict[str, float] = {
            "low": 0.2,
            "medium": 0.5,
            "high": 0.8,
            "urgent": 1.0,
        }
        priority_key = str(task.priority.value if hasattr(task.priority, "value") else "medium")
        features.append(priority_mapping.get(priority_key, 0.5))

        # Historical pattern features
        historical_features = await self._extract_historical_pattern_features(task, context)
        features.extend(historical_features)

        return np.array(features)

    async def _extract_historical_pattern_features(
        self,
        task: TaskData,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[float]:
        """Extract features based on historical patterns"""
        features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Similar task history
        similar_task_count = len(
            [
                entry
                for entry in self.risk_history
                if entry.get("task_type") == context.get("task_type", "unknown")
            ]
        )
        features.append(min(similar_task_count / 100.0, 1.0))  # Normalize

        # Recent risk trend
        if len(self.risk_history) >= 10:
            recent_risks = [entry["risk_score"] for entry in list(self.risk_history)[-10:]]
            features.extend(
                [
                    np.mean(recent_risks),
                    np.std(recent_risks),
                    recent_risks[-1] - recent_risks[0] if len(recent_risks) > 1 else 0.0,  # Trend
                ]
            )
        else:
            features.extend([0.5, 0.2, 0.0])  # Default values

        # Time-based patterns
        current_hour = datetime.now(timezone.utc).hour
        if current_hour in self.time_series_data:
            hourly_risks = self.time_series_data[current_hour]
            if hourly_risks:
                features.extend(
                    [
                        np.mean(hourly_risks),
                        len(hourly_risks) / 365.0,
                    ]  # Frequency normalization
                )
            else:
                features.extend([0.5, 0.0])
        else:
            features.extend([0.5, 0.0])

        return features

    async def _predict_base_risk(
        self,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Predict base risk score using ensemble of models"""
        if not SKLEARN_AVAILABLE or not self.prediction_models:
            return await self._fallback_base_risk_prediction(features)

        try:
            predictions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Get predictions from all available models
            for model_name, model in self.prediction_models.items():
                if model_name in self.scalers:
                    scaled_features = self.scalers[model_name].transform([features])
                    prediction = model.predict(scaled_features)[0]
                    predictions.append(max(0.0, min(1.0, prediction)))  # Clamp to [0,1]

            if predictions:
                # Weighted average (some models might be more reliable)
                weights = {
                    "random_forest": 0.25,
                    "gradient_boosting": 0.3,
                    "neural_network": 0.2,
                    "svr": 0.15,
                    "linear": 0.1,
                }

                weighted_sum = 0.0
                total_weight = 0.0

                for i, model_name in enumerate(self.prediction_models.keys()):
                    if i < len(predictions):
                        weight = weights.get(model_name, 0.2)
                        weighted_sum += predictions[i] * weight
                        total_weight += weight

                return (
                    float(weighted_sum / total_weight)
                    if total_weight > 0
                    else float(np.mean(predictions))
                )
            else:
                return await self._fallback_base_risk_prediction(features)

        except Exception as e:
            logger.error(f"Base risk prediction error: {e}")
            return await self._fallback_base_risk_prediction(features)

    async def _predict_temporal_risk(
        self,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
        task: TaskData,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:
        """Predict risk scores for different time horizons"""
        base_risk = await self._predict_base_risk(features)
        temporal_predictions: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        # Risk decay/escalation factors based on task characteristics
        text = f"{task.title} {task.description}".lower()

        # Determine risk evolution pattern
        escalation_keywords = ["urgent", "immediate", "critical", "deadline", "expire"]
        decay_keywords = ["gradual", "slow", "eventual", "future", "planned"]

        has_escalation = any(keyword in text for keyword in escalation_keywords)
        has_decay = any(keyword in text for keyword in decay_keywords)

        # Time-based risk multipliers
        time_multipliers = {
            "1_hour": 1.0,
            "6_hours": 0.95 if has_decay else (1.1 if has_escalation else 1.0),
            "24_hours": 0.9 if has_decay else (1.2 if has_escalation else 0.98),
            "7_days": 0.8 if has_decay else (1.4 if has_escalation else 0.9),
            "30_days": 0.6 if has_decay else (1.6 if has_escalation else 0.8),
        }

        for horizon, multiplier in time_multipliers.items():
            # Apply noise for uncertainty
            noise_factor = np.random.normal(1.0, 0.05)  # 5% noise
            predicted_risk = base_risk * multiplier * noise_factor
            temporal_predictions[horizon] = max(0.0, min(1.0, predicted_risk))

        return temporal_predictions

    async def _detect_risk_anomalies(
        self,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Detect anomalous risk patterns using isolation forest"""
        if not SKLEARN_AVAILABLE or "isolation_forest" not in self.anomaly_detectors:
            return 0.0  # No anomaly detected in fallback mode

        try:
            detector = self.anomaly_detectors["isolation_forest"]
            anomaly_score = detector.decision_function([features])[0]

            # Convert to 0-1 scale (higher = more anomalous)
            # Isolation forest returns negative values for anomalies
            normalized_score = max(0.0, min(1.0, (-anomaly_score + 0.5) / 1.0))

            return float(normalized_score)

        except Exception as e:
            logger.error(f"Anomaly detection error: {e}")
            return 0.0

    async def _analyze_risk_trend(self, task: TaskData, current_risk: float) -> str:
        """Analyze risk trend based on historical patterns"""
        if len(self.risk_history) < 5:
            return "stable"  # Insufficient data

        try:
            # Get recent risk scores for similar tasks
            recent_window = min(self.trend_analysis_window, len(self.risk_history))
            recent_history = list(self.risk_history)[-recent_window:]

            # Filter for similar task types if available
            task_type = task.metadata.get("type", "general")
            similar_risks = [
                entry["risk_score"]
                for entry in recent_history
                if entry.get("task_type") == task_type
            ]

            if len(similar_risks) < 3:
                # Fall back to all recent risks
                similar_risks = [entry["risk_score"] for entry in recent_history]

            if len(similar_risks) >= 3:
                # Calculate trend using linear regression slope
                x = np.arange(len(similar_risks))
                slope = np.polyfit(x, similar_risks, 1)[0]

                # Classify trend based on slope and current risk
                if slope > 0.05:  # Increasing trend
                    return "increasing"
                elif slope < -0.05:  # Decreasing trend
                    return "decreasing"
                else:
                    return "stable"
            else:
                return "stable"

        except Exception as e:
            logger.error(f"Trend analysis error: {e}")
            return "stable"

    async def _find_similar_cases(
        self,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
        task: TaskData,
        num_cases: int = 5,  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Find similar historical cases for context"""
        if not self.risk_history:
            return []

        try:
            similar_cases: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            current_features = features

            # Compare with stored cases
            for entry in self.risk_history:
                if "features" in entry:
                    stored_features = np.array(entry["features"])

                    # Calculate similarity (using simplified cosine similarity)
                    if len(stored_features) == len(current_features):
                        dot_product = np.dot(current_features, stored_features)
                        norms = np.linalg.norm(current_features) * np.linalg.norm(stored_features)

                        if norms > 0:
                            similarity = dot_product / norms

                            similar_cases.append(
                                {
                                    "similarity": float(similarity),
                                    "risk_score": entry["risk_score"],
                                    "task_id": entry.get("task_id", "unknown"),
                                    "timestamp": entry.get("timestamp", ""),
                                    "outcome": entry.get("actual_outcome", "unknown"),
                                }
                            )

            # Sort by similarity and return top cases
            similar_cases.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_cases[:num_cases]

        except Exception as e:
            logger.error(f"Similar cases search error: {e}")
            return []

    async def _calculate_prediction_confidence(
        self,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
        predicted_risk: float,  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate confidence in the prediction"""
        confidence_factors: list[float] = []

        # Model agreement (if multiple models available)
        if len(self.prediction_models) > 1:
            predictions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for model_name, model in self.prediction_models.items():
                try:
                    if model_name in self.scalers:
                        scaled_features = self.scalers[model_name].transform([features])
                        pred = model.predict(scaled_features)[0]
                        predictions.append(max(0.0, min(1.0, pred)))
                except Exception as e:
                    logger.debug(
                        f"Model {model_name} prediction failed: {str(e)}",
                        exc_info=False,
                    )
                    continue

            if len(predictions) > 1:
                # Higher agreement = higher confidence
                std_dev = np.std(predictions)
                agreement_confidence = max(0.1, 1.0 - (float(std_dev) * 2))  # Inverse of spread
                confidence_factors.append(agreement_confidence)

        # Historical accuracy confidence
        if self.prediction_accuracy_history:
            avg_accuracy = np.mean(self.prediction_accuracy_history[-100:])  # Recent accuracy
            confidence_factors.append(float(avg_accuracy))

        # Feature quality confidence
        feature_completeness = np.sum(features != 0) / len(features)  # Non-zero feature ratio
        confidence_factors.append(feature_completeness)

        # Risk magnitude confidence (extreme values less certain)
        risk_certainty = 1.0 - abs(predicted_risk - 0.5) * 0.5  # Middle range more certain
        confidence_factors.append(risk_certainty)

        # Calculate overall confidence
        if confidence_factors:
            base_confidence = float(np.mean(confidence_factors))
        else:
            base_confidence = 0.6  # Default moderate confidence

        # Add uncertainty for edge cases
        if predicted_risk < 0.1 or predicted_risk > 0.9:
            base_confidence *= 0.8  # Reduce confidence for extreme predictions

        return max(0.1, min(0.95, base_confidence))  # Clamp to reasonable range

    async def _calculate_uncertainty_bounds(
        self,
        risk_score: float,
        confidence: float,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[float, float]:
        """Calculate uncertainty bounds for the prediction"""
        # Base uncertainty from confidence
        base_uncertainty = (1.0 - confidence) * 0.3  # Max A+/-30% uncertainty

        # Additional uncertainty factors
        feature_uncertainty = np.std(features) / 10.0 if len(features) > 0 else 0.05

        # Historical uncertainty (if available)
        historical_uncertainty = 0.05  # Default
        if self.model_performance_metrics:
            for model_name, metrics in self.model_performance_metrics.items():
                if "mean_absolute_error" in metrics:
                    historical_uncertainty = max(
                        historical_uncertainty, metrics["mean_absolute_error"]
                    )

        # Combine uncertainties
        total_uncertainty = min(
            0.4, base_uncertainty + feature_uncertainty + historical_uncertainty
        )

        # Calculate bounds
        lower_bound = max(0.0, risk_score - float(total_uncertainty))
        upper_bound = min(1.0, risk_score + float(total_uncertainty))

        return (float(lower_bound), float(upper_bound))

    async def _assess_recommendation_urgency(
        self,
        risk_score: float,
        trend: str,
        anomaly_score: float,
        temporal_predictions: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Assess the urgency of recommendations based on multiple factors"""
        urgency_score = 0.0

        # Risk score contribution (40% weight)
        urgency_score += risk_score * 0.4

        # Trend contribution (25% weight)
        if trend == "increasing":
            urgency_score += 0.25
        elif trend == "stable":
            urgency_score += 0.125
        # Decreasing trend adds no urgency

        # Anomaly contribution (20% weight)
        urgency_score += anomaly_score * 0.2

        # Temporal escalation contribution (15% weight)
        if temporal_predictions:
            max_future_risk = max(temporal_predictions.values())
            risk_escalation = max(0, max_future_risk - risk_score)
            urgency_score += risk_escalation * 0.15

        # Map urgency score to categories
        if urgency_score >= 0.8:
            return "immediate"
        elif urgency_score >= 0.6:
            return "high"
        elif urgency_score >= 0.4:
            return "moderate"
        elif urgency_score >= 0.2:
            return "low"
        else:
            return "minimal"

    async def _identify_risk_factors(
        self,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
        task: TaskData,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:
        """Identify and score key risk factors"""
        risk_factors: dict[str, float] = {}

        text = f"{task.title} {task.description}".lower()

        # Data privacy risk
        privacy_indicators = ["personal", "private", "data", "information", "profile"]
        privacy_score = sum(1 for word in privacy_indicators if word in text) / 5.0
        risk_factors["data_privacy"] = min(1.0, privacy_score)

        # Security risk
        security_indicators = ["hack", "breach", "exploit", "vulnerability", "attack"]
        security_score = sum(1 for word in security_indicators if word in text) / 5.0
        risk_factors["security"] = min(1.0, security_score)

        # Automation risk
        automation_indicators = ["automate", "algorithm", "ai", "machine", "system"]
        automation_score = sum(1 for word in automation_indicators if word in text) / 5.0
        risk_factors["automation"] = min(1.0, automation_score)

        # Compliance risk
        compliance_indicators = ["regulation", "compliance", "legal", "policy", "law"]
        compliance_score = sum(1 for word in compliance_indicators if word in text) / 5.0
        risk_factors["compliance"] = min(1.0, compliance_score)

        # Scale factors based on feature importance
        if len(features) >= 4:  # Ensure we have enough features
            risk_factors["data_privacy"] *= min(1.5, features[2] + 1)  # Privacy keyword feature
            risk_factors["security"] *= min(1.5, features[3] + 1)  # Security keyword feature

        return risk_factors

    async def _generate_prediction_reasoning(
        self,
        risk_score: float,
        trend: str,
        anomaly_score: float,
        similar_cases: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        temporal_predictions: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate human-readable reasoning for the prediction"""
        reasoning: list[str] = []

        # Risk score reasoning
        if risk_score >= 0.8:
            reasoning.append(
                f"High risk prediction ({risk_score:.2f}) indicates significant concern"
            )
        elif risk_score >= 0.6:
            reasoning.append(f"Moderate-high risk ({risk_score:.2f}) requires careful attention")
        elif risk_score >= 0.4:
            reasoning.append(f"Moderate risk ({risk_score:.2f}) suggests standard precautions")
        else:
            reasoning.append(f"Low risk prediction ({risk_score:.2f}) indicates minimal concern")

        # Trend reasoning
        if trend == "increasing":
            reasoning.append("Historical trend shows increasing risk pattern")
        elif trend == "decreasing":
            reasoning.append("Historical trend shows decreasing risk pattern")
        else:
            reasoning.append("Risk pattern appears stable based on historical data")

        # Anomaly reasoning
        if anomaly_score >= 0.7:
            reasoning.append(
                f"High anomaly score ({anomaly_score:.2f}) suggests unusual risk pattern"
            )
        elif anomaly_score >= 0.4:
            reasoning.append(f"Moderate anomaly detected ({anomaly_score:.2f})")

        # Similar cases reasoning
        if similar_cases:
            avg_similar_risk = np.mean([case["risk_score"] for case in similar_cases])
            reasoning.append(f"Similar historical cases averaged {avg_similar_risk:.2f} risk score")

        # Temporal analysis reasoning
        if temporal_predictions:
            max_future_risk = max(temporal_predictions.values())
            min_future_risk = min(temporal_predictions.values())

            if max_future_risk > risk_score + 0.1:
                reasoning.append("Temporal analysis suggests potential risk escalation")
            elif min_future_risk < risk_score - 0.1:
                reasoning.append("Temporal analysis suggests potential risk reduction")

        return reasoning

    async def _store_prediction_result(
        self,
        task: TaskData,
        risk_score: float,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Store prediction result for future learning"""
        try:
            prediction_entry = {
                "task_id": task.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "risk_score": risk_score,
                "features": features.tolist(),
                "task_type": context.get("type", "general"),
                "context": context,
                "actual_outcome": None,  # To be updated later with actual results
            }

            self.risk_history.append(prediction_entry)

            # Update time series data
            current_hour = datetime.now(timezone.utc).hour
            self.time_series_data[current_hour].append(risk_score)

            # Periodic cleanup of time series data
            if len(self.time_series_data[current_hour]) > 1000:
                self.time_series_data[current_hour] = self.time_series_data[current_hour][-500:]

        except Exception as e:
            logger.error(f"Error storing prediction result: {e}")

    async def _initialize_prediction_models(self) -> None:
        """Initialize ensemble of prediction models"""
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn not available - using fallback prediction")
            return

        try:
            # Generate synthetic training data if no historical data
            if len(self.risk_history) < 100:
                training_data = await self._generate_synthetic_training_data()
            else:
                training_data = list(self.risk_history)

            if len(training_data) < 10:
                logger.warning("Insufficient training data for prediction models")
                return

            # Prepare training data
            X = np.array([entry["features"] for entry in training_data if "features" in entry])
            y = np.array([entry["risk_score"] for entry in training_data if "features" in entry])

            if len(X) < 10:
                logger.warning("Insufficient feature data for model training")
                return

            # Initialize models
            models = {
                "random_forest": RandomForestRegressor(n_estimators=100, random_state=42),
                "gradient_boosting": GradientBoostingRegressor(n_estimators=100, random_state=42),
                "neural_network": MLPRegressor(
                    hidden_layer_sizes=(50, 25), max_iter=1000, random_state=42
                ),
                "svr": SVR(kernel="rbf", C=1.0),
                "linear": Ridge(alpha=1.0),
            }

            # Train models with cross-validation
            for name, model in models.items():
                try:
                    # Scale features
                    scaler = StandardScaler()
                    X_scaled = scaler.fit_transform(X)
                    self.scalers[name] = scaler

                    # Train model
                    model.fit(X_scaled, y)
                    self.prediction_models[name] = model

                    # Evaluate model
                    scores = cross_val_score(
                        model, X_scaled, y, cv=min(5, len(X) // 2), scoring="r2"
                    )
                    avg_score = np.mean(scores)

                    # Store performance metrics
                    self.model_performance_metrics[name] = {
                        "r2_score": float(avg_score),
                        "cross_val_std": float(np.std(scores)),
                        "training_samples": len(X),
                    }

                    logger.info(f"Trained {name} model with RA^2 score: {avg_score:.3f}")

                except Exception as e:
                    logger.warning(f"Failed to train {name} model: {e}")

        except Exception as e:
            logger.error(f"Error initializing prediction models: {e}")

    async def _initialize_anomaly_detection(self) -> None:
        """Initialize anomaly detection models"""
        if not SKLEARN_AVAILABLE:
            return

        try:
            # Initialize isolation forest for anomaly detection
            self.anomaly_detectors["isolation_forest"] = IsolationForest(
                contamination="auto",
                random_state=42,  # Auto-detect anomalies
            )

            # Train on historical data if available
            if len(self.risk_history) >= 50:
                features_data = np.array(
                    [
                        entry["features"]
                        for entry in self.risk_history
                        if "features" in entry and len(entry["features"]) > 0
                    ]
                )

                if len(features_data) >= 10:
                    self.anomaly_detectors["isolation_forest"].fit(features_data)
                    logger.info("Anomaly detection model trained on historical data")

        except Exception as e:
            logger.error(f"Error initializing anomaly detection: {e}")

    async def _initialize_pattern_recognition(self) -> None:
        """Initialize pattern recognition for risk patterns"""
        if not SKLEARN_AVAILABLE:
            return

        try:
            # Initialize clustering for pattern recognition
            self.clustering_models["kmeans"] = KMeans(n_clusters=5, random_state=42)
            self.clustering_models["dbscan"] = DBSCAN(eps=0.5, min_samples=5)

            logger.info("Pattern recognition models initialized")

        except Exception as e:
            logger.error(f"Error initializing pattern recognition: {e}")

    async def _generate_synthetic_training_data(
        self,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Generate synthetic training data for initial model training"""
        synthetic_data: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Create diverse synthetic scenarios
        scenarios = [
            # Low risk scenarios
            {"text": "display user preferences", "risk": 0.1, "type": "display"},
            {"text": "show public information", "risk": 0.15, "type": "display"},
            {"text": "calculate statistics", "risk": 0.2, "type": "compute"},
            # Medium risk scenarios
            {"text": "collect user feedback data", "risk": 0.4, "type": "collection"},
            {"text": "process payment information", "risk": 0.5, "type": "payment"},
            {"text": "access user location data", "risk": 0.6, "type": "location"},
            # High risk scenarios
            {"text": "modify user security settings", "risk": 0.7, "type": "security"},
            {"text": "delete personal information", "risk": 0.8, "type": "deletion"},
            {"text": "share data with third parties", "risk": 0.9, "type": "sharing"},
        ]

        for i, scenario in enumerate(scenarios):
            # Create basic features (simplified version)
            _s: dict[str, Any] = scenario  # TODO(TYPE): replace Any with concrete type
            features = [
                len(_s["text"]),  # Text length
                len(_s["text"].split()),  # Word count
                1 if "delete" in _s["text"] else 0,  # High risk indicator
                1 if "access" in _s["text"] else 0,  # Medium risk indicator
                1 if "user" in _s["text"] else 0,  # Privacy indicator
                1 if "security" in _s["text"] else 0,  # Security indicator
                0.5,  # User data involved
                0.3,  # System critical
                0.2,  # External access
                0.4,  # Automated decision
                0.1,  # User count normalized
                _s["risk"],  # Data sensitivity
                0.5,  # Time of day
                0.3,  # Day of week
                0.6,  # Month of year
                0.5,  # Priority
                0.1,  # Similar task count
                0.5,  # Recent risk mean
                0.2,  # Recent risk std
                0.0,  # Risk trend
                0.5,  # Hourly risk mean
                0.1,  # Hourly frequency
            ]

            synthetic_data.append(
                {
                    "task_id": f"synthetic_{i}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "risk_score": scenario["risk"],
                    "features": features,
                    "task_type": scenario["type"],
                    "context": {"synthetic": True},
                }
            )

        return synthetic_data

    async def _load_models_and_data(self) -> None:
        """Load existing models and historical data"""
        try:
            # Load models if they exist
            models_file = self.models_path / "prediction_models.pkl"
            if models_file.exists():
                # SECURITY FIX: Use SecureModelLoader for safe pickle loading
                saved_data = self._secure_loader.load_pickle(models_file)
                self.prediction_models = saved_data.get("models", {})
                self.scalers = saved_data.get("scalers", {})
                self.model_performance_metrics = saved_data.get("metrics", {})

                logger.info("Loaded existing prediction models")

            # Load historical risk data
            history_file = self.models_path / "risk_history.json"
            if history_file.exists():
                with open(history_file) as f:
                    history_data = json.load(f)
                    self.risk_history.extend(history_data.get("risk_history", []))
                    self.time_series_data.update(history_data.get("time_series_data", {}))

                logger.info(f"Loaded {len(self.risk_history)} historical risk records")

        except Exception as e:
            logger.error(f"Error loading models and data: {e}")

    async def _load_historical_risk_data(self) -> None:
        """Load and process historical risk assessment data"""
        # This would typically load from database or files
        # For now, using in-memory storage

    async def _fallback_risk_prediction(
        self,
        task: TaskData,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> RiskPrediction:
        """Fallback prediction when advanced models unavailable"""
        # Simple keyword-based risk assessment
        text = f"{task.title} {task.description}".lower()

        high_risk_words = ["delete", "destroy", "hack", "breach", "exploit"]
        medium_risk_words = ["modify", "access", "change", "update", "process"]

        high_count = sum(1 for word in high_risk_words if word in text)
        medium_count = sum(1 for word in medium_risk_words if word in text)

        if high_count > 0:
            base_risk = min(0.9, 0.6 + high_count * 0.1)
        elif medium_count > 0:
            base_risk = min(0.6, 0.3 + medium_count * 0.1)
        else:
            base_risk = 0.2

        return RiskPrediction(
            risk_score=base_risk,
            confidence=0.5,
            risk_trend="stable",
            predicted_timeline={"24_hours": base_risk},
            risk_factors={"keyword_analysis": base_risk},
            anomaly_score=0.0,
            similar_cases=[],
            predictions_reasoning=[f"Fallback keyword-based assessment: {base_risk:.2f}"],
            uncertainty_bounds=(max(0, base_risk - 0.2), min(1, base_risk + 0.2)),
            recommendation_urgency="moderate" if base_risk > 0.5 else "low",
        )

    async def _fallback_base_risk_prediction(
        self,
        features: npt.NDArray[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Fallback base risk prediction"""
        # Use feature heuristics
        if len(features) >= 6:
            # Combine high/medium risk indicators with privacy/security factors
            risk_score = (
                features[4] * 0.3 + features[5] * 0.3 + features[6] * 0.2 + features[7] * 0.2
            )
            return float(max(0.0, min(1.0, risk_score)))
        else:
            return 0.5  # Default moderate risk

    async def save_models_and_data(self) -> None:
        """Save trained models and historical data"""
        try:
            # Save models
            models_data = {
                "models": self.prediction_models,
                "scalers": self.scalers,
                "metrics": self.model_performance_metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            with open(self.models_path / "prediction_models.pkl", "wb") as f:
                pickle.dump(models_data, f)

            # Save historical data
            history_data = {
                "risk_history": list(self.risk_history),
                "time_series_data": dict(self.time_series_data),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            with open(self.models_path / "risk_history.json", "w") as f:
                json.dump(history_data, f, indent=2)

            logger.info("Risk prediction models and data saved successfully")

        except Exception as e:
            logger.error(f"Error saving models and data: {e}")

    async def get_system_metrics(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive system performance metrics"""
        return {
            "models_available": len(self.prediction_models),
            "anomaly_detectors": len(self.anomaly_detectors),
            "historical_records": len(self.risk_history),
            "model_performance": self.model_performance_metrics,
            "prediction_accuracy_history": self.prediction_accuracy_history[
                -20:
            ],  # Recent accuracy
            "risk_thresholds": self.risk_thresholds,
            "prediction_horizons": self.prediction_horizons,
            "sklearn_available": SKLEARN_AVAILABLE,
            "pandas_available": PANDAS_AVAILABLE,
            "system_initialized": bool(self.prediction_models or not SKLEARN_AVAILABLE),
        }


# Factory function
async def create_risk_prediction_system() -> RiskPredictionSystem:
    """Create and initialize risk prediction system"""
    system = RiskPredictionSystem()
    await system.initialize()
    return system
