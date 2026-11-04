"""REST API endpoints for NLP-based scheduling.

Provides endpoints for natural language scheduling requests.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.config import settings
from src.core.database.database import get_db
from src.core.scheduling.nlp import ContextManager, NaturalLanguageParser
from src.core.scheduling.nlp.fuzzy import FuzzyMatcher, ParticipantResolver
from src.core.scheduling.schemas import SchedulingRequest
from src.core.security.security_manager import ThreatLevel
from src.core.governance.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/scheduling/nlp",
    tags=["Scheduling NLP"],
)

# Global instances (could be moved to dependency injection)
_context_manager = ContextManager(
    max_context_age_minutes=settings.NLP_CONTEXT_MAX_AGE_MINUTES,
    use_redis=settings.NLP_CONTEXT_ENABLE_REDIS,
    redis_url=settings.REDIS_URL if settings.NLP_CONTEXT_ENABLE_REDIS else None,
)
_parser: NaturalLanguageParser | None = None
_fuzzy_matcher = FuzzyMatcher(
    score_cutoff=settings.NLP_FUZZY_SCORE_CUTOFF,
    cache_ttl_seconds=settings.NLP_FUZZY_CACHE_TTL_SECONDS,
)


def get_parser() -> NaturalLanguageParser:
    """Get or create the NLP parser singleton."""
    global _parser
    if _parser is None:
        _parser = NaturalLanguageParser(context_manager=_context_manager)
    return _parser


def get_participant_resolver() -> ParticipantResolver:
    """Get the participant resolver."""
    return ParticipantResolver(
        fuzzy_matcher=_fuzzy_matcher,
        cache_ttl_seconds=settings.NLP_FUZZY_CACHE_TTL_SECONDS,
    )


def generate_secure_session_id(user_id: str, text: str) -> str:
    """Generate a cryptographically secure session ID.

    Args:
        user_id: User identifier
        text: Input text (used for uniqueness)

    Returns:
        Secure session ID string
    """
    # Generate cryptographically secure random component
    random_component = secrets.token_hex(settings.NLP_SESSION_ID_ENTROPY_BYTES)
    # Hash the user_id and text for deterministic uniqueness
    content_hash = hashlib.sha256(f"{user_id}:{text}".encode()).hexdigest()[:16]
    return f"{user_id}_{content_hash}_{random_component}"


def validate_text_length(text: str) -> None:
    """Validate text length for NLP input.

    Args:
        text: Input text to validate

    Raises:
        HTTPException: If text exceeds maximum length
    """
    if len(text) > settings.NLP_MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Text exceeds maximum length of "
                f"{settings.NLP_MAX_TEXT_LENGTH} characters "
                f"(received {len(text)})"
            ),
        )


def validate_candidates(candidates: list[dict[str, str]]) -> None:
    """Validate candidate list size.

    Args:
        candidates: List of candidate users

    Raises:
        HTTPException: If list exceeds maximum size
    """
    if len(candidates) > settings.NLP_MAX_CANDIDATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Too many candidates: maximum is {settings.NLP_MAX_CANDIDATES}, "
                f"received {len(candidates)}"
            ),
        )


# Request/Response schemas
class NaturalLanguageRequest:
    """Request to parse natural language."""

    text: str
    session_id: str | None = None


class NaturalLanguageResponse:
    """Response with parsed scheduling request."""

    success: bool
    intent: str
    confidence: float
    parsed_request: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    requires_clarification: bool = False
    clarification_question: str | None = None
    follow_up_suggestions: list[str] = []
    missing_info: list[str] = []


class ParticipantMatchRequest:
    """Request to match participant names."""

    names: list[str]


class ParticipantMatchResponse:
    """Response with matched participants."""

    matched: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    unmatched: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type


class SuggestCorrectionsRequest:
    """Request for name correction suggestions."""

    name: str
    candidates: list[dict[str, str]]


# -- Custom Exceptions -------------------------------------------------


class NLPParseError(Exception):
    """Exception for NLP parsing errors."""

    def __init__(self, message: str, error_code: str = "NLP_PARSE_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class EntityExtractionError(NLPParseError):
    """Exception for entity extraction errors."""

    def __init__(self, message: str):
        super().__init__(message, error_code="ENTITY_EXTRACTION_ERROR")


class IntentClassificationError(NLPParseError):
    """Exception for intent classification errors."""

    def __init__(self, message: str):
        super().__init__(message, error_code="INTENT_CLASSIFICATION_ERROR")


# -- Rate Limiting Decorator -------------------------------------------


class SimpleRateLimiter:
    """Simple in-memory rate limiter for NLP endpoints."""

    def __init__(self) -> None:
        self._requests: dict[str, list[datetime]] = {}
        self._window_seconds = 60  # 1 minute window

    def is_allowed(self, key: str, limit: int) -> bool:
        """Check if request is within rate limit.

        Args:
            key: Rate limit key (e.g., user_id + endpoint)
            limit: Maximum requests per window

        Returns:
            True if allowed, False otherwise
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self._window_seconds)

        # Get or create request list
        requests = self._requests.get(key, [])

        # Remove old requests outside window
        requests = [r for r in requests if r > window_start]

        # Check if under limit
        if len(requests) >= limit:
            self._requests[key] = requests
            return False

        # Add current request
        requests.append(now)
        self._requests[key] = requests
        return True

    def get_wait_time(self, key: str) -> int:
        """Get seconds until next request is allowed.

        Args:
            key: Rate limit key

        Returns:
            Seconds to wait
        """
        now = datetime.now(timezone.utc)
        requests = self._requests.get(key, [])
        if not requests:
            return 0

        window_start = now - timedelta(seconds=self._window_seconds)
        oldest_in_window = min(requests)
        wait_seconds = int((oldest_in_window - window_start).total_seconds())
        return max(0, wait_seconds)


