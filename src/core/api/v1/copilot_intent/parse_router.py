"""
Copilot Intent Parser - POST /parse endpoint (ADR-033 Laag 1).

Migrated from src/core/api/copilot_endpoints.py (SP-API-006 Dag 1).
DEPRECATED endpoint: use POST /api/v1/copilot/turn instead.
"""

import re
import time
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api._deprecation import (
    DEFAULT_SUNSET_DATE,
    emit_deprecation_headers,
    log_deprecated_call,
)
from src.core.auth.api_deps import get_current_user
from src.core.api.v1.copilot_intent.dependencies import get_db
from src.core.models.rbac_models import User

SUCCESSOR_PARSE = "/api/v1/copilot/turn"

# Expose DEFAULT_SUNSET_DATE for import completeness
__all__ = ["router", "DEFAULT_SUNSET_DATE"]


# ============================================================================
# SCHEMA DEFINITIONS
# ============================================================================


class AgentTypeEnum(str, Enum):
    """Agent types available for missions"""

    WORKFLOW = "workflow"
    MEMORY = "memory"
    GOVERNANCE = "governance"
    SPECIALIST = "specialist"


class IntentRequest(BaseModel):
    """User intent query for parsing"""

    query: str = Field(..., min_length=5, max_length=500, description="Natural language user query")
    context: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None,
        description="Optional context (tenant_id, current_workflow_id, etc.)",
    )


class ParsedIntent(BaseModel):
    """Structured parsed intent from natural language query"""

    what_you_asked: str = Field(..., description="Plain language summary of what user asked")
    what_i_understood: str = Field(..., description="What we interpreted as the intent")
    recommended_agent: AgentTypeEnum = Field(
        ...,
        description="Which agent should handle this: workflow, memory, governance, specialist",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score (0-1) for parse accuracy"
    )
    required_scopes: list[str] = Field(
        default_factory=list,
        description="OAuth2 scopes required to execute",
    )
    intent_keywords: list[str] = Field(
        default_factory=list,
        description="Key terms extracted from query (for logging/analytics)",
    )
    error_message: str | None = Field(default=None, description="If parse failed, explain why")


class IntentParseResponse(BaseModel):
    """Response from intent parser endpoint"""

    success: bool = Field(..., description="Parse succeeded or failed")
    intent: ParsedIntent | None = Field(default=None, description="Parsed intent if successful")
    execution_time_ms: float = Field(..., description="Time to parse intent")


# ============================================================================
# INTENT PARSER SERVICE
# ============================================================================


