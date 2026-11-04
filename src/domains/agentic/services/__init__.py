"""
Agentic Services Module.

This module provides all core services for the domain-agnostic
agentic AI system.

Services:
- FeatureRegistry: Dynamic feature management
- SessionManager: Redis-backed session storage
- PromptComposer: Dynamic prompt composition
- FeatureRouter: 4-layer feature detection
- ChatService: Main orchestration service
"""

from typing import Any

from src.domains.agentic.services.chat_service import (
    AgentChatService,
    ChatRequest,
    ChatResponse,
    ToolCallResult,
    create_chat_service,
)
from src.domains.agentic.services.feature_registry import (
    DynamicFeatureRegistry,
    FeatureContext,
    get_feature_registry,
)
from src.domains.agentic.services.feature_router import (
    DetectionRequest,
    FeatureContextDetector,
    create_feature_detector,
)
from src.domains.agentic.services.prompt_composer import (
    ComposedPrompt,
    DomainAgnosticPromptComposer,
    get_prompt_composer,
)
from src.domains.agentic.services.session_manager import (
    AgenticSessionManager,
    ChatMessage,
    Session,
    create_session_manager,
)

__all__ = [
    # Feature Registry
    "DynamicFeatureRegistry",
    "FeatureContext",
    "get_feature_registry",
    # Session Manager
    "AgenticSessionManager",
    "Session",
    "ChatMessage",
    "create_session_manager",
    # Prompt Composer
    "DomainAgnosticPromptComposer",
    "ComposedPrompt",
    "get_prompt_composer",
    # Feature Router
    "FeatureContextDetector",
    "DetectionRequest",
    "create_feature_detector",
    # Chat Service
    "AgentChatService",
    "ChatRequest",
    "ChatResponse",
    "ToolCallResult",
    "create_chat_service",
]
