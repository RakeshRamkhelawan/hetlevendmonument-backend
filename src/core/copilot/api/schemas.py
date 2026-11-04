from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class OfficerVerdictResponse(BaseModel):
    officer_name: str
    officer_version: str
    verdict: str
    confidence: float
    reason_code: str
    reason_text: str


class DecisionExplanationResponse(BaseModel):
    decision_id: UUID
    timestamp: datetime
    verdict: str
    action_type: str
    explanation_for_user: str
    reasoning_summary: str
    officer_verdicts: list[OfficerVerdictResponse]
    model_id: str
    model_version: str
    data_classification: str
    can_contest: bool
    contest_url: str | None = None


class ContestRequest(BaseModel):
    reason_category: Literal[
        "factual_error",
        "missing_context",
        "bias_concern",
        "privacy_concern",
        "other",
    ]
    reason_text: str = Field(..., min_length=10, max_length=4000)


class ContestResponse(BaseModel):
    contest_id: UUID
    status: str
    submitted_at: datetime
    expected_review_within_hours: int
    #: Of de melding aan de beheerders is verstuurd. Het bezwaar is in beide gevallen bewaard.
    admin_notification: Literal["verzonden", "mislukt"] = "verzonden"
    message: str | None = None


class ContestResolveRequest(BaseModel):
    status: Literal["upheld", "overturned"]
    resolution_text: str = Field(..., min_length=1, max_length=4000)


class ChainVerifyResponse(BaseModel):
    chain_valid: bool
    decisions_checked: int
    broken_links: list[UUID]
    checked_at: datetime
    tenant_id: int


class AuditReportSummary(BaseModel):
    total_decisions: int
    by_verdict: dict[str, int]
    by_action_type: dict[str, int]
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    hash_chain_valid: bool
