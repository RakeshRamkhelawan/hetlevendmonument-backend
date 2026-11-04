"""
Central Agent ML Training Platform

Provides ML capabilities to ALL agents in the SanskritiSetu ecosystem:
- Pack Intent Matching (bestaat)
- CVA Intent Classification
- Workflow Prediction
- Agent Selection Optimization
- Anomaly Detection
- Personalization

This is the single, centralized ML training infrastructure.
"""

import json
import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, TypeVar
from collections.abc import Callable

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MLTaskType(str, Enum):
    """Types of ML tasks agents can use"""

    INTENT_CLASSIFICATION = "intent_classification"  # CVA, Pack Matcher
    RECOMMENDATION = "recommendation"  # Workflow suggesties
    PREDICTION = "prediction"  # Success/Failure voorspelling
    ANOMALY_DETECTION = "anomaly_detection"  # Abnormaal gedrag detecteren
    PERSONALIZATION = "personalization"  # Tenant-specifieke aanpassingen
    SELECTION_OPTIMIZATION = "selection_optimization"  # Beste agent kiezen


@dataclass
class MLModelConfig:
    """Configuration for an ML model"""

    task_type: MLTaskType
    model_name: str
    feature_columns: list[str]
    target_column: str
    model_class: str = "RandomForestClassifier"
    hyperparameters: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    min_samples: int = 50
    retrain_interval: int = 100  # Retrain every N new samples


@dataclass
class TrainingRecord:
    """A single training record for any agent"""

    agent_id: str  # Which agent this is for
    tenant_id: int
    timestamp: datetime
    features: dict[str, Any]  # Input features  # TODO(TYPE): replace Any with concrete type
    prediction: Any  # What the model predicted  # TODO(TYPE): replace Any with concrete type
    actual: Any  # What actually happened  # TODO(TYPE): replace Any with concrete type
    was_correct: bool
    metadata: dict[str, Any]  # Extra context  # TODO(TYPE): replace Any with concrete type


@dataclass
class AgentMLModel:
    """An ML model for a specific agent"""

    config: MLModelConfig
    model: Any = None
    vectorizer: Any = None
    label_encoder: Any = None
    training_count: int = 0
    last_trained: datetime | None = None
    accuracy: float = 0.0


