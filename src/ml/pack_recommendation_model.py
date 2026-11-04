"""Pack recommendation ML model for predicting pack suitability."""

import logging
import os
from typing import Any, Optional

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


class PackRecommendationModel:
    """ML model for predicting pack suitability."""

    def __init__(self, model_path: str = "models/pack_recommendation.pkl"):
        """Initialize the model.

        Args:
            model_path: Path to save/load the trained model.
        """
        self.model: RandomForestClassifier | None = None
        self.model_path = model_path
        self.feature_columns = [
            "sector_encoded",
            "company_type_encoded",
            "has_strategic_goals",
            "has_operational_goals",
            "goal_count",
            "department_budget_bucket",
        ]

    def preprocess_features(
        self, df: pd.DataFrame
    ) -> tuple[Any, Any]:  # TODO(TYPE): replace Any with concrete type
        """Preprocess features for training/prediction.

        Args:
            df: DataFrame with raw features.

        Returns:
            Tuple of (X features, y target or None).
        """
        # Work on a copy to avoid modifying original
        df_processed = df.copy()

        # Encode categorical variables
        if "sector" in df_processed.columns:
            df_processed["sector_encoded"] = pd.Categorical(df_processed["sector"]).codes
        if "company_type" in df_processed.columns:
            df_processed["company_type_encoded"] = pd.Categorical(
                df_processed["company_type"]
            ).codes

        # Ensure all feature columns exist
        for col in self.feature_columns:
            if col not in df_processed.columns:
                df_processed[col] = 0

        X = df_processed[self.feature_columns].fillna(0)
        y = df_processed["activated"].astype(int) if "activated" in df_processed.columns else None
        return X, y

    def train(self, training_data: pd.DataFrame) -> dict[str, float]:
        """Train model and return metrics.

        Args:
            training_data: DataFrame with features and target.

        Returns:
            Dictionary with accuracy, precision, recall, and test_samples.
        """
        X, y = self.preprocess_features(training_data)

        if y is None:
            raise ValueError("Training data must contain 'activated' column")

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Train model
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test)
        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),  # pyright: ignore[reportArgumentType]
            "recall": recall_score(y_test, y_pred, zero_division=0),  # pyright: ignore[reportArgumentType]
            "test_samples": len(y_test),
        }

        logger.info(f"Model trained. Accuracy: {metrics['accuracy']:.3f}")
        return metrics

    def predict(
        self,
        features: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Predict activation probability.

        Args:
            features: Dictionary with feature values.

        Returns:
            Probability of activation (0.0 to 1.0).
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        # Convert dict to DataFrame
        df = pd.DataFrame([features])
        X, _ = self.preprocess_features(df)

        # Predict probability of class 1 (activated)
        proba = self.model.predict_proba(X)[0]
        return float(proba[1])

    def predict_batch(
        self,
        features_list: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> list[float]:  # TODO(TYPE): replace Any with concrete type
        """Predict activation probabilities for multiple items.

        Args:
            features_list: List of feature dictionaries.

        Returns:
            List of activation probabilities.
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        df = pd.DataFrame(features_list)
        X, _ = self.preprocess_features(df)
        proba = self.model.predict_proba(X)
        return [float(p[1]) for p in proba]

    def get_feature_importance(self) -> dict[str, float]:
        """Get feature importance from trained model.

        Returns:
            Dictionary mapping feature names to importance scores.
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        importance = self.model.feature_importances_
        return dict(zip(self.feature_columns, importance))

    def save(self) -> None:
        """Save model to disk."""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(self.model, self.model_path)
        logger.info(f"Model saved to {self.model_path}")

    def load(self) -> None:
        """Load model from disk."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        self.model = joblib.load(self.model_path)
        logger.info(f"Model loaded from {self.model_path}")

    def is_trained(self) -> bool:
        """Check if model is trained/loaded.

        Returns:
            True if model is ready for predictions.
        """
        return self.model is not None
