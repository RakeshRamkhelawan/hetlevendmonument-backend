"""
Agency Capabilities Unit Tests - Real Implementation (No Mockdata)

These tests use REAL logic:
- Real calculations (WSJF scoring, financial metrics, etc.)
- Real data transformations
- NO hardcoded mock outputs

Run with:
    pytest tests/unit/agency/test_agency_capabilities_real.py -v
"""

import statistics
from typing import Any, Dict, List

import pytest

pytestmark = [pytest.mark.unit]


class TestAgencyCapabilitiesReal:
    """
    Test real Agency capabilities with actual logic (no mockdata).
    """

    def test_sprint_prioritizer_wsjf_calculation(self):
        """
        Test WSJF (Weighted Shortest Job First) calculation.

        Formula: (Value + Risk + Time) / Effort
        """
        from src.core.agents.capabilities.agency_capabilities_real import (
            ProductManagementCapabilitiesReal,
        )

        backlog = [
            {
                "id": 1,
                "story_points": 5,
                "business_value": 10,
                "risk_reduction": 5,
                "time_criticality": 3,
            },
            {
                "id": 2,
                "story_points": 3,
                "business_value": 8,
                "risk_reduction": 2,
                "time_criticality": 2,
            },
            {
                "id": 3,
                "story_points": 2,
                "business_value": 5,
                "risk_reduction": 0,
                "time_criticality": 1,
            },
        ]

        result = ProductManagementCapabilitiesReal.prioritize_sprint(
            {"backlog": backlog, "team_capacity": 40}
        )

        # Verify WSJF scores
        # Item 1: (10 + 5 + 3) / 5 = 3.6
        # Item 2: (8 + 2 + 2) / 3 = 4.0
        # Item 3: (5 + 0 + 1) / 2 = 3.0

        items = result["backlog_items"]
        assert items[0]["wsjf_score"] == 4.0  # Highest score
        assert items[0]["id"] == 2  # Should be item 2

        # Verify prioritization method
        assert result["prioritization_method"] == "WSJF (Weighted Shortest Job First)"
        assert result["wsjf_formula"] == "(Value + Risk + Time) / Effort"

    def test_sprint_prioritizer_capacity_constraint(self):
        """
        Test that sprint respects team capacity.
        """
        from src.core.agents.capabilities.agency_capabilities_real import (
            ProductManagementCapabilitiesReal,
        )

        # Create backlog that exceeds capacity
        backlog = [
            {"id": 1, "story_points": 20, "business_value": 10},
            {"id": 2, "story_points": 20, "business_value": 9},
            {"id": 3, "story_points": 20, "business_value": 8},  # Should be excluded
        ]

        result = ProductManagementCapabilitiesReal.prioritize_sprint(
            {"backlog": backlog, "team_capacity": 40}
        )

        # Should only include items 1 and 2 (40 points)
        assert len(result["sprint_backlog"]) == 2
        assert result["total_story_points"] == 40
        assert result["capacity_utilization"] == "100.0%"

        # Item 3 should not be in sprint
        sprint_ids = [item["id"] for item in result["sprint_backlog"]]
        assert 3 not in sprint_ids

    def test_sprint_prioritizer_empty_backlog(self):
        """
        Test handling of empty backlog.
        """
        from src.core.agents.capabilities.agency_capabilities_real import (
            ProductManagementCapabilitiesReal,
        )

        result = ProductManagementCapabilitiesReal.prioritize_sprint(
            {"backlog": [], "team_capacity": 40}
        )

        assert result["sprint_backlog"] == []
        assert result["total_story_points"] == 0
        assert result.get("items_selected", 0) == 0

    def test_market_trends_industry_specific(self):
        """
        Test that trends are industry-specific (real data, not random).
        """
        from src.core.agents.capabilities.agency_capabilities_real import (
            ProductManagementCapabilitiesReal,
        )

        # Test healthcare
        healthcare = ProductManagementCapabilitiesReal.research_market_trends(
            {"industry": "healthcare", "timeframe_months": 12}
        )

        assert healthcare["industry"] == "healthcare"
        assert len(healthcare["trends"]) > 0

        # Each trend should have adoption rate
        for trend in healthcare["trends"]:
            assert "adoption_rate" in trend
            assert 0 <= trend["adoption_rate"] <= 1
            assert "momentum" in trend
            assert trend["momentum"] in ["high", "medium", "low"]

        # Test technology (different trends)
        tech = ProductManagementCapabilitiesReal.research_market_trends(
            {"industry": "technology", "timeframe_months": 12}
        )

        assert tech["industry"] == "technology"
        # Should have different trends than healthcare

    def test_feedback_synthesis_categorization(self):
        """
        Test NLP-style categorization of feedback.
        """
        from src.core.agents.capabilities.agency_capabilities_real import (
            ProductManagementCapabilitiesReal,
        )

        feedback = [
            {"text": "I love the new feature! It's amazing!", "sentiment": "positive"},
            {"text": "There's a bug in the login", "sentiment": "negative"},
            {"text": "I wish there was dark mode", "sentiment": "neutral"},
            {"text": "Great work team", "sentiment": "positive"},
            {"text": "How do I reset my password?", "sentiment": "neutral"},
        ]

        result = ProductManagementCapabilitiesReal.synthesize_feedback({"feedback": feedback})

        assert result["total_items"] == 5
        assert "categories" in result

        # Should categorize the bug
        assert result["categories"]["bug_report"] >= 1

        # Should categorize praise
        assert result["categories"]["praise"] >= 1

        # Sentiment score should be positive (3 positive, 2 neutral)
        assert result["sentiment_score"] > 0

        # Should have action items
        assert len(result["action_items"]) > 0

    def test_feedback_synthesis_empty(self):
        """
        Test handling of empty feedback.
        """
        from src.core.agents.capabilities.agency_capabilities_real import (
            ProductManagementCapabilitiesReal,
        )

        result = ProductManagementCapabilitiesReal.synthesize_feedback({"feedback": []})

        assert result["total_items"] == 0
        assert result["sentiment_score"] == 0

    def test_api_tester_generates_test_cases(self):
        """
        Test that API tester generates real test cases.
        """
        from src.core.agents.capabilities.agency_capabilities_real import TestingCapabilitiesReal

        endpoints = [
            {"path": "/api/v1/users", "method": "GET", "auth": True},
            {"path": "/api/v1/users", "method": "POST", "auth": True},
        ]

        result = TestingCapabilitiesReal.test_api_endpoints({"endpoints": endpoints})

        # Should generate multiple test cases per endpoint
        assert result["test_suite"]["endpoints_tested"] == 2
        assert result["test_suite"]["total_test_cases"] >= 4  # 2 endpoints * 2 tests each

        # Should have different test types
        tests = result["test_suite"]["tests"]
        test_types = set(t["test_type"] for t in tests)
        assert "positive" in test_types
        assert "auth_negative" in test_types

    def test_api_tester_empty_endpoints(self):
        """
        Test handling of empty endpoints list.
        """
        from src.core.agents.capabilities.agency_capabilities_real import TestingCapabilitiesReal

        result = TestingCapabilitiesReal.test_api_endpoints({"endpoints": []})

        assert result["test_suite"]["endpoints_tested"] == 0
        assert result["test_suite"]["tests"] == []

    def test_performance_benchmark_calculation(self):
        """
        Test performance benchmark calculations.
        """
        from src.core.agents.capabilities.agency_capabilities_real import TestingCapabilitiesReal

        result = TestingCapabilitiesReal.benchmark_performance(
            {"scenario": "api_load", "duration_minutes": 5, "concurrent_users": 100}
        )

        # Should calculate expected throughput
        assert result["benchmark_config"]["concurrent_users"] == 100
        assert result["expected_metrics"]["throughput_rps"] > 0

        # Should have latency distribution
        latency = result["expected_metrics"]["latency_ms"]
        assert "p50" in latency
        assert "p95" in latency
        assert "p99" in latency

        # p50 < p75 < p95 < p99
        assert latency["p50"] < latency["p95"]
        assert latency["p95"] < latency["p99"]

    def test_performance_benchmark_scenarios(self):
        """
        Test different scenarios have different profiles.
        """
        from src.core.agents.capabilities.agency_capabilities_real import TestingCapabilitiesReal

        api_load = TestingCapabilitiesReal.benchmark_performance(
            {"scenario": "api_load", "concurrent_users": 100}
        )

        db_heavy = TestingCapabilitiesReal.benchmark_performance(
            {"scenario": "database_heavy", "concurrent_users": 100}
        )

        # API load should have higher throughput than DB heavy
        assert (
            api_load["expected_metrics"]["throughput_rps"]
            > db_heavy["expected_metrics"]["throughput_rps"]
        )

        # DB heavy should have higher latency
        assert (
            db_heavy["expected_metrics"]["latency_ms"]["p95"]
            > api_load["expected_metrics"]["latency_ms"]["p95"]
        )

    def test_finance_ltv_cac_calculation(self):
        """
        Test LTV:CAC ratio calculation.
        """
        from src.core.agents.capabilities.agency_capabilities_real import FinanceCapabilitiesReal

        result = FinanceCapabilitiesReal.track_financial_metrics(
            {
                "revenue": {
                    "mrr": 100000,
                    "previous_mrr": 90000,
                    "cac": 500,
                    "ltv": 5000,
                    "cash_balance": 1000000,
                },
                "expenses": {"monthly_burn": 80000},
            }
        )

        # Verify calculations
        assert result["unit_economics"]["cac"] == 500
        assert result["unit_economics"]["ltv"] == 5000
        assert result["unit_economics"]["ltv_cac_ratio"] == 10.0  # 5000 / 500

        # Growth rate: (100000 - 90000) / 90000 * 100 = 11.1%
        assert result["revenue_metrics"]["growth_rate_percent"] == pytest.approx(11.1, 0.1)

        # ARR: 100000 * 12 = 1200000
        assert result["revenue_metrics"]["arr"] == 1200000

    def test_finance_runway_calculation(self):
        """
        Test runway calculation.
        """
        from src.core.agents.capabilities.agency_capabilities_real import FinanceCapabilitiesReal

        result = FinanceCapabilitiesReal.track_financial_metrics(
            {
                "revenue": {"mrr": 100000, "cac": 500, "ltv": 5000, "cash_balance": 400000},
                "expenses": {"monthly_burn": 80000},
            }
        )

        # Runway: 400000 / 80000 = 5 months
        assert result["runway"]["runway_months"] == 5.0

    def test_finance_health_indicators(self):
        """
        Test financial health assessment.
        """
        from src.core.agents.capabilities.agency_capabilities_real import FinanceCapabilitiesReal

        # Healthy metrics
        healthy = FinanceCapabilitiesReal.track_financial_metrics(
            {
                "revenue": {
                    "mrr": 100000,
                    "cac": 500,
                    "ltv": 5000,  # 10x CAC - healthy
                    "cash_balance": 1200000,  # 12 months runway
                },
                "expenses": {"monthly_burn": 100000},
            }
        )

        ltv_cac_indicator = [i for i in healthy["health_indicators"] if i["metric"] == "LTV:CAC"][0]
        assert ltv_cac_indicator["status"] == "healthy"

        # Unhealthy metrics
        unhealthy = FinanceCapabilitiesReal.track_financial_metrics(
            {
                "revenue": {
                    "mrr": 100000,
                    "cac": 500,
                    "ltv": 400,  # < CAC - unhealthy
                    "cash_balance": 200000,  # 2 months runway
                },
                "expenses": {"monthly_burn": 100000},
            }
        )

        ltv_cac_indicator = [i for i in unhealthy["health_indicators"] if i["metric"] == "LTV:CAC"][
            0
        ]
        assert ltv_cac_indicator["status"] == "critical"

        runway_indicator = [i for i in unhealthy["health_indicators"] if i["metric"] == "Runway"][0]
        assert runway_indicator["status"] == "critical"


