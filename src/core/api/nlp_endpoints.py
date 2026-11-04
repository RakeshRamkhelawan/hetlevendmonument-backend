# orphan:exempt -- legacy shim, pre-migration flat endpoint
#!/usr/bin/env python3
"""
Enhanced NLP API Endpoints for M-MDP
ASCII-compliant production-ready endpoints for enhanced NLP parser
"""

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from typing_extensions import TypedDict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.core.agents.nlp_parser import EnhancedNLPParser as _NLPParser, IntentType

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user, require_scopes, OAuth2Scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/nlp", tags=["NLP"])

# Lazy singleton -- ADR-033: module-level src.core.agents import verboden
_nlp_parser: "_NLPParser | None" = None


def _get_nlp_parser() -> "_NLPParser":
    global _nlp_parser
    if _nlp_parser is None:
        from src.core.agents.nlp_parser import EnhancedNLPParser  # lazy

        _nlp_parser = EnhancedNLPParser()
    return _nlp_parser


# ASCII-compliant response models
class ParseRequest(BaseModel):
    """Request model for text parsing"""

    text: str = Field(..., min_length=1, max_length=1000, description="Text to parse")
    include_confidence: bool = Field(True, description="Include confidence score")
    include_parameters: bool = Field(True, description="Include extracted parameters")


class ParseResponse(BaseModel):
    """ASCII-compliant parse response"""

    timestamp: str
    input_text: str
    intent: str
    confidence: float
    parameters: dict[str, str | int | None] | None
    suggestions: list[str]
    success: bool = True


class IntentsResponse(BaseModel):
    """Available intents response"""

    timestamp: str
    available_intents: list[dict[str, str | list[str] | bool]]
    total_count: int
    mmdp_specific_intents: list[str]


class ValidationRequest(BaseModel):
    """Request model for text validation"""

    text: str = Field(..., min_length=1, max_length=1000, description="Text to validate")


class BatchParseRequest(BaseModel):
    """Request model for batch text parsing"""

    texts: list[str] = Field(..., min_length=1, max_length=10, description="List of texts to parse")


class ValidationResponse(BaseModel):
    """Text validation response"""

    is_valid: bool
    validation_score: float
    issues: list[str]
    recommendations: list[str]


# TypedDicts for endpoint return types (concrete replacements for TODO(TYPE))
class NLPHealthResponse(TypedDict):
    status: str
    system: str
    version: str
    capabilities: list[str]
    timestamp: str
    parser_ready: bool


class ParseExamplesResponse(TypedDict):
    timestamp: str
    examples: dict[str, list[str]]
    usage_note: str


class BatchParseResult(TypedDict, total=False):
    index: int
    text: str
    intent: str
    confidence: float
    parameters: object
    success: bool
    error: str


class BatchParseResponse(TypedDict):
    timestamp: str
    total_texts: int
    successful_parses: int
    failed_parses: int
    average_confidence: float
    results: list[BatchParseResult]


class ParserStatisticsResponse(TypedDict):
    timestamp: str
    total_parses_today: int
    average_confidence: float
    intent_distribution: dict[str, int]
    language_distribution: dict[str, int]
    performance_metrics: dict[str, float]
    recent_trends: dict[str, str]


