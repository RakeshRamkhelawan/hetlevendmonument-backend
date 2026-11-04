# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/copilot_intent/ (SP-API-006)
"""
Copilot NLU Intent Parser Endpoints -- Legacy re-export shim.

DEPRECATED: This module is superseded by src/core/api/v1/copilot_intent/.
Kept for backwards-compatibility with any direct imports during transition.
"""

from src.core.api.v1.copilot_intent.parse_router import (  # noqa: F401
    AgentTypeEnum,
    IntentParseResponse,
    IntentParserService,
    IntentRequest,
    ParsedIntent,
    router,
)

__all__ = [
    "router",
    "AgentTypeEnum",
    "IntentParseResponse",
    "IntentParserService",
    "IntentRequest",
    "ParsedIntent",
]
