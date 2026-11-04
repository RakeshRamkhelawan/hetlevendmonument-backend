"""
CVA (Conversational Virtual Assistant) Schemas
Request/response models for chat endpoints
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============================================
# REQUEST SCHEMAS
# ============================================


class ChatRequest(BaseModel):
    """Request for chat endpoint"""

    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: int | None = Field(None, description="Continue existing conversation")
    system_prompt: str | None = Field(None, description="Custom system prompt (admin only)")
    mode: str | None = Field(None, description="Chat mode: text / voice / autonomous")
    model: str | None = Field(None, description="LLM model override e.g. gemini-2.5-flash")

    @field_validator("message")
    @classmethod
    def validate_message_not_whitespace(cls, v: str) -> str:
        """Ensure message is not only whitespace"""
        if not v or not v.strip():
            raise ValueError("Message cannot be empty or whitespace only")
        return v.strip()


class CVAAction(BaseModel):
    """Structured action the CVA can request the frontend to perform."""

    type: Literal["navigate_to", "navigate_to_vibe", "suggestion"]
    label: str | None = None
    route: str | None = None
    workflow_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    @field_validator("route")
    @classmethod
    def validate_route(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("/"):
            raise ValueError("route must be a relative path starting with '/'")
        return v


class ChatResponse(BaseModel):
    """Response from chat endpoint"""

    response: str = Field(..., description="Assistant response")
    conversation_id: int = Field(..., description="Conversation ID for follow-up")
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Response metadata"
    )  # TODO(TYPE): replace Any with concrete type
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score (reserved -- not yet computed from model output)",
    )
    suggestions: list[str] = Field(default_factory=list, description="Follow-up suggestions")
    actions: list[CVAAction] = Field(
        default_factory=list, description="Structured actions for the frontend to execute"
    )
    llm_provider_used: str | None = Field(
        default=None, description="LLM provider that handled this request"
    )
    decision_id: str | None = Field(
        default=None,
        description="Council decision ID for Right-to-Explanation (EU AI Act Art. 13)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "response": "Wij zijn open van 9:00 tot 17:00 uur.",
                "conversation_id": 123,
                "metadata": {
                    "tokens_used": 45,
                    "model": "gpt-4",
                    "timestamp": "2026-02-06T10:30:00Z",
                },
                "confidence": None,
                "suggestions": [],
                "actions": [],
                "llm_provider_used": "gemini",
            }
        }
    )


# ============================================
# RESPONSE SCHEMAS (LIST/DETAIL)
# ============================================


class ConversationMessageResponse(BaseModel):
    """Single message in conversation history"""

    id: int
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime
    tokens_used: int | None = None
    model: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(BaseModel):
    """Conversation details with messages"""

    id: int
    title: str | None
    agent_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(..., description="Total messages in conversation")
    messages: list[ConversationMessageResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """List of conversations (summary only)"""

    id: int
    title: str | None
    agent_id: str
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExplainResponse(BaseModel):
    """EU AI Act Art. 13 Right-to-Explanation response for a council decision."""

    decision_id: str
    verdict: str
    explanation_for_user: str
    deliberation_ms: int
