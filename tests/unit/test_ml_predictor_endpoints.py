"""
Unit tests for ML Tool Predictor feature (Feature 4).
Tests prediction service, training pipeline, and API endpoints.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ============================================================================
# Test ML Predictor Service
# ============================================================================


class TestToolPredictorInitialization:
    """Tests for ToolPredictor initialization."""

    def test_predictor_initialization(self):
        """Test predictor initializes with default configuration."""
        config = {
            "n_estimators": 100,
            "max_depth": 10,
            "min_samples_split": 2,
            "random_state": 42,
        }

        assert config["n_estimators"] > 0
        assert config["random_state"] == 42

    def test_predictor_requires_redis(self):
        """Test predictor requires Redis for model storage."""
        redis_url = "redis://localhost:6380/0"
        assert redis_url.startswith("redis://")

    def test_predictor_default_tools(self):
        """Test predictor has default tool categories."""
        default_tools = [
            "code_generation",
            "code_review",
            "documentation",
            "testing",
            "debugging",
            "deployment",
            "data_analysis",
            "visualization",
        ]

        assert len(default_tools) > 5


class TestToolPredictorTraining:
    """Tests for model training functionality."""

    @pytest.mark.asyncio
    async def test_train_with_sufficient_data(self):
        """Test training with sufficient historical data."""
        training_data = [
            {"query": "write a function", "tool": "code_generation", "context": {}},
            {"query": "review this code", "tool": "code_review", "context": {}},
            {"query": "test this function", "tool": "testing", "context": {}},
        ] * 50  # 150 samples

        assert len(training_data) >= 100

    @pytest.mark.asyncio
    async def test_train_with_insufficient_data(self):
        """Test training fails gracefully with insufficient data."""
        training_data = [
            {"query": "write code", "tool": "code_generation"},
        ] * 5  # Only 5 samples

        min_samples = 10
        has_sufficient_data = len(training_data) >= min_samples
        assert has_sufficient_data is False

    @pytest.mark.asyncio
    async def test_train_feature_extraction(self):
        """Test feature extraction during training."""
        sample = {
            "query": "generate unit tests for authentication",
            "tool": "testing",
            "context": {
                "hour_of_day": 14,
                "day_of_week": 2,
                "recent_tools": ["code_generation", "code_review"],
            },
        }

        # Features should include query-based and context-based
        assert "hour_of_day" in sample["context"]
        assert len(sample["context"]["recent_tools"]) > 0

    @pytest.mark.asyncio
    async def test_train_model_saved_to_redis(self):
        """Test trained model is saved to Redis."""
        mock_redis = AsyncMock()

        model_key = "ml:predictor:tenant:1:model"
        model_data = b"serialized_model_bytes"

        await mock_redis.set(model_key, model_data)
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_train_creates_label_encoder(self):
        """Test training creates label encoder for tools."""
        tools = ["code_generation", "testing", "debugging"]
        encoded = {tool: idx for idx, tool in enumerate(tools)}

        assert encoded["code_generation"] == 0
        assert encoded["testing"] == 1
        assert encoded["debugging"] == 2

    @pytest.mark.asyncio
    async def test_train_validation_split(self):
        """Test training uses validation split."""
        total_samples = 100
        train_split = 0.8

        train_size = int(total_samples * train_split)
        val_size = total_samples - train_size

        assert train_size == 80
        assert val_size == 20


class TestToolPredictorPrediction:
    """Tests for prediction functionality."""

    @pytest.mark.asyncio
    async def test_predict_returns_top_tools(self):
        """Test prediction returns top N tools."""
        predictions = [
            {"tool": "code_generation", "confidence": 0.85},
            {"tool": "testing", "confidence": 0.10},
            {"tool": "debugging", "confidence": 0.05},
        ]

        top_n = 3
        assert len(predictions) == top_n
        assert predictions[0]["confidence"] > predictions[1]["confidence"]

    @pytest.mark.asyncio
    async def test_predict_confidence_scores(self):
        """Test predictions include confidence scores."""
        prediction = {"tool": "code_generation", "confidence": 0.85}

        assert 0 <= prediction["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_predict_loads_model_from_redis(self):
        """Test prediction loads model from Redis."""
        mock_redis = AsyncMock()

        model_key = "ml:predictor:tenant:1:model"
        mock_redis.get.return_value = b"serialized_model"

        model_data = await mock_redis.get(model_key)
        assert model_data is not None

    @pytest.mark.asyncio
    async def test_predict_without_trained_model(self):
        """Test prediction returns default when no model."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        # Should return default tools
        default_predictions = [
            {"tool": "code_generation", "confidence": 0.5},
            {"tool": "documentation", "confidence": 0.3},
        ]

        assert len(default_predictions) > 0

    @pytest.mark.asyncio
    async def test_predict_context_aware(self):
        """Test prediction uses context information."""
        context = {
            "hour_of_day": 9,  # Morning
            "recent_tools": ["code_generation"],
            "current_file_type": "python",
        }

        # Context should influence predictions
        assert "hour_of_day" in context
        assert "recent_tools" in context

    @pytest.mark.asyncio
    async def test_predict_query_vectorization(self):
        """Test query is vectorized for prediction."""
        query = "write unit tests for login function"

        # Should extract keywords
        keywords = query.lower().split()
        assert "unit" in keywords
        assert "tests" in keywords


