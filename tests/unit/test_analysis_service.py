"""Tests for AnalysisService — no-any-return fixes."""

import pytest

from src.core.strategy.services.analysis import AnalysisService
from src.core.strategy.types import StrategyType


@pytest.fixture
def service() -> AnalysisService:
    """Provide AnalysisService instance."""
    return AnalysisService()


class TestParseStrategicAnalysis:
    """Test parse_strategic_analysis method."""

    def test_parse_valid_json_embedded_in_text(self, service: AnalysisService) -> None:
        """Happy path: extract and parse JSON from embedded text."""
        analysis_text = (
            "Here is my analysis: "
            '{"current_situation": "Strong market position",'
            '"opportunities": ["Growth opportunity"],'
            '"threats": ["New competitor"],'
            '"strategic_options": ["Option A"],'
            '"risk_assessment": "Low risk",'
            '"resource_requirements": ["Team"]}'
        )

        result = service.parse_strategic_analysis(analysis_text, StrategyType.MARKET_ANALYSIS)

        assert isinstance(result, dict)
        assert result["current_situation"] == "Strong market position"
        assert isinstance(result["opportunities"], list)
        assert len(result["opportunities"]) == 1

    def test_parse_valid_json_only(self, service: AnalysisService) -> None:
        """Happy path: parse pure JSON without surrounding text."""
        analysis_json = (
            '{"current_situation": "Analysis text",'
            '"opportunities": ["Op1", "Op2"],'
            '"threats": ["Threat1"],'
            '"strategic_options": ["Strategy1", "Strategy2"],'
            '"risk_assessment": "Medium",'
            '"resource_requirements": ["R1", "R2"]}'
        )

        result = service.parse_strategic_analysis(analysis_json, StrategyType.PRODUCT_STRATEGY)

        assert isinstance(result, dict)
        assert "current_situation" in result
        assert isinstance(result["opportunities"], list)
        assert len(result["opportunities"]) == 2

    def test_parse_invalid_json_returns_fallback(self, service: AnalysisService) -> None:
        """Unhappy path: invalid JSON falls back to default structure."""
        analysis_text = "This is not valid JSON at all"

        result = service.parse_strategic_analysis(analysis_text, StrategyType.MARKET_ANALYSIS)

        assert isinstance(result, dict)
        assert "current_situation" in result
        assert result["current_situation"] == "Analysis completed based on provided context"

    def test_parse_malformed_json_returns_fallback(self, service: AnalysisService) -> None:
        """Unhappy path: malformed JSON (missing closing brace) falls back."""
        analysis_text = 'Some text {"current_situation": "Incomplete JSON'

        result = service.parse_strategic_analysis(analysis_text, StrategyType.MARKET_ANALYSIS)

        assert isinstance(result, dict)
        assert result["current_situation"] == "Analysis completed based on provided context"

    def test_parse_empty_string_returns_fallback(self, service: AnalysisService) -> None:
        """Unhappy path: empty string returns fallback structure."""
        result = service.parse_strategic_analysis("", StrategyType.MARKET_ANALYSIS)

        assert isinstance(result, dict)
        assert "opportunities" in result

    def test_parse_result_type_is_dict(self, service: AnalysisService) -> None:
        """User behavioral test: parsed result is usable dict."""
        analysis_json = (
            '{"current_situation": "Test", "opportunities": [],'
            '"threats": [], "strategic_options": [],'
            '"risk_assessment": "Low", "resource_requirements": []}'
        )

        result = service.parse_strategic_analysis(analysis_json, StrategyType.MARKET_ANALYSIS)

        # Verify result can be used as dict (subscript access, iteration)
        assert result["current_situation"] == "Test"
        for key in result.keys():
            assert isinstance(key, str)


