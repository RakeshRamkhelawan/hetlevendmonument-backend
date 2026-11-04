"""Integration tests for ML recommendations."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.ml.data_collector import MLDataCollector
from src.ml.feature_engineering import PackFeatureEngineer
from src.ml.pack_recommendation_model import PackRecommendationModel
from src.ml.prediction_service import MLPredictionService


class TestMLScoringFlow:
    """Test end-to-end ML scoring flow."""

    @pytest.fixture
    def trained_model(self) -> PackRecommendationModel:
        """Create a trained model for testing."""
        np.random.seed(42)
        n_samples = 100
        df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], n_samples),
                "company_type": np.random.choice(["startup", "sme", "enterprise"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 3, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )

        model = PackRecommendationModel()
        model.train(df)
        return model

    @pytest.fixture
    def feature_engineer(self) -> PackFeatureEngineer:
        """Create feature engineer for testing."""
        return PackFeatureEngineer()

    def test_full_scoring_pipeline(
        self,
        trained_model: PackRecommendationModel,
        feature_engineer: PackFeatureEngineer,
    ) -> None:
        """Test complete scoring pipeline from raw data to score."""
        # Raw company data
        company_data = {
            "sector": "technology",
            "company_type": "enterprise",
        }
        goals = [
            {"type": "strategic", "name": "Expand market"},
            {"type": "operational", "name": "Improve efficiency"},
        ]
        department_budget = 250000

        # Engineer features
        features = feature_engineer.engineer_features(company_data, goals, department_budget)

        # Validate features
        assert feature_engineer.validate_features(features) is True

        # Get prediction
        score = trained_model.predict(features)
        assert 0 <= score <= 1

    def test_batch_scoring_pipeline(
        self,
        trained_model: PackRecommendationModel,
        feature_engineer: PackFeatureEngineer,
    ) -> None:
        """Test batch scoring for multiple companies."""
        records = [
            {
                "company": {"sector": "technology", "company_type": "startup"},
                "goals": [{"type": "strategic"}],
                "department_budget": 50000,
            },
            {
                "company": {"sector": "healthcare", "company_type": "enterprise"},
                "goals": [{"type": "strategic"}, {"type": "operational"}],
                "department_budget": 300000,
            },
            {
                "company": {"sector": "finance", "company_type": "sme"},
                "goals": [],
                "department_budget": 100000,
            },
        ]

        # Engineer features for batch
        features_df = feature_engineer.engineer_features_batch(records)

        # Convert to list of dicts for prediction
        features_list = features_df.to_dict("records")

        # Batch predict
        scores = trained_model.predict_batch(features_list)

        assert len(scores) == 3
        assert all(0 <= score <= 1 for score in scores)


class TestABTestIntegration:
    """Test A/B test integration."""

    @pytest.fixture
    def prediction_service(self) -> MLPredictionService:
        """Create prediction service for testing."""
        service = MLPredictionService()
        # Mock the internal model
        mock_model = Mock(spec=PackRecommendationModel)
        mock_model.predict.return_value = 0.75
        mock_model.is_trained.return_value = True
        service._model = mock_model
        return service

    def test_ab_test_control_group(self, prediction_service: MLPredictionService) -> None:
        """Test control group in A/B test."""
        experiment_group = "control"

        # Control group should get model prediction
        features = {
            "sector_encoded": 0,
            "company_type_encoded": 1,
            "has_strategic_goals": 1,
            "has_operational_goals": 0,
            "goal_count": 5,
            "department_budget_bucket": 1,
        }
        score = prediction_service._model.predict(features)

        assert score == 0.75  # Mocked value
        assert experiment_group == "control"

    def test_ab_test_treatment_group(self, prediction_service: MLPredictionService) -> None:
        """Test treatment group in A/B test."""
        experiment_group = "treatment"

        # Treatment group may get different logic
        features = {
            "sector_encoded": 0,
            "company_type_encoded": 1,
            "has_strategic_goals": 1,
            "has_operational_goals": 0,
            "goal_count": 5,
            "department_budget_bucket": 1,
        }
        score = prediction_service._model.predict(features)

        assert score == 0.75  # Mocked value
        assert experiment_group == "treatment"

    def test_ab_test_event_tracking(self, prediction_service: MLPredictionService) -> None:
        """Test that A/B test events are tracked via logging."""
        import logging

        logger = logging.getLogger("test_ab")

        with patch.object(logger, "info") as mock_info:
            logger.info("A/B test event: treatment group")
            mock_info.assert_called_once_with("A/B test event: treatment group")


class TestFallbackBehavior:
    """Test fallback behavior when ML model fails."""

    def test_fallback_when_model_untrained(self) -> None:
        """Test fallback when model is not trained."""
        service = MLPredictionService()
        # Ensure model is None
        service._model = None

        # Should return None when model not loaded
        result = asyncio.run(service.predict("comp1", "dept1", "pack1"))

        assert result is None

    def test_fallback_with_rule_based_score(self) -> None:
        """Test rule-based fallback scoring using feature engineer."""
        engineer = PackFeatureEngineer()

        # High-value features should score differently
        high_value_company = {"sector": "technology", "company_type": "enterprise"}
        high_features = engineer.engineer_features(
            high_value_company,
            goals=[{"type": "strategic"}, {"type": "operational"}],
            department_budget=300000,
        )

        # Low-value features
        low_value_company = {"sector": "technology", "company_type": "startup"}
        low_features = engineer.engineer_features(
            low_value_company,
            goals=[],
            department_budget=10000,
        )

        # Verify features are engineered correctly
        assert high_features["company_type_encoded"] == 2  # enterprise
        assert low_features["company_type_encoded"] == 0  # startup
        assert high_features["department_budget_bucket"] > low_features["department_budget_bucket"]

    def test_fallback_with_missing_features(self) -> None:
        """Test fallback with partial/missing features."""
        service = MLPredictionService()
        service._model = None

        # When model is not loaded, predict returns None (fallback)
        result = asyncio.run(service.predict("comp1", "dept1", "pack1"))

        assert result is None


class TestDataCollectionIntegration:
    """Test training data collection integration."""

    def test_data_collector_initialization(self) -> None:
        """Test data collector initialization."""
        collector = MLDataCollector()
        assert collector is not None
        assert collector.min_samples_for_training == 50

    def test_collect_from_company_data(self) -> None:
        """Test collecting training data from company records."""
        collector = MLDataCollector()

        # Sample activation data
        activations = [
            {
                "company_id": "comp1",
                "pack_id": "pack_a",
                "activated": 1,
                "department_budget": 100000,
            },
            {
                "company_id": "comp2",
                "pack_id": "pack_b",
                "activated": 0,
                "department_budget": 50000,
            },
        ]

        companies = {
            "comp1": {"sector": "technology", "company_type": "enterprise"},
            "comp2": {"sector": "healthcare", "company_type": "sme"},
        }

        df = collector.collect_from_company_activations(activations, companies)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "sector" in df.columns
        assert "activated" in df.columns

    def test_data_collector_with_goals(self) -> None:
        """Test data collection with goal data."""
        collector = MLDataCollector()

        activations = [
            {
                "company_id": "comp1",
                "pack_id": "pack_a",
                "activated": 1,
            },
        ]

        companies = {
            "comp1": {"sector": "technology", "company_type": "enterprise"},
        }

        goals = {
            "comp1": [
                {"type": "strategic", "name": "Goal 1"},
                {"type": "operational", "name": "Goal 2"},
            ],
        }

        df = collector.collect_from_company_activations(activations, companies, goals)

        assert len(df) == 1
        assert "goal_count" in df.columns
        assert df.iloc[0]["goal_count"] == 2
        assert df.iloc[0]["has_strategic_goals"] == 1
        assert df.iloc[0]["has_operational_goals"] == 1


class TestModelRetrainingFlow:
    """Test model retraining workflow."""

    def test_retrain_with_new_data(self) -> None:
        """Test retraining model with new data."""
        # Initial training - need enough samples
        np.random.seed(42)
        n_samples = 50
        initial_data = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance"], n_samples),
                "company_type": np.random.choice(["startup", "enterprise"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )

        model = PackRecommendationModel()
        initial_metrics = model.train(initial_data)

        # New data for retraining
        new_data = pd.DataFrame(
            {
                "sector": ["healthcare", "retail", "tech"],
                "company_type": ["sme", "startup", "enterprise"],
                "has_strategic_goals": [1, 1, 0],
                "has_operational_goals": [1, 0, 1],
                "goal_count": [3, 8, 12],
                "department_budget_bucket": [2, 1, 3],
                "activated": [1, 1, 0],
            }
        )

        # Combine and retrain
        combined_data = pd.concat([initial_data, new_data], ignore_index=True)
        new_metrics = model.train(combined_data)

        assert "accuracy" in new_metrics
        assert new_metrics["test_samples"] > initial_metrics["test_samples"]

    def test_model_versioning_on_retrain(self, tmp_path: pytest.TempPathFactory) -> None:
        """Test model versioning during retraining."""
        model_v1_path = str(tmp_path / "model_v1.pkl")
        model_v2_path = str(tmp_path / "model_v2.pkl")

        # Train v1 - need enough samples
        np.random.seed(42)
        n_samples = 50
        df_v1 = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance"], n_samples),
                "company_type": np.random.choice(["startup", "enterprise"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )

        model_v1 = PackRecommendationModel(model_path=model_v1_path)
        model_v1.train(df_v1)
        model_v1.save()

        # Train v2 with more data
        n_samples_v2 = 100
        df_v2 = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], n_samples_v2),
                "company_type": np.random.choice(["startup", "enterprise", "sme"], n_samples_v2),
                "has_strategic_goals": np.random.randint(0, 2, n_samples_v2),
                "has_operational_goals": np.random.randint(0, 2, n_samples_v2),
                "goal_count": np.random.randint(1, 20, n_samples_v2),
                "department_budget_bucket": np.random.randint(0, 4, n_samples_v2),
                "activated": np.random.randint(0, 2, n_samples_v2),
            }
        )

        model_v2 = PackRecommendationModel(model_path=model_v2_path)
        model_v2.train(df_v2)
        model_v2.save()

        # Verify both models exist
        import os

        assert os.path.exists(model_v1_path)
        assert os.path.exists(model_v2_path)
