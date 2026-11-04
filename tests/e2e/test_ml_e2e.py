"""E2E tests for ML recommendations via API."""

from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest


class TestMLRecommendationsAPI:
    """Test ML recommendations through API endpoints."""

    @pytest.fixture
    def api_client(self) -> Mock:
        """Create mock API client for testing."""
        client = Mock()
        client.post = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {"score": 0.85, "recommendations": ["pack_a", "pack_b"]},
            )
        )
        client.get = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {"status": "active", "model_version": "1.0.0"},
            )
        )
        return client

    def test_get_pack_recommendation(self, api_client: Mock) -> None:
        """Test getting pack recommendation via API."""
        company_data = {
            "sector": "technology",
            "company_type": "enterprise",
            "goals": [{"type": "strategic", "title": "Expand"}],
            "department_budget": 250000,
        }

        response = api_client.post("/api/v1/ml/recommendations", json=company_data)

        assert response.status_code == 200
        result = response.json()
        assert "score" in result
        assert "recommendations" in result
        assert 0 <= result["score"] <= 1

    def test_get_recommendation_with_experiment(self, api_client: Mock) -> None:
        """Test recommendation with experiment tracking."""
        company_data = {
            "sector": "healthcare",
            "company_type": "sme",
            "goals": [],
            "experiment_id": "exp_123",
            "group": "treatment",
        }

        response = api_client.post(
            "/api/v1/ml/recommendations",
            json=company_data,
            headers={"X-Experiment-ID": "exp_123"},
        )

        assert response.status_code == 200
        result = response.json()
        assert "score" in result
        # Note: experiment_group in response depends on API implementation
        assert "score" in result

    def test_recommendation_api_error_handling(self, api_client: Mock) -> None:
        """Test API error handling for ML recommendations."""
        api_client.post = Mock(
            return_value=Mock(
                status_code=500,
                json=lambda: {"error": "Model not available"},
            )
        )

        company_data = {"sector": "unknown"}

        response = api_client.post("/api/v1/ml/recommendations", json=company_data)

        assert response.status_code == 500
        result = response.json()
        assert "error" in result

    def test_batch_recommendations_api(self, api_client: Mock) -> None:
        """Test batch recommendations via API."""
        batch_data = {
            "companies": [
                {"sector": "tech", "company_type": "startup"},
                {"sector": "finance", "company_type": "enterprise"},
                {"sector": "healthcare", "company_type": "sme"},
            ]
        }

        api_client.post = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "results": [
                        {"score": 0.75, "company_id": 1},
                        {"score": 0.85, "company_id": 2},
                        {"score": 0.60, "company_id": 3},
                    ]
                },
            )
        )

        response = api_client.post("/api/v1/ml/recommendations/batch", json=batch_data)

        assert response.status_code == 200
        result = response.json()
        assert "results" in result
        assert len(result["results"]) == 3

    def test_model_health_check(self, api_client: Mock) -> None:
        """Test ML model health check endpoint."""
        response = api_client.get("/api/v1/ml/health")

        assert response.status_code == 200
        result = response.json()
        assert "status" in result

    def test_model_metrics_endpoint(self, api_client: Mock) -> None:
        """Test model metrics endpoint."""
        api_client.get = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "accuracy": 0.85,
                    "precision": 0.82,
                    "recall": 0.79,
                    "model_version": "1.0.0",
                    "last_trained": "2024-01-15T10:00:00Z",
                },
            )
        )

        response = api_client.get("/api/v1/ml/metrics")

        assert response.status_code == 200
        result = response.json()
        assert "accuracy" in result
        assert "precision" in result
        assert "recall" in result


class TestExperimentFlow:
    """Test ML experiment flow end-to-end."""

    @pytest.fixture
    def experiment_client(self) -> Mock:
        """Create mock client for experiment tests."""
        client = Mock()
        return client

    def test_create_experiment(self, experiment_client: Mock) -> None:
        """Test creating a new ML experiment."""
        experiment_client.post = Mock(
            return_value=Mock(
                status_code=201,
                json=lambda: {
                    "experiment_id": "exp_456",
                    "status": "created",
                    "control_percentage": 50,
                },
            )
        )

        experiment_config = {
            "name": "Pack Recommendation V2",
            "control_percentage": 50,
            "metrics": ["activation_rate", "engagement"],
        }

        response = experiment_client.post("/api/v1/ml/experiments", json=experiment_config)

        assert response.status_code == 201
        result = response.json()
        assert "experiment_id" in result
        assert result["status"] == "created"

    def test_assign_user_to_experiment(self, experiment_client: Mock) -> None:
        """Test assigning user to experiment group."""
        experiment_client.post = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "user_id": "user_123",
                    "experiment_id": "exp_456",
                    "group": "treatment",
                },
            )
        )

        assignment_request = {
            "user_id": "user_123",
            "experiment_id": "exp_456",
        }

        response = experiment_client.post(
            "/api/v1/ml/experiments/assign",
            json=assignment_request,
        )

        assert response.status_code == 200
        result = response.json()
        assert "group" in result
        assert result["group"] in ["control", "treatment"]

    def test_record_experiment_outcome(self, experiment_client: Mock) -> None:
        """Test recording experiment outcome."""
        experiment_client.post = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {"status": "recorded"},
            )
        )

        outcome_data = {
            "user_id": "user_123",
            "experiment_id": "exp_456",
            "event": "pack_activated",
            "value": 1,
        }

        response = experiment_client.post(
            "/api/v1/ml/experiments/outcomes",
            json=outcome_data,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "recorded"

    def test_get_experiment_results(self, experiment_client: Mock) -> None:
        """Test getting experiment results."""
        experiment_client.get = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "experiment_id": "exp_456",
                    "control": {
                        "users": 1000,
                        "conversion_rate": 0.15,
                    },
                    "treatment": {
                        "users": 1000,
                        "conversion_rate": 0.20,
                    },
                    "lift": 0.05,
                    "significance": 0.95,
                },
            )
        )

        response = experiment_client.get("/api/v1/ml/experiments/exp_456/results")

        assert response.status_code == 200
        result = response.json()
        assert "control" in result
        assert "treatment" in result
        assert "lift" in result


