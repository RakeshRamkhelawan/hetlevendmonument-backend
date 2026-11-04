import os

import pytest

from src.core.agents.cva_agent import CVAAgent
from src.core.ai.router import AIRouter, QueryComplexity


@pytest.mark.asyncio
async def test_cva_agent_has_ai_router():
    """Test that CVAAgent has AIRouter integration"""
    # Ensure required env vars
    os.environ.setdefault("SECRET_KEY", "test-secret-key")

    # Initialize agent
    agent = CVAAgent(agent_id="test_cva_routing", tenant_id=1)

    # Test that the agent has an AIRouter instance
    assert hasattr(agent, "ai_router")
    assert isinstance(agent.ai_router, AIRouter)


@pytest.mark.asyncio
async def test_ai_router_simple_query():
    """Test AIRouter routing for simple queries"""
    router = AIRouter()

    simple_query = "What is the capital of France?"
    complexity = router.analyze_complexity(simple_query)
    model = router.route_to_model(complexity)

    # Simple queries -> SIMPLE or MODERATE -> flash model
    assert complexity in [QueryComplexity.SIMPLE, QueryComplexity.MODERATE]
    assert "flash" in model.lower()


@pytest.mark.asyncio
async def test_ai_router_complex_query():
    """Test AIRouter routing for complex queries"""
    router = AIRouter()

    complex_query = "Analyze the geopolitical implications of the 19th century industrial revolution on modern economic structures, considering socio-political factors and their long-term impacts on global trade patterns."
    complexity = router.analyze_complexity(complex_query)
    model = router.route_to_model(complexity)

    # Complex queries -> COMPLEX -> pro model
    assert complexity == QueryComplexity.COMPLEX
    assert "pro" in model.lower()