# Global rate limiter instance
_rate_limiter = SimpleRateLimiter()


def parse_rate_limit(limit_str: str) -> int:
    """Parse rate limit string (e.g., '30/minute' -> 30).

    Args:
        limit_str: Rate limit string

    Returns:
        Number of requests allowed
    """
    return int(limit_str.split("/")[0])


def check_rate_limit(request: Request, limit: str) -> None:
    """Check rate limit for request.

    Args:
        request: FastAPI request
        limit: Rate limit string (e.g., '30/minute')

    Raises:
        HTTPException: If rate limit exceeded
    """
    # Get client identifier (IP or user)
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path}"

    limit_count = parse_rate_limit(limit)

    if not _rate_limiter.is_allowed(key, limit_count):
        wait_time = _rate_limiter.get_wait_time(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(f"Rate limit exceeded. Please wait {wait_time} seconds before retrying."),
            headers={"Retry-After": str(wait_time)},
        )


# -- Endpoints ---------------------------------------------------------


@router.post(
    "/parse",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Parse natural language scheduling request",
)
async def parse_natural_language(
    request: Request,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    parser: NaturalLanguageParser = Depends(get_parser),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Parse natural language into a structured scheduling request.

    Example:
        {
            "text": "Schedule a meeting with John tomorrow at 3pm",
            "session_id": "optional-session-id"
        }
    """
    # Rate limiting
    check_rate_limit(request, settings.NLP_PARSE_RATE_LIMIT)

    # Validate input
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text is required",
        )

    # Validate text length
    validate_text_length(text)

    # Generate secure session ID if not provided
    session_id = data.get("session_id") or generate_secure_session_id(str(current_user.id), text)

    try:
        result = await parser.parse(
            text=text,
            session_id=session_id,
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
        )

        response = {
            "success": result.success,
            "session_id": session_id,
            "intent": result.request.intent.intent_type.name,
            "confidence": result.request.intent.confidence,
            "is_complete": result.request.is_complete,
            "requires_clarification": result.requires_clarification,
        }

        if result.request.title:
            response["suggested_title"] = result.request.title

        if result.request.start_time:
            response["suggested_start"] = result.request.start_time.isoformat()

        if result.request.end_time:
            response["suggested_end"] = result.request.end_time.isoformat()

        if result.request.participants:
            response["extracted_participants"] = result.request.participants

        if result.request.location:
            response["extracted_location"] = result.request.location

        if result.request.priority != 3:
            response["suggested_priority"] = result.request.priority

        if result.requires_clarification:
            response["clarification_question"] = result.clarification_question
            response["follow_up_suggestions"] = result.follow_up_suggestions

        if result.request.missing_info:
            response["missing_info"] = result.request.missing_info

        if not result.success and result.error_message:
            response["error"] = result.error_message

        return response

    except NLPParseError as e:
        # Expected parsing errors - return user-friendly message
        logger.warning(f"NLP parse error: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": e.message, "code": e.error_code},
        )
    except Exception as e:
        # Unexpected errors - log full details but return generic message
        logger.exception(f"Unexpected error parsing NLP request: {text[:100]}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing your request.",
        )


@router.post(
    "/execute",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Parse and execute natural language scheduling request",
)
async def execute_natural_language(
    request: Request,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    parser: NaturalLanguageParser = Depends(get_parser),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Parse natural language and execute the scheduling request if complete.

    This endpoint parses the text and, if all required information is present,
    creates the calendar event.
    """
    # Rate limiting
    check_rate_limit(request, settings.NLP_EXECUTE_RATE_LIMIT)

    # Validate input
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text is required",
        )

    # Validate text length
    validate_text_length(text)

    # Generate secure session ID if not provided
    session_id = data.get("session_id") or generate_secure_session_id(str(current_user.id), text)

    try:
        # Parse the request
        result = await parser.parse(
            text=text,
            session_id=session_id,
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
        )
    except NLPParseError as e:
        logger.warning(f"NLP parse error in execute: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": e.message, "code": e.error_code},
        )
    except Exception as e:
        logger.exception(f"Unexpected error in execute: {text[:100]}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing your request.",
        )

    # If clarification needed, return that
    if result.requires_clarification:
        return {
            "success": True,
            "executed": False,
            "requires_clarification": True,
            "clarification_question": result.clarification_question,
            "session_id": session_id,
        }

    # If not complete, return what's missing
    if not result.request.is_complete:
        return {
            "success": True,
            "executed": False,
            "is_complete": False,
            "missing_info": result.request.missing_info,
            "session_id": session_id,
        }

    # Execute the scheduling request
    try:
        from src.core.scheduling.services.scheduling_service import SchedulingService

        scheduling_service = SchedulingService(db)

        # Build scheduling request
        scheduling_req = SchedulingRequest(
            title=result.request.title or "Meeting",
            description=result.request.description,
            duration_minutes=(
                int(result.request.duration.total_seconds() / 60) if result.request.duration else 30
            ),
            participants=result.request.participants,
            earliest_start=result.request.start_time or datetime.now(timezone.utc),
            latest_end=result.request.end_time
            or (
                result.request.start_time + timedelta(hours=1)
                if result.request.start_time
                else datetime.now(timezone.utc) + timedelta(hours=1)
            ),
            location=result.request.location,
            priority=result.request.priority,
        )

        # Execute scheduling
        schedule_result = await scheduling_service.schedule_meeting(
            request=scheduling_req,
            organizer_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
        )

        # Log the action
        await AuditService.log_event(
            db=db,
            event_type="NLP_SCHEDULING_EXECUTED",
            severity=ThreatLevel.LOW,
            source_ip="internal",
            endpoint="/api/v1/scheduling/nlp/execute",
            description=f"Executed NLP scheduling: {text[:50]}...",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="CREATE",
            resource=f"event:{schedule_result.event_id}" if schedule_result.success else None,
            metadata={
                "original_text": text,
                "intent": result.request.intent.intent_type.name,
                "success": schedule_result.success,
            },
        )

        await db.commit()

        return {
            "success": schedule_result.success,
            "executed": True,
            "event_id": schedule_result.event_id,
            "selected_option": schedule_result.selected_option,
            "alternatives": schedule_result.alternatives[:3],
            "message": schedule_result.message,
            "session_id": session_id,
        }

    except Exception as e:
        logger.exception(f"Error executing NLP schedule: {text[:100]}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute scheduling request.",
        )


