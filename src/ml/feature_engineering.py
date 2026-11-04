"""Feature engineering for pack recommendation model."""

import logging
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class PackFeatureEngineer:
    """Engineer features from company and goal data for pack recommendations."""

    # Budget bucket thresholds
    BUDGET_BUCKETS = [
        (0, 50000, 0),  # Small
        (50000, 200000, 1),  # Medium
        (200000, float("inf"), 2),  # Large
    ]

    # Sector mappings
    SECTOR_MAPPINGS = {
        "technology": 0,
        "healthcare": 1,
        "finance": 2,
        "manufacturing": 3,
        "retail": 4,
        "education": 5,
        "government": 6,
        "other": 7,
    }

    # Company type mappings
    COMPANY_TYPE_MAPPINGS = {
        "startup": 0,
        "sme": 1,
        "enterprise": 2,
        "nonprofit": 3,
    }

    def __init__(self) -> None:
        """Initialize the feature engineer."""
        self.feature_schema = {
            "sector_encoded": int,
            "company_type_encoded": int,
            "has_strategic_goals": int,
            "has_operational_goals": int,
            "goal_count": int,
            "department_budget_bucket": int,
        }

    def encode_sector(self, sector: str) -> int:
        """Encode sector to numeric value.

        Args:
            sector: Sector name.

        Returns:
            Encoded sector value.
        """
        normalized = sector.lower().strip() if sector else "other"
        return self.SECTOR_MAPPINGS.get(normalized, 7)

    def encode_company_type(self, company_type: str) -> int:
        """Encode company type to numeric value.

        Args:
            company_type: Company type name.

        Returns:
            Encoded company type value.
        """
        normalized = company_type.lower().strip() if company_type else "sme"
        return self.COMPANY_TYPE_MAPPINGS.get(normalized, 1)

    def bucket_budget(self, budget: float | None) -> int:
        """Bucket budget into categories.

        Args:
            budget: Department budget amount.

        Returns:
            Budget bucket index.
        """
        if budget is None or budget < 0:
            return 0

        for min_val, max_val, bucket in self.BUDGET_BUCKETS:
            if min_val <= budget < max_val:
                return bucket
        return 2  # Default to large

    def extract_goal_features(self, goals: list[dict[str, Any]]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract features from goals list.

        Args:
            goals: List of goal dictionaries.

        Returns:
            Dictionary with goal-related features.
        """
        if not goals:
            return {
                "has_strategic_goals": 0,
                "has_operational_goals": 0,
                "goal_count": 0,
            }

        goal_types = [g.get("type", "").lower() for g in goals]

        return {
            "has_strategic_goals": 1 if "strategic" in goal_types else 0,
            "has_operational_goals": 1 if "operational" in goal_types else 0,
            "goal_count": len(goals),
        }

    def engineer_features(
        self,
        company_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        goals: list[dict[str, Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
        department_budget: float | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Engineer features from raw data.

        Args:
            company_data: Dictionary with company information.
            goals: Optional list of goal dictionaries.
            department_budget: Optional department budget.

        Returns:
            Dictionary with engineered features.
        """
        sector = company_data.get("sector", "other")
        company_type = company_data.get("company_type", "sme")

        features = {
            "sector_encoded": self.encode_sector(sector),
            "company_type_encoded": self.encode_company_type(company_type),
            "department_budget_bucket": self.bucket_budget(department_budget),
        }

        # Add goal features
        goal_features = self.extract_goal_features(goals or [])
        features.update(goal_features)

        logger.debug(f"Engineered features: {features}")
        return features

    def engineer_features_batch(
        self,
        records: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> pd.DataFrame:
        """Engineer features for multiple records.

        Args:
            records: List of dictionaries with company/goal/budget data.

        Returns:
            DataFrame with engineered features.
        """
        features_list = []
        for record in records:
            features = self.engineer_features(
                company_data=record.get("company", {}),
                goals=record.get("goals", []),
                department_budget=record.get("department_budget"),
            )
            # Add target if available
            if "activated" in record:
                features["activated"] = record["activated"]
            features_list.append(features)

        return pd.DataFrame(features_list)

    def extract_company_features(self, company_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract features from company data.

        Args:
            company_data: Dictionary with company information.

        Returns:
            Dictionary with company-related features.
        """
        sector = company_data.get("sector", "other")
        company_type = company_data.get("company_type", "sme")

        return {
            "sector_encoded": self.encode_sector(sector),
            "company_type_encoded": self.encode_company_type(company_type),
        }

    def extract_department_features(self, dept_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract features from department data.

        Args:
            dept_data: Dictionary with department information.

        Returns:
            Dictionary with department-related features.
        """
        budget = dept_data.get("budget")
        goals = dept_data.get("goals", [])

        features = {
            "department_budget_bucket": self.bucket_budget(budget),
        }
        features.update(self.extract_goal_features(goals))

        return features

    def validate_features(self, features: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Validate that features match expected schema.

        Args:
            features: Dictionary with features.

        Returns:
            True if valid, False otherwise.
        """
        required_keys = set(self.feature_schema.keys())
        actual_keys = set(features.keys())

        if not required_keys.issubset(actual_keys):
            missing = required_keys - actual_keys
            logger.warning(f"Missing features: {missing}")
            return False

        # Validate types
        for key, expected_type in self.feature_schema.items():
            if not isinstance(features[key], (expected_type, int, float)):
                logger.warning(
                    f"Invalid type for {key}: expected {expected_type}, got {type(features[key])}"
                )
                return False

        return True
