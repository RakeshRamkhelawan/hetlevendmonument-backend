# tests/core/agents/test_proactive_suggestions.py
from src.core.agents.proactive_suggestions import get_suggestions


def test_returns_empty_when_no_apps():
    assert get_suggestions([]) == []


def test_returns_match_when_both_apps_present():
    results = get_suggestions(["asana", "teams"])
    assert len(results) == 1
    assert results[0]["label"] == "Teams-bericht bij nieuwe Asana-taak"
    assert "prompt" in results[0]


def test_returns_empty_when_only_one_app_matches():
    results = get_suggestions(["asana"])
    assert results == []


def test_max_3_suggestions_returned():
    # Connect enough apps to match > 3 pairs
    results = get_suggestions(["asana", "teams", "outlook", "gmail", "slack", "github"])
    assert len(results) <= 3


def test_case_insensitive_matching():
    results = get_suggestions(["Asana", "Teams"])
    assert len(results) == 1
