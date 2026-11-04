import pytest

from src.core.ai.router import AIRouter, QueryComplexity


@pytest.fixture
def router():
    return AIRouter()


def test_analyze_complexity_simple(router):
    """Test simple query detection"""
    query = "What is the capital of France?"
    assert router.analyze_complexity(query) == QueryComplexity.SIMPLE

    query = "Hello, how are you?"
    assert router.analyze_complexity(query) == QueryComplexity.SIMPLE


def test_analyze_complexity_moderate(router):
    """Test moderate query detection"""
    query = "Summarize the following text into 3 bullet points."
    assert router.analyze_complexity(query) == QueryComplexity.MODERATE

    query = "Explain the difference between TCP and UDP."
    assert router.analyze_complexity(query) == QueryComplexity.MODERATE


def test_analyze_complexity_complex(router):
    """Test complex query detection"""
    query = "Design a microservices architecture for a banking system."
    assert router.analyze_complexity(query) == QueryComplexity.COMPLEX

    query = "Debug this Python code: def foo(): return 1/0"
    assert router.analyze_complexity(query) == QueryComplexity.COMPLEX


def test_analyze_complexity_length(router):
    """Test length-based complexity"""
    # Moderate length
    moderate_query = "word " * 150
    assert router.analyze_complexity(moderate_query) == QueryComplexity.MODERATE

    # Complex length
    complex_query = "word " * 600
    assert router.analyze_complexity(complex_query) == QueryComplexity.COMPLEX


def test_route_to_model(router):
    """Test model routing mapping"""
    assert router.route_to_model(QueryComplexity.SIMPLE) == "gemini-1.5-flash"
    assert router.route_to_model(QueryComplexity.MODERATE) == "gemini-1.5-pro"
    assert router.route_to_model(QueryComplexity.COMPLEX) == "gemini-1.5-pro"
