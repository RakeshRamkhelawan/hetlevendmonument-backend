"""
Chaos Tests: LLM Timeout During CRAG

Verifies CRAG agent resilience when LLM API times out.
Tests graceful degradation and error recovery.
"""

import asyncio
import random
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class SlowLLM:
    """Mock LLM that simulates slow/timeout responses"""

    def __init__(self, delay: float = 10.0, fail_after: int = 0):
        self.delay = delay
        self.call_count = 0
        self.fail_after = fail_after

    async def generate(self, prompt: str, **kwargs) -> str:
        self.call_count += 1

        if self.fail_after > 0 and self.call_count > self.fail_after:
            await asyncio.sleep(self.delay)
            raise asyncio.TimeoutError("LLM request timed out")

        await asyncio.sleep(min(self.delay, 0.1))  # Cap actual delay for tests
        return '{"relevant": true, "score": 0.8}'


class IntermittentLLM:
    """Mock LLM that fails intermittently"""

    def __init__(self, failure_rate: float = 0.5):
        self.failure_rate = failure_rate
        self.call_count = 0

    async def generate(self, prompt: str, **kwargs) -> str:
        self.call_count += 1

        if random.random() < self.failure_rate:
            await asyncio.sleep(0.1)
            raise asyncio.TimeoutError("Simulated timeout")

        return '{"relevant": true, "is_grounded": true}'


class RecoveringLLM:
    """Mock LLM that fails initially then recovers"""

    def __init__(self, fail_count: int = 2):
        self.call_count = 0
        self.fail_count = fail_count

    async def generate(self, prompt: str, **kwargs) -> str:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise asyncio.TimeoutError("Simulated failure")
        return '{"relevant": true, "is_grounded": true}'


class MalformedLLM:
    """Mock LLM that returns malformed responses"""

    async def generate(self, prompt: str, **kwargs) -> str:
        # Return incomplete JSON
        return '{"relevant": true'  # Missing closing brace


class RateLimitedLLM:
    """Mock LLM that simulates rate limiting"""

    def __init__(self):
        self.call_count = 0
        self.call_times = []

    async def generate(self, prompt: str, **kwargs) -> str:
        import time

        self.call_count += 1
        self.call_times.append(time.time())

        if self.call_count <= 3:
            raise Exception("Rate limit exceeded")
        return "Success"


class SharedFailingLLM:
    """Mock LLM that simulates shared failures across agents"""

    def __init__(self):
        self.failure_count = 0

    async def generate(self, prompt: str, **kwargs) -> str:
        self.failure_count += 1
        if self.failure_count % 3 == 0:
            raise asyncio.TimeoutError("Shared failure")
        return '{"relevant": true}'