@router.post(
    "/match-participants",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Match participant names to users using fuzzy matching",
)
async def match_participants(
    request: Request,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Match extracted participant names to actual users.

    Example:
        {
            "names": ["John", "jane.doe@example.com"],
            "candidates": [
                {"id": "1", "name": "John Smith", "email": "john@example.com"},
                {"id": "2", "name": "Jane Doe", "email": "jane.doe@example.com"}
            ]
        }
    """
    # Rate limiting
    check_rate_limit(request, settings.NLP_MATCH_RATE_LIMIT)

    names = data.get("names", [])
    candidates = data.get("candidates", [])

    if not names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Names list is required",
        )

    # Validate candidate count
    validate_candidates(candidates)

    # Validate names count
    if len(names) > settings.NLP_MAX_NAMES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Too many names: maximum is {settings.NLP_MAX_NAMES_PER_REQUEST}, "
                f"received {len(names)}"
            ),
        )

    resolver = get_participant_resolver()
    resolved, unresolved = resolver.resolve_multiple(names, candidates)

    return {
        "matched": resolved,
        "unmatched": unresolved,
        "match_count": len(resolved),
        "unmatched_count": len(unresolved),
    }


@router.post(
    "/suggest-corrections",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get name correction suggestions",
)
async def suggest_corrections(
    request: Request,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Suggest corrections for a potentially misspelled name.

    Example:
        {
            "name": "Jon Smth",
            "candidates": [
                {"id": "1", "name": "John Smith", "email": "john@example.com"},
                {"id": "2", "name": "Jane Smith", "email": "jane@example.com"}
            ]
        }
    """
    # Rate limiting
    check_rate_limit(request, settings.NLP_SUGGEST_RATE_LIMIT)

    name = data.get("name", "").strip()
    candidates = data.get("candidates", [])

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name is required",
        )

    # Validate candidate count
    validate_candidates(candidates)

    suggestions = _fuzzy_matcher.suggest_corrections(
        name, candidates, limit=settings.NLP_FUZZY_MAX_SUGGESTIONS
    )

    return {
        "name": name,
        "suggestions": suggestions,
        "has_suggestions": len(suggestions) > 0,
    }


