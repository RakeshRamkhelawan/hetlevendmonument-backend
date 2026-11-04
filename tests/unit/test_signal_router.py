"""Tests for SignalRouter topic resolution."""
import pytest
from src.core.events.signal_router import resolve_topics, resolve_channel, DEPARTMENT_TOPICS

def test_resolve_topics_hr() -> None:
    topics = resolve_topics("hr")
    assert "user.created" in topics
    assert "user.updated" in topics

def test_resolve_topics_with_custom() -> None:
    topics = resolve_topics("hr", ["custom.alert"])
    assert "custom.alert" in topics
    assert "user.created" in topics

def test_resolve_topics_unknown_dept() -> None:
    topics = resolve_topics("unknown_dept", ["fallback"])
    assert topics == ["fallback"]

def test_resolve_channel() -> None:
    ch = resolve_channel("user.created", 1)
    assert ch == "organism:1:user.created"

def test_department_topics_frozen() -> None:
    assert "hr" in DEPARTMENT_TOPICS
    with pytest.raises(TypeError):
        DEPARTMENT_TOPICS["new"] = ()
