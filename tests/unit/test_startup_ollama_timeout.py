"""
Test: B-003a Ollama timeout reduction.
Verifies that OllamaProvider and RobustOllamaClient use 1s timeout.
"""

import pytest


@pytest.mark.unit
class TestOllamaTimeoutReduction:
    """B-003a: Ollama connection timeout must be 1s, not 5s."""

    def test_ollama_provider_timeout_is_1s(self) -> None:
        """OllamaProvider.initialize uses aiohttp.ClientTimeout(total=1)."""
        from pathlib import Path

        provider_path = Path("src/core/llm/ollama_provider.py")
        content = provider_path.read_text()
        assert "timeout=aiohttp.ClientTimeout(total=1)" in content
        assert "timeout=aiohttp.ClientTimeout(total=5)" not in content

    def test_ollama_client_timeout_is_1s(self) -> None:
        """RobustOllamaClient health checks use aiohttp.ClientTimeout(total=1)."""
        from pathlib import Path

        client_path = Path("src/core/llm/ollama_client.py")
        content = client_path.read_text()
        assert "timeout=aiohttp.ClientTimeout(total=1)" in content
        # The old 5s timeout must be gone from health checks
        health_lines = [
            line for line in content.splitlines() if "api/tags" in line or "timeout" in line
        ]
        for line in health_lines:
            if "ClientTimeout(total=5)" in line:
                pytest.fail(f"Found stale 5s timeout in ollama_client.py: {line}")

    def test_ollama_provider_skips_quickly_when_unreachable(self) -> None:
        """OllamaProvider.initialize returns False quickly when host is down."""
        import asyncio
        import time

        from src.core.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:59999")  # unreachable port
        start = time.perf_counter()
        result = asyncio.run(provider.initialize())
        elapsed = time.perf_counter() - start

        assert result is False
        assert elapsed < 3.0, f"Ollama init took {elapsed:.2f}s, expected < 3s"
