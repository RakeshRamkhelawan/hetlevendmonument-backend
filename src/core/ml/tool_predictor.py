"""
Tool Predictor ML Service.
Feature 4: Predict next best tool based on history and context.

Uses a Random Forest classifier trained on user tool usage history.
"""

from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import joblib
import redis.asyncio as redis_asyncio
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from src.core.database.redis import get_redis_client

logger = logging.getLogger(__name__)

__all__ = ["ToolPredictor", "get_tool_predictor"]


class ToolPredictor:
    """
    ML-based tool suggestion predictor.

    Features used:
    - Hour of day (0-23)
    - Day of week (0-6)
    - Previous N tools used (encoded)
    - Query embedding similarity (optional, simplified here)
    """

    MODEL_KEY_PREFIX = "ml:tool_predictor:"
    ENCODER_KEY_PREFIX = "ml:tool_encoder:"
    HISTORY_WINDOW = 5  # Number of previous tools to consider

    def __init__(self) -> None:
        self.redis: redis_asyncio.Redis | None = None  # type: ignore[type-arg]
        self._models: dict[int, RandomForestClassifier] = {}
        self._encoders: dict[int, LabelEncoder] = {}

    async def _get_redis(self) -> redis_asyncio.Redis:  # type: ignore[type-arg]
        if self.redis is None:
            self.redis = await get_redis_client()
        return self.redis

    def _model_key(self, tenant_id: int) -> str:
        return f"{self.MODEL_KEY_PREFIX}{tenant_id}"

    def _encoder_key(self, tenant_id: int) -> str:
        return f"{self.ENCODER_KEY_PREFIX}{tenant_id}"

    def _extract_features(
        self, timestamp: datetime, history: list[str], encoder: LabelEncoder
    ) -> np.ndarray[Any, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Extract feature vector from context.
        """
        features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Time features
        features.append(timestamp.hour)  # 0-23
        features.append(timestamp.weekday())  # 0-6

        # History features (last N tools, encoded)
        history_encoded: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i in range(self.HISTORY_WINDOW):
            if i < len(history):
                try:
                    encoded = encoder.transform([history[-(i + 1)]])[0]
                except ValueError:
                    encoded = -1  # Unknown tool
            else:
                encoded = -1  # Padding for missing history
            history_encoded.append(encoded)

        features.extend(history_encoded)

        return np.array(features).reshape(1, -1)

    async def train(
        self,
        tenant_id: int,
        usage_data: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Train the model for a specific tenant.

        usage_data format:
        [
            {"tool_id": "tool1", "timestamp": "2025-01-15T10:30:00", "context": {...}},
            ...
        ]

        Returns training metrics.
        """
        if len(usage_data) < 10:
            return {
                "status": "error",
                "message": "Insufficient data (need at least 10 records)",
            }

        # Extract all unique tools
        all_tools = list({d["tool_id"] for d in usage_data})

        # Create label encoder
        encoder = LabelEncoder()
        encoder.fit(all_tools)

        # Prepare training data
        X_list: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        y_list: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        sorted_data = sorted(usage_data, key=lambda x: x["timestamp"])

        for i in range(self.HISTORY_WINDOW, len(sorted_data)):
            current = sorted_data[i]
            history = [d["tool_id"] for d in sorted_data[max(0, i - self.HISTORY_WINDOW) : i]]

            timestamp = datetime.fromisoformat(current["timestamp"].replace("Z", "+00:00"))
            features = self._extract_features(timestamp, history, encoder)

            X_list.append(features.flatten())
            y_list.append(encoder.transform([current["tool_id"]])[0])

        X = np.array(X_list)
        y = np.array(y_list)

        # Train Random Forest
        model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
        model.fit(X, y)

        # Evaluate (simple train accuracy)
        train_accuracy = model.score(X, y)

        # Save to Redis
        redis = await self._get_redis()

        # Serialize model
        model_buffer = io.BytesIO()
        joblib.dump(model, model_buffer)
        model_bytes = model_buffer.getvalue()

        # Serialize encoder
        encoder_buffer = io.BytesIO()
        joblib.dump(encoder, encoder_buffer)
        encoder_bytes = encoder_buffer.getvalue()

        await redis.set(self._model_key(tenant_id), model_bytes)
        await redis.set(self._encoder_key(tenant_id), encoder_bytes)

        # Cache locally
        self._models[tenant_id] = model
        self._encoders[tenant_id] = encoder

        logger.info(
            f"Trained tool predictor for tenant {tenant_id} with accuracy {train_accuracy:.2%}"
        )

        return {
            "status": "success",
            "samples": len(X),
            "tools": len(all_tools),
            "train_accuracy": round(train_accuracy, 4),
        }

    async def _load_model(self, tenant_id: int) -> bool:
        """Load model from Redis if not cached."""
        if tenant_id in self._models:
            return True

        redis = await self._get_redis()

        model_bytes = await redis.get(self._model_key(tenant_id))
        encoder_bytes = await redis.get(self._encoder_key(tenant_id))

        if model_bytes and encoder_bytes:
            self._models[tenant_id] = joblib.load(io.BytesIO(model_bytes))
            self._encoders[tenant_id] = joblib.load(io.BytesIO(encoder_bytes))
            return True

        return False

    async def predict(
        self,
        tenant_id: int,
        history: list[str],
        timestamp: datetime | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Predict next best tools for a tenant.

        Returns list of tool suggestions with confidence scores.
        """
        if not await self._load_model(tenant_id):
            logger.warning(f"No trained model for tenant {tenant_id}")
            return []

        model = self._models[tenant_id]
        encoder = self._encoders[tenant_id]

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        features = self._extract_features(timestamp, history, encoder)

        # Get probability predictions
        probabilities = model.predict_proba(features)[0]

        # Get top-k predictions
        top_indices = np.argsort(probabilities)[::-1][:top_k]

        suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for idx in top_indices:
            tool_id = encoder.inverse_transform([idx])[0]
            confidence = float(probabilities[idx])

            suggestions.append({"tool_id": tool_id, "confidence": round(confidence, 4)})

        return suggestions


# Singleton instance
_tool_predictor: ToolPredictor | None = None


async def get_tool_predictor() -> ToolPredictor:
    """Get the singleton ToolPredictor instance."""
    global _tool_predictor
    if _tool_predictor is None:
        _tool_predictor = ToolPredictor()
    return _tool_predictor
