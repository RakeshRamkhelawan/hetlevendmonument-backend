"""Data collector for ML training data."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class MLDataCollector:
    """Collect and prepare data for ML model training."""

    def __init__(self) -> None:
        """Initialize the data collector."""
        self.min_samples_for_training = 50

    def collect_from_company_activations(
        self,
        activations: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        companies: dict[str, dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        goals: dict[str, list[dict[str, Any]]]
        | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> pd.DataFrame:
        """Collect training data from company pack activations.

        Args:
            activations: List of pack activation records.
            companies: Dictionary mapping company_id to company data.
            goals: Optional dictionary mapping company_id to goals.

        Returns:
            DataFrame with features and target.
        """
        records = []

        for activation in activations:
            company_id = activation.get("company_id")
            company_data = companies.get(str(company_id), {}) if company_id is not None else {}
            company_goals = (
                goals.get(str(company_id), []) if (goals and company_id is not None) else []
            )

            record = {
                "company_id": company_id,
                "pack_id": activation.get("pack_id"),
                "sector": company_data.get("sector", "other"),
                "company_type": company_data.get("company_type", "sme"),
                "has_strategic_goals": (
                    1 if any(g.get("type") == "strategic" for g in company_goals) else 0
                ),
                "has_operational_goals": (
                    1 if any(g.get("type") == "operational" for g in company_goals) else 0
                ),
                "goal_count": len(company_goals),
                "department_budget_bucket": self._bucket_budget(
                    activation.get("department_budget")
                ),
                "activated": activation.get("activated", 0),
                "activated_at": activation.get("activated_at"),
            }
            records.append(record)

        df = pd.DataFrame(records)
        logger.info(f"Collected {len(df)} records from company activations")
        return df

    def collect_from_interactions(
        self,
        interactions: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        company_context: dict[str, dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> pd.DataFrame:
        """Collect training data from user-pack interactions.

        Args:
            interactions: List of user interaction records.
            company_context: Dictionary with company context per interaction.

        Returns:
            DataFrame with features and target.
        """
        records = []

        for interaction in interactions:
            context = company_context.get(interaction.get("interaction_id"), {})  # type: ignore[arg-type]

            record = {
                "interaction_id": interaction.get("interaction_id"),
                "pack_id": interaction.get("pack_id"),
                "sector": context.get("sector", "other"),
                "company_type": context.get("company_type", "sme"),
                "has_strategic_goals": int(context.get("has_strategic_goals", 0)),
                "has_operational_goals": int(context.get("has_operational_goals", 0)),
                "goal_count": context.get("goal_count", 0),
                "department_budget_bucket": self._bucket_budget(context.get("department_budget")),
                "activated": 1 if interaction.get("outcome") == "activated" else 0,
                "interaction_type": interaction.get("type"),
            }
            records.append(record)

        df = pd.DataFrame(records)
        logger.info(f"Collected {len(df)} records from interactions")
        return df

    def _bucket_budget(self, budget: float | None) -> int:
        """Bucket budget into categories.

        Args:
            budget: Budget amount.

        Returns:
            Budget bucket (0=small, 1=medium, 2=large).
        """
        if budget is None or budget < 0:
            return 0
        if budget < 50000:
            return 0
        if budget < 200000:
            return 1
        return 2

    def filter_recent_data(
        self,
        df: pd.DataFrame,
        date_column: str = "activated_at",
        days: int = 90,
    ) -> pd.DataFrame:
        """Filter data to recent records only.

        Args:
            df: DataFrame with timestamp data.
            date_column: Column name containing timestamps.
            days: Number of days to look back.

        Returns:
            Filtered DataFrame.
        """
        if date_column not in df.columns:
            logger.warning(f"Date column {date_column} not found, returning all data")
            return df

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Handle string dates
        if df[date_column].dtype == "object":
            df[date_column] = pd.to_datetime(df[date_column], errors="coerce")

        filtered = df[df[date_column] >= cutoff_date]
        logger.info(f"Filtered to {len(filtered)} records from last {days} days")
        return filtered  # pyright: ignore[reportReturnType]

    def balance_classes(self, df: pd.DataFrame, target_col: str = "activated") -> pd.DataFrame:
        """Balance positive and negative classes by undersampling majority.

        Args:
            df: DataFrame with features and target.
            target_col: Name of target column.

        Returns:
            Balanced DataFrame.
        """
        if target_col not in df.columns:
            logger.warning(f"Target column {target_col} not found, returning as-is")
            return df

        positive = df[df[target_col] == 1]
        negative = df[df[target_col] == 0]

        if len(positive) == 0 or len(negative) == 0:
            logger.warning("Cannot balance: one class is empty")
            return df

        # Undersample majority class
        if len(positive) > len(negative):
            positive = positive.sample(n=len(negative), random_state=42)
        else:
            negative = negative.sample(n=len(positive), random_state=42)

        balanced = pd.concat([positive, negative]).sample(frac=1, random_state=42)
        logger.info(f"Balanced dataset: {len(balanced)} records")
        return balanced  # pyright: ignore[reportReturnType]

    def validate_data_quality(
        self, df: pd.DataFrame
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Validate data quality and return report.

        Args:
            df: DataFrame to validate.

        Returns:
            Dictionary with quality metrics.
        """
        report = {
            "total_records": len(df),
            "sufficient_for_training": len(df) >= self.min_samples_for_training,
            "missing_values": df.isnull().sum().to_dict(),
            "total_missing": int(df.isnull().sum().sum()),
            "duplicate_rows": int(df.duplicated().sum()),
        }

        if "activated" in df.columns:
            class_counts = df["activated"].value_counts().to_dict()
            report["class_distribution"] = class_counts
            report["class_balance_ratio"] = (
                min(class_counts.values()) / max(class_counts.values()) if class_counts else 0
            )

        logger.info(f"Data quality report: {report}")
        return report

    def prepare_training_data(
        self,
        raw_data: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        balance: bool = True,
        recent_only: bool = True,
        days: int = 90,
    ) -> pd.DataFrame:
        """Prepare raw data for model training.

        Args:
            raw_data: List of raw data records.
            balance: Whether to balance classes.
            recent_only: Whether to filter to recent data only.
            days: Days to look back if recent_only is True.

        Returns:
            Prepared DataFrame.
        """
        df = pd.DataFrame(raw_data)

        if len(df) == 0:
            logger.warning("Empty dataset provided")
            return df

        # Filter to recent data
        if recent_only and "activated_at" in df.columns:
            df = self.filter_recent_data(df, days=days)

        # Balance classes
        if balance:
            df = self.balance_classes(df)

        # Validate
        quality = self.validate_data_quality(df)
        if not quality["sufficient_for_training"]:
            logger.warning(f"Insufficient data for training: {quality['total_records']} samples")

        return df