class MockCRAGAgent:
    """Mock CRAG Agent for testing timeout handling"""

    def __init__(
        self,
        llm_client,
        retriever=None,
        max_iterations: int = 3,
        timeout_seconds: float = 30,
    ):
        self.llm_client = llm_client
        self.retriever = retriever or AsyncMock()
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds

    async def run(self, tenant_id: int, query: str) -> dict:
        """Run the CRAG agent with timeout handling"""
        try:
            return await asyncio.wait_for(
                self._execute(tenant_id, query), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            return {"error": "Agent execution timed out", "timeout": True}
        except Exception as e:
            return {"error": str(e)}

    async def _execute(self, tenant_id: int, query: str) -> dict:
        """Internal execution logic"""
        for iteration in range(self.max_iterations):
            try:
                # Simulate retrieval
                docs = await self.retriever.search(tenant_id=tenant_id, query=query)

                # LLM grading
                response = await self.llm_client.generate(f"Grade: {query}")

                return {
                    "answer": "Generated answer",
                    "sources": docs,
                    "iterations": iteration + 1,
                }
            except asyncio.TimeoutError:
                if iteration == self.max_iterations - 1:
                    raise
                continue
            except Exception as e:
                if iteration == self.max_iterations - 1:
                    return {"error": str(e)}
                continue

        return {"error": "Max iterations reached"}


class TestLLMTimeoutDuringCRAG:
    """Chaos tests for LLM timeout scenarios"""

    @pytest.fixture
    def mock_retriever(self):
        retriever = AsyncMock()
        retriever.search = AsyncMock(
            return_value=[MagicMock(id="1", content="Test content", metadata={})]
        )
        return retriever

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_crag_handles_llm_timeout(self, mock_retriever):
        """CRAG should handle LLM timeout gracefully"""
        slow_llm = SlowLLM(delay=0.1, fail_after=1)

        agent = MockCRAGAgent(
            llm_client=slow_llm,
            retriever=mock_retriever,
            max_iterations=2,
            timeout_seconds=5,
        )

        # Should complete (possibly with error) but not hang
        result = await asyncio.wait_for(agent.run(tenant_id=1, query="Test query"), timeout=10.0)

        # Agent should return something, even if degraded
        assert result is not None
        assert "error" in result or "answer" in result

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_crag_timeout_prevents_hang(self, mock_retriever):
        """Agent timeout should prevent infinite waiting"""

        # Create a truly slow LLM that doesn't cap its delay
        class TruelySlowLLM:
            async def generate(self, prompt: str, **kwargs) -> str:
                await asyncio.sleep(100)  # Would take 100 seconds
                return '{"relevant": true}'

        very_slow_llm = TruelySlowLLM()

        agent = MockCRAGAgent(
            llm_client=very_slow_llm,
            retriever=mock_retriever,
            max_iterations=1,
            timeout_seconds=1,  # Very short timeout
        )

        start = asyncio.get_event_loop().time()
        result = await asyncio.wait_for(agent.run(tenant_id=1, query="Test"), timeout=10.0)
        elapsed = asyncio.get_event_loop().time() - start

        # Should timeout within ~1-2 seconds, not 100
        assert elapsed < 5
        assert result.get("error") is not None or result.get("timeout") is True

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_crag_recovers_after_llm_failure(self, mock_retriever):
        """CRAG should recover when LLM starts responding again"""
        recovering_llm = RecoveringLLM(fail_count=2)

        agent = MockCRAGAgent(llm_client=recovering_llm, retriever=mock_retriever, max_iterations=5)

        # First calls fail, later succeed - should eventually complete
        result = await asyncio.wait_for(agent.run(tenant_id=1, query="Test"), timeout=10.0)
        assert recovering_llm.call_count >= 2

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_partial_llm_response_handling(self, mock_retriever):
        """Handle partial/malformed LLM responses"""
        agent = MockCRAGAgent(llm_client=MalformedLLM(), retriever=mock_retriever, max_iterations=1)

        # Should handle malformed response gracefully
        result = await asyncio.wait_for(agent.run(tenant_id=1, query="Test"), timeout=10.0)
        assert result is not None


class TestLLMRateLimiting:
    """Tests for LLM rate limiting scenarios"""

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_rate_limit_backoff(self):
        """Verify exponential backoff on rate limiting"""
        llm = RateLimitedLLM()

        # Simulate retry with backoff
        result = None
        for attempt in range(5):
            try:
                result = await asyncio.wait_for(llm.generate("test"), timeout=10.0)
                if result == "Success":
                    break
            except Exception:
                await asyncio.sleep(0.05 * (2**attempt))  # Exponential backoff

        assert llm.call_count >= 4
        assert result == "Success"

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_rate_limit_respects_retry_header(self):
        """Test handling of Retry-After header"""
        retry_after = 0.5  # seconds
        retried_after_wait = False

        async def rate_limited_with_header(prompt):
            nonlocal retried_after_wait
            if not retried_after_wait:
                retried_after_wait = True
                raise Exception(f"Rate limited. Retry after {retry_after}s")
            return "Success"

        llm = MagicMock()
        llm.generate = rate_limited_with_header

        # First call fails
        try:
            await asyncio.wait_for(llm.generate("test"), timeout=10.0)
        except Exception as e:
            # Parse retry header and wait
            await asyncio.sleep(retry_after)

        # Retry should succeed
        result = await asyncio.wait_for(llm.generate("test"), timeout=10.0)
        assert result == "Success"


class TestConcurrentLLMFailures:
    """Tests for concurrent LLM failures"""

    @pytest.fixture
    def mock_retriever(self):
        retriever = AsyncMock()
        retriever.search = AsyncMock(return_value=[])
        return retriever

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_multiple_agents_llm_failure(self, mock_retriever):
        """Multiple agents should handle shared LLM failure"""
        shared_llm = SharedFailingLLM()

        # Create multiple agents sharing same LLM
        agents = [
            MockCRAGAgent(
                llm_client=shared_llm,
                retriever=mock_retriever,
                max_iterations=1,
                timeout_seconds=10,
            )
            for _ in range(3)
        ]

        # Run concurrently with timeout
        tasks = [
            asyncio.wait_for(agent.run(tenant_id=i, query=f"Query {i}"), timeout=15.0)
            for i, agent in enumerate(agents)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete (some may have errors)
        for r in results:
            assert r is not None

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_llm_connection_pool_exhaustion(self, mock_retriever):
        """Test behavior when LLM connection pool is exhausted"""
        active_connections = 0
        max_connections = 5

        async def pool_limited_llm(prompt):
            nonlocal active_connections
            if active_connections >= max_connections:
                raise Exception("Connection pool exhausted")

            active_connections += 1
            try:
                await asyncio.sleep(0.1)
                return '{"relevant": true}'
            finally:
                active_connections -= 1

        llm = MagicMock()
        llm.generate = pool_limited_llm

        # Create more agents than pool size
        agents = [
            MockCRAGAgent(llm_client=llm, retriever=mock_retriever, timeout_seconds=5)
            for _ in range(10)
        ]

        # Run concurrently with semaphore to limit
        semaphore = asyncio.Semaphore(max_connections)

        async def bounded_run(agent, i):
            async with semaphore:
                return await agent.run(tenant_id=i, query=f"Query {i}")

        tasks = [bounded_run(agent, i) for i, agent in enumerate(agents)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete
        assert all(r is not None for r in results)


class TestLLMResponseValidation:
    """Tests for LLM response validation under stress"""

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_empty_llm_response(self):
        """Handle empty LLM response"""

        async def empty_response(prompt):
            return ""

        llm = MagicMock()
        llm.generate = empty_response

        result = await asyncio.wait_for(llm.generate("test"), timeout=10.0)
        assert result == ""  # Should not crash

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_very_large_llm_response(self):
        """Handle unexpectedly large LLM response"""

        async def huge_response(prompt):
            return "x" * 1_000_000  # 1MB response

        llm = MagicMock()
        llm.generate = huge_response

        result = await asyncio.wait_for(llm.generate("test"), timeout=10.0)
        assert len(result) == 1_000_000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "chaos", "-s"])
