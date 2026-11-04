"""TDD tests for LLMClient._sanitize_messages() + generate_response() DLP -- SP-DLP-001 Dag 2."""

import pytest

from src.core.llm.llm_client import LLMMessage, LLMResponse, MockLLMClient


def _client() -> MockLLMClient:
    return MockLLMClient()


def test_sanitize_messages_masks_email_in_user_role():
    client = _client()
    messages = [LLMMessage(role="user", content="Stuur naar jan@example.com graag")]
    sanitized, token_map = client._sanitize_messages(messages)
    assert "jan@example.com" not in sanitized[0].content
    assert len(token_map) == 1


def test_sanitize_messages_preserves_system_role_unchanged():
    client = _client()
    messages = [LLMMessage(role="system", content="Systeem instelling met jan@example.com")]
    sanitized, token_map = client._sanitize_messages(messages)
    assert sanitized[0].content == "Systeem instelling met jan@example.com"
    assert token_map == {}


def test_sanitize_messages_preserves_assistant_role_unchanged():
    client = _client()
    messages = [LLMMessage(role="assistant", content="jan@example.com was gevonden")]
    sanitized, token_map = client._sanitize_messages(messages)
    assert sanitized[0].content == "jan@example.com was gevonden"
    assert token_map == {}


def test_sanitize_messages_no_pii_returns_unchanged():
    client = _client()
    messages = [LLMMessage(role="user", content="Hoe laat is het?")]
    sanitized, token_map = client._sanitize_messages(messages)
    assert sanitized[0].content == "Hoe laat is het?"
    assert token_map == {}


def test_sanitize_messages_mixed_roles_only_user_sanitized():
    client = _client()
    messages = [
        LLMMessage(role="system", content="Je bent een assistent voor jan@example.com"),
        LLMMessage(role="user", content="Mijn email is jan@example.com"),
        LLMMessage(role="assistant", content="Begrepen, jan@example.com"),
    ]
    sanitized, token_map = client._sanitize_messages(messages)
    assert sanitized[0].content == "Je bent een assistent voor jan@example.com"
    assert "jan@example.com" not in sanitized[1].content
    assert sanitized[2].content == "Begrepen, jan@example.com"
    assert len(token_map) == 1


class _FailingTextClient(MockLLMClient):
    """Echos de (gemaskeerde) prompt terug in error_message -- voor H-1 test."""

    async def text_completion(self, prompt: str, **kwargs: object) -> LLMResponse:
        return LLMResponse(
            content=prompt,
            error_message=f"Provider failed: {prompt}",
            model="mock",
            provider="mock",
            success=False,
        )


def test_sanitize_messages_no_token_collision_multi_user():
    """R2: twee user-berichten met PII mogen niet hetzelfde placeholder krijgen."""
    client = _client()
    msgs = [
        LLMMessage(role="user", content="jan@example.com"),
        LLMMessage(role="user", content="piet@example.com"),
    ]
    sanitized, token_map = client._sanitize_messages(msgs)
    assert len(token_map) == 2, f"verwacht 2 tokens, maar: {token_map}"
    assert sanitized[0].content != sanitized[1].content, "beide berichten hetzelfde placeholder"


@pytest.mark.asyncio
async def test_generate_response_text_path_detokenizes_error_on_failure():
    """H-1: placeholder mag niet in error_message lekken als success=False."""
    client = _FailingTextClient()
    result = await client.generate_response("jan@example.com")
    assert result["success"] is False
    error_str = result.get("error", "")
    assert "[TOKEN_PII_" not in error_str, f"placeholder lekt: {error_str!r}"
