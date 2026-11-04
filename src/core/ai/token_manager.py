"""Token Management -- Counts and fits messages to LLM context windows."""

import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


class TokenCountMessage(TypedDict, total=False):
    """Message structure for token counting."""

    role: str
    content: str


class TokenManager:
    """Manages token counting and context window fitting.

    Uses langchain_core for token estimation; falls back to word-count heuristic
    if model is unknown.
    """

    # HIGH-1: Allowed models (whitelist for model parameter validation)
    ALLOWED_MODELS = frozenset(
        {
            "deepseek-chat",
            "deepseek-reasoner",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "ollama-default",
            "default",
        }
    )

    # HIGH-1: Maximum input length (1M chars ~= 250k tokens)
    MAX_TEXT_LENGTH = 1_000_000

    # Context window sizes (tokens)
    CONTEXT_WINDOWS: dict[str, int] = {
        "deepseek-chat": 128000,
        "deepseek-reasoner": 128000,
        "gemini-2.0-flash": 1000000,
        "gemini-1.5-pro": 2097152,
        "ollama-default": 4096,
        "default": 4096,
    }

    def __init__(self) -> None:
        """Initialize TokenManager."""
        pass

    def count_tokens(
        self,
        text: str,
        model: str = "default",
    ) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for
            model: Model identifier (used for model-specific counting if available)

        Returns:
            Estimated token count

        Raises:
            ValueError: If model is not in ALLOWED_MODELS or text exceeds MAX_TEXT_LENGTH
        """
        # HIGH-1: Validate model parameter
        if model not in self.ALLOWED_MODELS:
            raise ValueError(
                f"Unknown model: {model}. Allowed models: {sorted(self.ALLOWED_MODELS)}"
            )

        if not text:
            return 0

        # HIGH-1: Validate input length (fail-secure)
        if len(text) > self.MAX_TEXT_LENGTH:
            raise ValueError(
                f"Input text exceeds maximum length {self.MAX_TEXT_LENGTH} chars "
                f"(got {len(text)} chars)"
            )

        # Fallback: estimate tokens based on character length
        # Assume ~4 characters per token (more conservative than 5)
        estimated_tokens = max(1, len(text) // 4)
        return estimated_tokens

    def count_messages(
        self,
        messages: list[TokenCountMessage],
        model: str = "default",
    ) -> int:
        """
        Count tokens across a list of messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier

        Returns:
            Estimated total token count
        """
        if not messages:
            return 0

        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self.count_tokens(content, model)

        return total

    def fit_to_window(
        self,
        messages: list[TokenCountMessage],
        model: str = "default",
        reserve_output: int = 1000,
    ) -> tuple[list[TokenCountMessage], int]:
        """
        Trim messages to fit context window, preserving system message.

        Args:
            messages: List of messages (assumes first message is system)
            model: Model identifier for context window lookup
            reserve_output: Tokens to reserve for model output (default 1000)

        Returns:
            Tuple of (trimmed_messages, total_tokens)

        Raises:
            ValueError: If model is not in ALLOWED_MODELS
        """
        # HIGH-1: Validate model parameter (MEDIUM-4: model validation)
        if model not in self.ALLOWED_MODELS:
            raise ValueError(
                f"Unknown model: {model}. Allowed models: {sorted(self.ALLOWED_MODELS)}"
            )

        if not messages:
            return [], 0

        window = self.CONTEXT_WINDOWS.get(model, self.CONTEXT_WINDOWS["default"])
        max_input_tokens = window - reserve_output

        # Always preserve system message (first one)
        system_msg = messages[0] if messages else None
        system_tokens = self.count_tokens(system_msg.get("content", ""), model) if system_msg else 0

        if system_tokens > max_input_tokens:
            # System message alone exceeds window -- return just system
            return messages[:1], system_tokens

        # Fit remaining messages in reverse order (recent messages first)
        fitted = [system_msg] if system_msg else []
        other_msgs = messages[1:] if messages else []
        total_tokens = system_tokens

        # Build list in reverse order (newest to oldest), then reverse at end
        recent_msgs = []
        for msg in reversed(other_msgs):
            msg_tokens = self.count_tokens(msg.get("content", ""), model)
            if total_tokens + msg_tokens <= max_input_tokens:
                recent_msgs.append(msg)
                total_tokens += msg_tokens
            else:
                break

        # Reverse back to chronological order (system first, then oldest to newest)
        fitted.extend(reversed(recent_msgs))
        return fitted, total_tokens