class IntentParserService:
    """NLU service for parsing user intents into structured missions"""

    WORKFLOW_PATTERNS = [
        r"(?:create|build|make|generate|new)\s+(?:workflow|flow|pipeline|process)",
        r"workflow(?:\s+variant|s)?",
        r"(?:suggest|recommend|create)\s+(?:workflow|process)\s+variant",
        r"(?:add|create|design)\s+(?:node|step|stage)",
        r"workflow\s+(?:optimization|improvement|enhancement)",
    ]
    MEMORY_PATTERNS = [
        r"(?:search|find|look for|query)\s+(?:archive|document|memory|record)",
        r"(?:semantic|full-text)\s+search",
        r"(?:re-?index|reindex|batch)\s+(?:document|media|data)",
        r"(?:create|new)\s+collection",
        r"(?:analyze|explore)\s+(?:dataset|document|record)",
    ]
    GOVERNANCE_PATTERNS = [
        r"(?:detect|find|check|audit|review)\s+(?:bias|anomaly|risk|compliance|issue)",
        r"(?:audit|compliance|governance)\s+(?:check|report|dashboard)",
        r"(?:cost|optimization|efficiency)\s+(?:analysis|suggestion|recommendation)",
        r"data\s+(?:privacy|gdpr|protection)\s+(?:check|audit)",
        r"(?:approval|consent|governance)\s+(?:decision|log|trail)",
    ]
    SPECIALIST_PATTERNS = [
        r"(?:translate|sentiment|knowledge|diagnosis|specialized)",
        r"(?:advanced|special|custom)\s+(?:analysis|processing)",
    ]

    @staticmethod
    def _calculate_confidence(
        query: str, agent_type: AgentTypeEnum, keyword_matches: int, total_keywords: int
    ) -> float:
        """Calculate confidence score for intent parse (0-1)"""
        base_confidence = 0.5
        keyword_factor = (
            min(0.3, (keyword_matches / total_keywords) * 0.4) if total_keywords > 0 else 0.0
        )
        length_factor = min(0.1, len(query) / 500 * 0.15)
        certainty_factors = {
            AgentTypeEnum.WORKFLOW: 0.09,
            AgentTypeEnum.MEMORY: 0.08,
            AgentTypeEnum.GOVERNANCE: 0.10,
            AgentTypeEnum.SPECIALIST: 0.05,
        }
        certainty = certainty_factors.get(agent_type, 0.05)
        confidence = base_confidence + keyword_factor + length_factor + certainty
        return min(1.0, max(0.5, confidence))

    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        """Extract key terms from query"""
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "to",
            "for",
            "of",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "by",
            "with",
            "from",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "what",
            "when",
            "where",
            "why",
            "how",
            "do",
            "does",
        }
        words = re.findall(r"\b\w+\b", query.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return keywords[:10]

    @staticmethod
    def parse(query: str) -> ParsedIntent:
        """Parse natural language intent into structured mission parameters."""
        logger.info("Parsing intent: %s...", query[:50])

        if not query or len(query.strip()) < 5:
            return ParsedIntent(
                what_you_asked=query,
                what_i_understood="Query too short or empty",
                recommended_agent=AgentTypeEnum.SPECIALIST,
                confidence=0.0,
                error_message="Query must be at least 5 characters",
            )

        query_lower = query.lower()
        keywords = IntentParserService._extract_keywords(query)
        agent_scores = {
            AgentTypeEnum.WORKFLOW: sum(
                1 for p in IntentParserService.WORKFLOW_PATTERNS if re.search(p, query_lower)
            ),
            AgentTypeEnum.MEMORY: sum(
                1 for p in IntentParserService.MEMORY_PATTERNS if re.search(p, query_lower)
            ),
            AgentTypeEnum.GOVERNANCE: sum(
                1 for p in IntentParserService.GOVERNANCE_PATTERNS if re.search(p, query_lower)
            ),
            AgentTypeEnum.SPECIALIST: sum(
                1 for p in IntentParserService.SPECIALIST_PATTERNS if re.search(p, query_lower)
            ),
        }
        recommended_agent = max(agent_scores, key=lambda x: agent_scores[x])
        if agent_scores[recommended_agent] == 0:
            if any(kw in ["search", "find", "query"] for kw in keywords):
                recommended_agent = AgentTypeEnum.MEMORY
            elif any(kw in ["audit", "bias", "risk", "compliance"] for kw in keywords):
                recommended_agent = AgentTypeEnum.GOVERNANCE
            elif any(kw in ["create", "build", "workflow", "process"] for kw in keywords):
                recommended_agent = AgentTypeEnum.WORKFLOW

        keyword_matches = agent_scores[recommended_agent]
        confidence = IntentParserService._calculate_confidence(
            query,
            recommended_agent,
            keyword_matches,
            len(IntentParserService.WORKFLOW_PATTERNS)
            + len(IntentParserService.MEMORY_PATTERNS)
            + len(IntentParserService.GOVERNANCE_PATTERNS)
            + len(IntentParserService.SPECIALIST_PATTERNS),
        )
        scope_mapping = {
            AgentTypeEnum.WORKFLOW: ["agents:read", "workflows:manage"],
            AgentTypeEnum.MEMORY: ["agents:read", "memory:read"],
            AgentTypeEnum.GOVERNANCE: ["agents:read", "compliance:read"],
            AgentTypeEnum.SPECIALIST: ["agents:read"],
        }
        return ParsedIntent(
            what_you_asked=query,
            what_i_understood="User wants to use %s agent" % recommended_agent.value,
            recommended_agent=recommended_agent,
            confidence=round(confidence, 2),
            required_scopes=scope_mapping.get(recommended_agent, ["agents:read"]),
            intent_keywords=keywords,
            error_message=None,
        )


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(prefix="/api/v1/intents", tags=["Copilot - Intent Parser"])


@router.post(
    "/parse",
    response_model=IntentParseResponse,
    status_code=status.HTTP_200_OK,
    summary="[DEPRECATED] Parse natural language intent",
    description=(
        "**DEPRECATED**: Use `POST /api/v1/copilot/turn` instead. "
        "This endpoint will be removed on 2026-07-17."
    ),
    deprecated=True,
)
async def parse_intent(
    request: IntentRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntentParseResponse:
    """Parse user's natural language query into structured intent. DEPRECATED."""
    emit_deprecation_headers(response, successor=SUCCESSOR_PARSE)
    log_deprecated_call(
        "/api/v1/intents/parse",
        tenant_id=current_user.tenant_id if current_user else None,
        user_id=current_user.id if current_user else None,
        successor=SUCCESSOR_PARSE,
    )
    start_time = time.time()
    try:
        parsed = IntentParserService.parse(request.query)
        success = parsed.error_message is None and parsed.confidence >= 0.5
        execution_time = (time.time() - start_time) * 1000

        if current_user:
            logger.info(
                "Intent parsed%s",
                " successfully" if success else " with low confidence",
                extra={
                    "user_id": current_user.id,
                    "recommended_agent": (
                        parsed.recommended_agent.value if parsed.recommended_agent else "unknown"
                    ),
                    "confidence": parsed.confidence,
                    "execution_time_ms": execution_time,
                },
            )

        return IntentParseResponse(
            success=success, intent=parsed, execution_time_ms=round(execution_time, 1)
        )
    except Exception as e:
        logger.error(
            "Intent parse error: %s: %s",
            type(e).__name__,
            e,
            extra={"user_id": current_user.id if current_user else None},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse intent",
        ) from e