@router.get("/health", status_code=status.HTTP_200_OK)
async def nlp_system_health(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> NLPHealthResponse:
    """
    Get NLP system health status. Requires: Permission.READ
    """
    try:
        logger.info(f"User {current_user.id} requesting NLP health status")
        return {
            "status": "healthy",
            "system": "M-MDP Enhanced NLP Parser",
            "version": "3.0.0",
            "capabilities": [
                "Intent classification with confidence scoring",
                "Parameter extraction and validation",
                "M-MDP command recognition",
                "Multi-language support (English/Dutch)",
                "Context-aware parsing",
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parser_ready": True,
        }
    except Exception as e:
        logger.error("NLP health check failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/parse", response_model=ParseResponse, status_code=status.HTTP_200_OK)
async def parse_text(
    request: ParseRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> ParseResponse:
    """
    Parse text and extract intent with parameters. Requires: Permission.READ
    """
    try:
        logger.info(f"User {current_user.id} parsing text: {request.text[:50]}...")

        # Parse the text
        parse_result = _get_nlp_parser().parse(request.text)

        # Extract parameters if requested
        parameters = None
        if request.include_parameters and parse_result.parameters is not None:
            # Handle both dataclass and dict parameters safely
            if hasattr(parse_result.parameters, "__dataclass_fields__"):
                parameters = asdict(parse_result.parameters)
            elif isinstance(parse_result.parameters, dict):
                parameters = parse_result.parameters
            else:
                parameters = {"value": str(parse_result.parameters)}

        # Generate suggestions based on intent and confidence
        from src.core.agents.nlp_parser import IntentType  # lazy

        suggestions: list[str] = []
        if parse_result.confidence < 0.8:
            suggestions.append("Consider rephrasing for better recognition")
        if parse_result.intent == IntentType.UNKNOWN:
            suggestions.append("Try using more specific M-MDP commands")
            suggestions.append("Use keywords like 'learning', 'safety', or 'prediction'")

        return ParseResponse(
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_text=request.text,
            intent=parse_result.intent.value,
            confidence=parse_result.confidence if request.include_confidence else 1.0,
            parameters=parameters,  # pyright: ignore[reportArgumentType]
            suggestions=suggestions,
        )

    except Exception as e:
        logger.error("Text parsing failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/intents", response_model=IntentsResponse, status_code=status.HTTP_200_OK)
async def get_available_intents(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> IntentsResponse:
    """
    Get all available intent types and their descriptions. Requires: Permission.READ
    """
    try:
        logger.info(f"User {current_user.id} requesting available intents")
        from src.core.agents.nlp_parser import IntentType  # lazy

        # Get all intent types
        all_intents: list[dict[str, str | list[str] | bool]] = []
        mmdp_intents: list[str] = []
        for intent_type in IntentType:
            intent_info = {
                "name": intent_type.value,
                "description": _get_intent_description(intent_type),
                "examples": _get_intent_examples(intent_type),
                "is_mmdp_specific": _is_mmdp_intent(intent_type),
            }
            all_intents.append(intent_info)

            if intent_info["is_mmdp_specific"]:
                mmdp_intents.append(intent_type.value)

        return IntentsResponse(
            timestamp=datetime.now(timezone.utc).isoformat(),
            available_intents=all_intents,
            total_count=len(all_intents),
            mmdp_specific_intents=mmdp_intents,
        )

    except Exception as e:
        logger.error("Failed to get intents: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/validate", response_model=ValidationResponse, status_code=status.HTTP_200_OK)
async def validate_text(
    request: ValidationRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> ValidationResponse:
    """
    Validate text for NLP processing. Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} validating text")
        # Basic validation
        issues: list[str] = []
        recommendations: list[str] = []
        validation_score = 1.0

        text = request.text

        # Check text length
        if len(text) < 5:
            issues.append("Text too short for reliable parsing")
            validation_score -= 0.3
            recommendations.append("Provide more context in your request")

        if len(text) > 500:
            issues.append("Text very long - may affect parsing accuracy")
            validation_score -= 0.1
            recommendations.append("Consider breaking into shorter requests")

        # Check for ASCII compliance
        try:
            text.encode("ascii")
        except UnicodeEncodeError:
            issues.append("Non-ASCII characters detected")
            validation_score -= 0.2
            recommendations.append("Use ASCII-only characters for best results")

        # Check for M-MDP keywords
        mmdp_keywords = [
            "learning",
            "meta",
            "safety",
            "prediction",
            "training",
            "monitor",
        ]
        has_mmdp_keywords = any(keyword in text.lower() for keyword in mmdp_keywords)

        if not has_mmdp_keywords:
            recommendations.append(
                "Consider using M-MDP specific keywords for better intent recognition"
            )

        # Ensure minimum score
        validation_score = max(0.0, validation_score)

        return ValidationResponse(
            is_valid=validation_score >= 0.5,
            validation_score=validation_score,
            issues=issues,
            recommendations=recommendations,
        )

    except Exception as e:
        logger.error("Text validation failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/examples", status_code=status.HTTP_200_OK)
async def get_parse_examples(
    intent_type: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> ParseExamplesResponse:
    """
    Get example texts for different intent types. Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting parse examples")
        from src.core.agents.nlp_parser import IntentType  # lazy

        examples: dict[str, list[str]] = {}
        if intent_type:
            # Get examples for specific intent
            try:
                intent_enum = IntentType(intent_type)
                examples[intent_type] = _get_intent_examples(intent_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown intent type: {intent_type}",
                )
        else:
            # Get examples for all intents
            for intent in IntentType:
                examples[intent.value] = _get_intent_examples(intent)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "examples": examples,
            "usage_note": "Use these examples as templates for your requests",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get examples: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/batch-parse", status_code=status.HTTP_200_OK)
async def batch_parse_texts(
    request: BatchParseRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> BatchParseResponse:
    """
    Parse multiple texts in batch. Requires: OAuth2Scope.AGENTS_WRITE
    """
    try:
        logger.info(f"User {current_user.id} batch parsing {len(request.texts)} texts")
        results: list[BatchParseResult] = []
        for i, text in enumerate(request.texts):
            try:
                parse_result = _get_nlp_parser().parse(text)
                results.append(
                    {
                        "index": i,
                        "text": text,
                        "intent": parse_result.intent.value,
                        "confidence": parse_result.confidence,
                        "parameters": parse_result.parameters,
                        "success": True,
                    }
                )
            except Exception as e:
                logger.error("batch_parse_texts mislukt: %s: %s", type(e).__name__, e, exc_info=True)
                results.append({"index": i, "text": text, "error": "Er is een fout opgetreden.", "success": False})

        # Calculate summary statistics
        successful_parses = [r for r in results if r["success"]]  # pyright: ignore[reportTypedDictNotRequiredAccess]
        avg_confidence = (
            sum(r["confidence"] for r in successful_parses) / len(successful_parses)  # pyright: ignore[reportTypedDictNotRequiredAccess]
            if successful_parses
            else 0
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_texts": len(request.texts),
            "successful_parses": len(successful_parses),
            "failed_parses": len(request.texts) - len(successful_parses),
            "average_confidence": avg_confidence,
            "results": results,
        }

    except Exception as e:
        logger.error("Batch parsing failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/statistics", status_code=status.HTTP_200_OK)
async def get_parser_statistics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> ParserStatisticsResponse:
    """
    Get NLP parser usage statistics. Requires: OAuth2Scope.AGENTS_READ
    """
    try:
        logger.info(f"User {current_user.id} requesting parser statistics")
        # Mock statistics - replace with actual tracking
        stats: ParserStatisticsResponse = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_parses_today": 127,
            "average_confidence": 0.847,
            "intent_distribution": {
                "learning_management": 45,
                "safety_monitoring": 23,
                "prediction_request": 31,
                "system_status": 18,
                "unknown": 10,
            },
            "language_distribution": {"english": 89, "dutch": 38},
            "performance_metrics": {
                "average_parse_time_ms": 12.3,
                "high_confidence_rate": 0.784,
                "parameter_extraction_success_rate": 0.923,
            },
            "recent_trends": {
                "confidence_trend": "stable",
                "volume_trend": "increasing",
                "error_rate_trend": "decreasing",
            },
        }

        return stats

    except Exception as e:
        logger.error("Failed to get statistics: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# Helper functions
def _get_intent_description(intent_type: "IntentType") -> str:
    """Get description for intent type"""
    from src.core.agents.nlp_parser import IntentType  # lazy

    descriptions = {
        IntentType.GREETING: "General greetings and conversation starters",
        IntentType.CONVERSATION: "General conversation and information requests",
        IntentType.SYSTEM_STATUS: "System status and health inquiries",
        IntentType.LEARNING_MANAGEMENT: "M-MDP learning system management and control",
        IntentType.META_LEARNING: "Meta-learning and strategy management commands",
        IntentType.SAFETY_MONITORING: "Safety system monitoring and validation requests",
        IntentType.PREDICTION_REQUEST: "Predictive analytics and forecasting requests",
        IntentType.UNKNOWN: "Unrecognized or ambiguous requests",
    }
    return descriptions.get(intent_type, "No description available")


def _get_intent_examples(intent_type: "IntentType") -> list[str]:
    """Get example texts for intent type"""
    from src.core.agents.nlp_parser import IntentType  # lazy

    examples = {
        IntentType.GREETING: ["Hello", "Good morning", "Hi there"],
        IntentType.CONVERSATION: [
            "Tell me about the system",
            "What can you do?",
            "Explain the features",
        ],
        IntentType.SYSTEM_STATUS: [
            "Show system status",
            "How is the system running?",
            "Get health report",
        ],
        IntentType.LEARNING_MANAGEMENT: [
            "Start PPO learning",
            "Check learning progress",
            "Update learning parameters",
        ],
        IntentType.META_LEARNING: [
            "Get meta learning status",
            "Apply strategy transfer",
            "Show learning strategies",
        ],
        IntentType.SAFETY_MONITORING: [
            "Check safety violations",
            "Trigger safety validation",
            "Show safety status",
        ],
        IntentType.PREDICTION_REQUEST: [
            "Predict system performance",
            "Show 24h forecast",
            "Get bottleneck predictions",
        ],
        IntentType.UNKNOWN: ["Ambiguous request", "Unclear command"],
    }
    return examples.get(intent_type, [])


def _is_mmdp_intent(intent_type: "IntentType") -> bool:
    """Check if intent is M-MDP specific"""
    from src.core.agents.nlp_parser import IntentType  # lazy

    mmdp_intents = {
        IntentType.LEARNING_MANAGEMENT,
        IntentType.META_LEARNING,
        IntentType.SAFETY_MONITORING,
        IntentType.PREDICTION_REQUEST,
    }
    return intent_type in mmdp_intents