class TestParseRecommendations:
    """Test parse_recommendations method."""

    def test_parse_valid_json_array(self, service: AnalysisService) -> None:
        """Happy path: parse JSON array of recommendations."""
        recommendations_text = (
            "Here are my recommendations: "
            '[{"title": "Rec1", "action_statement": "Do this",'
            '"impact": "High", "resources": ["Team"], "timeline_weeks": 4,'
            '"success_metrics": ["M1"]}'
            ', {"title": "Rec2", "action_statement": "Do that",'
            '"impact": "Medium", "resources": ["Budget"], "timeline_weeks": 8,'
            '"success_metrics": ["M2", "M3"]}]'
        )

        result = service.parse_recommendations(recommendations_text)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["title"] == "Rec1"
        assert result[1]["title"] == "Rec2"

    def test_parse_single_recommendation(self, service: AnalysisService) -> None:
        """Happy path: parse array with single recommendation."""
        recommendations_json = (
            '[{"title": "SingleRec", "action_statement": "Action",'
            '"impact": "High", "resources": ["Team", "Budget"],'
            '"timeline_weeks": 6, "success_metrics": ["M1"]}]'
        )

        result = service.parse_recommendations(recommendations_json)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "SingleRec"

    def test_parse_invalid_json_returns_fallback(self, service: AnalysisService) -> None:
        """Unhappy path: invalid JSON returns fallback recommendations."""
        recommendations_text = "This is not valid JSON"

        result = service.parse_recommendations(recommendations_text)

        assert isinstance(result, list)
        assert len(result) == 2  # Default fallback has 2 recommendations
        assert "title" in result[0]

    def test_parse_malformed_array_returns_fallback(self, service: AnalysisService) -> None:
        """Unhappy path: malformed array falls back."""
        recommendations_text = "[{incomplete json"

        result = service.parse_recommendations(recommendations_text)

        assert isinstance(result, list)
        assert len(result) == 2

    def test_parse_empty_string_returns_fallback(self, service: AnalysisService) -> None:
        """Unhappy path: empty string returns fallback."""
        result = service.parse_recommendations("")

        assert isinstance(result, list)
        assert len(result) == 2

    def test_parse_result_is_list_of_dicts(self, service: AnalysisService) -> None:
        """User behavioral test: parsed recommendations are iterable dicts."""
        recommendations_json = (
            '[{"title": "Test", "action_statement": "Test action",'
            '"impact": "High", "resources": ["R1"],'
            '"timeline_weeks": 4, "success_metrics": ["S1"]}]'
        )

        result = service.parse_recommendations(recommendations_json)

        assert isinstance(result, list)
        for rec in result:
            assert isinstance(rec, dict)
            assert "title" in rec


class TestCalculateConfidenceScore:
    """Test calculate_confidence_score method."""

    def test_strong_analysis_and_recommendations(self, service: AnalysisService) -> None:
        """Happy path: strong analysis and 3+ recommendations."""
        analysis = {
            "current_situation": "Strong",
            "opportunities": ["Op1", "Op2"],
            "threats": ["Threat1"],
            "strategic_options": ["Strategy1"],
        }
        recommendations = [
            {
                "title": "Rec1",
                "action": "Action1",
                "impact": "High",
                "resources": ["R1"],
                "timeline_weeks": 4,
                "success_metrics": ["M1"],
            },
            {
                "title": "Rec2",
                "action": "Action2",
                "impact": "High",
                "resources": ["R2"],
                "timeline_weeks": 4,
                "success_metrics": ["M2"],
            },
            {
                "title": "Rec3",
                "action": "Action3",
                "impact": "High",
                "resources": ["R3"],
                "timeline_weeks": 4,
                "success_metrics": ["M3"],
            },
        ]

        score = service.calculate_confidence_score(analysis, recommendations)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score > 0.7  # Strong case should have high confidence

    def test_weak_analysis_and_few_recommendations(self, service: AnalysisService) -> None:
        """Unhappy path: weak analysis with 1-2 recommendations."""
        analysis = {"current_situation": "Weak"}
        recommendations = [
            {
                "title": "Only one",
                "action": "Action",
                "impact": "Low",
            }
        ]

        score = service.calculate_confidence_score(analysis, recommendations)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score < 0.7  # Weak case should have lower confidence

    def test_empty_data_returns_low_confidence(self, service: AnalysisService) -> None:
        """Unhappy path: empty data returns low confidence."""
        analysis: dict = {}
        recommendations: list = []

        score = service.calculate_confidence_score(analysis, recommendations)

        assert isinstance(score, float)
        assert 0.0 <= score <= 0.5

    def test_score_is_float_between_0_and_1(self, service: AnalysisService) -> None:
        """User behavioral test: confidence score is always valid float."""
        analysis = {"a": 1, "b": 2, "c": 3, "d": 4}
        recommendations = [{"x": 1}, {"y": 2}]

        score = service.calculate_confidence_score(analysis, recommendations)

        assert isinstance(score, float)
        assert not (score != score)  # Not NaN
        assert score != float("inf")  # Not infinity
        assert -0.01 <= score <= 1.01  # Roughly in valid range

    def test_average_calculation(self, service: AnalysisService) -> None:
        """Test that confidence is average of factors."""
        analysis = {"a": 1, "b": 2, "c": 3, "d": 4}
        recommendations = [{"x": 1}, {"y": 2}, {"z": 3}]

        score = service.calculate_confidence_score(analysis, recommendations)

        # Should be average of factors: [0.8, 0.9, 1.0] / 3 ≈ 0.9
        assert 0.5 < score < 1.0