@router.post(
    "/context/{session_id}/reset",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Reset conversation context",
)
async def reset_context(
    session_id: str,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Reset the conversation context for a session."""
    parser = get_parser()
    success = await parser.reset_context(session_id)

    return {
        "success": success,
        "session_id": session_id,
        "message": "Context reset" if success else "Context not found",
    }


@router.get(
    "/context/{session_id}",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get conversation context",
)
async def get_context(
    session_id: str,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get the current conversation context for a session."""
    parser = get_parser()
    context = await parser.get_context(session_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context not found or expired",
        )

    return {
        "session_id": session_id,
        "current_intent": context.current_intent,
        "extracted_entities": {k.name: str(v) for k, v in context.extracted_entities.items()},
        "pending_questions": context.pending_questions,
        "clarification_attempts": context.clarification_attempts,
        "message_count": len(context.messages),
        "is_expired": context.is_expired(),
    }


@router.get(
    "/examples",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get example natural language queries",
)
async def get_examples() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get example natural language queries that the system can parse."""
    return {
        "examples": [
            {
                "text": "Schedule a meeting with John tomorrow at 3pm",
                "description": "Basic scheduling with participant, date, and time",
            },
            {
                "text": "Book a 30-minute standup with the team every Monday",
                "description": "Recurring meeting with duration and meeting type",
            },
            {
                "text": "Reschedule my meeting with Jane to next Tuesday",
                "description": "Rescheduling an existing meeting",
            },
            {
                "text": "Cancel the team meeting on Friday",
                "description": "Canceling a meeting",
            },
            {
                "text": "When is John available next week?",
                "description": "Querying availability",
            },
            {
                "text": "Show my meetings for today",
                "description": "Listing events",
            },
            {
                "text": "Schedule a high priority interview with candidates in Conference Room A",  # noqa: E501
                "description": "Meeting with priority and location",
            },
            {
                "text": "Find time for a 1-hour planning session with the dev team",
                "description": "Finding available time slots",
            },
        ],
        "tips": [
            "Be specific about dates and times",
            "Mention participant names clearly",
            "Include meeting type words like 'standup', 'interview', 'review'",
            "Specify duration explicitly (e.g., '30 minutes', '1 hour')",
            "Mention location with 'in' or 'at'",
        ],
    }