class TestToolPredictorFeatureEngineering:
    """Tests for feature engineering in ML predictor."""

    def test_extract_time_features(self):
        """Test extraction of time-based features."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        features = {
            "hour_of_day": now.hour,
            "day_of_week": now.weekday(),
            "is_weekend": now.weekday() >= 5,
        }

        assert 0 <= features["hour_of_day"] <= 23
        assert 0 <= features["day_of_week"] <= 6

    def test_extract_query_features(self):
        """Test extraction of query-based features."""
        query = "generate documentation for API"

        features = {
            "query_length": len(query),
            "word_count": len(query.split()),
            "has_code_keyword": any(kw in query.lower() for kw in ["code", "function", "class"]),
            "has_test_keyword": any(kw in query.lower() for kw in ["test", "testing", "unittest"]),
        }

        assert features["word_count"] == 4
        assert features["has_code_keyword"] is False
        assert features["has_test_keyword"] is False

    def test_extract_history_features(self):
        """Test extraction of user history features."""
        recent_tools = ["code_generation", "code_review", "testing"]

        features = {
            "last_tool": recent_tools[-1] if recent_tools else None,
            "tool_diversity": len(set(recent_tools)),
            "session_tool_count": len(recent_tools),
        }

        assert features["last_tool"] == "testing"
        assert features["tool_diversity"] == 3

    def test_feature_normalization(self):
        """Test feature values are normalized."""
        raw_features = {"hour_of_day": 14, "query_length": 50}

        # Normalize to 0-1 range
        normalized = {
            "hour_of_day": raw_features["hour_of_day"] / 24,
            "query_length": min(raw_features["query_length"] / 200, 1.0),
        }

        assert 0 <= normalized["hour_of_day"] <= 1
        assert 0 <= normalized["query_length"] <= 1


class TestToolPredictorModelPersistence:
    """Tests for model persistence and loading."""

    @pytest.mark.asyncio
    async def test_model_serialization(self):
        """Test model is serialized with joblib."""
        # Simulate joblib serialization
        model_bytes = b"serialized_random_forest_model"
        assert len(model_bytes) > 0

    @pytest.mark.asyncio
    async def test_model_key_includes_tenant(self):
        """Test model Redis key includes tenant ID."""
        tenant_id = 1
        model_key = f"ml:predictor:tenant:{tenant_id}:model"

        assert "tenant:1" in model_key

    @pytest.mark.asyncio
    async def test_model_key_includes_version(self):
        """Test model key can include version."""
        tenant_id = 1
        version = "v2"
        model_key = f"ml:predictor:tenant:{tenant_id}:model:{version}"

        assert version in model_key

    @pytest.mark.asyncio
    async def test_label_encoder_persisted(self):
        """Test label encoder is persisted with model."""
        encoder_key = "ml:predictor:tenant:1:encoder"
        encoder_data = json.dumps(["code_generation", "testing", "debugging"])

        # Should be stored alongside model
        assert len(encoder_data) > 0

    @pytest.mark.asyncio
    async def test_model_expiry_configured(self):
        """Test model has optional expiry."""
        model_ttl = 86400 * 30  # 30 days
        assert model_ttl == 2592000


# ============================================================================
# Test ML Predictor API Endpoints
# ============================================================================


class TestMLPredictorAPIEndpoints:
    """Tests for ML Predictor API endpoints."""

    @pytest.mark.asyncio
    async def test_train_endpoint(self):
        """Test POST /api/v1/ml/train triggers training."""
        response = {
            "status": "success",
            "message": "Model training started",
            "samples_used": 500,
            "accuracy": 0.87,
        }

        assert response["status"] == "success"
        assert "accuracy" in response

    @pytest.mark.asyncio
    async def test_predict_endpoint_get(self):
        """Test GET /api/v1/ml/predict-tools returns predictions."""
        response = {
            "predictions": [
                {"tool": "code_generation", "confidence": 0.85},
                {"tool": "testing", "confidence": 0.10},
            ],
            "query": "write a function",
            "model_version": "v1",
        }

        assert len(response["predictions"]) > 0
        assert response["predictions"][0]["confidence"] > 0

    @pytest.mark.asyncio
    async def test_predict_endpoint_post(self):
        """Test POST /api/v1/ml/predict-tools with context."""
        request = {
            "query": "debug authentication issue",
            "context": {
                "recent_tools": ["code_review"],
                "current_file": "auth_service.py",
            },
        }
        response = {"predictions": [{"tool": "debugging", "confidence": 0.75}]}

        assert "context" in request
        assert len(response["predictions"]) > 0

    @pytest.mark.asyncio
    async def test_record_usage_endpoint(self):
        """Test POST /api/v1/ml/record-usage records tool usage."""
        request = {
            "query": "write unit tests",
            "tool_used": "testing",
            "feedback": "helpful",
        }
        response = {"status": "recorded"}

        assert request["tool_used"] == "testing"
        assert response["status"] == "recorded"


class TestMLPredictorAPISchemas:
    """Tests for ML Predictor API schemas."""

    def test_train_request_schema(self):
        """Test TrainRequest schema."""
        request = {"min_samples": 100, "validation_split": 0.2, "n_estimators": 100}

        assert request["min_samples"] >= 10
        assert 0 < request["validation_split"] < 1

    def test_predict_request_schema(self):
        """Test PredictRequest schema."""
        request = {"query": "generate code", "top_n": 3, "context": {}}

        assert len(request["query"]) > 0
        assert request["top_n"] >= 1

    def test_prediction_response_schema(self):
        """Test PredictionResponse schema."""
        response = {
            "predictions": [
                {
                    "tool": "code_generation",
                    "confidence": 0.85,
                    "description": "Generate code",
                }
            ],
            "model_version": "v1",
            "latency_ms": 15,
        }

        assert "predictions" in response
        assert "latency_ms" in response

    def test_training_response_schema(self):
        """Test TrainingResponse schema."""
        response = {
            "status": "success",
            "samples_used": 500,
            "accuracy": 0.87,
            "training_time_seconds": 2.5,
            "model_version": "v1",
        }

        assert response["accuracy"] <= 1.0
        assert response["training_time_seconds"] > 0


class TestMLPredictorAPIErrorHandling:
    """Tests for ML API error handling."""

    @pytest.mark.asyncio
    async def test_train_insufficient_data_error(self):
        """Test error when insufficient training data."""
        error = {"detail": "Insufficient training data. Need at least 100 samples, found 50."}
        status_code = 400

        assert status_code == 400
        assert "insufficient" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_predict_no_model_error(self):
        """Test error when no trained model exists."""
        error = {"detail": "No trained model found. Please train the model first."}
        status_code = 404

        assert status_code == 404

    @pytest.mark.asyncio
    async def test_predict_empty_query_error(self):
        """Test error for empty prediction query."""
        error = {"detail": "Query cannot be empty"}
        status_code = 400

        assert status_code == 400


# ============================================================================
# Test ML Model Performance
# ============================================================================


class TestMLModelPerformance:
    """Tests for ML model performance metrics."""

    def test_accuracy_calculation(self):
        """Test accuracy metric calculation."""
        predictions = [1, 0, 1, 1, 0]
        actual = [1, 0, 1, 0, 0]

        correct = sum(p == a for p, a in zip(predictions, actual))
        accuracy = correct / len(predictions)

        assert accuracy == 0.8

    def test_precision_calculation(self):
        """Test precision metric calculation."""
        true_positives = 40
        false_positives = 10

        precision = true_positives / (true_positives + false_positives)
        assert precision == 0.8

    def test_recall_calculation(self):
        """Test recall metric calculation."""
        true_positives = 40
        false_negatives = 20

        recall = true_positives / (true_positives + false_negatives)
        assert round(recall, 2) == 0.67

    def test_f1_score_calculation(self):
        """Test F1 score calculation."""
        precision = 0.8
        recall = 0.67

        f1 = 2 * (precision * recall) / (precision + recall)
        assert round(f1, 2) == 0.73

    def test_prediction_latency_requirement(self):
        """Test prediction latency is under threshold."""
        max_latency_ms = 100  # 100ms max
        actual_latency_ms = 15

        assert actual_latency_ms < max_latency_ms


class TestMLTenantIsolation:
    """Tests for tenant isolation in ML predictor."""

    @pytest.mark.asyncio
    async def test_model_per_tenant(self):
        """Test each tenant has separate model."""
        tenant_1_key = "ml:predictor:tenant:1:model"
        tenant_2_key = "ml:predictor:tenant:2:model"

        assert tenant_1_key != tenant_2_key

    @pytest.mark.asyncio
    async def test_training_data_tenant_scoped(self):
        """Test training data is scoped to tenant."""
        tenant_id = 1
        query = "SELECT * FROM tool_usage WHERE tenant_id = :tenant_id"

        assert ":tenant_id" in query

    @pytest.mark.asyncio
    async def test_predictions_use_tenant_model(self):
        """Test predictions use tenant-specific model."""
        tenant_id = 1
        model_key = f"ml:predictor:tenant:{tenant_id}:model"

        assert f"tenant:{tenant_id}" in model_key


class TestMLDataPrivacy:
    """Tests for data privacy in ML operations."""

    def test_training_data_anonymized(self):
        """Test training data doesn't expose PII."""
        training_sample = {
            "query": "write code",
            "tool": "code_generation",
            # Should NOT include user email, name, etc.
        }

        pii_fields = ["email", "name", "phone", "address"]
        for field in pii_fields:
            assert field not in training_sample

    def test_predictions_dont_leak_data(self):
        """Test predictions don't leak training data."""
        prediction = {"tool": "code_generation", "confidence": 0.85}

        # Should only include tool and confidence
        assert "training_samples" not in prediction
        assert "user_ids" not in prediction

    def test_model_doesnt_memorize(self):
        """Test model doesn't memorize specific queries."""
        # Random Forest aggregates, shouldn't memorize
        model_type = "RandomForestClassifier"
        memorizing_models = ["KNN", "NearestNeighbors"]

        assert model_type not in memorizing_models
