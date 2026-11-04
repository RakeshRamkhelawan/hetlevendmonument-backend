"""Unit tests for compliance PDF i18n module.

Covers language parsing and label retrieval.
"""

import pytest

from src.core.i18n.compliance_pdf import get_labels, parse_lang


@pytest.mark.unit
class TestParseLang:
    def test_returns_en_for_simple_en_header(self) -> None:
        assert parse_lang("en") == "en"

    def test_returns_en_for_en_us_header(self) -> None:
        assert parse_lang("en-US,en;q=0.9") == "en"

    def test_returns_nl_for_nl_header(self) -> None:
        assert parse_lang("nl-NL,nl;q=0.9") == "nl"

    def test_returns_nl_for_missing_header(self) -> None:
        assert parse_lang("") == "nl"

    def test_returns_nl_for_unknown_language(self) -> None:
        assert parse_lang("de-DE,de;q=0.9") == "nl"

    def test_en_wins_when_listed_before_nl(self) -> None:
        assert parse_lang("en-US,en;q=0.9,nl;q=0.8") == "en"

    def test_nl_wins_when_listed_before_en(self) -> None:
        assert parse_lang("nl-NL,nl;q=0.9,en;q=0.8") == "nl"


@pytest.mark.unit
class TestGetLabels:
    def test_returns_english_labels_for_en(self) -> None:
        labels = get_labels("en")
        assert labels["cover_title"] == "AI Act Compliance Report"
        assert labels["generated_at"] == "Generated: {}"
        assert labels["overall_score"] == "Overall Score: {}"

    def test_returns_dutch_labels_for_nl(self) -> None:
        labels = get_labels("nl")
        assert labels["cover_title"] == "AI Act Compliance Rapport"
        assert labels["generated_at"] == "Gemaakt op: {}"
        assert labels["overall_score"] == "Totaalscore: {}"

    def test_falls_back_to_dutch_for_unknown_lang(self) -> None:
        labels = get_labels("de")
        assert labels["cover_title"] == "AI Act Compliance Rapport"
        assert labels["generated_at"] == "Gemaakt op: {}"