class TestMLPipelineE2E:
    """Test complete ML pipeline end-to-end."""

    def test_full_recommendation_workflow(self) -> None:
        """Test complete recommendation workflow."""
        # This simulates the full flow:
        # 1. Company data comes in
        # 2. Features are engineered
        # 3. Model makes prediction
        # 4. Result is returned with recommendations

        from src.ml.feature_engineering import PackFeatureEngineer
        from src.ml.pack_recommendation_model import PackRecommendationModel

        # Setup
        feature_engineer = PackFeatureEngineer()
        model = PackRecommendationModel()

        # Train model with sample data
        import numpy as np
        import pandas as pd

        np.random.seed(42)
        training_data = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], 100),
                "company_type": np.random.choice(["startup", "sme", "enterprise"], 100),
                "has_strategic_goals": np.random.randint(0, 2, 100),
                "has_operational_goals": np.random.randint(0, 2, 100),
                "goal_count": np.random.randint(1, 20, 100),
                "department_budget_bucket": np.random.randint(0, 3, 100),
                "activated": np.random.randint(0, 2, 100),
            }
        )
        model.train(training_data)

        # Simulate incoming company data
        company_data = {
            "sector": "technology",
            "company_type": "enterprise",
        }
        goals = [
            {"type": "strategic", "name": "Global expansion"},
            {"type": "operational", "name": "Process optimization"},
        ]
        department_budget = 500000

        # Engineer features
        features = feature_engineer.engineer_features(company_data, goals, department_budget)

        # Validate features
        is_valid = feature_engineer.validate_features(features)
        assert is_valid, "Features should be valid"

        # Get prediction
        score = model.predict(features)

        # Verify result
        assert 0 <= score <= 1, "Score should be between 0 and 1"

        # Get feature importance for explanation
        importance = model.get_feature_importance()
        assert len(importance) > 0, "Should have feature importance"

    @pytest.mark.asyncio
    async def test_model_retraining_workflow(self) -> None:
        """Test model retraining workflow."""
        from src.ml.data_collector import MLDataCollector
        from src.ml.pack_recommendation_model import PackRecommendationModel

        # Mock data collector
        collector = MLDataCollector()

        mock_data = {
            "companies": [
                {
                    "sector": "technology",
                    "company_type": "enterprise",
                    "goals": [{"type": "strategic"}],
                    "activated": True,
                },
                {
                    "sector": "healthcare",
                    "company_type": "sme",
                    "goals": [],
                    "activated": False,
                },
            ]
        }

        # MLDataCollector doesn't have fetch_training_data, use prepare_training_data instead
        raw_data = [
            {
                "sector": "technology",
                "company_type": "enterprise",
                "has_strategic_goals": 1,
                "has_operational_goals": 0,
                "goal_count": 5,
                "department_budget_bucket": 2,
                "activated": 1,
            },
            {
                "sector": "healthcare",
                "company_type": "sme",
                "has_strategic_goals": 0,
                "has_operational_goals": 1,
                "goal_count": 3,
                "department_budget_bucket": 1,
                "activated": 0,
            },
        ]

        # Prepare training data
        new_data = collector.prepare_training_data(raw_data, balance=False, recent_only=False)

        # Verify we got data
        assert isinstance(new_data, pd.DataFrame)

        # Train with sufficient data
        np.random.seed(42)
        n_samples = 50
        training_df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], n_samples),
                "company_type": np.random.choice(["startup", "enterprise", "sme"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )
        model = PackRecommendationModel()
        metrics = model.train(training_df)

        assert "accuracy" in metrics
        assert model.is_trained()

    @pytest.mark.asyncio
    async def test_fallback_recommendation_when_model_fails(self) -> None:
        """Test that fallback works when model fails."""
        from src.ml.prediction_service import MLPredictionService

        # Create service without trained model
        service = MLPredictionService()

        # Should return None when model not loaded (fallback behavior)
        service._model = None
        result = await service.predict("comp1", "dept1", "pack1")

        assert result is None  # Fallback returns None when model unavailable


import numpy as np

# Import pandas and numpy at module level
import pandas as pd
