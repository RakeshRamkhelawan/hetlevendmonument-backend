"""Tests for PackRecommendationModel."""

import numpy as np
import pandas as pd
import pytest

from src.ml.feature_engineering import PackFeatureEngineer
from src.ml.pack_recommendation_model import PackRecommendationModel


class TestPackRecommendationModel:
    """Test suite for PackRecommendationModel."""

    def test_model_initialization(self) -> None:
        """Test that model initializes correctly."""
        model = PackRecommendationModel()
        assert model.model is None
        assert len(model.feature_columns) > 0

    def test_feature_preprocessing(self) -> None:
        """Test feature preprocessing."""
        df = pd.DataFrame(
            {
                "sector": ["tech", "finance", "healthcare"],
                "company_type": ["mkb", "enterprise", "zzp"],
                "has_strategic_goals": [1, 0, 1],
                "has_operational_goals": [0, 1, 1],
                "goal_count": [5, 10, 2],
                "department_budget_bucket": [1, 3, 0],
                "activated": [1, 0, 1],
            }
        )

        model = PackRecommendationModel()
        X, y = model.preprocess_features(df)

        assert X.shape[0] == 3
        assert y is not None
        assert len(y) == 3

    def test_model_training(self) -> None:
        """Test model training with synthetic data."""
        # Create synthetic training data
        np.random.seed(42)
        n_samples = 200
        df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], n_samples),
                "company_type": np.random.choice(["mkb", "enterprise", "zzp"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )

        model = PackRecommendationModel()
        metrics = model.train(df)

        assert "accuracy" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert 0 <= metrics["accuracy"] <= 1

    def test_model_prediction(self) -> None:
        """Test model prediction."""
        # Train model first - need enough samples for stratified split
        np.random.seed(42)
        n_samples = 50
        df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], n_samples),
                "company_type": np.random.choice(["mkb", "enterprise", "zzp"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )

        model = PackRecommendationModel()
        model.train(df)

        features = {
            "sector": "tech",
            "company_type": "mkb",
            "has_strategic_goals": 1,
            "has_operational_goals": 0,
            "goal_count": 5,
            "department_budget_bucket": 1,
        }

        score = model.predict(features)
        assert 0 <= score <= 1

    def test_model_save_load(self, tmp_path: pytest.TempPathFactory) -> None:
        """Test model save and load functionality."""
        model = PackRecommendationModel(model_path=str(tmp_path / "test_model.pkl"))

        # Train - need enough samples for stratified split
        np.random.seed(42)
        n_samples = 50
        df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance"], n_samples),
                "company_type": np.random.choice(["mkb", "enterprise"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )
        model.train(df)

        # Save and load
        model.save()
        model.load()

        assert model.model is not None

    def test_predict_without_training_raises(self) -> None:
        """Test that prediction without training raises error."""
        model = PackRecommendationModel()
        features = {
            "sector": "tech",
            "company_type": "mkb",
            "has_strategic_goals": 1,
            "has_operational_goals": 0,
            "goal_count": 5,
            "department_budget_bucket": 1,
        }

        with pytest.raises(ValueError, match="Model not trained or loaded"):
            model.predict(features)

    def test_train_without_target_raises(self) -> None:
        """Test that training without target raises error."""
        df = pd.DataFrame(
            {
                "sector": ["tech", "finance"],
                "company_type": ["mkb", "enterprise"],
                "has_strategic_goals": [1, 0],
                "has_operational_goals": [0, 1],
                "goal_count": [5, 10],
                "department_budget_bucket": [1, 3],
            }
        )

        model = PackRecommendationModel()
        with pytest.raises(ValueError, match="Training data must contain 'activated' column"):
            model.train(df)

    def test_get_feature_importance(self) -> None:
        """Test feature importance extraction."""
        np.random.seed(42)
        n_samples = 50
        df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], n_samples),
                "company_type": np.random.choice(["mkb", "enterprise", "zzp"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )

        model = PackRecommendationModel()
        model.train(df)

        importance = model.get_feature_importance()
        assert len(importance) == len(model.feature_columns)
        assert all(0 <= v <= 1 for v in importance.values())

    def test_is_trained(self) -> None:
        """Test is_trained method."""
        model = PackRecommendationModel()
        assert not model.is_trained()

        np.random.seed(42)
        n_samples = 50
        df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance"], n_samples),
                "company_type": np.random.choice(["mkb", "enterprise"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )
        model.train(df)
        assert model.is_trained()

    def test_predict_batch(self) -> None:
        """Test batch prediction."""
        np.random.seed(42)
        n_samples = 50
        df = pd.DataFrame(
            {
                "sector": np.random.choice(["tech", "finance", "healthcare"], n_samples),
                "company_type": np.random.choice(["mkb", "enterprise", "zzp"], n_samples),
                "has_strategic_goals": np.random.randint(0, 2, n_samples),
                "has_operational_goals": np.random.randint(0, 2, n_samples),
                "goal_count": np.random.randint(1, 20, n_samples),
                "department_budget_bucket": np.random.randint(0, 4, n_samples),
                "activated": np.random.randint(0, 2, n_samples),
            }
        )

        model = PackRecommendationModel()
        model.train(df)

        features_list = [
            {
                "sector": "tech",
                "company_type": "mkb",
                "has_strategic_goals": 1,
                "has_operational_goals": 0,
                "goal_count": 5,
                "department_budget_bucket": 1,
            },
            {
                "sector": "finance",
                "company_type": "enterprise",
                "has_strategic_goals": 0,
                "has_operational_goals": 1,
                "goal_count": 10,
                "department_budget_bucket": 3,
            },
        ]

        scores = model.predict_batch(features_list)
        assert len(scores) == 2
        assert all(0 <= score <= 1 for score in scores)


class TestPackFeatureEngineer:
    """Test suite for PackFeatureEngineer."""

    def test_encode_sector(self) -> None:
        """Test sector encoding."""
        engineer = PackFeatureEngineer()
        assert engineer.encode_sector("technology") == 0
        assert engineer.encode_sector("healthcare") == 1
        assert engineer.encode_sector("unknown") == 7  # Default

    def test_encode_company_type(self) -> None:
        """Test company type encoding."""
        engineer = PackFeatureEngineer()
        assert engineer.encode_company_type("startup") == 0
        assert engineer.encode_company_type("enterprise") == 2
        assert engineer.encode_company_type("unknown") == 1  # Defaults to sme

    def test_bucket_budget(self) -> None:
        """Test budget bucketing."""
        engineer = PackFeatureEngineer()
        assert engineer.bucket_budget(10000) == 0  # Small
        assert engineer.bucket_budget(100000) == 1  # Medium
        assert engineer.bucket_budget(500000) == 2  # Large
        assert engineer.bucket_budget(None) == 0  # Default
        assert engineer.bucket_budget(-100) == 0  # Negative handled

    def test_extract_goal_features(self) -> None:
        """Test goal feature extraction."""
        engineer = PackFeatureEngineer()

        # No goals
        features = engineer.extract_goal_features([])
        assert features["has_strategic_goals"] == 0
        assert features["has_operational_goals"] == 0
        assert features["goal_count"] == 0

        # With goals
        goals = [
            {"type": "strategic"},
            {"type": "operational"},
            {"type": "strategic"},
        ]
        features = engineer.extract_goal_features(goals)
        assert features["has_strategic_goals"] == 1
        assert features["has_operational_goals"] == 1
        assert features["goal_count"] == 3

    def test_engineer_features(self) -> None:
        """Test feature engineering."""
        engineer = PackFeatureEngineer()

        company_data = {
            "sector": "technology",
            "company_type": "enterprise",
        }
        goals = [{"type": "strategic"}]
        budget = 150000

        features = engineer.engineer_features(company_data, goals, budget)

        assert "sector_encoded" in features
        assert "company_type_encoded" in features
        assert "has_strategic_goals" in features
        assert "has_operational_goals" in features
        assert "goal_count" in features
        assert "department_budget_bucket" in features

    def test_engineer_features_batch(self) -> None:
        """Test batch feature engineering."""
        engineer = PackFeatureEngineer()

        records = [
            {
                "company": {"sector": "technology", "company_type": "startup"},
                "goals": [{"type": "strategic"}],
                "department_budget": 50000,
                "activated": 1,
            },
            {
                "company": {"sector": "healthcare", "company_type": "enterprise"},
                "goals": [],
                "department_budget": 200000,
                "activated": 0,
            },
        ]

        df = engineer.engineer_features_batch(records)
        assert len(df) == 2
        assert "activated" in df.columns

    def test_validate_features_valid(self) -> None:
        """Test feature validation with valid features."""
        engineer = PackFeatureEngineer()

        features = {
            "sector_encoded": 0,
            "company_type_encoded": 1,
            "has_strategic_goals": 1,
            "has_operational_goals": 0,
            "goal_count": 5,
            "department_budget_bucket": 1,
        }

        assert engineer.validate_features(features) is True

    def test_validate_features_invalid(self) -> None:
        """Test feature validation with invalid features."""
        engineer = PackFeatureEngineer()

        # Missing features
        features = {
            "sector_encoded": 0,
            "company_type_encoded": 1,
        }
        assert engineer.validate_features(features) is False

    def test_extract_company_features(self) -> None:
        """Test company feature extraction."""
        engineer = PackFeatureEngineer()

        company_data = {
            "sector": "finance",
            "company_type": "sme",
        }

        features = engineer.extract_company_features(company_data)
        assert "sector_encoded" in features
        assert "company_type_encoded" in features

    def test_extract_department_features(self) -> None:
        """Test department feature extraction."""
        engineer = PackFeatureEngineer()

        dept_data = {
            "budget": 100000,
            "goals": [{"type": "operational"}],
        }

        features = engineer.extract_department_features(dept_data)
        assert "department_budget_bucket" in features
        assert "has_operational_goals" in features