class CentralAgentMLPlatform:
    """
    Centralized ML Training Platform for ALL Agents

    Single source of truth for:
    - Model training
    - Feature extraction
    - Prediction serving
    - Feedback collection
    - Performance monitoring

    Usage:
        platform = get_ml_platform()

        # Register an agent's ML needs
        platform.register_agent(
            agent_id="cva_supervisor",
            task_type=MLTaskType.INTENT_CLASSIFICATION,
            config={...}
        )

        # Get prediction
        result = platform.predict("cva_supervisor", features={...})

        # Provide feedback
        platform.record_feedback(
            agent_id="cva_supervisor",
            prediction=result.prediction,
            actual=outcome,
            was_correct=True
        )
    """

    def __init__(self, model_dir: str = ".models/agents") -> None:
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        # Registry of agent models
        self._agent_models: dict[str, AgentMLModel] = {}
        self._training_records: dict[str, list[TrainingRecord]] = {}

        # Feature extractors (shared across agents)
        self._text_vectorizer: TfidfVectorizer | None = None
        self._initialized = False

        # Performance tracking
        self._performance_stats: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

        self._load_all_models()

    # =========================================================================
    # Agent Registration
    # =========================================================================

    def register_agent(
        self,
        agent_id: str,
        task_type: MLTaskType,
        feature_columns: list[str],
        target_column: str,
        model_class: str = "RandomForestClassifier",
        hyperparameters: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        min_samples: int = 50,
    ) -> bool:
        """
        Register an agent for ML capabilities

        Example:
            platform.register_agent(
                agent_id="pack_intent_matcher",
                task_type=MLTaskType.INTENT_CLASSIFICATION,
                feature_columns=["text_similarity", "department_match"],
                target_column="was_helpful",
                model_class="RandomForestClassifier",
                min_samples=50
            )
        """
        if agent_id in self._agent_models:
            logger.info(f"Agent {agent_id} already registered, updating config")

        config = MLModelConfig(
            task_type=task_type,
            model_name=f"{agent_id}_{task_type.value}",
            feature_columns=feature_columns,
            target_column=target_column,
            model_class=model_class,
            hyperparameters=hyperparameters or {},
            min_samples=min_samples,
        )

        self._agent_models[agent_id] = AgentMLModel(config=config)
        self._training_records[agent_id] = []

        # Load existing model if available
        self._load_agent_model(agent_id)

        logger.info(f"Registered agent {agent_id} for {task_type.value}")
        return True

    # =========================================================================
    # Prediction
    # =========================================================================

    def predict(
        self, agent_id: str, features: dict[str, Any], return_confidence: bool = True  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get prediction from an agent's ML model

        Returns:
            {
                "prediction": <value>,
                "confidence": <0-1>,
                "model_version": <str>,
                "features_used": <dict>,
                "agent_id": <str>
            }
        """
        if agent_id not in self._agent_models:
            raise ValueError(f"Agent {agent_id} not registered. Call register_agent() first.")

        agent_model = self._agent_models[agent_id]

        # If no model trained yet, return fallback
        if agent_model.model is None:
            return self._fallback_prediction(agent_id, features)

        try:
            # Extract features
            feature_vector = self._extract_features(agent_id, features)

            # Predict
            prediction = agent_model.model.predict([feature_vector])[0]

            result = {
                "prediction": prediction,
                "agent_id": agent_id,
                "model_version": (
                    agent_model.last_trained.isoformat()
                    if agent_model.last_trained
                    else "untrained"
                ),
                "features_used": features,
            }

            if return_confidence:
                proba = agent_model.model.predict_proba([feature_vector])[0]
                confidence = max(proba)
                result["confidence"] = confidence

                # Add all class probabilities
                if agent_model.label_encoder:
                    classes = agent_model.label_encoder.classes_
                    result["class_probabilities"] = {
                        str(cls): float(prob) for cls, prob in zip(classes, proba)
                    }

            return result

        except Exception as e:
            logger.error(f"Prediction failed for {agent_id}: {e}")
            return self._fallback_prediction(agent_id, features)

    def predict_batch(
        self, agent_id: str, features_list: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Batch prediction for efficiency"""
        return [self.predict(agent_id, f) for f in features_list]

    # =========================================================================
    # Feedback & Training
    # =========================================================================

    def record_feedback(
        self,
        agent_id: str,
        features: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        prediction: Any,  # TODO(TYPE): replace Any with concrete type
        actual: Any,  # TODO(TYPE): replace Any with concrete type
        was_correct: bool,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Record feedback for continuous learning

        Auto-triggers model retraining when enough samples collected.
        """
        if agent_id not in self._agent_models:
            logger.warning(f"Cannot record feedback: agent {agent_id} not registered")
            return

        record = TrainingRecord(
            agent_id=agent_id,
            tenant_id=metadata.get("tenant_id", 0) if metadata else 0,
            timestamp=datetime.now(timezone.utc),
            features=features,
            prediction=prediction,
            actual=actual,
            was_correct=was_correct,
            metadata=metadata or {},
        )

        self._training_records[agent_id].append(record)

        # Update stats
        self._update_performance_stats(agent_id, was_correct)

        # Auto-save every 10 records
        if len(self._training_records[agent_id]) % 10 == 0:
            self._save_training_data(agent_id)

        # Auto-retrain if enough samples
        agent_model = self._agent_models[agent_id]
        config = agent_model.config

        records_count = len(self._training_records[agent_id])

        if records_count >= config.min_samples:
            # Retrain every N samples
            if records_count % config.retrain_interval == 0:
                logger.info(f"Auto-retraining {agent_id} with {records_count} samples")
                self.train_agent_model(agent_id)

    def train_agent_model(self, agent_id: str) -> bool:
        """Train/update ML model for a specific agent"""
        if agent_id not in self._agent_models:
            logger.error(f"Cannot train: agent {agent_id} not registered")
            return False

        records = self._training_records.get(agent_id, [])

        if len(records) < self._agent_models[agent_id].config.min_samples:
            logger.warning(f"Not enough samples to train {agent_id}")
            return False

        try:
            agent_model = self._agent_models[agent_id]
            config = agent_model.config

            # Prepare training data
            X_list: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            y_list: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for record in records:
                features = self._extract_features(agent_id, record.features)
                X_list.append(features)

                # Encode target if needed
                target = record.actual
                if isinstance(target, bool):
                    target = int(target)
                y_list.append(target)

            X = np.array(X_list)
            y = np.array(y_list)

            # Split
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            # Create and train model
            if config.model_class == "RandomForestClassifier":
                model = RandomForestClassifier(
                    n_estimators=config.hyperparameters.get("n_estimators", 100),
                    max_depth=config.hyperparameters.get("max_depth", 10),
                    random_state=42,
                )
            elif config.model_class == "GradientBoostingClassifier":
                model = GradientBoostingClassifier(
                    n_estimators=config.hyperparameters.get("n_estimators", 100), random_state=42
                )
            else:
                model = RandomForestClassifier(random_state=42)

            model.fit(X_train, y_train)

            # Evaluate
            train_score = model.score(X_train, y_train)
            test_score = model.score(X_test, y_test)

            # Update agent model
            agent_model.model = model
            agent_model.last_trained = datetime.now(timezone.utc)
            agent_model.training_count = len(records)
            agent_model.accuracy = test_score

            # Save
            self._save_agent_model(agent_id)

            logger.info(
                f"Trained {agent_id}: train_acc={train_score:.3f}, "
                f"test_acc={test_score:.3f}, samples={len(records)}"
            )

            return True

        except Exception as e:
            logger.error(f"Training failed for {agent_id}: {e}")
            return False

    def train_all_models(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Train all registered agent models"""
        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_id in self._agent_models:
            results[agent_id] = self.train_agent_model(agent_id)
        return results

    # =========================================================================
    # Feature Extraction (Shared)
    # =========================================================================

    def _extract_features(self, agent_id: str, features: dict[str, Any]) -> np.ndarray[Any, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract feature vector from feature dict"""
        agent_model = self._agent_models[agent_id]
        config = agent_model.config

        feature_vector: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for col in config.feature_columns:
            value = features.get(col, 0)

            # Handle text features
            if isinstance(value, str) and col.endswith("_text"):
                if self._text_vectorizer is None:
                    self._text_vectorizer = TfidfVectorizer(max_features=100)
                # This is simplified - in practice need consistent vectorization
                value = len(value)  # Placeholder

            # Normalize
            if isinstance(value, bool):
                value = float(value)

            feature_vector.append(float(value))

        return np.array(feature_vector)

    def _fallback_prediction(self, agent_id: str, features: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Fallback when model not available"""
        return {
            "prediction": None,
            "confidence": 0.0,
            "agent_id": agent_id,
            "model_version": "untrained_fallback",
            "features_used": features,
            "error": "Model not trained yet",
        }

    # =========================================================================
    # Analytics & Monitoring
    # =========================================================================

    def get_agent_performance(self, agent_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get performance metrics for an agent"""
        if agent_id not in self._agent_models:
            return {"error": "Agent not registered"}

        agent_model = self._agent_models[agent_id]
        records = self._training_records.get(agent_id, [])

        if not records:
            return {"agent_id": agent_id, "status": "no_data", "total_predictions": 0}

        correct = sum(1 for r in records if r.was_correct)

        return {
            "agent_id": agent_id,
            "status": "trained" if agent_model.model else "untrained",
            "task_type": agent_model.config.task_type.value,
            "total_predictions": len(records),
            "correct_predictions": correct,
            "accuracy": correct / len(records) if records else 0,
            "model_accuracy": agent_model.accuracy,
            "last_trained": agent_model.last_trained,
            "training_samples": agent_model.training_count,
        }

    def get_all_agents_performance(self) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get performance for all agents"""
        return {agent_id: self.get_agent_performance(agent_id) for agent_id in self._agent_models}

    def get_platform_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall platform statistics"""
        total_records = sum(len(records) for records in self._training_records.values())

        trained_models = sum(1 for m in self._agent_models.values() if m.model is not None)

        return {
            "registered_agents": len(self._agent_models),
            "trained_models": trained_models,
            "untrained_models": len(self._agent_models) - trained_models,
            "total_training_records": total_records,
            "agents": list(self._agent_models.keys()),
        }

    def _update_performance_stats(self, agent_id: str, was_correct: bool) -> None:
        """Update running performance stats"""
        if agent_id not in self._performance_stats:
            self._performance_stats[agent_id] = {"total": 0, "correct": 0, "recent": []}

        stats = self._performance_stats[agent_id]
        stats["total"] += 1
        if was_correct:
            stats["correct"] += 1

        stats["recent"].append(was_correct)
        if len(stats["recent"]) > 100:
            stats["recent"] = stats["recent"][-100:]

    # =========================================================================
    # Persistence
    # =========================================================================

    def _save_agent_model(self, agent_id: str) -> None:
        """Save an agent's model to disk"""
        agent_model = self._agent_models[agent_id]

        if agent_model.model is None:
            return

        model_path = self.model_dir / f"{agent_id}_model.pkl"

        data = {
            "config": agent_model.config,
            "model": agent_model.model,
            "vectorizer": agent_model.vectorizer,
            "label_encoder": agent_model.label_encoder,
            "training_count": agent_model.training_count,
            "last_trained": agent_model.last_trained,
            "accuracy": agent_model.accuracy,
        }

        with open(model_path, "wb") as f:
            pickle.dump(data, f)

    def _load_agent_model(self, agent_id: str) -> None:
        """Load an agent's model from disk"""
        model_path = self.model_dir / f"{agent_id}_model.pkl"

        if not model_path.exists():
            return

        try:
            with open(model_path, "rb") as f:
                data = pickle.load(f)  # nosec B301 - controlled local model file written by this service

            agent_model = self._agent_models[agent_id]
            agent_model.model = data.get("model")
            agent_model.vectorizer = data.get("vectorizer")
            agent_model.label_encoder = data.get("label_encoder")
            agent_model.training_count = data.get("training_count", 0)
            agent_model.last_trained = data.get("last_trained")
            agent_model.accuracy = data.get("accuracy", 0.0)

            logger.info(f"Loaded model for {agent_id}")

        except Exception as e:
            logger.error(f"Failed to load model for {agent_id}: {e}")

    def _save_training_data(self, agent_id: str) -> None:
        """Save training records to disk"""
        records = self._training_records.get(agent_id, [])

        data_path = self.model_dir / f"{agent_id}_training.json"

        data = [
            {
                "timestamp": r.timestamp.isoformat(),
                "features": r.features,
                "prediction": r.prediction,
                "actual": r.actual,
                "was_correct": r.was_correct,
                "metadata": r.metadata,
            }
            for r in records
        ]

        with open(data_path, "w") as f:
            json.dump(data, f)

    def _load_all_models(self) -> None:
        """Load all saved models on startup"""
        if not self.model_dir.exists():
            return

        for model_file in self.model_dir.glob("*_model.pkl"):
            agent_id = model_file.stem.replace("_model", "")
            # Will be loaded when agent registers
            logger.debug(f"Found saved model for {agent_id}")

    def _load_training_data(self, agent_id: str) -> None:
        """Load training records from disk"""
        data_path = self.model_dir / f"{agent_id}_training.json"

        if not data_path.exists():
            return

        try:
            with open(data_path) as f:
                data = json.load(f)

            self._training_records[agent_id] = [
                TrainingRecord(
                    agent_id=agent_id,
                    tenant_id=r.get("metadata", {}).get("tenant_id", 0),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    features=r["features"],
                    prediction=r["prediction"],
                    actual=r["actual"],
                    was_correct=r["was_correct"],
                    metadata=r.get("metadata", {}),
                )
                for r in data
            ]

            logger.info(f"Loaded {len(data)} training records for {agent_id}")

        except Exception as e:
            logger.error(f"Failed to load training data for {agent_id}: {e}")


# Singleton
_ml_platform: CentralAgentMLPlatform | None = None


def get_ml_platform() -> CentralAgentMLPlatform:
    """Get or create singleton ML platform"""
    global _ml_platform
    if _ml_platform is None:
        _ml_platform = CentralAgentMLPlatform()
    return _ml_platform
