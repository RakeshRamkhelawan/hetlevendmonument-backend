import logging
from typing import Any, Optional

from src.core.learning.production_integration import ab_testing_framework

logger = logging.getLogger(__name__)


class PromptAnalyticsService:
    """
    Service to analyze experiment results and identify winning prompt variants.
    """

    def __init__(self) -> None:
        self.ab_framework = ab_testing_framework

    async def get_experiment_results(self, experiment_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Wrapper to get raw results."""
        return await self.ab_framework.get_test_results(experiment_id)

    async def get_winning_variant(
        self, experiment_id: str, metric: str = "user_satisfaction"
    ) -> str | None:
        """
        Identify the winning variant for a specific metric.
        Returns variant_id if a significant winner exists, else None.
        """
        data = await self.ab_framework.get_test_results(experiment_id)
        if not data:
            logger.warning(f"No results found for experiment {experiment_id}")
            return None

        significance_data = data.get("statistical_significance", {})
        metrics_data = data.get("metrics", {}).get(metric, {})

        # config = data['config'] (Not in result dict, but we could fetch test config if needed)
        # But we can assume Control is the baseline.
        # significance keys format: "{metric_name}_{treatment_group}"

        best_variant: str | None = None
        best_improvement: float = 0.0

        prefix = f"{metric}_"

        for key, stats in significance_data.items():
            if not key.startswith(prefix):
                continue

            variant_id = key[len(prefix) :]  # Extract variant name

            # Check if significant
            is_significant = stats.get("significant", False)
            if not is_significant:
                continue

            # Check effect size (assuming positive is good)
            effect_size = stats.get("effect_size", 0.0)

            # Double check with means if effect size sign is ambiguous
            # (Treatment Mean - Control Mean)
            # But let's rely on effect_size being directional or check means
            variant_mean = metrics_data.get(variant_id, {}).get("mean", 0)
            # We don't easily know control mean here without config, but if effect_size is positive
            # and significant, we assume it's better.

            if effect_size > 0 and effect_size > best_improvement:
                best_improvement = effect_size
                best_variant = variant_id

        if best_variant:
            logger.info(
                f"Found winning variant {best_variant} for {experiment_id} (Effect: {best_improvement:.2f})"
            )

        return best_variant