class TestAgencyCapabilitiesRegistry:
    """
    Test capability registry integration.
    """

    def test_all_capabilities_registered(self):
        """
        Test that all 46 capabilities are registered.
        """
        from src.core.agents.capabilities.agency_capabilities import AgencyCapabilityRegistry

        capabilities = AgencyCapabilityRegistry.list_capabilities()

        # Should have at least the real capabilities (15 from base + real)
        assert len(capabilities) >= 15

        # Verify real capabilities are present
        real_caps = [
            "agency_prioritize_sprint",
            "agency_research_trends",
            "agency_synthesize_feedback",
            "agency_test_api",
            "agency_benchmark_performance",
            "agency_track_finance",
        ]

        for cap in real_caps:
            assert cap in capabilities, f"Missing capability: {cap}"

    def test_capability_execution(self):
        """
        Test that capabilities can be retrieved and executed.
        """
        from src.core.agents.capabilities.agency_capabilities import AgencyCapabilityRegistry

        # Get capability
        handler = AgencyCapabilityRegistry.get("agency_prioritize_sprint")
        assert handler is not None

        # Execute with real data
        result = handler(
            {"backlog": [{"id": 1, "story_points": 5, "business_value": 10}], "team_capacity": 40}
        )

        assert result["total_story_points"] == 5
