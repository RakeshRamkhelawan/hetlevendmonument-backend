"""Learning rules and feedback endpoints (ADR-033 Laag 1, max 200 regels)."""

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.learning.dependencies import (
    AdaptationRuleService,
    get_db,
    store_async,
)
from src.core.middleware.tenant_context import require_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    """Feedback submission request."""

    feedback_type: Literal["correction", "confirmation", "usage"]
    message_id: str = Field(..., max_length=128, description="ID of message being rated")
    query: str = Field(..., max_length=4096, description="Original user query")
    target_supervisor: str | None = Field(
        None, max_length=128, description="Which supervisor handled it"
    )
    correct_routing: bool | None = Field(None, description="Was routing correct?")
    correct_supervisor: str | None = Field(
        None, max_length=128, description="Correct supervisor if misrouted"
    )
    rating: int | None = Field(None, ge=1, le=5, description="User rating 1-5")
    comments: str | None = Field(None, max_length=2000, description="User comments")


class RuleCreateRequest(BaseModel):
    """Create adaptation rule request."""

    rule_type: Literal["routing_correction", "prompt_enhancement"]
    trigger_keywords: list[str] = Field(..., description="Keywords that trigger this rule")
    target_supervisor: str | None = Field(
        None, max_length=128, description="Target supervisor for routing"
    )
    prompt_addition: str | None = Field(None, max_length=4096, description="Text to add to prompts")
    priority: int = Field(5, ge=1, le=10, description="Priority 1-10")
    confidence: float = Field(0.8, ge=0.0, le=1.0, description="Confidence threshold")


class RuleResponse(BaseModel):
    """Adaptation rule response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_type: str
    trigger_keywords: list[str]
    target_supervisor: str | None
    priority: int
    confidence: float
    active: bool
    success_rate: float
    created_at: datetime


def _build_rule_response(rule: object) -> RuleResponse:
    """Convert ORM rule to response model."""
    return RuleResponse(
        id=getattr(rule, "id", None) or "",
        rule_type=getattr(rule, "rule_type", None) or "",
        trigger_keywords=getattr(rule, "trigger_keywords", None) or [],
        target_supervisor=getattr(rule, "target_supervisor", None),
        priority=getattr(rule, "priority", None) or 0,
        confidence=getattr(rule, "confidence", None) or 0.0,
        active=bool(getattr(rule, "active", False)),
        success_rate=getattr(rule, "success_rate", None) or 0.0,
        created_at=getattr(rule, "created_at", None) or datetime.now(timezone.utc),
    )


@router.post("/feedback", status_code=202)
async def submit_feedback(
    request: FeedbackRequest,
) -> dict[str, str]:
    """Submit feedback for a message asynchronously via background worker queue."""
    tenant_id = require_tenant_id()
    try:
        payload = request.model_dump()
        payload["tenant_id"] = str(tenant_id)
        await store_async(payload)
        return {"status": "accepted", "message": "Feedback queued for processing"}
    except Exception as e:
        logger.error("submit_feedback failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process feedback")


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    active_only: bool = Query(True, description="Only return active rules"),
    supervisor: str | None = Query(None, description="Filter by supervisor"),
    limit: int = Query(50, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
) -> list[RuleResponse]:
    """List all adaptation rules."""
    tenant_id = str(require_tenant_id())
    try:
        service = AdaptationRuleService(db)
        rules = await service.get_active_rules(tenant_id=tenant_id, limit=limit)
        if active_only:
            rules = [r for r in rules if r.active]
        if supervisor:
            rules = [r for r in rules if r.target_supervisor == supervisor]
        return [_build_rule_response(r) for r in rules[offset:]]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_rules failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list rules")


@router.post("/rules", response_model=RuleResponse, status_code=201)
async def create_rule(
    request: RuleCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    """Create a new adaptation rule."""
    tenant_id = str(require_tenant_id())
    try:
        service = AdaptationRuleService(db)
        rule = await service.create_rule(
            tenant_id=tenant_id,
            rule_type=request.rule_type,
            trigger_keywords=request.trigger_keywords,
            target_supervisor=request.target_supervisor or "default",
            confidence=request.confidence,
            priority=request.priority,
        )
        return _build_rule_response(rule)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_rule failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create rule")


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deactivate (soft-delete) a rule."""
    tenant_id = str(require_tenant_id())
    try:
        service = AdaptationRuleService(db)
        success = await service.deactivate_rule(rule_id, tenant_id=tenant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Rule not found")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_rule failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete rule")
