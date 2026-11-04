"""Tests for TokenManager — Token Counting & Context Window Management (TDD: RED phase)"""

import pytest
from src.core.ai.token_manager import TokenManager


class TestTokenManagerHappyPath:
    """Tests with normal, fitting input"""

    def test_count_tokens_simple_string(self):
        """Happy path: Simple string returns positive token count"""
        mgr = TokenManager()
        count = mgr.count_tokens("hello world", model="default")
        assert count > 0
        assert isinstance(count, int)

    def test_messages_fit_within_window(self):
        """Happy path: 50-token messages fit unchanged"""
        mgr = TokenManager()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "The answer is 4."},
        ]
        trimmed, used_tokens = mgr.fit_to_window(messages, model="default", reserve_output=500)
        assert len(trimmed) == len(messages)
        assert used_tokens > 0

    def test_system_message_always_preserved(self):
        """Happy path: System message always kept during trim"""
        mgr = TokenManager()
        messages = [
            {"role": "system", "content": "Critical instruction"},
            {"role": "user", "content": "x" * 5000},
        ]
        trimmed, _ = mgr.fit_to_window(messages, model="default", reserve_output=500)
        # System message should always be present
        assert any(m.get("role") == "system" for m in trimmed)

    def test_token_count_empty_string(self):
        """Happy path: Empty string returns 0"""
        mgr = TokenManager()
        count = mgr.count_tokens("", model="default")
        assert count == 0


class TestTokenManagerUnhappyPath:
    """Tests with large/exceeding input"""

    def test_messages_trimmed_when_exceeds_window(self):
        """Unhappy path: 100K token messages trimmed to fit 4096-token window"""
        mgr = TokenManager()
        # Create artificially large message list (simulate long conversation)
        messages = [
            {"role": "system", "content": "You are helpful."},
        ]
        for i in range(50):
            messages.append({"role": "user", "content": f"Question {i}: " + "x" * 500})
            messages.append({"role": "assistant", "content": f"Answer {i}: " + "y" * 500})

        trimmed, used_tokens = mgr.fit_to_window(
            messages, model="ollama-default", reserve_output=500
        )
        # Should be trimmed
        assert len(trimmed) < len(messages)
        # Should still fit in window
        assert used_tokens <= (4096 - 500)

    def test_recent_messages_priority_by_default(self):
        """Unhappy path: When trimming, keep recent messages, drop old ones"""
        mgr = TokenManager()
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Old question from 50 messages ago"},
            {"role": "user", "content": "Very recent question just now"},
        ]
        trimmed, _ = mgr.fit_to_window(messages, model="default")
        # Recent message should be kept
        assert any("recent" in str(m).lower() for m in trimmed)

    def test_unknown_model_raises_error(self):
        """Unhappy path: Unknown model raises ValueError (HIGH-1 security fix)"""
        mgr = TokenManager()
        # Unknown models should raise ValueError to prevent injection/abuse
        with pytest.raises(ValueError, match="Unknown model"):
            mgr.count_tokens("hello world", model="unknown-model-xyz")


class TestTokenManagerUserBehavioral:
    """User behavioral test: What the user experiences"""

    def test_agent_conversation_history_fits_context_window(self):
        """
        Behavioral test: User has 50-message conversation.
        After trim: Agent receives ingekorte history that fits in model window,
        with most recent messages intact.
        """
        mgr = TokenManager()

        # Simulate 50-message conversation
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        for i in range(25):
            messages.append(
                {
                    "role": "user",
                    "content": f"User question {i}: Tell me about topic {i}",
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": f"Assistant answer {i}: Here is information about topic {i}. "
                    + "x" * 100,
                }
            )

        # Trim to fit in 4K window (like Ollama)
        trimmed, used_tokens = mgr.fit_to_window(
            messages, model="ollama-default", reserve_output=500
        )

        # Should have trimmed but not removed everything
        assert len(trimmed) > 1
        # Recent messages should still be there
        assert "User question 24" in str(trimmed) or "question 23" in str(trimmed)
        # Should fit in window
        assert used_tokens <= (4096 - 500)
