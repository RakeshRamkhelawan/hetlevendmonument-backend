"""Tests for ToolRiskClassifier - YAML config loading and risk classification."""

import pytest
import yaml

from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel


class TestToolRiskLevelEnum:
    """Test ToolRiskLevel enum values."""

    def test_low_value(self):
        assert ToolRiskLevel.LOW.value == "low"

    def test_medium_value(self):
        assert ToolRiskLevel.MEDIUM.value == "medium"

    def test_high_value(self):
        assert ToolRiskLevel.HIGH.value == "high"


class TestToolRiskClassifierDefaultConfig:
    """Test classifier with default config file."""

    def test_classify_low_risk_tool(self):
        classifier = ToolRiskClassifier()
        result = classifier.classify("local__read_file")
        assert result == ToolRiskLevel.LOW

    def test_classify_medium_risk_tool(self):
        classifier = ToolRiskClassifier()
        result = classifier.classify("local__write_file")
        assert result == ToolRiskLevel.MEDIUM

    def test_classify_high_risk_tool(self):
        """Was `local__run_shell` tot die tool is verwijderd (ADR-036 OP-126).

        Let op waarom die verwijdering deze test ROOD maakte en niet stil groen liet: de naam
        viel niet terug op de zero-trust `default_risk_level: high` maar op de prefixregel
        `local__: medium`. Een `local__`-tool zonder eigen regel omzeilt dus de HITL-poort.
        `tests/architecture/test_every_executable_tool_has_a_risk_level.py` bewaakt dat sinds
        2026-08-11.
        """
        classifier = ToolRiskClassifier()
        result = classifier.classify("local__send_email")
        assert result == ToolRiskLevel.HIGH

    def test_classify_unknown_tool_returns_default(self):
        classifier = ToolRiskClassifier()
        result = classifier.classify("unknown_tool_xyz")
        assert result == ToolRiskLevel.HIGH  # default is high (zero-trust)

    def test_classify_serena_search(self):
        classifier = ToolRiskClassifier()
        result = classifier.classify("serena__search")
        assert result == ToolRiskLevel.LOW

    def test_classify_test_tools(self):
        classifier = ToolRiskClassifier()
        assert classifier.classify("test__echo") == ToolRiskLevel.LOW
        assert classifier.classify("test__fail") == ToolRiskLevel.LOW


class TestToolRiskClassifierCustomConfig:
    """Test classifier with custom config path."""

    def test_custom_config_path(self, tmp_path):
        config_file = tmp_path / "custom_risk.yml"
        config_file.write_text(
            "tool_risk_levels:\n"
            "  my_custom_tool: low\n"
            "  another_tool: medium\n"
            "default_risk_level: medium\n"
        )

        classifier = ToolRiskClassifier(config_path=str(config_file))
        assert classifier.classify("my_custom_tool") == ToolRiskLevel.LOW
        assert classifier.classify("another_tool") == ToolRiskLevel.MEDIUM
        assert classifier.classify("unknown") == ToolRiskLevel.MEDIUM

    def test_missing_config_file_uses_defaults(self, tmp_path):
        nonexistent = str(tmp_path / "nonexistent.yml")
        classifier = ToolRiskClassifier(config_path=nonexistent)
        # Falls back to default HIGH
        assert classifier.classify("anything") == ToolRiskLevel.HIGH

    def test_invalid_yaml_syntax_uses_defaults(self, tmp_path):
        config_file = tmp_path / "bad.yml"
        config_file.write_text("{{invalid: yaml: [}")

        classifier = ToolRiskClassifier(config_path=str(config_file))
        # Falls back to default HIGH
        assert classifier.classify("anything") == ToolRiskLevel.HIGH

    def test_empty_config_uses_defaults(self, tmp_path):
        config_file = tmp_path / "empty.yml"
        config_file.write_text("")

        classifier = ToolRiskClassifier(config_path=str(config_file))
        assert classifier.classify("anything") == ToolRiskLevel.HIGH

    def test_unknown_risk_level_skips_entry(self, tmp_path):
        config_file = tmp_path / "bad_risk.yml"
        config_file.write_text(
            "tool_risk_levels:\n"
            "  valid_tool: low\n"
            "  invalid_tool: EXTREME\n"
            "default_risk_level: high\n"
        )

        classifier = ToolRiskClassifier(config_path=str(config_file))
        assert classifier.classify("valid_tool") == ToolRiskLevel.LOW
        # invalid_tool gets skipped, falls back to default
        assert classifier.classify("invalid_tool") == ToolRiskLevel.HIGH

    def test_yaml_without_tool_risk_levels_key(self, tmp_path):
        """Config file has content but no tool_risk_levels key."""
        config_file = tmp_path / "no_levels.yml"
        config_file.write_text("some_other_key: value\n")

        classifier = ToolRiskClassifier(config_path=str(config_file))
        assert classifier.classify("anything") == ToolRiskLevel.HIGH

    def test_yaml_with_invalid_default_risk_level(self, tmp_path):
        """Config file with invalid default_risk_level value."""
        config_file = tmp_path / "bad_default.yml"
        config_file.write_text(
            "tool_risk_levels:\n" "  my_tool: low\n" "default_risk_level: EXTREME\n"
        )

        classifier = ToolRiskClassifier(config_path=str(config_file))
        assert classifier.classify("my_tool") == ToolRiskLevel.LOW
        # Unknown tool falls back to HIGH (invalid default replaced)
        assert classifier.classify("unknown") == ToolRiskLevel.HIGH

    def test_yaml_with_list_instead_of_dict(self, tmp_path):
        """Config file is valid YAML but not a dict."""
        config_file = tmp_path / "list.yml"
        config_file.write_text("- item1\n- item2\n")

        classifier = ToolRiskClassifier(config_path=str(config_file))
        assert classifier.classify("anything") == ToolRiskLevel.HIGH
