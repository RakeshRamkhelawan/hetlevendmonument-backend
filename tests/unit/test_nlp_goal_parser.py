"""Unit tests for NLPGoalParser and TemplateGoalParser."""

import pytest

from src.core.autonomy.nlp_goal_parser import NLPGoalParser, TemplateGoalParser


def test_nlp_goal_parser_can_parse() -> None:
    parser = NLPGoalParser()
    assert parser.can_parse("Please analyze current security posture for tenant")
    assert not parser.can_parse("")


def test_template_goal_parser_can_parse() -> None:
    parser = TemplateGoalParser()
    assert not parser.can_parse("")
