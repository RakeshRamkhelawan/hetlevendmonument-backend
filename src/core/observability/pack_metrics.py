"""
Pack Intelligence Metrics

Comprehensive metrics collection for pack usage, matching accuracy,
and system performance. Integrates with Prometheus for monitoring.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from prometheus_client import Counter, Gauge, Histogram, Info

logger = logging.getLogger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

# Matching metrics
PACK_MATCH_ATTEMPTS = Counter(
    "pack_match_attempts_total", "Total number of pack match attempts", ["tenant_id", "result"]
)

PACK_MATCH_CONFIDENCE = Histogram(
    "pack_match_confidence_score",
    "Confidence score distribution for pack matches",
    ["tenant_id", "department"],
    buckets=[0.0, 0.5, 0.7, 0.85, 0.95, 1.0],
)

PACK_MATCH_DURATION = Histogram(
    "pack_match_duration_seconds",
    "Time spent on pack matching",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# Template usage metrics
PACK_TEMPLATE_LOADS = Counter(
    "pack_template_loads_total",
    "Total number of pack template loads",
    ["pack_id", "pack_name", "tenant_id"],
)

PACK_TEMPLATE_NODES = Gauge(
    "pack_template_nodes", "Number of nodes in loaded template", ["pack_id", "pack_name"]
)

# Feedback metrics
PACK_FEEDBACK_SUBMITTED = Counter(
    "pack_feedback_submitted_total",
    "Total feedback submissions",
    ["pack_id", "was_helpful", "rating"],
)

PACK_HELPFULNESS_RATIO = Gauge(
    "pack_helpfulness_ratio", "Ratio of helpful vs total feedback", ["pack_id", "pack_name"]
)

PACK_AVERAGE_RATING = Gauge(
    "pack_average_rating", "Average rating for a pack", ["pack_id", "pack_name"]
)

# Global repository metrics
GLOBAL_PACK_CONTRIBUTIONS = Counter(
    "global_pack_contributions_total",
    "Total contributions to global repository",
    ["department", "contribution_type"],
)

GLOBAL_PACK_APPROVALS = Counter(
    "global_pack_approvals_total", "Total pack approvals/rejections", ["decision"]
)

GLOBAL_PACK_USAGE = Counter(
    "global_pack_usage_total", "Total usage of global packs", ["pack_id", "pack_name"]
)

# Multi-pack assembly metrics
MULTIPACK_ASSEMBLY_ATTEMPTS = Counter(
    "multipack_assembly_attempts_total",
    "Total multi-pack assembly attempts",
    ["strategy", "result"],
)

MULTIPACK_ASSEMBLY_DURATION = Histogram(
    "multipack_assembly_duration_seconds",
    "Time spent on multi-pack assembly",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

MULTIPACK_COMPATIBILITY = Gauge(
    "multipack_compatibility_score", "Compatibility score between packs", ["pack_a", "pack_b"]
)

# AI customization metrics
AI_CUSTOMIZATION_ATTEMPTS = Counter(
    "ai_customization_attempts_total",
    "Total AI customization attempts",
    ["result", "save_to_global"],
)

AI_CUSTOMIZATION_DURATION = Histogram(
    "ai_customization_duration_seconds",
    "Time spent on AI customization",
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

AI_GENERATED_PACKS = Counter(
    "ai_generated_packs_total", "Total packs generated from scratch by AI", ["department"]
)

# System info
PACK_SYSTEM_INFO = Info("pack_intelligence_system", "Pack intelligence system information")


# =============================================================================
# Metrics Collector
# =============================================================================


@dataclass
class MatchMetrics:
    """Metrics for a single pack match"""

    timestamp: datetime
    tenant_id: int
    prompt: str
    matched_pack_id: str | None
    matched_pack_name: str | None
    confidence_score: float
    confidence_level: str
    duration_ms: float
    success: bool


@dataclass
class UsageMetrics:
    """Metrics for pack usage"""

    pack_id: str
    pack_name: str
    tenant_id: int
    timestamp: datetime
    node_count: int
    edge_count: int
    load_duration_ms: float
    customization_applied: bool


class PackMetricsCollector:
    """
    Centralized metrics collection for Pack Intelligence System.

    Collects:
    - Matching performance and accuracy
    - Template usage statistics
    - User feedback data
    - Global repository metrics
    - System performance
    """

    def __init__(self) -> None:
        self._match_history: list[MatchMetrics] = []
        self._usage_history: list[UsageMetrics] = []
        self._feedback_cache: dict[str, dict[str, Any]] = defaultdict(  # TODO(TYPE): replace Any with concrete type
            lambda: {"total": 0, "helpful": 0, "ratings": [], "recent": []}
        )

        # Set system info
        PACK_SYSTEM_INFO.info(
            {
                "version": "1.0.0",
                "build_date": datetime.now(timezone.utc).isoformat(),
            }
        )

    # =========================================================================
    # Match Metrics
    # =========================================================================

    def record_match_attempt(
        self,
        tenant_id: int,
        prompt: str,
        matched_pack_id: str | None,
        matched_pack_name: str | None,
        confidence_score: float,
        confidence_level: str,
        duration_ms: float,
        success: bool,
    ) -> None:
        """Record a pack match attempt"""
        # Prometheus counter
        result = "success" if success and matched_pack_id else "no_match" if success else "error"
        PACK_MATCH_ATTEMPTS.labels(tenant_id=str(tenant_id), result=result).inc()

        # Prometheus histogram
        if success and matched_pack_id:
            # Try to get department from pack name
            department = self._infer_department(matched_pack_name or "")
            PACK_MATCH_CONFIDENCE.labels(tenant_id=str(tenant_id), department=department).observe(
                confidence_score
            )

        PACK_MATCH_DURATION.observe(duration_ms / 1000)

        # Store in history
        self._match_history.append(
            MatchMetrics(
                timestamp=datetime.now(timezone.utc),
                tenant_id=tenant_id,
                prompt=prompt,
                matched_pack_id=matched_pack_id,
                matched_pack_name=matched_pack_name,
                confidence_score=confidence_score,
                confidence_level=confidence_level,
                duration_ms=duration_ms,
                success=success,
            )
        )

        # Trim history if needed
        if len(self._match_history) > 10000:
            self._match_history = self._match_history[-5000:]

        logger.debug(
            f"Match recorded: tenant={tenant_id}, "
            f"pack={matched_pack_name}, confidence={confidence_score:.2f}"
        )

    # =========================================================================
    # Usage Metrics
    # =========================================================================

    def record_template_load(
        self,
        pack_id: str,
        pack_name: str,
        tenant_id: int,
        node_count: int,
        edge_count: int,
        duration_ms: float,
        customization_applied: bool = False,
    ) -> None:
        """Record a pack template being loaded"""
        PACK_TEMPLATE_LOADS.labels(
            pack_id=pack_id, pack_name=pack_name, tenant_id=str(tenant_id)
        ).inc()

        PACK_TEMPLATE_NODES.labels(pack_id=pack_id, pack_name=pack_name).set(node_count)

        # Store in history
        self._usage_history.append(
            UsageMetrics(
                pack_id=pack_id,
                pack_name=pack_name,
                tenant_id=tenant_id,
                timestamp=datetime.now(timezone.utc),
                node_count=node_count,
                edge_count=edge_count,
                load_duration_ms=duration_ms,
                customization_applied=customization_applied,
            )
        )

        if len(self._usage_history) > 10000:
            self._usage_history = self._usage_history[-5000:]

    # =========================================================================
    # Feedback Metrics
    # =========================================================================

    def record_feedback(
        self,
        pack_id: str,
        pack_name: str,
        was_helpful: bool,
        rating: int | None = None,
        tenant_id: int | None = None,
    ) -> None:
        """Record user feedback on a pack"""
        helpful_str = "yes" if was_helpful else "no"
        rating_str = str(rating) if rating else "none"

        PACK_FEEDBACK_SUBMITTED.labels(
            pack_id=pack_id, was_helpful=helpful_str, rating=rating_str
        ).inc()

        # Update cache
        cache = self._feedback_cache[pack_id]
        cache["total"] += 1
        if was_helpful:
            cache["helpful"] += 1
        if rating:
            cache["ratings"].append(rating)

        # Update Prometheus gauges
        if cache["total"] > 0:
            PACK_HELPFULNESS_RATIO.labels(pack_id=pack_id, pack_name=pack_name).set(
                cache["helpful"] / cache["total"]
            )

        if cache["ratings"]:
            avg_rating = sum(cache["ratings"]) / len(cache["ratings"])
            PACK_AVERAGE_RATING.labels(pack_id=pack_id, pack_name=pack_name).set(avg_rating)

    # =========================================================================
    # Global Repository Metrics
    # =========================================================================

    def record_global_contribution(
        self, department: str, contribution_type: str = "customization"
    ) -> None:
        """Record a contribution to global repository"""
        GLOBAL_PACK_CONTRIBUTIONS.labels(
            department=department, contribution_type=contribution_type
        ).inc()

    def record_global_approval(self, approved: bool) -> None:
        """Record a pack approval/rejection"""
        decision = "approved" if approved else "rejected"
        GLOBAL_PACK_APPROVALS.labels(decision=decision).inc()

    def record_global_pack_usage(self, pack_id: str, pack_name: str) -> None:
        """Record usage of a global pack"""
        GLOBAL_PACK_USAGE.labels(pack_id=pack_id, pack_name=pack_name).inc()

    # =========================================================================
    # Multi-Pack Assembly Metrics
    # =========================================================================

    def record_multipack_assembly(self, strategy: str, success: bool, duration_ms: float) -> None:
        """Record a multi-pack assembly attempt"""
        result = "success" if success else "failed"
        MULTIPACK_ASSEMBLY_ATTEMPTS.labels(strategy=strategy, result=result).inc()

        MULTIPACK_ASSEMBLY_DURATION.observe(duration_ms / 1000)

    def record_compatibility_score(self, pack_a: str, pack_b: str, score: float) -> None:
        """Record compatibility score between two packs"""
        MULTIPACK_COMPATIBILITY.labels(pack_a=pack_a, pack_b=pack_b).set(score)

    # =========================================================================
    # AI Customization Metrics
    # =========================================================================

    def record_ai_customization(
        self, success: bool, save_to_global: bool, duration_ms: float
    ) -> None:
        """Record an AI customization attempt"""
        result = "success" if success else "failed"
        save_str = "yes" if save_to_global else "no"

        AI_CUSTOMIZATION_ATTEMPTS.labels(result=result, save_to_global=save_str).inc()

        AI_CUSTOMIZATION_DURATION.observe(duration_ms / 1000)

    def record_ai_generated_pack(self, department: str) -> None:
        """Record a pack generated from scratch by AI"""
        AI_GENERATED_PACKS.labels(department=department).inc()

    # =========================================================================
    # Analytics Methods
    # =========================================================================

    def get_match_statistics(
        self, tenant_id: int | None = None, hours: int = 24
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get match statistics for a time period"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        matches = [
            m
            for m in self._match_history
            if m.timestamp >= cutoff and (tenant_id is None or m.tenant_id == tenant_id)
        ]

        if not matches:
            return {
                "total_attempts": 0,
                "successful_matches": 0,
                "match_rate": 0,
                "average_confidence": 0,
                "average_duration_ms": 0,
            }

        successful = [m for m in matches if m.matched_pack_id]

        return {
            "total_attempts": len(matches),
            "successful_matches": len(successful),
            "match_rate": len(successful) / len(matches) * 100,
            "average_confidence": (
                sum(m.confidence_score for m in successful) / len(successful) if successful else 0
            ),
            "average_duration_ms": (sum(m.duration_ms for m in matches) / len(matches)),
            "confidence_distribution": self._calculate_distribution(
                [m.confidence_score for m in matches]
            ),
        }

    def get_popular_packs(self, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get most popular packs"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        usage_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "name": ""})  # TODO(TYPE): replace Any with concrete type

        for usage in self._usage_history:
            if usage.timestamp >= cutoff:
                usage_counts[usage.pack_id]["count"] += 1
                usage_counts[usage.pack_id]["name"] = usage.pack_name

        sorted_packs = sorted(usage_counts.items(), key=lambda x: x[1]["count"], reverse=True)[
            :limit
        ]

        return [
            {"pack_id": pack_id, "pack_name": info["name"], "usage_count": info["count"]}
            for pack_id, info in sorted_packs
        ]

    def get_pack_feedback_summary(self, pack_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get feedback summary for a specific pack"""
        cache = self._feedback_cache[pack_id]

        return {
            "total_feedback": cache["total"],
            "helpful_count": cache["helpful"],
            "helpfulness_rate": (
                cache["helpful"] / cache["total"] * 100 if cache["total"] > 0 else 0
            ),
            "average_rating": (
                sum(cache["ratings"]) / len(cache["ratings"]) if cache["ratings"] else None
            ),
            "rating_distribution": self._calculate_distribution(cache["ratings"]),
        }

    def get_tenant_insights(self, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive insights for a tenant"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        tenant_matches = [
            m for m in self._match_history if m.tenant_id == tenant_id and m.timestamp >= cutoff
        ]

        tenant_usage = [
            u for u in self._usage_history if u.tenant_id == tenant_id and u.timestamp >= cutoff
        ]

        return {
            "total_workflows_generated": len(tenant_matches),
            "pack_match_rate": (
                len([m for m in tenant_matches if m.matched_pack_id]) / len(tenant_matches) * 100
                if tenant_matches
                else 0
            ),
            "favorite_packs": self._get_favorite_packs(tenant_usage),
            "average_customization_rate": (
                len([u for u in tenant_usage if u.customization_applied]) / len(tenant_usage) * 100
                if tenant_usage
                else 0
            ),
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _infer_department(self, pack_name: str) -> str:
        """Infer department from pack name"""
        name_lower = pack_name.lower()
        if "hr" in name_lower or "human" in name_lower:
            return "hr"
        elif "sales" in name_lower:
            return "sales"
        elif "finance" in name_lower or "accounting" in name_lower:
            return "finance"
        elif "marketing" in name_lower:
            return "marketing"
        elif "it" in name_lower or "tech" in name_lower:
            return "it"
        elif "legal" in name_lower:
            return "legal"
        return "general"

    def _calculate_distribution(self, values: list[float]) -> dict[str, int]:
        """Calculate distribution of values"""
        if not values:
            return {}

        distribution: dict[str, int] = defaultdict(int)
        for v in values:
            if v < 0.5:
                distribution["low"] += 1
            elif v < 0.7:
                distribution["medium"] += 1
            elif v < 0.85:
                distribution["high"] += 1
            else:
                distribution["excellent"] += 1

        return dict(distribution)

    def _get_favorite_packs(self, usage_list: list[UsageMetrics]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get favorite packs from usage list"""
        pack_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "name": ""})  # TODO(TYPE): replace Any with concrete type

        for usage in usage_list:
            pack_counts[usage.pack_id]["count"] += 1
            pack_counts[usage.pack_id]["name"] = usage.pack_name

        sorted_packs = sorted(pack_counts.items(), key=lambda x: x[1]["count"], reverse=True)[:5]

        return [
            {"pack_id": pack_id, "pack_name": info["name"], "usage_count": info["count"]}
            for pack_id, info in sorted_packs
        ]


# Singleton instance
_metrics_collector: PackMetricsCollector | None = None


def get_metrics_collector() -> PackMetricsCollector:
    """Get or create singleton metrics collector"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = PackMetricsCollector()
    return _metrics_collector
