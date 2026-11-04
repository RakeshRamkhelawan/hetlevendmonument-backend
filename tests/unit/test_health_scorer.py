"""Unit tests for HealthScorer - pure stateless health score computation."""

from __future__ import annotations

import pytest

from src.core.agents.health_scorer import HealthScorer


@pytest.mark.unit
def test_perfect_agent_scores_one():
    score = HealthScorer.score(success_rate=1.0, avg_latency_ms=0.0, health_status="HEALTHY")
    assert score == pytest.approx(1.0, abs=0.001)


@pytest.mark.unit
def test_completely_failed_agent_scores_near_zero():
    score = HealthScorer.score(success_rate=0.0, avg_latency_ms=5000.0, health_status="CRITICAL")
    assert score == pytest.approx(0.03, abs=0.01)


@pytest.mark.unit
def test_unknown_status_uses_0_5_multiplier():
    score = HealthScorer.score(success_rate=1.0, avg_latency_ms=0.0, health_status="UNKNOWN")
    # 1.0*0.4 + 1.0*0.3 + 0.5*0.3 = 0.4 + 0.3 + 0.15 = 0.85
    assert score == pytest.approx(0.85, abs=0.001)


@pytest.mark.unit
def test_latency_above_max_clamps_to_zero():
    score = HealthScorer.score(success_rate=0.0, avg_latency_ms=10000.0, health_status="UNKNOWN")
    # latency term = max(0, 1 - 10000/5000) = 0
    assert score >= 0.0


@pytest.mark.unit
def test_score_clamped_to_0_1():
    score = HealthScorer.score(success_rate=2.0, avg_latency_ms=-100.0, health_status="HEALTHY")
    assert 0.0 <= score <= 1.0


@pytest.mark.unit
def test_warning_status_multiplier():
    score = HealthScorer.score(success_rate=1.0, avg_latency_ms=0.0, health_status="WARNING")
    # 1.0*0.4 + 1.0*0.3 + 0.6*0.3 = 0.4 + 0.3 + 0.18 = 0.88
    assert score == pytest.approx(0.88, abs=0.001)


@pytest.mark.unit
def test_unknown_health_status_string_treated_as_unknown():
    score_explicit = HealthScorer.score(1.0, 0.0, health_status="UNKNOWN")
    score_typo = HealthScorer.score(1.0, 0.0, health_status="BOGUS_STATUS")
    assert score_explicit == score_typo


@pytest.mark.unit
def test_manifest_helper_uses_manifest_fields():
    """score_manifest() uses success_rate, avg_latency_ms, and health_status from the manifest."""
    from unittest.mock import MagicMock

    manifest = MagicMock()
    manifest.success_rate = 0.95
    manifest.avg_latency_ms = 400.0
    manifest.health_status = "UNKNOWN"
    score = HealthScorer.score_manifest(manifest)
    # 0.95*0.4 + (1 - 400/5000)*0.3 + 0.5*0.3
    # = 0.38 + 0.276 + 0.15 = 0.806
    assert score == pytest.approx(0.806, abs=0.001)


@pytest.mark.unit
def test_manifest_helper_respects_health_status():
    """score_manifest() passes health_status to score() — HEALTHY outranks UNKNOWN."""
    from unittest.mock import MagicMock

    manifest_healthy = MagicMock()
    manifest_healthy.success_rate = 0.9
    manifest_healthy.avg_latency_ms = 500.0
    manifest_healthy.health_status = "HEALTHY"

    manifest_unknown = MagicMock()
    manifest_unknown.success_rate = 0.9
    manifest_unknown.avg_latency_ms = 500.0
    manifest_unknown.health_status = "UNKNOWN"

    assert HealthScorer.score_manifest(manifest_healthy) > HealthScorer.score_manifest(
        manifest_unknown
    )
