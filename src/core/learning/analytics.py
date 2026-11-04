"""
Advanced analytics for learning insights.

Provides:
- Trend analysis
- Performance metrics
- ROI calculations
"""

import logging
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.loop import AdaptationRule, LearningInsight

logger = logging.getLogger(__name__)


class DailyReportDict(TypedDict, total=False):
    """Return type for generate_daily_report."""

    period: str
    date: str
    summary: dict[str, object]
    performance: dict[str, str]
    top_categories: list[dict[str, str | int]]


class WeeklyReportDict(TypedDict, total=False):
    """Return type for generate_weekly_report."""

    period: str
    date_range: dict[str, str]
    summary: dict[str, object]
    roi: dict[str, str | float]
    performance: dict[str, str]


@dataclass
class LearningMetrics:
    """Comprehensive learning metrics."""

    total_insights: int
    adaptations_applied: int
    success_rate: float
    avg_confidence: float
    trend_direction: str  # "improving", "stable", "declining"
    trend_percentage: float
    top_categories: list[dict[str, str | int]]  # each entry: {"category": str, "count": int}
    performance_score: float  # 0-100


@dataclass
class ROIMetrics:
    """Return on Investment metrics for learning system."""

    time_saved_hours: float
    accuracy_improvement: float
    manual_interventions_prevented: int
    estimated_cost_savings: float
    roi_percentage: float


