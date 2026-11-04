"""
ML Model Training Job

Background job that trains the pack recommendation ML model.
Runs daily to retrain on historical pack activation data.

Usage:
    from src.core.jobs.ml_training_job import train_pack_recommendation_model
    await train_pack_recommendation_model()
"""

import logging
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.core.config.config import get_settings
from src.core.database.session import get_db_session

logger = logging.getLogger(__name__)

# Try to import MLMonitor, may not be available yet
try:
    from src.ml.monitoring import MLMonitor
except ImportError:
    MLMonitor = None  # type: ignore[misc, assignment]  # class used as sentinel


async def train_pack_recommendation_model() -> dict[
    str, Any  # TODO(TYPE): replace Any with concrete type
]:  # TODO(TYPE): replace Any with concrete type
    """
    Train ML model on historical pack activation data.
    Scheduled to run daily at 3 AM.

    Returns:
        Dictionary with training results and metrics.
    """
    settings = get_settings()
    logger.info("Starting ML model training...")

    try:
        # Import ML modules here to avoid circular imports
        from src.ml.pack_recommendation_model import PackRecommendationModel

        # Collect data
        training_data = await collect_training_data(
            min_samples=settings.ml_min_training_samples,
            lookback_days=settings.ml_training_lookback_days,
        )

        sample_count = len(training_data)
        logger.info(f"Collected {sample_count} training samples")

        if sample_count < settings.ml_min_training_samples:
            logger.warning(
                f"Insufficient training data: {sample_count} samples "
                f"(minimum: {settings.ml_min_training_samples})"
            )
            return {
                "status": "skipped",
                "reason": "insufficient_data",
                "sample_count": sample_count,
                "min_required": settings.ml_min_training_samples,
            }

        # Train model
        model = PackRecommendationModel(model_path=settings.ml_model_path)
        metrics = model.train(training_data)

        # Save model
        model.save()
        logger.info(f"Model saved to {settings.ml_model_path}")

        # Store metrics in database
        await store_training_metrics(metrics, sample_count)

        # Log success
        logger.info(
            f"Model training complete. "
            f"Accuracy: {metrics['accuracy']:.3f}, "
            f"Precision: {metrics['precision']:.3f}, "
            f"Recall: {metrics['recall']:.3f}"
        )

        # Log metrics to Prometheus
        if MLMonitor is not None:
            MLMonitor.log_training_metrics(
                accuracy=metrics["accuracy"],
                precision=metrics["precision"],
                recall=metrics["recall"],
                sample_count=sample_count,
                model_version="1.0.0",
            )

        # Reload prediction service cache
        from src.ml.prediction_service import ml_prediction_service

        ml_prediction_service.reload_model()

        return {
            "status": "success",
            "metrics": metrics,
            "sample_count": sample_count,
            "model_path": settings.ml_model_path,
        }

    except Exception as e:
        logger.error(f"Model training failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }


async def collect_training_data(min_samples: int = 100, lookback_days: int = 90) -> pd.DataFrame:
    """
    Collect training data from pack activation history.

    Args:
        min_samples: Minimum number of samples required.
        lookback_days: Number of days to look back for data.

    Returns:
        DataFrame with training data.
    """
    from src.ml.data_collector import MLDataCollector

    collector = MLDataCollector()

    db = get_db_session()
    async with db as db_session:
        # Query pack activation audit logs with company data
        query = text(
            """
            SELECT
                p.id as pack_id,
                p.name as pack_name,
                c.id as company_id,
                c.sector,
                c.company_type,
                paal.activated,
                paal.created_at as activated_at,
                paal.department_budget
            FROM pack_activation_audit_logs paal
            JOIN companies c ON paal.company_id = c.id
            JOIN domain_packs p ON paal.pack_id = p.id
            WHERE paal.created_at >= NOW() - INTERVAL ':lookback_days days'
            ORDER BY paal.created_at DESC
        """
        )

        result = await db_session.execute(query, {"lookback_days": lookback_days})
        rows = result.fetchall()

        if not rows:
            logger.warning(f"No training data found in last {lookback_days} days")
            return pd.DataFrame()

        # Convert to records
        records = []
        for row in rows:
            record = {
                "pack_id": row.pack_id,
                "company_id": row.company_id,
                "sector": row.sector or "other",
                "company_type": row.company_type or "sme",
                "activated": 1 if row.activated else 0,
                "activated_at": row.activated_at,
                "department_budget": row.department_budget,
                # Default values for features that may not be in DB yet
                "has_strategic_goals": 0,
                "has_operational_goals": 0,
                "goal_count": 0,
            }
            records.append(record)

        # Get goal data for companies
        company_ids = list({r["company_id"] for r in records})
        if company_ids:
            # Query company goals
            goals_query = text(
                """
                SELECT
                    company_id,
                    type,
                    COUNT(*) as goal_count
                FROM company_goals
                WHERE company_id = ANY(:company_ids)
                GROUP BY company_id, type
            """
            )

            goals_result = await db_session.execute(goals_query, {"company_ids": company_ids})
            goals_rows = goals_result.fetchall()

            # Build goal data map
            goals_map: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
            for g in goals_rows:
                if g.company_id not in goals_map:
                    goals_map[g.company_id] = {
                        "has_strategic_goals": 0,
                        "has_operational_goals": 0,
                        "goal_count": 0,
                    }
                goals_map[g.company_id]["goal_count"] += g.goal_count
                if g.type == "strategic":
                    goals_map[g.company_id]["has_strategic_goals"] = 1
                elif g.type == "operational":
                    goals_map[g.company_id]["has_operational_goals"] = 1

            # Update records with goal data
            for record in records:
                company_goals = goals_map.get(record["company_id"], {})
                record.update(company_goals)

        df = pd.DataFrame(records)

        # Add budget bucket feature
        df["department_budget_bucket"] = df["department_budget"].apply(collector._bucket_budget)

        logger.info(f"Collected {len(df)} training records")
        return df


async def store_training_metrics(metrics: dict[str, float], sample_count: int) -> None:
    """Store training metrics in database for monitoring."""
    try:
        db = get_db_session()
        async with db as db_session:
            await db_session.execute(
                text(
                    """
                    INSERT INTO ml_training_metrics
                    (accuracy, precision, recall, sample_count, trained_at)
                    VALUES (:accuracy, :precision, :recall, :sample_count, NOW())
                """
                ),
                {
                    "accuracy": metrics["accuracy"],
                    "precision": metrics["precision"],
                    "recall": metrics["recall"],
                    "sample_count": sample_count,
                },
            )
            await db_session.commit()
            logger.info("Training metrics stored in database")
    except Exception as e:
        logger.error(f"Failed to store training metrics: {e}")
        raise