class LearningAnalytics:
    """
    Analytics engine for learning insights.
    """

    def __init__(self, db_session: AsyncSession | None = None) -> None:
        self.db = db_session

    async def get_metrics(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> LearningMetrics:
        """
        Get comprehensive learning metrics.

        Args:
            start_date: Start of period (default: 30 days ago)
            end_date: End of period (default: now)
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        insights = await self._fetch_insights(start_date, end_date)
        rules = await self._fetch_rules()

        # Calculate metrics
        total = len(insights)
        adaptations = sum(1 for i in insights if i.adaptation_applied)
        success_rate = adaptations / total if total > 0 else 0

        avg_confidence = 0.0
        if insights:
            avg_confidence = sum(i.confidence_score or 0 for i in insights) / len(insights)

        # Calculate trend
        trend_direction, trend_pct = self._calculate_trend(insights)

        # Top categories
        categories = Counter(i.category for i in insights if i.category)
        top_categories: list[dict[str, str | int]] = [
            {"category": cat, "count": count} for cat, count in categories.most_common(5)
        ]

        # Performance score (0-100)
        performance = self._calculate_performance_score(success_rate, avg_confidence, rules)

        return LearningMetrics(
            total_insights=total,
            adaptations_applied=adaptations,
            success_rate=success_rate,
            avg_confidence=avg_confidence,
            trend_direction=trend_direction,
            trend_percentage=trend_pct,
            top_categories=top_categories,
            performance_score=performance,
        )

    async def _fetch_insights(
        self, start_date: datetime, end_date: datetime
    ) -> list[LearningInsight]:
        """Fetch insights from database."""
        if not self.db:
            return []

        # In production, this would query the database
        # For now, return empty list
        return []

    async def _fetch_rules(self) -> list[AdaptationRule]:
        """Fetch rules from database."""
        if not self.db:
            return []

        return []

    def _calculate_trend(self, insights: list[LearningInsight]) -> tuple[str, float]:
        """
        Calculate trend direction and percentage.

        Returns: (direction, percentage) where direction is "improving"|"stable"|"declining"
        """
        if len(insights) < 10:
            return "stable", 0.0

        # Split into two halves
        mid = len(insights) // 2
        first_half = insights[:mid]
        second_half = insights[mid:]

        first_success = sum(1 for i in first_half if i.adaptation_applied)
        second_success = sum(1 for i in second_half if i.adaptation_applied)

        first_rate = first_success / len(first_half) if first_half else 0
        second_rate = second_success / len(second_half) if second_half else 0

        if first_rate == 0:
            return "improving", 100.0 if second_rate > 0 else 0.0

        change_pct = ((second_rate - first_rate) / first_rate) * 100

        if change_pct > 10:
            return "improving", change_pct
        elif change_pct < -10:
            return "declining", abs(change_pct)
        else:
            return "stable", abs(change_pct)

    def _calculate_performance_score(
        self, success_rate: float, avg_confidence: float, rules: list[AdaptationRule]
    ) -> float:
        """
        Calculate overall performance score (0-100).
        """
        # Weight factors
        success_weight = 0.5
        confidence_weight = 0.3
        rules_weight = 0.2

        # Success score (0-100)
        success_score = success_rate * 100

        # Confidence score (0-100)
        confidence_score = avg_confidence * 100

        # Rules score based on success rates
        if rules:
            success_rates = [r.success_rate for r in rules if r.success_rate is not None]
            avg_rule_success = sum(success_rates) / len(success_rates) if success_rates else 0.0
            rules_score = avg_rule_success * 100
        else:
            rules_score = 50  # Neutral if no rules

        # Weighted average
        score = (
            success_score * success_weight
            + confidence_score * confidence_weight
            + rules_score * rules_weight
        )

        return min(score, 100.0)

    async def calculate_roi(self, hourly_cost: float = 50.0, period_days: int = 30) -> ROIMetrics:
        """
        Calculate ROI for learning system.

        Args:
            hourly_cost: Cost per hour of manual work
            period_days: Analysis period in days
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=period_days)

        insights = await self._fetch_insights(start_date, end_date)

        # Calculate time saved
        # Assume each successful adaptation saves 5 minutes
        successful_adaptations = sum(1 for i in insights if i.adaptation_applied)
        time_saved_hours = successful_adaptations * (5 / 60)

        # Accuracy improvement
        if len(insights) >= 2:
            recent = insights[-len(insights) // 2 :]
            older = insights[: len(insights) // 2]

            recent_success = (
                sum(1 for i in recent if i.adaptation_applied) / len(recent) if recent else 0
            )
            older_success = (
                sum(1 for i in older if i.adaptation_applied) / len(older) if older else 0
            )

            accuracy_improvement = (recent_success - older_success) * 100
        else:
            accuracy_improvement = 0.0

        # Cost savings
        cost_savings = time_saved_hours * hourly_cost

        # ROI calculation (simplified)
        # Assume system cost is fixed monthly
        estimated_system_cost = 500.0  # Placeholder
        roi_pct = (
            ((cost_savings - estimated_system_cost) / estimated_system_cost * 100)
            if estimated_system_cost > 0
            else 0
        )

        return ROIMetrics(
            time_saved_hours=time_saved_hours,
            accuracy_improvement=accuracy_improvement,
            manual_interventions_prevented=successful_adaptations,
            estimated_cost_savings=cost_savings,
            roi_percentage=roi_pct,
        )


class TrendAnalyzer:
    """
    Analyze trends in learning data.
    """

    def __init__(self) -> None:
        self.min_data_points = 5

    def detect_trends(
        self,
        data: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        value_key: str = "value",
        date_key: str = "date",
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Detect trends in time-series data.

        Args:
            data: List of data-point dicts (each has a value and date field)
            value_key: Key for value field
            date_key: Key for date field

        Returns: List of detected trend dicts (type, direction, change_percentage, confidence)
        """
        if len(data) < self.min_data_points:
            return []

        # Sort by date
        sorted_data = sorted(data, key=lambda x: x.get(date_key, ""))

        trends: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        # Simple linear trend detection
        values = [d.get(value_key, 0) for d in sorted_data]

        if len(values) >= 3:
            # Calculate moving averages
            window = min(3, len(values) // 2)
            ma: list[float] = []
            for i in range(window - 1, len(values)):
                window_values = values[i - window + 1 : i + 1]
                ma.append(sum(window_values) / len(window_values))

            # Detect trend direction
            if len(ma) >= 2:
                first_avg = sum(ma[: len(ma) // 2]) / (len(ma) // 2)
                second_avg = sum(ma[len(ma) // 2 :]) / (len(ma) - len(ma) // 2)

                change_pct = ((second_avg - first_avg) / first_avg * 100) if first_avg != 0 else 0

                if abs(change_pct) > 5:  # Significant change
                    trends.append(
                        {
                            "type": "linear_trend",
                            "direction": "increasing" if change_pct > 0 else "decreasing",
                            "change_percentage": abs(change_pct),
                            "confidence": min(abs(change_pct) / 50, 0.95),
                        }
                    )

        return trends

    def forecast(self, data: list[float], periods: int = 7) -> list[float]:
        """
        Simple forecasting using moving average.

        Args:
            data: Historical data points
            periods: Number of periods to forecast

        Returns:
            Forecasted values
        """
        if len(data) < 3:
            return [sum(data) / len(data)] * periods if data else [0] * periods

        # Use exponential moving average for forecast
        alpha = 0.3  # Smoothing factor
        ema = data[0]

        for value in data[1:]:
            ema = alpha * value + (1 - alpha) * ema

        # Project forward
        forecast: list[float] = []
        for _ in range(periods):
            forecast.append(ema)
            ema = alpha * ema + (1 - alpha) * ema  # Continue trend

        return forecast


class ReportGenerator:
    """
    Generate analytics reports.
    """

    def __init__(self, analytics: LearningAnalytics) -> None:
        self.analytics = analytics

    async def generate_daily_report(self) -> DailyReportDict:
        """Generate daily learning report."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=1)

        metrics = await self.analytics.get_metrics(start_date, end_date)

        return {
            "period": "daily",
            "date": end_date.isoformat(),
            "summary": {
                "insights_collected": metrics.total_insights,
                "adaptations_applied": metrics.adaptations_applied,
                "success_rate": f"{metrics.success_rate:.1%}",
            },
            "performance": {
                "score": f"{metrics.performance_score:.1f}/100",
                "trend": metrics.trend_direction,
            },
            "top_categories": metrics.top_categories,
        }

    async def generate_weekly_report(self) -> WeeklyReportDict:
        """Generate weekly learning report."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)

        metrics = await self.analytics.get_metrics(start_date, end_date)
        roi = await self.analytics.calculate_roi(period_days=7)

        return {
            "period": "weekly",
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "summary": {
                "insights_collected": metrics.total_insights,
                "adaptations_applied": metrics.adaptations_applied,
                "success_rate": f"{metrics.success_rate:.1%}",
            },
            "roi": {
                "time_saved_hours": round(roi.time_saved_hours, 2),
                "cost_savings": f"${roi.estimated_cost_savings:.2f}",
                "roi_percentage": f"{roi.roi_percentage:.1f}%",
            },
            "performance": {
                "score": f"{metrics.performance_score:.1f}/100",
                "trend": metrics.trend_direction,
                "trend_change": f"{metrics.trend_percentage:.1f}%",
            },
        }


# Convenience functions
async def get_learning_metrics(
    db_session: AsyncSession | None = None,
    days: int = 30,
) -> LearningMetrics:
    """Get learning metrics for specified period."""
    analytics = LearningAnalytics(db_session)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    return await analytics.get_metrics(start_date, end_date)


async def get_roi_report(
    db_session: AsyncSession | None = None,
    hourly_cost: float = 50.0,
) -> ROIMetrics:
    """Get ROI report."""
    analytics = LearningAnalytics(db_session)
    return await analytics.calculate_roi(hourly_cost=hourly_cost)
